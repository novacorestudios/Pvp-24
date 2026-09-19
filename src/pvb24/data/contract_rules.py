from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import pairwise

from pvb24.decimal_math import require_decimal
from pvb24.types import utc


@dataclass(frozen=True)
class MaintenanceTier:
    notional_floor: Decimal
    notional_cap: Decimal
    rate: Decimal
    deduction: Decimal
    max_leverage: int

    def __post_init__(self):
        for v in (self.notional_floor, self.rate, self.deduction):
            require_decimal(v, nonnegative=True)
        require_decimal(self.notional_cap, positive=True)
        if self.notional_cap <= self.notional_floor or self.rate >= 1 or self.max_leverage < 1:
            raise ValueError("Invalid maintenance tier")


@dataclass(frozen=True)
class ContractRules:
    symbol: str
    effective_from: datetime
    available_at: datetime
    source: str
    revision_id: str
    tick: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal
    maximum_quantity: Decimal
    contract_size: Decimal
    tiers: tuple[MaintenanceTier, ...]
    historical_verified: bool
    liquidation_validated: bool
    supports_ioc: bool = False
    supports_last_stop: bool = False
    effective_to: datetime | None = None

    def __post_init__(self):
        utc(self.effective_from)
        utc(self.available_at)
        if self.effective_to is not None and utc(self.effective_to) <= self.effective_from:
            raise ValueError("Invalid rule validity interval")
        for flag in (
            self.historical_verified,
            self.liquidation_validated,
            self.supports_ioc,
            self.supports_last_stop,
        ):
            if type(flag) is not bool:
                raise TypeError("Explicit boolean rule evidence required")
        if not self.symbol or not self.source or not self.revision_id:
            raise ValueError("Rule provenance required")
        for value in (
            self.tick,
            self.quantity_step,
            self.minimum_quantity,
            self.maximum_quantity,
            self.contract_size,
        ):
            require_decimal(value, positive=True)
        require_decimal(self.minimum_notional, nonnegative=True)
        if self.maximum_quantity < self.minimum_quantity:
            raise ValueError("Invalid quantity bounds")
        if not isinstance(self.tiers, tuple):
            raise TypeError("Maintenance tiers must be immutable")
        if self.liquidation_validated and not self.tiers:
            raise ValueError("Validated liquidation requires maintenance tiers")
        for previous, current in pairwise(self.tiers):
            if previous.notional_cap != current.notional_floor:
                raise ValueError("Maintenance tiers must be contiguous")


def rules_at(rows: list[ContractRules], symbol: str, decision: datetime) -> ContractRules | None:
    candidates = [
        x
        for x in rows
        if x.symbol == symbol
        and x.effective_from <= utc(decision)
        and x.available_at <= decision
        and (x.effective_to is None or decision < x.effective_to)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x.effective_from, x.available_at))
    if len(candidates) > 1:
        a, b = candidates[-2:]
        if (a.effective_from, a.available_at) == (b.effective_from, b.available_at) and a != b:
            raise ValueError("Ambiguous contract revision")
    return candidates[-1]
