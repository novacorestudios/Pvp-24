"""Compare-and-swap portfolio acceptance and ENTRY intent in one WAL transaction."""

import json
from dataclasses import asdict
from decimal import localcontext

from pvb24.decimal_math import CONTEXT, D
from pvb24.ids import canonical
from pvb24.risk.portfolio import Exposure, Portfolio
from pvb24.risk.sizing import SizingResult
from pvb24.state import Conflict, Journal
from pvb24.types import Side


def restore_portfolio(payload) -> Portfolio:
    exposures = []
    for item in payload["exposures"]:
        values = dict(item)
        values["side"] = Side(values["side"])
        for key in (
            "initial_quantity",
            "remaining_quantity",
            "initial_reserved_risk",
            "valuation_price",
            "initial_margin_commitment",
        ):
            values[key] = D(values[key])
        exposures.append(Exposure(**values))
    return Portfolio(D(payload["equity"]), D(payload["free_collateral"]), tuple(exposures))


class Reservations:
    def __init__(self, journal: Journal, scope: str):
        if not scope:
            raise ValueError("Account scope required")
        self.journal = journal
        self.scope = scope
        self.stream = "portfolio:" + scope

    def initialize(self, portfolio: Portfolio):
        with self.journal.transaction() as db:
            if db.execute("SELECT 1 FROM snapshots WHERE stream=?", (self.stream,)).fetchone():
                raise Conflict("Portfolio already initialized")
            Journal.append_tx(db, "initialize:" + self.scope, asdict(portfolio))
            db.execute(
                "INSERT INTO snapshots VALUES(?,1,?)", (self.stream, canonical(asdict(portfolio)))
            )
            gate = {
                "ready": not portfolio.exposures,
                "reason": "INITIAL_ACCOUNT",
                "safety_paused": False,
            }
            db.execute(
                "INSERT INTO snapshots VALUES(?,1,?)",
                ("account-gate:" + self.scope, canonical(gate)),
            )
            return 1

    def read(self):
        version, payload = self.journal.snapshot(self.stream)
        if payload is None:
            raise Conflict("Portfolio not initialized")
        return version, restore_portfolio(payload)

    def reserve(
        self,
        expected_version: int,
        signal_id: str,
        symbol: str,
        side: Side,
        result: SizingResult,
        *,
        reduced: bool = False,
    ) -> str:
        if result.entry is None or result.reason != "ACCEPTED":
            raise ValueError("Only a converged accepted sizing result can reserve")
        entry = result.entry
        if entry.symbol != symbol or entry.side is not side:
            raise ValueError("Sizing identity does not match reservation")
        with self.journal.transaction() as db, localcontext(CONTEXT):
            gate = db.execute(
                "SELECT payload FROM snapshots WHERE stream=?", ("account-gate:" + self.scope,)
            ).fetchone()
            if gate is None or json.loads(gate["payload"]).get("ready") is not True:
                raise Conflict("Account reconciliation required before reserving a new entry")
            control = db.execute(
                "SELECT payload FROM snapshots WHERE stream=?", ("equity-control:" + self.scope,)
            ).fetchone()
            if control is not None:
                status = json.loads(control["payload"]).get("last_status")
                if status is None or status.get("entries_allowed") is not True:
                    raise Conflict("Equity risk overlay blocks new entries")
                if (D(status["risk_fraction"]) == D("0.005")) != reduced:
                    raise Conflict("Sizing risk fraction differs from the durable equity overlay")
            row = db.execute("SELECT * FROM snapshots WHERE stream=?", (self.stream,)).fetchone()
            if row is None or row["version"] != expected_version:
                raise Conflict("Portfolio changed: recompute sizing before acceptance")
            portfolio = restore_portfolio(json.loads(row["payload"]))
            if portfolio.slots >= 3 or any(
                x.symbol == symbol and x.remaining_quantity > 0 for x in portfolio.exposures
            ):
                raise Conflict("Slot or symbol already reserved")
            notional = entry.quantity * entry.costs.entry
            obligations = entry.quantity * (
                entry.costs.entry_fee
                + entry.costs.exit_fee
                + entry.costs.stop_slippage
                + entry.costs.funding
            )
            if (
                entry.reserved_loss > portfolio.budget(side, reduced=reduced)
                or entry.reserved_loss < D("0.0025") * portfolio.equity
                or notional > portfolio.equity
                or portfolio.gross_notional + notional > 3 * portfolio.equity
                or entry.initial_margin > D("0.2") * portfolio.equity
                or portfolio.margin + entry.initial_margin > D("0.6") * portfolio.equity
                or entry.initial_margin + obligations > portfolio.free_collateral
            ):
                raise Conflict("Portfolio capacity no longer permits acceptance")
            pending = Exposure(
                signal_id,
                symbol,
                side,
                entry.quantity,
                entry.quantity,
                entry.reserved_loss,
                entry.costs.entry,
                entry.initial_margin,
                True,
            )
            updated = Portfolio(
                portfolio.equity,
                portfolio.free_collateral - entry.initial_margin - obligations,
                portfolio.exposures + (pending,),
            )
            payload = {"symbol": symbol, "side": side, "sizing": asdict(entry)}
            client_id, created = Journal.prepare_intent_tx(
                db, self.scope, signal_id, "ENTRY", payload
            )
            if not created:
                raise Conflict("Signal already consumed; reconcile existing reservation")
            Journal.append_tx(
                db,
                "reservation:" + client_id,
                {"portfolio_version": expected_version + 1, "pending": asdict(pending)},
            )
            db.execute(
                "UPDATE snapshots SET version=?,payload=? WHERE stream=?",
                (expected_version + 1, canonical(asdict(updated)), self.stream),
            )
            return client_id
