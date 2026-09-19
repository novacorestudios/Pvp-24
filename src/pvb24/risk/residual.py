"""Liquidation repair from actual isolated collateral, never a newly sized entry."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from pvb24.data.contract_rules import ContractRules
from pvb24.decimal_math import CONTEXT, ZERO, D, quantize_step, require_decimal
from pvb24.risk.liquidation import Liquidation, buffer_ok, isolated_liquidation
from pvb24.types import Quality, Side, utc


@dataclass(frozen=True)
class ResidualPosition:
    symbol: str
    side: Side
    quantity: Decimal
    entry_vwap: Decimal
    initial_stop: Decimal
    isolated_collateral: Decimal  # after actual charged fees and settled funding

    def __post_init__(self):
        if not self.symbol or not isinstance(self.side, Side):
            raise ValueError("Position identity required")
        for value in (self.quantity, self.entry_vwap, self.initial_stop):
            require_decimal(value, positive=True)
        require_decimal(self.isolated_collateral)
        with localcontext(CONTEXT):
            if self.side.sign * (self.entry_vwap - self.initial_stop) <= 0:
                raise ValueError("Original price risk must remain adverse and fixed")


@dataclass(frozen=True)
class ReductionProjection:
    remaining_quantity: Decimal
    execution_price: Decimal
    fee: Decimal
    collateral_released: Decimal
    available_at: datetime
    source: str
    revision_id: str
    quality: Quality

    def __post_init__(self):
        for value in (self.remaining_quantity, self.execution_price):
            require_decimal(value, positive=True)
        for value in (self.fee, self.collateral_released):
            require_decimal(value, nonnegative=True)
        utc(self.available_at)
        if not self.source or not self.revision_id or not isinstance(self.quality, Quality):
            raise ValueError("Explicit residual-collateral projection provenance required")


@dataclass(frozen=True)
class LiquidationRemedy:
    remaining_quantity: Decimal
    reduce_only_quantity: Decimal
    reason: str
    expected_collateral: Decimal | None
    liquidation: Liquidation | None
    candidates: int


def liquidation_remedy(
    position: ResidualPosition,
    rules: ContractRules,
    decision: datetime,
    project_reduction: Callable[[Decimal], ReductionProjection | None],
    *,
    require_verified=True,
) -> LiquidationRemedy:
    """Largest step quantity retaining the mandatory original 3R buffer.

    Venue-specific collateral release and adverse execution must be supplied by
    the adapter. Unknown projections fail closed to a full reduce-only close;
    no added collateral, leverage change or collateral-retention policy is invented.
    This repairs liquidation distance only, not all post-fill portfolio limits.
    """
    decision = utc(decision)
    if type(require_verified) is not bool:
        raise TypeError("Explicit quality requirement needed")
    count = 0

    def close(reason):
        return LiquidationRemedy(ZERO, position.quantity, reason, None, None, count)

    if (
        rules.symbol != position.symbol
        or rules.available_at > decision
        or rules.effective_from > decision
        or (rules.effective_to is not None and decision >= rules.effective_to)
    ):
        return close("RULES_UNAVAILABLE_CLOSE")
    if require_verified and not (rules.historical_verified and rules.liquidation_validated):
        return close("LIQUIDATION_UNVERIFIED_CLOSE")
    if position.isolated_collateral <= 0:
        return close("NONPOSITIVE_COLLATERAL_CLOSE")
    with localcontext(CONTEXT):
        step = rules.quantity_step * rules.contract_size
        upper = int(quantize_step(position.quantity, step) / step)
        if D(upper) * step != position.quantity:
            return close("UNSUPPORTED_POSITION_INCREMENT_CLOSE")
        for units in range(upper, 0, -1):
            remaining = D(units) * step
            count += 1
            if remaining < rules.minimum_quantity * rules.contract_size:
                break
            collateral = position.isolated_collateral
            if remaining != position.quantity:
                try:
                    projection = project_reduction(remaining)
                except (ValueError, ArithmeticError):
                    return close("REDUCTION_ECONOMICS_UNKNOWN_CLOSE")
                if (
                    projection is None
                    or projection.remaining_quantity != remaining
                    or projection.available_at > decision
                    or (require_verified and projection.quality is not Quality.VERIFIED)
                ):
                    return close("REDUCTION_ECONOMICS_UNKNOWN_CLOSE")
                reduced = position.quantity - remaining
                # Realize the closed fraction at actual/projected adverse execution,
                # subtract its fee once, then deduct collateral returned to the wallet.
                collateral += (
                    position.side.sign
                    * reduced
                    * (projection.execution_price - position.entry_vwap)
                )
                collateral -= projection.fee + projection.collateral_released
            if collateral <= 0:
                continue
            try:
                result = isolated_liquidation(
                    position.side, remaining, position.entry_vwap, collateral, rules
                )
            except (ValueError, ArithmeticError):
                return close("LIQUIDATION_MODEL_UNKNOWN_CLOSE")
            if buffer_ok(position.side, position.entry_vwap, position.initial_stop, result.price):
                return LiquidationRemedy(
                    remaining,
                    position.quantity - remaining,
                    "COMPLIANT" if remaining == position.quantity else "REDUCE_ONLY",
                    collateral,
                    result,
                    count,
                )
        return close("NO_BUFFER_REPAIR_CLOSE")
