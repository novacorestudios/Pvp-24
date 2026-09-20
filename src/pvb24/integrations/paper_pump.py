"""Bounded dispatch of shared-core safety actions, without an entry scheduler."""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import localcontext

from pvb24.accounting.coordinator import AccountCoordinator, read_tx
from pvb24.decimal_math import CONTEXT, ZERO, D
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, client_identity
from pvb24.integrations.paper_actions import PURPOSES, accepted_order
from pvb24.integrations.paper_session import Recovery
from pvb24.state import Conflict, Journal
from pvb24.types import utc


@dataclass(frozen=True)
class PumpResult:
    dispatched: tuple[str, ...]
    retired: tuple[str, ...]
    deferred: tuple[str, ...]
    pending: tuple[str, ...]
    recovery: Recovery


def _pending(db, scope):
    return db.execute(
        "SELECT * FROM intents WHERE scope=? AND state='PREPARED' "
        "AND purpose IN ('PROTECT','EXIT_MARKET','CANCEL_ENTRY','CANCEL_PROTECTION') "
        "ORDER BY CASE purpose WHEN 'EXIT_MARKET' THEN 0 WHEN 'PROTECT' THEN 1 "
        "WHEN 'CANCEL_ENTRY' THEN 2 ELSE 3 END, rowid",
        (scope,),
    ).fetchall()


def _reserved_exits(db, scope, position, exclude):
    total = ZERO
    for row in db.execute(
        "SELECT * FROM intents WHERE scope=? AND signal_id=? AND purpose='EXIT_MARKET' "
        "AND state IN ('PREPARED','UNKNOWN','ACKNOWLEDGED') AND client_id!=? ORDER BY rowid",
        (scope, position.signal_id, exclude),
    ):
        filled = ZERO
        try:
            order_id = accepted_order(db, row["client_id"])
        except Conflict:
            pass
        else:
            filled = sum(
                (f.quantity for f in position.fills.values() if f.order_id == order_id), ZERO
            )
        total += max(ZERO, D(json.loads(row["payload"])["quantity"]) - filled)
    return total


def retire_stale(session, client_id):
    """Cancel only proven unsent requests, retaining their immutable original IDs.

    A smaller successor exit is a new shared-core action with its own identity.
    No submitted/unknown request is resized, canceled locally or resent.
    """
    host, journal = session.host, session.journal
    host._guard()
    now = utc(host.clock())
    with journal.transaction() as db, localcontext(CONTEXT):
        row = host._intent(db, client_id, purposes=PURPOSES)
        if row["state"] != "PREPARED":
            return False
        if db.execute(
            "SELECT 1 FROM events WHERE event_id IN (?,?)",
            ("paper-ticket:" + client_id, "dispatch:" + client_id),
        ).fetchone():
            raise Conflict("Unsent action has conflicting dispatch evidence")
        _, mode = read_tx(db, "replay-account:" + host.scope)
        _, gate = read_tx(db, "account-gate:" + host.scope)
        for stamp in (mode["last_time"], gate.get("last_evidence_at")):
            if stamp is not None and datetime.fromisoformat(stamp) > now:
                raise Conflict("Cannot backdate action retirement behind account evidence")
        _, raw = read_tx(db, "protection:" + host.scope + ":" + row["signal_id"])
        position = Protection.restore(raw)
        purpose, payload = row["purpose"], json.loads(row["payload"])
        action = None
        if purpose != "CANCEL_ENTRY":
            action = position.actions.get(payload["sequence"])
            if (
                action is None
                or canonical(action) != canonical(payload)
                or action.purpose != purpose
            ):
                raise Conflict("Retired action must match shared protection ownership")
        reason, replacement = None, ZERO
        if purpose in ("PROTECT", "EXIT_MARKET"):
            if position.remaining == 0:
                reason = "CONFIRMED_FLAT"
            elif position.remaining > 0:
                if action.quantity > position.remaining:
                    reason = "CONFIRMED_QUANTITY_REDUCED"
                    if purpose == "EXIT_MARKET":
                        replacement = max(
                            ZERO,
                            position.remaining
                            - _reserved_exits(db, host.scope, position, client_id),
                        )
                elif purpose == "PROTECT":
                    if action.stop != position.effective_stop:
                        reason = "STOP_PROPOSAL_SUPERSEDED"
                    else:
                        for other in db.execute(
                            "SELECT payload FROM intents WHERE scope=? AND signal_id=? "
                            "AND purpose='PROTECT' "
                            "AND state IN ('PREPARED','UNKNOWN','ACKNOWLEDGED')",
                            (host.scope, position.signal_id),
                        ):
                            candidate = json.loads(other["payload"])
                            if (
                                candidate["sequence"] > action.sequence
                                and D(candidate["quantity"]) >= position.remaining
                                and D(candidate["stop"]) == position.effective_stop
                            ):
                                reason = "CUMULATIVE_PROTECTION_SUPERSEDED"
                                break
        else:
            target = client_identity(
                host.scope,
                position.signal_id,
                "ENTRY" if purpose == "CANCEL_ENTRY" else "PROTECT",
                0 if action is None else action.target_sequence,
            )[2]
            if purpose == "CANCEL_ENTRY" and payload.get("target_client_id") != target:
                raise Conflict("Retired cancel must target its owned entry")
            target_row = db.execute(
                "SELECT state FROM intents WHERE client_id=?", (target,)
            ).fetchone()
            if target_row is not None and target_row["state"] in ("FILLED", "CANCELED", "REJECTED"):
                reason = "TARGET_ALREADY_TERMINAL"
        if reason is None:
            return False
        proof = {
            "client_id": client_id,
            "never_dispatched": True,
            "reason": reason,
            "time": now,
            "position": raw,
            "intent": payload,
            "successor_exit_quantity": replacement,
        }
        Journal.append_tx(db, "paper-retired:" + client_id, proof)
        db.execute("UPDATE intents SET state='CANCELED' WHERE client_id=?", (client_id,))
        coordinator = AccountCoordinator(journal, host.scope)
        if replacement:
            coordinator.protection_event(
                position.signal_id,
                "paper-successor:" + client_id,
                proof,
                lambda p: p.close(replacement),
                now,
            )
        coordinator._pause(db, "PAPER_UNSENT_ACTION_RETIRED", now)
        return True


def pump_actions(session, *, max_actions=100, max_events=100):
    if type(max_actions) is not int or max_actions <= 0:
        raise ValueError("Positive action work budget required")
    dispatched, retired, deferred = [], [], []
    recovery = session.recover(max_events=max_events)
    for _ in range(max_actions):
        if not recovery.caught_up:
            break
        rows = _pending(session.journal.db, session.host.scope)
        row = next((r for r in rows if r["client_id"] not in deferred), None)
        if row is None:
            break
        cid = row["client_id"]
        if retire_stale(session, cid):
            retired.append(cid)
            continue
        try:
            session.host.dispatch_action(cid)
        except Conflict:
            # A validation failure before the write-ahead claim is a deferred
            # action, not permission to discard it. Other safety actions may run.
            state = session.journal.db.execute(
                "SELECT state FROM intents WHERE client_id=?", (cid,)
            ).fetchone()[0]
            if state != "PREPARED":
                session._pause("PAPER_ACTION_OUTCOME_PENDING")
                raise
            deferred.append(cid)
            session._pause("PAPER_ACTION_VALIDATION_DEFERRED")
            continue
        except Exception:
            session._pause("PAPER_ACTION_OUTCOME_PENDING")
            raise
        dispatched.append(cid)
        recovery = session.recover(max_events=max_events)
    pending = tuple(row["client_id"] for row in _pending(session.journal.db, session.host.scope))
    return PumpResult(tuple(dispatched), tuple(retired), tuple(deferred), pending, recovery)
