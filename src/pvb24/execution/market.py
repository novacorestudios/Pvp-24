"""Frozen entry gates and explicitly labelled OHLC execution proxies."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.data.candles import causal_candles
from pvb24.data.schemas import Candle
from pvb24.decimal_math import CONTEXT, ZERO, D, population_std, quantize_step, require_decimal
from pvb24.execution.book import Book, Sweep
from pvb24.types import Quality, Side, utc


@dataclass(frozen=True)
class EntryBounds:
    symbol: str
    side: Side
    signal_time: datetime
    signal_close: Decimal
    channel: Decimal
    atr_previous: Decimal
    tick: Decimal

    def __post_init__(self):
        if not self.symbol or not isinstance(self.side, Side):
            raise ValueError("Signal identity required")
        utc(self.signal_time)
        for value in (self.signal_close, self.channel, self.atr_previous, self.tick):
            require_decimal(value, positive=True)

    def valid_price(self, price: Decimal):
        require_decimal(price, positive=True)
        with localcontext(CONTEXT):
            return (
                ZERO < self.side.sign * (price - self.channel) <= self.atr_previous
                and abs(price - self.signal_close) <= D("0.25") * self.atr_previous
            )

    def ioc_limit(self, arrival: Decimal):
        require_decimal(arrival, positive=True)
        with localcontext(CONTEXT):
            candidates = (
                self.channel + self.side.sign * self.atr_previous,
                self.signal_close + self.side.sign * D("0.25") * self.atr_previous,
                arrival * (1 + self.side.sign * D("0.001")),
            )
            raw = min(candidates) if self.side is Side.LONG else max(candidates)
            result = quantize_step(raw, self.tick, up=self.side is Side.SHORT)
            if result <= 0 or self.side.sign * (result - arrival) < 0:
                raise ValueError("No valid marketable IOC tick")
            return result

    def timely(self, decision: datetime, sent: datetime):
        return (
            self.signal_time
            <= utc(decision)
            <= utc(sent)
            <= self.signal_time + timedelta(seconds=90)
        )


def minute_inputs(rows: list[Candle], symbol: str, decision: datetime):
    candles = causal_candles(rows, symbol, timedelta(minutes=1), decision)[-16:]
    if len(candles) != 16 or any(c.price_type != "LAST" for c in candles):
        raise ValueError("Sixteen completed LAST minute candles required")
    for previous, current in zip(candles, candles[1:], strict=False):
        if previous.timing.interval_end != current.timing.interval_start:
            raise ValueError("Minute input gap")
    # The latest completed minute must be available; do not silently use an old window.
    if candles[-1].timing.interval_end != utc(decision).replace(second=0, microsecond=0):
        raise ValueError("Latest completed minute missing")
    with localcontext(CONTEXT):
        returns = [(b.close / a.close).ln() for a, b in zip(candles, candles[1:], strict=False)]
        volume = sum((c.quote_volume for c in candles[-15:]), ZERO)
        if volume <= 0:
            raise ValueError("No recent quote volume")
        return population_std(returns), volume


@dataclass(frozen=True)
class Proxy:
    price: Decimal
    impact: Decimal
    slippage: Decimal
    stop_slippage: Decimal
    quality: Quality = Quality.PRELIMINARY
    unverified: tuple[str, ...] = ("book_age", "spread", "depth", "partial_fills")


def preliminary_proxy(
    reference: Decimal,
    quantity: Decimal,
    side: Side,
    sigma: Decimal,
    recent_quote_volume: Decimal,
    *,
    stop_exit=False,
) -> Proxy:
    for value in (reference, quantity, recent_quote_volume):
        require_decimal(value, positive=True)
    require_decimal(sigma, nonnegative=True)
    if not isinstance(side, Side) or type(stop_exit) is not bool:
        raise ValueError("Explicit fill side and stop-exit flag required")
    with localcontext(CONTEXT):
        impact = max(D("0.00025"), sigma * (quantity * reference / recent_quote_volume).sqrt())
        slippage, stop_slippage = D("0.00025") + impact, D("0.00025") + 2 * impact
        price = reference * (1 + side.sign * (stop_slippage if stop_exit else slippage))
        if price <= 0:
            raise ValueError("Proxy implies nonpositive execution price")
        return Proxy(price, impact, slippage, stop_slippage)


@dataclass(frozen=True)
class IOCPreview:
    limit: Decimal | None
    sweep: Sweep | None
    reason: str


def preview_ioc(
    book: Book,
    bounds: EntryBounds,
    quantity: Decimal,
    recent_quote_volume: Decimal,
    decision: datetime,
    sent: datetime,
    *,
    haircut: Decimal = ZERO,
) -> IOCPreview:
    require_decimal(quantity, positive=True)
    require_decimal(recent_quote_volume, positive=True)
    if book.symbol != bounds.symbol or not bounds.timely(decision, sent):
        return IOCPreview(None, None, "IDENTITY_OR_DEADLINE")
    if not book.fresh(sent):
        return IOCPreview(None, None, "STALE_OR_UNSYNCED_BOOK")
    if not book.bids or not book.asks:
        return IOCPreview(None, None, "NO_VISIBLE_DEPTH")
    with localcontext(CONTEXT):
        bid, ask = book.best_bid, book.best_ask
        if (ask - bid) / ((ask + bid) / 2) > D("0.0005"):
            return IOCPreview(None, None, "SPREAD")
        arrival = ask if bounds.side is Side.LONG else bid
        if not bounds.valid_price(arrival):
            return IOCPreview(None, None, "BREAKOUT_OR_CHASING")
        try:
            limit = bounds.ioc_limit(arrival)
        except ValueError:
            return IOCPreview(None, None, "NO_MARKETABLE_TICK")
        sweep = book.sweep(bounds.side, quantity, limit, haircut=haircut)
        if sweep.filled == 0:
            return IOCPreview(limit, sweep, "NO_VISIBLE_DEPTH")
        if not bounds.valid_price(sweep.vwap):
            return IOCPreview(limit, sweep, "BREAKOUT_OR_CHASING")
        # Requested notional is used even when visible depth would fill only part.
        if quantity * sweep.vwap / recent_quote_volume > D("0.001"):
            return IOCPreview(limit, sweep, "PARTICIPATION")
        return IOCPreview(limit, sweep, "ACCEPTED")
