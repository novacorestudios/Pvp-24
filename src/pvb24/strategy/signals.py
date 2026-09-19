from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.data.availability import available
from pvb24.data.schemas import Candle, Timing
from pvb24.data.universe import Universe
from pvb24.decimal_math import CONTEXT, D, median
from pvb24.ids import digest, signal_identity
from pvb24.strategy.atr import WilderATR
from pvb24.types import Side, utc


@dataclass(frozen=True)
class Frame:
    candle: Candle
    channel_high: Decimal | None
    channel_low: Decimal | None
    atr_previous: Decimal | None
    atr_current: Decimal | None
    rvol: Decimal | None
    previous_long: bool | None
    previous_short: bool | None
    current_long: bool | None
    current_short: bool | None
    warmup_ok: bool
    input_hash: str
    evaluated_at: datetime


@dataclass(frozen=True)
class SignalDecision:
    signal_id: str
    identity: str
    symbol: str
    side: Side
    signal_time: datetime
    decision_time: datetime
    frame: Frame
    universe_id: str | None
    median_daily_quote_volume: Decimal | None
    rejection_codes: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.rejection_codes


class Indicators:
    """Streaming causal indicators with restartable ATR origin and rolling inputs.

    Late revisions of an already processed candle require a caller-controlled
    rebuild from its as-of source history. They never overwrite an emitted frame.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.atr = WilderATR()
        self.rows = deque(maxlen=48)
        self.consecutive = 0
        self.previous_long = None
        self.previous_short = None
        self.lineage = digest(["PVB-24", "1.0", symbol])
        self.last_frame = None

    def push(self, candle: Candle, decision_time: datetime) -> Frame:
        decision_time = utc(decision_time)
        if self.last_frame is not None and decision_time < self.last_frame.evaluated_at:
            raise ValueError("Processing time cannot move backwards")
        if (
            candle.symbol != self.symbol
            or candle.price_type != "LAST"
            or candle.duration != timedelta(hours=1)
        ):
            raise ValueError("Indicators require this symbol's hourly Last candles")
        if not available(candle.timing, decision_time):
            raise ValueError("DATA_NOT_AVAILABLE")
        if self.rows:
            previous = self.rows[-1]
            if candle.timing.interval_end <= previous.timing.interval_end:
                if candle == previous and self.last_frame is not None:
                    return self.last_frame
                raise ValueError("Out-of-order/revised history requires causal state rebuild")
            continuous = candle.timing.interval_start == previous.timing.interval_end
        else:
            previous, continuous = None, False
        if not continuous:
            # Missing TR is not zero. Preserve canonical ATR origin but skip an
            # undefined gap-crossing TR; require 720 new contiguous hourly bars.
            self.rows.clear()
            self.consecutive = 0
            self.previous_long = self.previous_short = None
        prior = list(self.rows)
        with localcontext(CONTEXT):
            high = max(x.high for x in prior[-24:]) if len(prior) >= 24 else None
            low = min(x.low for x in prior[-24:]) if len(prior) >= 24 else None
            atr_previous = self.atr.value
            reference = median([x.quote_volume for x in prior]) if len(prior) == 48 else None
            rvol = (
                candle.quote_volume / reference if reference is not None and reference > 0 else None
            )
            long = (
                candle.close > high + D("0.10") * atr_previous
                if high is not None and atr_previous is not None
                else None
            )
            short = (
                candle.close < low - D("0.10") * atr_previous
                if low is not None and atr_previous is not None
                else None
            )
        if continuous:
            self.atr.update(candle.high, candle.low, previous.close)
        self.consecutive += 1
        self.lineage = digest([self.lineage, candle])
        frame = Frame(
            candle,
            high,
            low,
            atr_previous,
            self.atr.value,
            rvol,
            self.previous_long,
            self.previous_short,
            long,
            short,
            self.consecutive >= 720,
            self.lineage,
            decision_time,
        )
        self.previous_long, self.previous_short = long, short
        self.rows.append(candle)
        self.last_frame = frame
        return frame

    def checkpoint(self):
        return {
            "schema_version": "1.0.0",
            "strategy_version": "1.0",
            "symbol": self.symbol,
            "atr": self.atr.checkpoint(),
            "rows": list(self.rows),
            "consecutive": self.consecutive,
            "previous_long": self.previous_long,
            "previous_short": self.previous_short,
            "lineage": self.lineage,
            "last_frame": self.last_frame,
        }

    @classmethod
    def restore(cls, state):
        if state["schema_version"] != "1.0.0" or state["strategy_version"] != "1.0":
            raise ValueError("Checkpoint version mismatch")
        result = cls(state["symbol"])
        result.atr = WilderATR.restore(state["atr"])
        for row in state["rows"]:
            timing = dict(row["timing"])
            for k in (
                "event_time",
                "interval_start",
                "interval_end",
                "available_at",
                "received_at",
            ):
                if timing[k] is not None:
                    timing[k] = datetime.fromisoformat(timing[k])
            kwargs = dict(row, timing=Timing(**timing))
            for k in ("open", "high", "low", "close", "quote_volume"):
                kwargs[k] = D(kwargs[k])
            result.rows.append(Candle(**kwargs))
        result.consecutive = state["consecutive"]
        result.previous_long = state["previous_long"]
        result.previous_short = state["previous_short"]
        result.lineage = state["lineage"]
        if state.get("last_frame") is not None:
            raw = dict(state["last_frame"])
            raw["candle"] = result.rows[-1]
            raw["evaluated_at"] = datetime.fromisoformat(raw["evaluated_at"])
            for k in ("channel_high", "channel_low", "atr_previous", "atr_current", "rvol"):
                if raw[k] is not None:
                    raw[k] = D(raw[k])
            result.last_frame = Frame(**raw)
        return result


def decide(
    frame: Frame,
    side: Side,
    universe: Universe | None,
    decision_time: datetime,
    *,
    has_position=False,
    pending_entry=False,
    cooldown_end: datetime | None = None,
):
    decision_time = utc(decision_time)
    signal_time = frame.candle.timing.interval_end
    symbol = frame.candle.symbol
    identity, signal_id = signal_identity("1.0", symbol, side, signal_time)
    reasons = []
    if universe is None or not universe.allows(symbol, decision_time):
        reasons.append("NOT_IN_UNIVERSE")
    if not frame.warmup_ok:
        reasons.append("WARMUP_INCOMPLETE")
    if not available(frame.candle.timing, decision_time) or decision_time < frame.evaluated_at:
        reasons.append("DATA_NOT_AVAILABLE")
    if decision_time > signal_time + timedelta(seconds=30):
        reasons.append("STALE_SIGNAL")
    current = frame.current_long if side is Side.LONG else frame.current_short
    previous = frame.previous_long if side is Side.LONG else frame.previous_short
    if current is None or previous is None or frame.rvol is None or frame.atr_previous is None:
        reasons.append("DATA_GAP")
    if current is not True or previous is not False:
        reasons.append("NO_NEW_BREAKOUT")
    if frame.rvol is not None and frame.rvol < D("1.5"):
        reasons.append("LOW_RVOL")
    if has_position or pending_entry:
        reasons.append("POSITION_EXISTS")
    if cooldown_end is not None and decision_time < utc(cooldown_end):
        reasons.append("COOLDOWN")
    volume = dict(universe.medians).get(symbol) if universe is not None else None
    return SignalDecision(
        signal_id,
        identity,
        symbol,
        side,
        signal_time,
        decision_time,
        frame,
        universe.universe_id if universe else None,
        volume,
        tuple(reasons),
    )


def rank_signals(signals: list[SignalDecision]) -> list[SignalDecision]:
    accepted = [x for x in signals if x.accepted]
    if len({x.signal_time for x in accepted}) > 1:
        raise ValueError("Cannot rank different hourly batches together")
    return sorted(
        accepted,
        key=lambda x: (
            x.frame.rvol.copy_negate(),
            x.median_daily_quote_volume.copy_negate(),
            x.symbol,
        ),
    )


@dataclass(frozen=True)
class Batch:
    decision_time: datetime
    decisions: tuple[SignalDecision, ...]
    ranked: tuple[SignalDecision, ...]
    missing_symbols: tuple[str, ...]


def signal_batch(
    frames: dict[str, Frame],
    universe: Universe,
    signal_time: datetime,
    now: datetime,
    symbol_status: dict | None = None,
) -> Batch | None:
    """Wait for the whole universe, or expire only missing symbols at +30s."""
    now = utc(now)
    deadline = utc(signal_time) + timedelta(seconds=30)
    ready = {
        symbol: frame
        for symbol, frame in frames.items()
        if symbol in universe.symbols
        and frame.candle.symbol == symbol
        and frame.candle.timing.interval_end == signal_time
        and frame.evaluated_at <= now
        and available(frame.candle.timing, now)
    }
    missing = tuple(sorted(set(universe.symbols) - set(ready)))
    if now < signal_time or (missing and now < deadline):
        return None
    decisions = []
    for symbol, frame in sorted(ready.items()):
        status = (symbol_status or {}).get(symbol, {})
        for side in Side:
            decisions.append(decide(frame, side, universe, now, **status))
    return Batch(now, tuple(decisions), tuple(rank_signals(decisions)), missing)
