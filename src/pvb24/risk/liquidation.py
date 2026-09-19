"""Isolated linear balance equation with self-consistent maintenance brackets.

This is an UNVERIFIED reconstruction unless the effective rules carry external
exchange validation evidence. Synthetic fixtures alone never establish that.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from itertools import pairwise

from pvb24.data.contract_rules import ContractRules
from pvb24.decimal_math import CONTEXT, D, require_decimal
from pvb24.types import Quality, Side


@dataclass(frozen=True)
class Liquidation:
    price: Decimal
    tier_index: int
    quality: Quality
    rule_revision: str


def isolated_liquidation(
    side: Side,
    quantity: Decimal,
    entry: Decimal,
    collateral_after_costs: Decimal,
    rules: ContractRules,
) -> Liquidation:
    """Solve collateral + signed UPNL = notional * maintenance rate - deduction.

    Quantity is base units (not exchange contract count). No cross-wallet offset,
    added collateral, funding credit or liquidation-fee assumption is invented.
    Adapter supplies collateral after actual fees/funding or conservative reserves.
    """
    if not isinstance(side, Side):
        raise TypeError("Side enum required")
    for value in (quantity, entry, collateral_after_costs):
        require_decimal(value, positive=True)
    if not rules.tiers or rules.tiers[0].notional_floor != 0:
        raise ValueError("Complete maintenance tiers required")
    with localcontext(CONTEXT):
        if rules.tiers[0].deduction != 0:
            raise ValueError("Invalid first maintenance deduction")
        for previous, current in pairwise(rules.tiers):
            expected = previous.deduction + current.notional_floor * (current.rate - previous.rate)
            if current.rate < previous.rate or current.deduction != expected:
                raise ValueError("Discontinuous maintenance schedule")
        for index, tier in enumerate(rules.tiers):
            price = (collateral_after_costs + tier.deduction - side.sign * quantity * entry) / (
                quantity * (tier.rate - side.sign)
            )
            notional = quantity * price
            if price > 0 and tier.notional_floor <= notional < tier.notional_cap:
                return Liquidation(
                    price,
                    index,
                    Quality.VERIFIED
                    if rules.historical_verified and rules.liquidation_validated
                    else Quality.PRELIMINARY,
                    rules.revision_id,
                )
    # Do not silently clip negative roots to zero or use a tier outside coverage.
    raise ValueError("No positive self-consistent liquidation root in supplied tiers")


def buffer_ok(side: Side, entry: Decimal, stop: Decimal, liquidation: Decimal) -> bool:
    for value in (entry, stop, liquidation):
        require_decimal(value, positive=True)
    if not isinstance(side, Side):
        raise TypeError("Side enum required")
    with localcontext(CONTEXT):
        ordered = liquidation < stop < entry if side is Side.LONG else liquidation > stop > entry
        return ordered and abs(entry - liquidation) >= D(3) * abs(entry - stop)
