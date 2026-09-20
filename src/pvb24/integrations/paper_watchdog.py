"""Explicitly frozen timeout for unconfirmed PAPER protection; no retry orders."""

import json
from datetime import datetime, timedelta
from decimal import localcontext

from pvb24.accounting.coordinator import AccountCoordinator, read_tx, save_tx
from pvb24.decimal_math import CONTEXT, ZERO
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, digest
from pvb24.state import Conflict
from pvb24.types import utc


class ProtectionWatchdog:
    def __init__(self, host, *, max_ack_age=None, policy_id=None):
        self.host = host
        self.stream = "paper-protection-policy:" + host.scope
        host._guard()
        self.policy = None
        if max_ack_age is not None:
            if (
                not isinstance(max_ack_age, timedelta)
                or max_ack_age <= timedelta(0)
                or not policy_id
            ):
                raise ValueError(
                    "Explicit positive protection timeout and policy identity required"
                )
            self.policy = {
                "policy_id": policy_id,
                "max_ack_age_microseconds": (
                    max_ack_age.days * 86400000000
                    + max_ack_age.seconds * 1000000
                    + max_ack_age.microseconds
                ),
                "failure": "SAFETY_PAUSE_AND_CLOSE_UNCOVERED_QUANTITY",
            }
        elif policy_id is not None:
            raise ValueError("Protection policy requires an explicit timeout")
        with host.journal.transaction() as db:
            _, existing = host.journal.snapshot(self.stream)
            if existing is not None and canonical(existing) != canonical(self.policy):
                raise Conflict(
                    "Frozen protection acknowledgement policy cannot change or disappear"
                )
            if existing is None and self.policy is not None:
                if db.execute(
                    "SELECT 1 FROM intents i JOIN events e "
                    "ON e.event_id='paper-ticket:'||i.client_id "
                    "WHERE i.scope=? LIMIT 1",
                    (host.scope,),
                ).fetchone():
                    raise Conflict("Freeze protection policy before the first PAPER dispatch")
                save_tx(db, self.stream, self.policy)
        self._frozen = canonical(self.policy)

    def guard(self):
        self.host._guard()
        _, persisted = self.host.journal.snapshot(self.stream)
        if canonical(self.policy) != self._frozen or canonical(persisted) != self._frozen:
            raise Conflict("Protection acknowledgement policy changed")

    def check(self):
        from pvb24.integrations.paper_pump import _reserved_exits

        self.guard()
        if self.policy is None:
            return ()  # unqualified research mode; no invented production timeout
        now = utc(self.host.clock())
        age = timedelta(microseconds=self.policy["max_ack_age_microseconds"])
        triggered = []
        with self.host.journal.transaction() as db, localcontext(CONTEXT):
            _, mode = read_tx(db, "replay-account:" + self.host.scope)
            _, gate = read_tx(db, "account-gate:" + self.host.scope)
            for stamp in (mode["last_time"], gate.get("last_evidence_at")):
                if stamp is not None and datetime.fromisoformat(stamp) > now:
                    raise Conflict("Cannot backdate protection timeout behind account evidence")
            rows = db.execute(
                "SELECT i.client_id,i.signal_id,e.payload FROM intents i "
                "JOIN events e ON e.event_id='paper-ticket:'||i.client_id "
                "WHERE i.scope=? AND i.purpose='PROTECT' AND i.state='UNKNOWN' ORDER BY i.rowid",
                (self.host.scope,),
            ).fetchall()
            for row in rows:
                ticket = json.loads(row["payload"])
                deadline = datetime.fromisoformat(ticket["prepared_at"]) + age
                if now < deadline:
                    continue
                _, raw = read_tx(db, "protection:" + self.host.scope + ":" + row["signal_id"])
                p = Protection.restore(raw)
                if p.remaining <= 0 or p.protected:
                    continue
                key = "paper-protection-timeout:" + row["client_id"]
                coordinator = AccountCoordinator(self.host.journal, self.host.scope)
                if db.execute(
                    "SELECT 1 FROM events WHERE event_id=?",
                    ("account-protection:" + self.host.scope + ":" + key,),
                ).fetchone():
                    continue
                quantity = max(ZERO, p.remaining - _reserved_exits(db, self.host.scope, p, ""))

                def fail(position, quantity=quantity):
                    position.safety_paused = True
                    return position.close(quantity)

                coordinator.protection_event(
                    p.signal_id,
                    key,
                    {
                        "client_id": row["client_id"],
                        "deadline": deadline,
                        "observed_at": now,
                        "policy_hash": digest(self.policy),
                        "uncovered_exit_quantity": quantity,
                    },
                    fail,
                    now,
                )
                triggered.append(row["client_id"])
        return tuple(triggered)
