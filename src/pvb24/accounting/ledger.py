"""As-of fill accounting: actual execution prices, fees and funding exactly once."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from itertools import groupby

from pvb24.data.schemas import Mark
from pvb24.decimal_math import CONTEXT, ZERO, require_decimal
from pvb24.ids import canonical
from pvb24.state import Conflict, Journal
from pvb24.types import Fill, Side, utc


class ReconciliationRequired(RuntimeError):
    pass


@dataclass(frozen=True)
class OwnedPosition:
    position_id: str
    symbol: str
    side: Side
    available_at: datetime

    def __post_init__(self):
        if not self.position_id or not self.symbol or not isinstance(self.side, Side):
            raise ValueError("Explicit position ownership required")
        utc(self.available_at)


@dataclass(frozen=True)
class FillRecord:
    fill: Fill
    exchange_sequence: int | None = None
    liquidation: bool = False

    def __post_init__(self):
        if self.exchange_sequence is not None and (
            type(self.exchange_sequence) is not int or self.exchange_sequence < 0
        ):
            raise ValueError("Invalid exchange sequence")
        if type(self.liquidation) is not bool or type(self.fill.reduce_only) is not bool:
            raise TypeError("Explicit fill flags required")
        if self.liquidation and not self.fill.reduce_only:
            raise ValueError("Liquidation must reduce an owned position")


@dataclass(frozen=True)
class FundingPayment:
    event_id: str
    position_id: str
    side: Side
    eligible_quantity: Decimal
    mark_price: Decimal
    final_rate: Decimal
    settlement_time: datetime
    available_at: datetime
    source: str
    eligibility_evidence: str

    def __post_init__(self):
        if not all((self.event_id, self.position_id, self.source, self.eligibility_evidence)):
            raise ValueError("Funding identity and boundary-eligibility evidence required")
        if not isinstance(self.side, Side):
            raise TypeError("Explicit funding position side required")
        require_decimal(self.eligible_quantity, nonnegative=True)
        require_decimal(self.mark_price, positive=True)
        require_decimal(self.final_rate)
        if utc(self.settlement_time) > utc(self.available_at):
            raise ValueError("Funding unavailable before settlement")

    @property
    def cashflow(self):
        with localcontext(CONTEXT):
            return -self.side.sign * self.eligible_quantity * self.mark_price * self.final_rate


@dataclass(frozen=True)
class PositionBalance:
    owner: OwnedPosition
    quantity: Decimal
    remaining_cost_basis: Decimal
    realized_gross: Decimal
    fees: Decimal
    funding: Decimal
    liquidation_count: int


@dataclass(frozen=True)
class LedgerView:
    as_of: datetime
    starting_cash: Decimal
    cash: Decimal
    realized_gross: Decimal
    fees: Decimal
    funding: Decimal
    positions: tuple[PositionBalance, ...]
    liquidation_count: int
    ambiguous_fill_order_count: int

    def equity(self, marks: list[Mark], *, max_mark_age: timedelta) -> Decimal:
        """Freshness must be specified by a separately frozen source policy, no default.

        Missing/stale Mark raises; LAST is never accepted as an equity substitute.
        Future-appended or late-revised Marks cannot alter this as-of sample.
        """
        if not isinstance(max_mark_age, timedelta) or max_mark_age < timedelta(0):
            raise ValueError("Explicit nonnegative Mark freshness policy required")
        with localcontext(CONTEXT):
            unrealized = ZERO
            for position in self.positions:
                if position.quantity == 0:
                    continue
                candidates = [
                    m
                    for m in marks
                    if m.symbol == position.owner.symbol and m.timing.available_at <= self.as_of
                ]
                if not candidates:
                    raise ReconciliationRequired("Missing causal Mark: pause new entries")
                candidates.sort(key=lambda m: (m.timing.event_time, m.timing.available_at))
                mark = candidates[-1]
                if len(candidates) > 1:
                    previous = candidates[-2]
                    if (previous.timing.event_time, previous.timing.available_at) == (
                        mark.timing.event_time,
                        mark.timing.available_at,
                    ) and previous != mark:
                        raise ReconciliationRequired("Conflicting Mark observations")
                if self.as_of - mark.timing.event_time > max_mark_age:
                    raise ReconciliationRequired("Stale Mark: pause new entries")
                unrealized += position.owner.side.sign * (
                    position.quantity * mark.price - position.remaining_cost_basis
                )
            return self.cash + unrealized


class Ledger:
    """Event evidence survives late/out-of-order arrivals; views fail closed if incomplete."""

    def __init__(self, starting_cash: Decimal):
        require_decimal(starting_cash, positive=True)
        self.starting_cash = starting_cash
        self.owners = {}
        self.fills = {}
        self.funding = {}

    def register(self, owner: OwnedPosition):
        previous = self.owners.get(owner.position_id)
        if previous is not None and previous != owner:
            raise Conflict("Position ownership changed")
        self.owners[owner.position_id] = owner

    def ingest_fill(self, record: FillRecord):
        f = record.fill
        owner = self.owners.get(f.position_id)
        if owner is None or owner.symbol != f.symbol:
            raise ReconciliationRequired("Unknown fill ownership")
        if owner.available_at > f.event_time:
            raise ReconciliationRequired("Ownership was not established before fill")
        expected_side = (
            (Side.SHORT if owner.side is Side.LONG else Side.LONG) if f.reduce_only else owner.side
        )
        if f.side is not expected_side:
            raise ReconciliationRequired("Fill would reverse or contradict owned side")
        previous = self.fills.get(f.fill_id)
        if previous is not None:
            if previous != record:
                raise Conflict("Fill ID reused with different economics")
            return False
        self.fills[f.fill_id] = record
        return True

    def ingest_funding(self, payment: FundingPayment):
        owner = self.owners.get(payment.position_id)
        if owner is None or owner.side is not payment.side:
            raise ReconciliationRequired("Unknown funding ownership")
        previous = self.funding.get(payment.event_id)
        if previous is not None:
            if previous != payment:
                raise Conflict("Funding ID reused with different economics")
            return False
        self.funding[payment.event_id] = payment
        return True

    def view(self, as_of: datetime) -> LedgerView:
        as_of = utc(as_of)
        with localcontext(CONTEXT):
            positions = []
            ambiguous = 0
            for owner in sorted(self.owners.values(), key=lambda p: p.position_id):
                if owner.available_at > as_of:
                    continue
                rows = [
                    r
                    for r in self.fills.values()
                    if r.fill.position_id == owner.position_id and r.fill.received_at <= as_of
                ]
                rows.sort(key=lambda r: (r.fill.event_time, r.fill.fill_id))
                ordered = []
                for _, group in groupby(rows, key=lambda r: r.fill.event_time):
                    group = list(group)
                    if len(group) > 1 and all(r.exchange_sequence is not None for r in group):
                        if len({r.exchange_sequence for r in group}) != len(group):
                            raise ReconciliationRequired("Conflicting exchange fill sequences")
                        group.sort(key=lambda r: r.exchange_sequence)
                    else:
                        # UD-12 conservative fallback: confirmed reductions before entries.
                        if len({r.fill.reduce_only for r in group}) > 1:
                            ambiguous += 1
                        group.sort(
                            key=lambda r: (
                                not r.liquidation,
                                not r.fill.reduce_only,
                                r.fill.fill_id,
                            )
                        )
                    ordered.extend(group)
                quantity = basis = gross = fees = ZERO
                liquidations = 0
                for record in ordered:
                    f = record.fill
                    fees += f.fee  # Fill.fee is actual USDT expense, negative means rebate.
                    if f.reduce_only:
                        if f.quantity > quantity:
                            raise ReconciliationRequired("Exit exceeds known entry quantity")
                        allocated = (
                            basis if f.quantity == quantity else basis * f.quantity / quantity
                        )
                        gross += owner.side.sign * (f.quantity * f.price - allocated)
                        basis -= allocated
                        quantity -= f.quantity
                    else:
                        quantity += f.quantity
                        basis += f.quantity * f.price
                    liquidations += record.liquidation
                funding = sum(
                    (
                        p.cashflow
                        for p in self.funding.values()
                        if p.position_id == owner.position_id and p.available_at <= as_of
                    ),
                    ZERO,
                )
                positions.append(
                    PositionBalance(owner, quantity, basis, gross, fees, funding, liquidations)
                )
            gross = sum((p.realized_gross for p in positions), ZERO)
            fees = sum((p.fees for p in positions), ZERO)
            funding = sum((p.funding for p in positions), ZERO)
            return LedgerView(
                as_of,
                self.starting_cash,
                self.starting_cash + gross - fees + funding,
                gross,
                fees,
                funding,
                tuple(positions),
                sum(p.liquidation_count for p in positions),
                ambiguous,
            )

    def checkpoint(self):
        return dict(
            starting_cash=self.starting_cash,
            owners=[asdict(o) for o in self.owners.values()],
            fills=[asdict(r) for r in self.fills.values()],
            funding=[asdict(p) for p in self.funding.values()],
        )

    @classmethod
    def restore(cls, payload):
        from pvb24.decimal_math import D

        result = cls(D(payload["starting_cash"]))
        for item in payload["owners"]:
            result.register(
                OwnedPosition(
                    item["position_id"],
                    item["symbol"],
                    Side(item["side"]),
                    datetime.fromisoformat(item["available_at"]),
                )
            )
        for item in payload["fills"]:
            record = dict(item)
            f = dict(record["fill"])
            f["side"] = Side(f["side"])
            for key in ("quantity", "price", "fee"):
                f[key] = D(f[key])
            for key in ("event_time", "received_at"):
                f[key] = datetime.fromisoformat(f[key])
            result.ingest_fill(
                FillRecord(Fill(**f), record["exchange_sequence"], record["liquidation"])
            )
        for item in payload["funding"]:
            p = dict(item)
            p["side"] = Side(p["side"])
            for key in ("eligible_quantity", "mark_price", "final_rate"):
                p[key] = D(p[key])
            for key in ("settlement_time", "available_at"):
                p[key] = datetime.fromisoformat(p[key])
            result.ingest_funding(FundingPayment(**p))
        return result


class LedgerStore:
    def __init__(self, journal: Journal, scope: str):
        if not scope:
            raise ValueError("Ledger scope required")
        self.journal, self.scope = journal, scope
        self.stream = "ledger:" + scope

    def initialize(self, ledger: Ledger):
        return self.journal.checkpoint(
            self.stream, 0, ledger.checkpoint(), "ledger-init:" + self.scope
        )

    def read(self):
        version, state = self.journal.snapshot(self.stream)
        if state is None:
            raise ReconciliationRequired("Ledger not initialized")
        return version, Ledger.restore(state)

    def apply(self, event_id: str, evidence, operation):
        """Local evidence reducer only; no network I/O inside the transaction."""
        with self.journal.transaction() as db:
            row = db.execute("SELECT * FROM snapshots WHERE stream=?", (self.stream,)).fetchone()
            if row is None:
                raise ReconciliationRequired("Ledger not initialized")
            if not Journal.append_tx(db, "ledger-event:" + self.scope + ":" + event_id, evidence):
                return False
            ledger = Ledger.restore(json.loads(row["payload"]))
            operation(ledger)
            db.execute(
                "UPDATE snapshots SET version=?,payload=? WHERE stream=?",
                (row["version"] + 1, canonical(ledger.checkpoint()), self.stream),
            )
            return True


def execution_shortfall(fill: Fill, arrival_side_price: Decimal) -> Decimal:
    """Analytical only. This amount is never deducted from ledger cash."""
    require_decimal(arrival_side_price, positive=True)
    with localcontext(CONTEXT):
        return fill.quantity * fill.side.sign * (fill.price - arrival_side_price)
