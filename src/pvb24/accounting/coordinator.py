"""One transaction for confirmed fill evidence, ledger, protection and entry pause.

A fill invalidates the previous account-risk reconciliation. Pending reservations
stay locked until actual account/collateral reconciliation completes.
"""

import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from pvb24.accounting.ledger import (
    FillRecord,
    FundingPayment,
    Ledger,
    OwnedPosition,
    ReconciliationRequired,
)
from pvb24.execution.protection import Protection
from pvb24.ids import canonical
from pvb24.risk.portfolio import Portfolio
from pvb24.risk.reservations import restore_portfolio
from pvb24.state import Conflict, Journal
from pvb24.types import utc


def read_tx(db, stream):
    row = db.execute("SELECT * FROM snapshots WHERE stream=?", (stream,)).fetchone()
    if row is None:
        raise ReconciliationRequired("Required account stream is missing: " + stream)
    return row["version"], json.loads(row["payload"])


def save_tx(db, stream, payload):
    db.execute(
        "INSERT INTO snapshots VALUES(?,1,?) ON CONFLICT(stream) DO UPDATE SET "
        "version=snapshots.version+1,payload=excluded.payload",
        (stream, canonical(payload)),
    )


class AccountCoordinator:
    def __init__(self, journal: Journal, scope: str):
        if not scope:
            raise ValueError("Account scope required")
        self.journal, self.scope = journal, scope
        self.ledger_stream = "ledger:" + scope
        self.portfolio_stream = "portfolio:" + scope
        self.gate_stream = "account-gate:" + scope

    def _protection_stream(self, signal_id):
        return "protection:" + self.scope + ":" + signal_id

    def _actions(self, db, state, actions):
        ids = []
        for action in actions:
            cid, _ = Journal.prepare_intent_tx(
                db, self.scope, state.signal_id, action.purpose, asdict(action), action.sequence
            )
            ids.append(cid)
        return tuple(ids)

    def _pause(self, db, reason, received_at, safety=False):
        _, gate = read_tx(db, self.gate_stream)
        received_at = utc(received_at)
        previous = gate.get("last_evidence_at")
        if previous is not None:
            received_at = max(received_at, datetime.fromisoformat(previous))
        save_tx(
            db,
            self.gate_stream,
            {
                "ready": False,
                "last_evidence_at": received_at,
                "reason": reason,
                "safety_paused": gate.get("safety_paused", False) or safety,
            },
        )

    def register_pending(self, state: Protection, accepted_at: datetime):
        accepted_at = utc(accepted_at)
        if state.fills or state.actions or state.terminal:
            raise ValueError("Only a fresh pending protection state can be registered")
        with self.journal.transaction() as db:
            _, payload = read_tx(db, self.portfolio_stream)
            portfolio = restore_portfolio(payload)
            pending = next(
                (x for x in portfolio.exposures if x.position_id == state.signal_id), None
            )
            if (
                pending is None
                or not pending.pending
                or pending.symbol != state.symbol
                or pending.side is not state.side
                or pending.initial_quantity != state.requested_quantity
            ):
                raise Conflict("Protection ownership must match an accepted pending reservation")
            stream = self._protection_stream(state.signal_id)
            if db.execute("SELECT 1 FROM snapshots WHERE stream=?", (stream,)).fetchone():
                raise Conflict("Position protection already initialized")
            _, payload = read_tx(db, self.ledger_stream)
            ledger = Ledger.restore(payload)
            ledger.register(OwnedPosition(state.signal_id, state.symbol, state.side, accepted_at))
            Journal.append_tx(
                db,
                "account-register:" + self.scope + ":" + state.signal_id,
                {"state": state.checkpoint(), "accepted_at": accepted_at},
            )
            save_tx(db, stream, state.checkpoint())
            save_tx(db, self.ledger_stream, ledger.checkpoint())

    def confirmed_fill(self, record: FillRecord):
        f = record.fill
        with self.journal.transaction() as db:
            if not Journal.append_tx(db, "account-fill:" + self.scope + ":" + f.fill_id, record):
                return ()
            _, payload = read_tx(db, self.ledger_stream)
            ledger = Ledger.restore(payload)
            for payment in ledger.funding.values():
                if (
                    payment.position_id == f.position_id
                    and f.event_time <= payment.settlement_time
                ):
                    raise ReconciliationRequired(
                        "Late fill revises frozen funding boundary eligibility"
                    )
            _, payload = read_tx(db, self._protection_stream(f.position_id))
            state = Protection.restore(payload)
            ledger.ingest_fill(record)
            actions = state.fill(f)
            ids = self._actions(db, state, actions)
            save_tx(db, self.ledger_stream, ledger.checkpoint())
            save_tx(db, self._protection_stream(f.position_id), state.checkpoint())
            self._pause(db, "POST_FILL_RECONCILIATION_REQUIRED", f.received_at, state.safety_paused)
            return ids

    def confirmed_funding(self, payment: FundingPayment):
        with self.journal.transaction() as db:
            if not Journal.append_tx(
                db, "account-funding:" + self.scope + ":" + payment.event_id, payment
            ):
                return False
            _, payload = read_tx(db, self.ledger_stream)
            ledger = Ledger.restore(payload)
            ledger.ingest_funding(payment)
            save_tx(db, self.ledger_stream, ledger.checkpoint())
            self._pause(db, "POST_FUNDING_RECONCILIATION_REQUIRED", payment.available_at)
            return True

    def protection_event(
        self, signal_id: str, event_id: str, evidence, operation, received_at: datetime
    ):
        """Venue-confirmed terminal/stop outcomes, or explicit protection failure."""
        if not evidence:
            raise ValueError("Outcome evidence required")
        with self.journal.transaction() as db:
            if not Journal.append_tx(
                db,
                "account-protection:" + self.scope + ":" + event_id,
                {"signal_id": signal_id, "evidence": evidence},
            ):
                return ()
            _, payload = read_tx(db, self._protection_stream(signal_id))
            state = Protection.restore(payload)
            actions = operation(state)
            ids = self._actions(db, state, actions)
            save_tx(db, self._protection_stream(signal_id), state.checkpoint())
            self._pause(
                db,
                "PROTECTION_OR_TERMINAL_RECONCILIATION_REQUIRED",
                received_at,
                state.safety_paused,
            )
            return ids

    def reconcile_flat(self, time: datetime, observed_cash: Decimal, evidence: str):
        """Release all reservations only with flat ledger + proven terminal entries.

        Open-position reconciliation must additionally prove collateral, margin,
        risk reservation, Mark and liquidation compliance; it is not bypassed here.
        """
        from pvb24.decimal_math import require_decimal

        require_decimal(observed_cash)
        time = utc(time)
        if not evidence:
            raise ValueError("Account reconciliation evidence required")
        with self.journal.transaction() as db:
            _, payload = read_tx(db, self.ledger_stream)
            ledger = Ledger.restore(payload)
            _, gate = read_tx(db, self.gate_stream)
            watermark = gate.get("last_evidence_at")
            if watermark is not None and datetime.fromisoformat(watermark) > time:
                raise ReconciliationRequired("Cannot backdate account reconciliation")
            view = ledger.view(time)
            if view.cash != observed_cash or any(p.quantity != 0 for p in view.positions):
                raise ReconciliationRequired("Cash mismatch or non-flat position")
            _, payload = read_tx(db, self.portfolio_stream)
            portfolio = restore_portfolio(payload)
            for exposure in portfolio.exposures:
                _, payload = read_tx(db, self._protection_stream(exposure.position_id))
                state = Protection.restore(payload)
                if state.remaining != 0 or not state.terminal:
                    raise ReconciliationRequired("Position/IOC outcome still unresolved")
            if not Journal.append_tx(
                db,
                "account-flat:" + self.scope + ":" + evidence,
                {"time": time, "cash": view.cash, "evidence": evidence},
            ):
                return False
            # Dedicated strategy account: no external deposits, loans or foreign orders.
            save_tx(db, self.portfolio_stream, asdict(Portfolio(view.cash, view.cash)))
            _, gate = read_tx(db, self.gate_stream)
            safe = not gate.get("safety_paused", False) and view.cash > 0
            save_tx(
                db,
                self.gate_stream,
                {
                    "ready": safe,
                    "last_evidence_at": time,
                    "reason": "FLAT_RECONCILED" if safe else "SAFETY_PAUSED",
                    "safety_paused": gate.get("safety_paused", False),
                },
            )
            return True
