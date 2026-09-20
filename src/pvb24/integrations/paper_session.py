"""Restartable consumption of the local PRELIMINARY model's durable evidence.

Account effects commit before the source cursor. A crash between these commits
replays the immutable account receipt; it cannot duplicate fills or action IDs.
This coordinator never clears an account pause or infers a missing outcome.
"""

import json
from dataclasses import dataclass

from pvb24.accounting.coordinator import AccountCoordinator, read_tx, save_tx
from pvb24.ids import canonical, digest
from pvb24.integrations.paper_evidence import PaperEvidence
from pvb24.integrations.paper_venue import L2PaperVenue
from pvb24.state import Conflict, Journal
from pvb24.types import Quality, utc


@dataclass(frozen=True)
class Recovery:
    cursor: int
    consumed: int
    caught_up: bool
    unresolved: tuple[str, ...]


class PaperSession:
    """Own no additional order path: every request goes through PaperDispatch.

    Only the concrete socket-free model is supported at this stage. Page limits
    bound work per call; they do not drop events or authorize entry on backlog.
    """

    def __init__(self, host):
        host._guard()
        if not isinstance(host.backend, L2PaperVenue) or host.quality is not Quality.PRELIMINARY:
            raise ValueError("Local PRELIMINARY L2 model required")
        if host.scope != host.backend.scope:
            raise Conflict("Session account and model scopes differ")
        account_path = host.journal.db.execute("PRAGMA database_list").fetchone()["file"]
        model_path = host.backend.journal.db.execute("PRAGMA database_list").fetchone()["file"]
        import os

        if os.path.samefile(account_path, model_path):
            raise Conflict("Account and model require separate durable journals")
        self.host, self.journal = host, host.journal
        self.stream = "paper-session:" + host.scope
        self.binding = {
            "instance_id": host.backend.instance_id,
            "policy_hash": digest(host.backend.policy),
            "scope": host.scope,
            "quality": host.quality,
            "consumer": "ACCOUNT_RECEIPT_BEFORE_CURSOR_V1",
        }
        self.evidence = PaperEvidence(host)
        with self.journal.transaction() as db:
            _, previous = self.journal.snapshot(self.stream)
            if previous is None:
                save_tx(db, self.stream, {"binding": self.binding, "cursor": 0, "anchor": None})
            elif canonical(previous["binding"]) != canonical(self.binding):
                raise Conflict("Durable PAPER session binding changed")

    def _pause(self, reason):
        with self.journal.transaction() as db:
            AccountCoordinator(self.journal, self.host.scope)._pause(
                db, reason, utc(self.host.clock())
            )

    def _state(self):
        self.host._guard()
        if digest(self.host.backend.policy) != self.binding["policy_hash"]:
            raise Conflict("PAPER session source policy changed")
        _, state = self.journal.snapshot(self.stream)
        if state is None or canonical(state["binding"]) != canonical(self.binding):
            raise Conflict("PAPER session checkpoint binding changed")
        cursor = state["cursor"]
        if type(cursor) is not int or cursor < 0:
            raise Conflict("Invalid PAPER source cursor")
        if cursor:
            # Detect reopening a truncated/replaced source with the same label.
            rows = self.host.backend.events_after(cursor - 1, limit=1)
            if not rows or rows[0][0] != cursor or self._anchor(rows[0][1]) != state["anchor"]:
                raise Conflict("PAPER source no longer matches its committed cursor")
            self._receipt(rows[0][1])
        elif state["anchor"] is not None:
            raise Conflict("Unexpected source anchor at initial cursor")
        return state

    @staticmethod
    def _anchor(event):
        return {"event_id": event.event_id, "evidence_hash": digest(event)}

    def _receipt(self, event):
        row = self.journal.db.execute(
            "SELECT payload FROM events WHERE event_id=?",
            ("paper-evidence:" + self.host.scope + ":" + event.event_id,),
        ).fetchone()
        if row is None or json.loads(row["payload"])["evidence_hash"] != digest(event):
            raise Conflict("Source cursor requires matching committed account evidence")

    def _advance(self, previous, sequence, event):
        # Deliberately separate from ingest's account transaction. Replaying the
        # same immutable receipt is safe after failure here or process restart.
        with self.journal.transaction() as db:
            _, current = read_tx(db, self.stream)
            if current != previous or sequence <= current["cursor"]:
                raise Conflict("Source cursor changed concurrently or moved backwards")
            self._receipt(event)
            state = {"binding": self.binding, "cursor": sequence, "anchor": self._anchor(event)}
            Journal.append_tx(db, self.stream + ":" + str(sequence), state)
            save_tx(db, self.stream, state)
        return json.loads(canonical(state))

    def unresolved(self):
        self.host._guard()
        rows = self.journal.db.execute(
            "SELECT client_id FROM intents WHERE scope=? AND (state='UNKNOWN' "
            "OR (state='ACKNOWLEDGED' AND purpose IN ('ENTRY','EXIT_MARKET'))) "
            "ORDER BY rowid",
            (self.host.scope,),
        ).fetchall()
        return tuple(row["client_id"] for row in rows)

    def recover(self, *, max_events=100):
        if type(max_events) is not int or max_events <= 0:
            raise ValueError("Positive recovery event budget required")
        self.host._guard()
        try:
            current = self._state()
            # Only missing transport receipts need lookup. Known acceptance is
            # not terminal proof, but repeatedly querying it adds no evidence.
            for cid in self.unresolved():
                if (
                    self.journal.db.execute(
                        "SELECT 1 FROM events WHERE event_id IN (?,?)",
                        ("paper-accepted:" + cid, "paper-rejected:" + cid),
                    ).fetchone()
                    is None
                ):
                    self.host.lookup(cid)  # None retains UNKNOWN; never resend.
            rows = self.host.backend.events_after(current["cursor"], limit=max_events + 1)
            for sequence, event in rows[:max_events]:
                if type(sequence) is not int or sequence <= current["cursor"]:
                    raise Conflict("PAPER source evidence is not ordered")
                self.evidence.ingest(event)
                current = self._advance(current, sequence, event)
            unresolved = self.unresolved()
            caught_up = len(rows) <= max_events
            if unresolved or not caught_up:
                self._pause("PAPER_EXECUTION_RECOVERY_PENDING")
            return Recovery(current["cursor"], min(len(rows), max_events), caught_up, unresolved)
        except Exception:
            self._pause("PAPER_EXECUTION_RECOVERY_FAILED")
            raise

    def dispatch_entry(self, client_id, inputs, book, *, max_events=100):
        recovery = self.recover(max_events=max_events)
        if not recovery.caught_up or recovery.unresolved:
            raise Conflict("PAPER recovery must finish before new entry dispatch")
        response = self.host.dispatch_entry(client_id, inputs, book)
        self.recover(max_events=max_events)
        return response

    def dispatch_action(self, client_id, *, max_events=100):
        recovery = self.recover(max_events=max_events)
        if not recovery.caught_up:
            raise Conflict("Drain available execution evidence before preparing an action")
        # Missing outcomes block entry, but must not block valid protection or
        # an uncovered safety exit. PaperDispatch validates quantity and ownership.
        response = self.host.dispatch_action(client_id)
        self.recover(max_events=max_events)
        return response
