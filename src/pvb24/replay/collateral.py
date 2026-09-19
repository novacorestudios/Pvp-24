"""Explicit PRELIMINARY isolated collateral model, never exchange observation.

BASE_MARGIN_RELEASE_ONLY returns released cost-basis margin on partial exits;
realized PnL, fees and funding remain in the isolated collateral until full exit.
The source-specific run manifest must select this assumption before trading.
It cannot certify historical exchange liquidation or funding coverage.
"""

import json
from datetime import timedelta
from decimal import localcontext

from pvb24.accounting.coordinator import read_tx, save_tx
from pvb24.accounting.ledger import LedgerStore, ReconciliationRequired
from pvb24.accounting.reconciliation import AccountObservation, PositionObservation
from pvb24.decimal_math import CONTEXT, ZERO
from pvb24.ids import digest
from pvb24.state import Conflict, Journal
from pvb24.types import Quality, utc


class SyntheticCollateral:
    POLICY = "BASE_MARGIN_RELEASE_ONLY"

    def __init__(self, journal, scope):
        self.journal, self.scope = journal, scope
        self.stream = "synthetic-collateral-policy:" + scope

    def freeze(self, *, policy: str, manifest_id: str):
        if policy != self.POLICY or not manifest_id:
            raise ValueError("Explicit preliminary collateral policy and run manifest required")
        with self.journal.transaction() as db:
            row = db.execute(
                "SELECT payload FROM snapshots WHERE stream=?", (self.stream,)
            ).fetchone()
            value = {"policy": policy, "manifest_id": manifest_id, "quality": Quality.PRELIMINARY}
            if row is not None:
                if json.loads(row["payload"]) != value:
                    raise Conflict("Synthetic collateral policy already frozen")
                return
            _, ledger = LedgerStore(self.journal, self.scope).read()
            if ledger.fills or ledger.funding:
                raise Conflict("Freeze collateral model before trading cashflows")
            Journal.append_tx(db, self.stream, value)
            save_tx(db, self.stream, value)

    def observe(self, time, marks, rules, *, max_mark_age: timedelta):
        time = utc(time)
        with self.journal.transaction() as db, localcontext(CONTEXT):
            _, policy = read_tx(db, self.stream)
            _, ledger = LedgerStore(self.journal, self.scope).read()
            view = ledger.view(time)
            view.equity(marks, max_mark_age=max_mark_age)  # validate as-of Mark coverage first
            positions, encumbered = [], ZERO
            for balance in view.positions:
                if balance.quantity == 0:
                    continue
                candidates = [
                    m
                    for m in marks
                    if m.symbol == balance.owner.symbol and m.timing.available_at <= time
                ]
                mark = max(candidates, key=lambda m: (m.timing.event_time, m.timing.available_at))
                row = db.execute(
                    "SELECT payload FROM intents WHERE scope=? AND signal_id=? AND purpose='ENTRY'",
                    (self.scope, balance.owner.position_id),
                ).fetchone()
                if row is None or balance.owner.symbol not in rules:
                    raise ReconciliationRequired("Missing synthetic entry terms or contract rules")
                leverage = json.loads(row["payload"])["sizing"]["leverage"]
                margin = balance.remaining_cost_basis / leverage
                collateral = margin + balance.realized_gross - balance.fees + balance.funding
                encumbered += collateral
                positions.append(
                    PositionObservation(
                        balance.owner.position_id,
                        balance.quantity,
                        margin,
                        collateral,
                        leverage,
                        mark,
                        rules[balance.owner.symbol],
                    )
                )
            return AccountObservation(
                time,
                time,
                view.cash,
                view.cash - encumbered,
                tuple(positions),
                Quality.PRELIMINARY,
                "PVB24_SYNTHETIC_COLLATERAL:" + policy["policy"],
                digest({"policy": policy, "time": time, "ledger": view, "positions": positions}),
            )
