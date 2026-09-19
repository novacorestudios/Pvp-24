"""Immutable portfolio view: one slot per symbol; no risk released by stop moves."""

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext

from pvb24.decimal_math import CONTEXT, ZERO, D, require_decimal
from pvb24.types import Side


@dataclass(frozen=True)
class Exposure:
    position_id: str
    symbol: str
    side: Side
    initial_quantity: Decimal
    remaining_quantity: Decimal
    initial_reserved_risk: Decimal
    valuation_price: Decimal  # current causal Mark if open; expected entry if pending
    initial_margin_commitment: Decimal  # exchange-obligated amount; not Mark / leverage
    pending: bool

    def __post_init__(self):
        if not self.position_id or not self.symbol or not isinstance(self.side, Side):
            raise ValueError("Exposure identity required")
        for value in (self.initial_quantity, self.valuation_price):
            require_decimal(value, positive=True)
        for value in (
            self.remaining_quantity,
            self.initial_reserved_risk,
            self.initial_margin_commitment,
        ):
            require_decimal(value, nonnegative=True)
        if self.remaining_quantity > self.initial_quantity or type(self.pending) is not bool:
            raise ValueError("Invalid exposure")

    @property
    def reserved_risk(self) -> Decimal:
        with localcontext(CONTEXT):
            return self.initial_reserved_risk * self.remaining_quantity / self.initial_quantity

    @property
    def notional(self) -> Decimal:
        with localcontext(CONTEXT):
            return self.remaining_quantity * self.valuation_price

    def confirmed_exit(self, remaining: Decimal, exchange_margin: Decimal) -> "Exposure":
        require_decimal(remaining, nonnegative=True)
        if self.pending or remaining > self.remaining_quantity:
            raise ValueError("Confirmed exit cannot increase quantity or reduce a pending entry")
        return replace(
            self, remaining_quantity=remaining, initial_margin_commitment=exchange_margin
        )


@dataclass(frozen=True)
class Portfolio:
    equity: Decimal
    free_collateral: Decimal  # already net of existing open + pending commitments
    exposures: tuple[Exposure, ...] = ()

    def __post_init__(self):
        require_decimal(self.equity)
        require_decimal(self.free_collateral)
        if not isinstance(self.exposures, tuple):
            raise TypeError("Immutable exposure tuple required")
        active = [x for x in self.exposures if x.remaining_quantity > 0]
        if len({x.symbol for x in active}) != len(active):
            raise ValueError("Open and pending must share one aggregate symbol reservation")
        if len({x.position_id for x in self.exposures}) != len(self.exposures):
            raise ValueError("Duplicate position identity")

    @property
    def slots(self):
        return sum(x.remaining_quantity > 0 for x in self.exposures)

    @property
    def reserved_risk(self):
        with localcontext(CONTEXT):
            return sum((x.reserved_risk for x in self.exposures), ZERO)

    @property
    def gross_notional(self):
        with localcontext(CONTEXT):
            return sum((x.notional for x in self.exposures), ZERO)

    @property
    def margin(self):
        with localcontext(CONTEXT):
            return sum((x.initial_margin_commitment for x in self.exposures), ZERO)

    def budget(self, side: Side, *, reduced: bool = False) -> Decimal:
        if not isinstance(side, Side) or type(reduced) is not bool:
            raise TypeError("Explicit side and risk state required")
        with localcontext(CONTEXT):
            direction = sum((x.reserved_risk for x in self.exposures if x.side is side), ZERO)
            return min(
                (D("0.005") if reduced else D("0.01")) * self.equity,
                D("0.03") * self.equity - self.reserved_risk,
                D("0.02") * self.equity - direction,
            )
