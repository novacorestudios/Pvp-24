"""Durable minute equity overlay and risk-driven cancel/close intents."""

from dataclasses import asdict
from datetime import datetime, timedelta

from pvb24.accounting.controls import EquityControl
from pvb24.accounting.coordinator import read_tx, save_tx
from pvb24.accounting.ledger import Ledger, ReconciliationRequired
from pvb24.data.lifecycle import prepare_entry_cancel
from pvb24.execution.protection import Protection
from pvb24.state import Conflict, Journal
from pvb24.types import timestamp, utc


class AccountRiskService:
    def __init__(self, journal: Journal, scope: str):
        if not scope:
            raise ValueError("Account scope required")
        self.journal, self.scope = journal, scope
        self.stream = "equity-control:" + scope
        self.policy_stream = "mark-policy:" + scope

    def initialize(self, start: datetime, *, max_mark_age: timedelta, policy_id: str):
        """Caller must freeze a source-specific policy before replay; there is no default."""
        start = utc(start)
        if not policy_id or not isinstance(max_mark_age, timedelta) or max_mark_age < timedelta(0):
            raise ValueError("Explicit frozen Mark policy required")
        age_us = (
            max_mark_age.days * 86400 + max_mark_age.seconds
        ) * 1000000 + max_mark_age.microseconds
        with self.journal.transaction() as db:
            if db.execute("SELECT 1 FROM snapshots WHERE stream=?", (self.stream,)).fetchone():
                raise Conflict("Risk policy/control already frozen")
            _, state = read_tx(db, "ledger:" + self.scope)
            ledger = Ledger.restore(state)
            if ledger.fills or ledger.funding:
                raise Conflict("Freeze risk policy before observing trading cashflows")
            control = EquityControl(start, ledger.starting_cash)
            policy = {"policy_id": policy_id, "max_mark_age_us": age_us, "frozen_at": start}
            Journal.append_tx(db, "risk-init:" + self.scope, policy)
            save_tx(db, self.stream, control.checkpoint())
            save_tx(db, self.policy_stream, policy)

    def sample(self, time: datetime, marks):
        time = utc(time)
        with self.journal.transaction() as db:
            _, payload = read_tx(db, self.stream)
            control = EquityControl.restore(payload)
            if time < control.last_time:
                raise ValueError("Cannot replay an old sample as the current risk state")
            _, policy = read_tx(db, self.policy_stream)
            _, payload = read_tx(db, "ledger:" + self.scope)
            ledger = Ledger.restore(payload)
            view = None
            try:
                view = ledger.view(time)
                equity = view.equity(
                    marks, max_mark_age=timedelta(microseconds=policy["max_mark_age_us"])
                )
            except ReconciliationRequired:
                equity = None
            event_id = "risk-sample:" + self.scope + ":" + timestamp(time)
            evidence = {"time": time, "equity": equity, "policy": policy}
            if not Journal.append_tx(db, event_id, evidence):
                return control.last_status, ()
            was_daily, was_hard = control.daily_paused, control.hard_paused
            _, gate = read_tx(db, "account-gate:" + self.scope)
            if gate.get("safety_paused", False):
                control.pause_safety()
            status = control.sample(time, equity)
            ids = []
            if (status.daily_paused and not was_daily) or (status.hard_paused and not was_hard):
                rows = db.execute(
                    "SELECT * FROM intents WHERE scope=? AND purpose='ENTRY' "
                    "AND state IN ('PREPARED','UNKNOWN','ACKNOWLEDGED')",
                    (self.scope,),
                ).fetchall()
                for row in rows:
                    if row["state"] == "PREPARED":
                        # BEGIN IMMEDIATE proves no concurrent dispatch can intervene.
                        db.execute(
                            "UPDATE intents SET state='CANCELED' WHERE client_id=?",
                            (row["client_id"],),
                        )
                        Journal.append_tx(
                            db,
                            "cancel-unsent:" + row["client_id"],
                            {"reason": "GLOBAL_RISK_PAUSE", "never_dispatched": True},
                        )
                        stream = "protection:" + self.scope + ":" + row["signal_id"]
                        existing = db.execute(
                            "SELECT payload FROM snapshots WHERE stream=?", (stream,)
                        ).fetchone()
                        if existing:
                            import json

                            state = Protection.restore(json.loads(existing["payload"]))
                            state.entry_terminal()
                            save_tx(db, stream, state.checkpoint())
                    else:
                        cid = prepare_entry_cancel(
                            db, self.scope, row["signal_id"], row["client_id"], "GLOBAL_RISK_PAUSE"
                        )
                        ids.append(cid)
            if status.hard_paused and view is not None:
                for position in view.positions:
                    if position.quantity == 0:
                        continue
                    stream = "protection:" + self.scope + ":" + position.owner.position_id
                    _, payload = read_tx(db, stream)
                    state = Protection.restore(payload)
                    import json
                    from decimal import localcontext

                    from pvb24.decimal_math import CONTEXT, ZERO, D

                    pending = db.execute(
                        "SELECT payload FROM intents WHERE scope=? AND signal_id=? "
                        "AND purpose='EXIT_MARKET' "
                        "AND state IN ('PREPARED','UNKNOWN','ACKNOWLEDGED')",
                        (self.scope, state.signal_id),
                    ).fetchall()
                    with localcontext(CONTEXT):
                        committed = sum(
                            (D(json.loads(row["payload"])["quantity"]) for row in pending), ZERO
                        )
                        uncovered = max(ZERO, state.remaining - committed)
                    for action in state.close(uncovered):
                        cid, _ = Journal.prepare_intent_tx(
                            db,
                            self.scope,
                            state.signal_id,
                            action.purpose,
                            asdict(action),
                            action.sequence,
                        )
                        ids.append(cid)
                    save_tx(db, stream, state.checkpoint())
            save_tx(db, self.stream, control.checkpoint())
            return status, tuple(ids)

    def status(self):
        _, state = self.journal.snapshot(self.stream)
        if state is None:
            raise ReconciliationRequired("Risk control not initialized")
        return EquityControl.restore(state).last_status
