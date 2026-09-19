"""Close-based exits; a stop proposal never becomes retroactively effective."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.data.schemas import Candle
from pvb24.decimal_math import CONTEXT, D, quantize_step, require_decimal
from pvb24.ids import digest
from pvb24.types import Side, utc


@dataclass(frozen=True)
class Entry:
    position_id: str
    symbol: str
    side: Side
    first_fill_time: datetime
    vwap: Decimal
    initial_stop: Decimal
    channel_high: Decimal
    channel_low: Decimal
    tick: Decimal

    def __post_init__(self):
        if not self.position_id or not self.symbol or not isinstance(self.side, Side):
            raise ValueError("Entry identity required")
        utc(self.first_fill_time)
        for x in (self.vwap, self.initial_stop, self.channel_high, self.channel_low, self.tick):
            require_decimal(x, positive=True)
        if self.channel_low > self.channel_high:
            raise ValueError("Invalid frozen channel")
        if self.side.sign * (self.vwap - self.initial_stop) <= 0:
            raise ValueError("Initial stop must be adverse to entry")
        if quantize_step(self.initial_stop, self.tick) != self.initial_stop:
            raise ValueError("Initial stop not on tick")

    @property
    def price_risk(self):
        with localcontext(CONTEXT):
            return abs(self.vwap - self.initial_stop)


@dataclass(frozen=True)
class ExitDecision:
    decision_id: str
    decided_at: datetime
    reason: str | None
    proposed_stop: Decimal | None
    eligible_close_number: int
    close_mfe: Decimal | None
    trailing_active: bool


class Exits:
    def __init__(self, entry: Entry):
        self.entry = entry
        self.effective_stop = entry.initial_stop
        self.effective_at = entry.first_fill_time
        self.proposed_stop = entry.initial_stop
        self.proposed_at = entry.first_fill_time
        self.trailing_active = False
        self.count = 0
        self.highest_close = None
        self.lowest_close = None
        self.last_end = None
        self.last_input_hash = None
        self.last_decision = None
        self.exit_decision = None

    def _decision(self, now, reason=None, stop=None):
        with localcontext(CONTEXT):
            extreme = self.highest_close if self.entry.side is Side.LONG else self.lowest_close
            mfe = None if extreme is None else self.entry.side.sign * (extreme - self.entry.vwap)
        return ExitDecision(
            digest([self.entry.position_id, now, reason, stop, self.count]),
            now,
            reason,
            stop,
            self.count,
            mfe,
            self.trailing_active,
        )

    def timer(self, now: datetime) -> ExitDecision | None:
        now = utc(now)
        if now < self.entry.first_fill_time:
            raise ValueError("Position timer before first fill")
        if self.exit_decision is not None:
            return self.exit_decision
        if now >= self.entry.first_fill_time + timedelta(hours=72):
            self.exit_decision = self._decision(now, "MAXIMUM_HOLD")
            return self.exit_decision
        return None

    def push(
        self, candle: Candle, atr_current: Decimal, decision_time: datetime, last_price: Decimal
    ) -> ExitDecision | None:
        decision_time = utc(decision_time)
        require_decimal(atr_current, nonnegative=True)
        require_decimal(last_price, positive=True)
        if (
            candle.symbol != self.entry.symbol
            or candle.price_type != "LAST"
            or candle.duration != timedelta(hours=1)
        ):
            raise ValueError("Exit engine requires owned hourly LAST candle")
        if candle.timing.available_at > decision_time:
            raise ValueError("Exit input not causally available")
        end = candle.timing.interval_end
        if end <= self.entry.first_fill_time:
            return None  # an equal-time/pre-fill close is ineligible
        identity = digest([candle, atr_current])
        if end == self.last_end and identity == self.last_input_hash:
            return self.last_decision
        if self.last_decision is not None and decision_time < self.last_decision.decided_at:
            raise ValueError("Cannot backdate exit processing")
        expected = (
            self.entry.first_fill_time.replace(minute=0, second=0, microsecond=0)
            if self.last_end is None
            else self.last_end
        ) + timedelta(hours=1)
        if end != expected:
            raise ValueError(
                "Missing/revised close requires causal reconciliation; no skipped counting"
            )
        if self.exit_decision is not None:
            return self.exit_decision
        if self.timer(decision_time) is not None:
            return self.exit_decision
        with localcontext(CONTEXT):
            self.count += 1
            close = candle.close
            self.highest_close = (
                close if self.highest_close is None else max(self.highest_close, close)
            )
            self.lowest_close = (
                close if self.lowest_close is None else min(self.lowest_close, close)
            )
            self.last_end, self.last_input_hash = end, identity
            boundary = (
                self.entry.channel_high if self.entry.side is Side.LONG else self.entry.channel_low
            )
            failure = self.count <= 3 and self.entry.side.sign * (close - boundary) <= 0
            extreme = self.highest_close if self.entry.side is Side.LONG else self.lowest_close
            mfe = self.entry.side.sign * (extreme - self.entry.vwap)
            weak = self.count == 6 and mfe < D("0.5") * self.entry.price_risk
            if failure or weak:
                self.exit_decision = self._decision(
                    decision_time, "EARLY_FAILURE" if failure else "WEAK_FOLLOWTHROUGH"
                )
                self.last_decision = self.exit_decision
                return self.exit_decision
            self.trailing_active |= (
                self.entry.side.sign * (close - self.entry.vwap) >= 2 * self.entry.price_risk
            )
            proposal = None
            if self.trailing_active:
                raw = extreme - self.entry.side.sign * 3 * atr_current
                chooser = max if self.entry.side is Side.LONG else min
                candidate = chooser(self.effective_stop, self.proposed_stop, raw)
                candidate = quantize_step(
                    candidate, self.entry.tick, up=self.entry.side is Side.LONG
                )
                if candidate <= 0:
                    raise ValueError("Nonpositive trailing stop")
                if self.entry.side.sign * (last_price - candidate) <= 0:
                    self.exit_decision = self._decision(decision_time, "TRAILING_TRIGGER_CROSSED")
                    self.last_decision = self.exit_decision
                    return self.exit_decision
                if self.entry.side.sign * (candidate - self.proposed_stop) > 0:
                    proposal = candidate
                    self.proposed_stop, self.proposed_at = candidate, decision_time
            self.last_decision = self._decision(decision_time, stop=proposal)
            return self.last_decision

    def acknowledge_stop(self, stop: Decimal, acknowledged_at: datetime):
        """Called only after execution layer proves matching reduce-only LAST protection."""
        require_decimal(stop, positive=True)
        acknowledged_at = utc(acknowledged_at)
        if stop != self.proposed_stop or acknowledged_at < max(self.proposed_at, self.effective_at):
            raise ValueError("Unknown or backdated protective acknowledgement")
        with localcontext(CONTEXT):
            if self.entry.side.sign * (stop - self.effective_stop) < 0:
                raise ValueError("Cannot widen confirmed stop")
        self.effective_stop, self.effective_at = stop, acknowledged_at

    def checkpoint(self):
        return dict(
            entry=asdict(self.entry),
            effective_stop=self.effective_stop,
            effective_at=self.effective_at,
            proposed_stop=self.proposed_stop,
            proposed_at=self.proposed_at,
            trailing_active=self.trailing_active,
            count=self.count,
            highest_close=self.highest_close,
            lowest_close=self.lowest_close,
            last_end=self.last_end,
            last_input_hash=self.last_input_hash,
            last_decision=None if self.last_decision is None else asdict(self.last_decision),
            exit_decision=None if self.exit_decision is None else asdict(self.exit_decision),
        )

    @classmethod
    def restore(cls, payload):
        e = dict(payload["entry"])
        e["side"] = Side(e["side"])
        e["first_fill_time"] = datetime.fromisoformat(e["first_fill_time"])
        for key in ("vwap", "initial_stop", "channel_high", "channel_low", "tick"):
            e[key] = D(e[key])
        result = cls(Entry(**e))
        for key in ("effective_stop", "proposed_stop", "highest_close", "lowest_close"):
            setattr(result, key, None if payload[key] is None else D(payload[key]))
        for key in ("effective_at", "proposed_at", "last_end"):
            setattr(
                result, key, None if payload[key] is None else datetime.fromisoformat(payload[key])
            )
        for key in ("trailing_active", "count", "last_input_hash"):
            setattr(result, key, payload[key])
        for key in ("last_decision", "exit_decision"):
            value = payload[key]
            if value is not None:
                value = dict(value)
                value["decided_at"] = datetime.fromisoformat(value["decided_at"])
                for field in ("proposed_stop", "close_mfe"):
                    value[field] = None if value[field] is None else D(value[field])
                value = ExitDecision(**value)
            setattr(result, key, value)
        return result
