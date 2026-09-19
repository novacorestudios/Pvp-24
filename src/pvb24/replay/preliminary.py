"""Explicitly preliminary minute-open fills and adverse OHLC ambiguities.

MinuteOpen is a separate observation: it contains no future high/low/close/volume.
The historical adapter may expose an archived candle's open at interval_start,
provided that this modelling assumption is recorded in the run manifest.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.data.schemas import Candle
from pvb24.decimal_math import CONTEXT, D, require_decimal
from pvb24.execution.market import EntryBounds, Proxy, preliminary_proxy
from pvb24.types import Quality, Side, utc


@dataclass(frozen=True)
class MinuteOpen:
    symbol: str
    time: datetime
    available_at: datetime
    price: Decimal
    source: str
    revision_id: str

    def __post_init__(self):
        time = utc(self.time)
        if time.second or time.microsecond or utc(self.available_at) < time:
            raise ValueError("Causal minute boundary required")
        if not self.symbol or not self.source or not self.revision_id:
            raise ValueError("Minute-open provenance required")
        require_decimal(self.price, positive=True)


@dataclass(frozen=True)
class FrozenEntry:
    bounds: EntryBounds
    decision_time: datetime
    quantity: Decimal
    sigma: Decimal
    recent_quote_volume: Decimal
    inputs_available_at: datetime

    def __post_init__(self):
        if utc(self.inputs_available_at) > utc(self.decision_time):
            raise ValueError("Decision inputs include future information")
        if not self.bounds.timely(self.decision_time, self.decision_time):
            raise ValueError("Invalid decision deadline")
        require_decimal(self.quantity, positive=True)
        require_decimal(self.sigma, nonnegative=True)
        require_decimal(self.recent_quote_volume, positive=True)

    @property
    def expected_open(self):
        return utc(self.decision_time).replace(second=0, microsecond=0) + timedelta(minutes=1)


@dataclass(frozen=True)
class EntryOutcome:
    reason: str
    proxy: Proxy | None = None
    fill_time: datetime | None = None
    quality: Quality = Quality.PRELIMINARY
    unverified: tuple[str, ...] = ("book_age", "spread", "depth", "partial_fills")


def entry_at_open(order: FrozenEntry, observed: MinuteOpen, now: datetime) -> EntryOutcome:
    now = utc(now)
    if observed.symbol != order.bounds.symbol or observed.available_at > now:
        raise ValueError("Wrong or unavailable execution observation")
    if observed.time != order.expected_open:
        return EntryOutcome("FIRST_POST_DECISION_OPEN_MISSING")
    if not order.bounds.timely(order.decision_time, now):
        return EntryOutcome("ORDER_DEADLINE")
    proxy = preliminary_proxy(
        observed.price, order.quantity, order.bounds.side, order.sigma, order.recent_quote_volume
    )
    if not order.bounds.valid_price(observed.price) or not order.bounds.valid_price(proxy.price):
        return EntryOutcome("BREAKOUT_OR_CHASING")
    try:
        limit = order.bounds.ioc_limit(observed.price)
    except ValueError:
        return EntryOutcome("NO_MARKETABLE_TICK")
    with localcontext(CONTEXT):
        if order.bounds.side.sign * (proxy.price - limit) > 0:
            return EntryOutcome("IOC_LIMIT")
        if order.quantity * proxy.price / order.recent_quote_volume > D("0.001"):
            return EntryOutcome("PARTICIPATION")
    return EntryOutcome("MODELED_FULL_FILL", proxy, observed.time)


@dataclass(frozen=True)
class BarExit:
    reason: str | None
    reference_price: Decimal | None
    ambiguous_event_count: int
    quality: Quality = Quality.PRELIMINARY


def adverse_bar_exit(
    last: Candle,
    mark: Candle,
    side: Side,
    *,
    stop: Decimal,
    stop_effective_at: datetime,
    first_fill_time: datetime,
    liquidation: Decimal,
    now: datetime,
) -> BarExit:
    """No reconstructed intrabar timestamp; result is known only at bar availability.

    Only fully-owned bars with an already-effective stop are eligible. A partial
    entry/stop-activation bar needs finer data; old extrema cannot trigger it.
    Liquidation reference is explicitly the adverse Mark extreme, not a claimed
    executable LAST price; the caller must label its synthetic forced fill.
    """
    for value in (stop, liquidation):
        require_decimal(value, positive=True)
    if not isinstance(side, Side):
        raise TypeError("Explicit position side required")
    now = utc(now)
    if (
        last.price_type != "LAST"
        or mark.price_type != "MARK"
        or last.symbol != mark.symbol
        or last.duration != timedelta(minutes=1)
        or mark.duration != timedelta(minutes=1)
        or last.timing.interval_start != mark.timing.interval_start
        or last.timing.interval_end != mark.timing.interval_end
    ):
        raise ValueError("Separate aligned LAST and MARK minute bars required")
    if max(last.timing.available_at, mark.timing.available_at) > now:
        raise ValueError("Future bar information")
    start = last.timing.interval_start
    if utc(first_fill_time) > start or utc(stop_effective_at) > start:
        return BarExit("FINER_DATA_REQUIRED", None, 0)
    stopped = last.low <= stop if side is Side.LONG else last.high >= stop
    liquidated = mark.low <= liquidation if side is Side.LONG else mark.high >= liquidation
    if liquidated:
        return BarExit(
            "MODELED_LIQUIDATION", mark.low if side is Side.LONG else mark.high, int(stopped)
        )
    if stopped:
        # Opening gaps execute at the worse first price, never the old trigger.
        reference = min(stop, last.open) if side is Side.LONG else max(stop, last.open)
        return BarExit("MODELED_STOP", reference, 0)
    return BarExit(None, None, 0)
