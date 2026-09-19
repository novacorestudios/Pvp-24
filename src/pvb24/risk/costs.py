"""UD-11: arrival shortfall belongs in the gate, never twice in sizing/PnL."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from pvb24.decimal_math import CONTEXT, ZERO, D, quantize_step, require_decimal
from pvb24.types import Side


@dataclass(frozen=True)
class CostEstimate:
    entry: Decimal
    stop: Decimal
    price_risk: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    stop_slippage: Decimal
    funding: Decimal
    arrival_shortfall: Decimal
    loss_per_unit: Decimal
    gate_cost_per_unit: Decimal
    cost_to_risk: Decimal


def estimate_costs(
    side: Side,
    entry: Decimal,
    arrival_side_price: Decimal,
    atr_previous: Decimal,
    tick: Decimal,
    entry_fee_rate: Decimal,
    exit_fee_rate: Decimal,
    stop_slippage_fraction: Decimal,
    funding_rate_per_hour: Decimal,
) -> CostEstimate:
    """All amounts per base unit; initial stop rounds away from entry."""
    if not isinstance(side, Side):
        raise TypeError("Side enum required")
    for value in (entry, arrival_side_price, atr_previous, tick):
        require_decimal(value, positive=True)
    for value in (entry_fee_rate, exit_fee_rate, stop_slippage_fraction, funding_rate_per_hour):
        require_decimal(value, nonnegative=True)
    with localcontext(CONTEXT):
        stop = quantize_step(entry - side.sign * 2 * atr_previous, tick, up=side is Side.SHORT)
        if stop <= 0:
            raise ValueError("Nonpositive protective stop")
        price_risk = abs(entry - stop)
        entry_fee, exit_fee = entry * entry_fee_rate, stop * exit_fee_rate
        slippage = entry * stop_slippage_fraction
        funding = entry * funding_rate_per_hour * 72
        # A price improvement does not subsidize other costs.
        shortfall = max(ZERO, side.sign * (entry - arrival_side_price))
        embedded = entry_fee + exit_fee + slippage + funding
        return CostEstimate(
            entry,
            stop,
            price_risk,
            entry_fee,
            exit_fee,
            slippage,
            funding,
            shortfall,
            price_risk + embedded,
            shortfall + embedded,
            (shortfall + embedded) / price_risk,
        )


def cost_gate(estimate: CostEstimate) -> bool:
    return estimate.cost_to_risk <= D("0.25")
