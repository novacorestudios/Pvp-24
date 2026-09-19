"""Deterministic descending quantity-step solver (UD-09).

Descending search is deliberately conservative about monotonic *feasibility*:
rounding, tier changes and cost ratios can break a binary-search assumption.
Every larger step is evaluated before accepting a smaller one. No upward rounding.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from pvb24.data.contract_rules import ContractRules
from pvb24.decimal_math import CONTEXT, ZERO, D, quantize_step, require_decimal
from pvb24.risk.costs import CostEstimate, cost_gate, estimate_costs
from pvb24.risk.liquidation import Liquidation, buffer_ok, isolated_liquidation
from pvb24.risk.portfolio import Portfolio
from pvb24.types import Quality, Side, utc


@dataclass(frozen=True)
class Quote:
    expected_entry: Decimal
    arrival_side_price: Decimal
    entry_fee_rate: Decimal
    exit_fee_rate: Decimal
    stop_slippage_fraction: Decimal
    funding_rate_per_hour: Decimal
    quality: Quality
    available_at: datetime
    source_revision: str

    def __post_init__(self):
        for value in (self.expected_entry, self.arrival_side_price):
            require_decimal(value, positive=True)
        for value in (
            self.entry_fee_rate,
            self.exit_fee_rate,
            self.stop_slippage_fraction,
            self.funding_rate_per_hour,
        ):
            require_decimal(value, nonnegative=True)
        if not isinstance(self.quality, Quality) or not self.source_revision:
            raise ValueError("Quote provenance required")
        utc(self.available_at)


@dataclass(frozen=True)
class SizedEntry:
    symbol: str
    side: Side
    quantity: Decimal  # base units
    leverage: int
    initial_margin: Decimal
    reserved_loss: Decimal
    costs: CostEstimate
    liquidation: Liquidation
    quote: Quote


@dataclass(frozen=True)
class SizingResult:
    entry: SizedEntry | None
    reason: str
    iterations: int
    candidates_evaluated: int


# Callback returns exchange-obligated margin for base quantity, price, leverage.
MarginModel = Callable[[Decimal, Decimal, int], Decimal]
QuoteModel = Callable[[Decimal], Quote | None]


def linear_margin(quantity: Decimal, price: Decimal, leverage: int) -> Decimal:
    """Theoretical PRELIMINARY margin only; VERIFIED must pass an exchange model."""
    with localcontext(CONTEXT):
        return quantity * price / leverage


def candidate(
    quantity: Decimal,
    side: Side,
    atr_previous: Decimal,
    quote: Quote,
    portfolio: Portfolio,
    rules: ContractRules,
    budget: Decimal,
    margin_model: MarginModel,
    *,
    require_verified: bool,
) -> SizedEntry | None:
    with localcontext(CONTEXT):
        c = estimate_costs(
            side,
            quote.expected_entry,
            quote.arrival_side_price,
            atr_previous,
            rules.tick,
            quote.entry_fee_rate,
            quote.exit_fee_rate,
            quote.stop_slippage_fraction,
            quote.funding_rate_per_hour,
        )
        notional = quantity * c.entry
        risk = quantity * c.loss_per_unit
        if (
            risk > budget
            or not cost_gate(c)
            or notional > portfolio.equity
            or portfolio.gross_notional + notional > 3 * portfolio.equity
        ):
            return None
        tier = next((t for t in rules.tiers if t.notional_floor <= notional < t.notional_cap), None)
        if tier is None:
            return None
        for leverage in range(1, min(5, tier.max_leverage) + 1):
            margin = margin_model(quantity, c.entry, leverage)
            require_decimal(margin, positive=True)
            if margin < linear_margin(quantity, c.entry, leverage):
                raise ValueError("Margin adapter underestimates theoretical obligation")
            # Fees and funding reserves are commitments, not realized cash expenses.
            obligations = quantity * (c.entry_fee + c.exit_fee + c.funding + c.stop_slippage)
            if (
                margin > D("0.20") * portfolio.equity
                or portfolio.margin + margin > D("0.60") * portfolio.equity
                or margin + obligations > portfolio.free_collateral
            ):
                continue
            collateral = margin - quantity * (c.entry_fee + c.funding)
            if collateral <= 0:
                continue
            try:
                liq = isolated_liquidation(side, quantity, c.entry, collateral, rules)
            except ValueError:
                continue
            if require_verified and liq.quality is not Quality.VERIFIED:
                continue
            if buffer_ok(side, c.entry, c.stop, liq.price):
                return SizedEntry(
                    rules.symbol, side, quantity, leverage, margin, risk, c, liq, quote
                )
    return None


def size_entry(
    symbol: str,
    side: Side,
    atr_previous: Decimal,
    decision: datetime,
    portfolio: Portfolio,
    rules: ContractRules,
    quote_model: QuoteModel,
    *,
    reduced: bool = False,
    require_verified: bool = True,
    margin_model: MarginModel | None = None,
    maximum_quantity: Decimal | None = None,
) -> SizingResult:
    """The quote model must include the candidate's execution/liquidity feasibility.

    A snapshot quote model is preferred. Re-evaluate up to five outer passes and
    require identical rounded quantities on successive passes. Operational timing
    gates remain mandatory at dispatch even if an expensive search finishes late.
    """
    require_decimal(atr_previous, positive=True)
    decision = utc(decision)
    if type(require_verified) is not bool:
        raise TypeError("Explicit quality requirement needed")
    if rules.symbol != symbol or rules.effective_from > decision or rules.available_at > decision:
        return SizingResult(None, "RULES_UNAVAILABLE", 0, 0)
    if rules.effective_to is not None and decision >= rules.effective_to:
        return SizingResult(None, "RULES_EXPIRED", 0, 0)
    if not rules.supports_ioc or not rules.supports_last_stop:
        return SizingResult(None, "ORDER_CAPABILITIES_UNVERIFIED", 0, 0)
    if require_verified and (
        not rules.historical_verified or not rules.liquidation_validated or margin_model is None
    ):
        return SizingResult(None, "RULES_OR_MARGIN_UNVERIFIED", 0, 0)
    if portfolio.equity <= 0 or portfolio.free_collateral <= 0:
        return SizingResult(None, "NONPOSITIVE_EQUITY_OR_COLLATERAL", 0, 0)
    if portfolio.slots >= 3 or any(
        x.symbol == symbol and x.remaining_quantity > 0 for x in portfolio.exposures
    ):
        return SizingResult(None, "SLOT_OR_SYMBOL_RESERVED", 0, 0)
    budget = portfolio.budget(side, reduced=reduced)
    with localcontext(CONTEXT):
        if budget < D("0.0025") * portfolio.equity:
            return SizingResult(None, "INSUFFICIENT_RISK_CAPACITY", 0, 0)
        step = rules.quantity_step * rules.contract_size
        cap = min(rules.maximum_quantity * rules.contract_size, budget / (2 * atr_previous))
        if maximum_quantity is not None:
            require_decimal(maximum_quantity, nonnegative=True)
            cap = min(cap, maximum_quantity)
        upper = int(quantize_step(cap, step) / step)
        minimum = rules.minimum_quantity * rules.contract_size
        previous_quantity = None
        evaluations = 0
        for iteration in range(1, 6):
            best = None
            for units in range(upper, 0, -1):
                quantity = D(units) * step
                if quantity < minimum:
                    break
                quote = quote_model(quantity)
                evaluations += 1
                if quote is None or quote.available_at > decision:
                    continue
                if require_verified and quote.quality is not Quality.VERIFIED:
                    continue
                if quantity * quote.expected_entry < rules.minimum_notional:
                    continue
                try:
                    best = candidate(
                        quantity,
                        side,
                        atr_previous,
                        quote,
                        portfolio,
                        rules,
                        budget,
                        margin_model or linear_margin,
                        require_verified=require_verified,
                    )
                except (ValueError, ArithmeticError):
                    best = None
                if best is not None and best.reserved_loss >= D("0.0025") * portfolio.equity:
                    break
                best = None
            if best is None:
                return SizingResult(None, "NO_COMPLIANT_QUANTITY", iteration, evaluations)
            if best.quantity == previous_quantity:
                return SizingResult(best, "ACCEPTED", iteration, evaluations)
            previous_quantity = best.quantity
        return SizingResult(None, "SIZING_NOT_CONVERGED", 5, evaluations)


@dataclass(frozen=True)
class PostFillAction:
    remaining_quantity: Decimal
    reduce_only_quantity: Decimal
    reason: str


def post_fill_reduction(
    filled_quantity: Decimal, solve_remaining: Callable[[Decimal], SizingResult]
):
    """Solve against confirmed fill economics and a portfolio excluding this position.

    Existing collateral/margin and initial stop must be supplied by the caller's
    post-fill model; this function never assumes that exit costs restore collateral.
    Unknown/nonconverged compliance always requests a full reduce-only close.
    """
    require_decimal(filled_quantity, positive=True)
    try:
        result = solve_remaining(filled_quantity)
    except (ValueError, ArithmeticError):
        return PostFillAction(ZERO, filled_quantity, "COMPLIANCE_UNKNOWN_CLOSE")
    if (
        result.entry is None
        or result.reason != "ACCEPTED"
        or not ZERO < result.entry.quantity <= filled_quantity
    ):
        return PostFillAction(ZERO, filled_quantity, "NO_SAFE_COMPLIANT_QUANTITY_CLOSE")
    with localcontext(CONTEXT):
        remaining = result.entry.quantity
        return PostFillAction(
            remaining,
            filled_quantity - remaining,
            "COMPLIANT" if remaining == filled_quantity else "REDUCE_ONLY",
        )
