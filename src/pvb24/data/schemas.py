from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pvb24.decimal_math import require_decimal
from pvb24.types import utc


@dataclass(frozen=True)
class Timing:
    event_time: datetime
    interval_start: datetime
    interval_end: datetime
    available_at: datetime
    received_at: datetime | None
    source: str
    revision_id: str
    record_type: str = "interval"
    processing_monotonic_ns: int | None = None

    def __post_init__(self):
        for t in (self.event_time, self.interval_start, self.interval_end, self.available_at):
            utc(t)
        if not self.source or not self.revision_id:
            raise ValueError("Source and revision identity required")
        if self.record_type == "interval":
            if self.interval_start >= self.interval_end or self.interval_end > self.available_at:
                raise ValueError("Interval not completed before availability")
        elif self.record_type == "snapshot":
            if not self.interval_start == self.interval_end == self.event_time:
                raise ValueError("Snapshot interval must equal event time")
        else:
            raise ValueError("Unknown record type")
        if self.event_time > self.available_at:
            raise ValueError("Event cannot be available before it happened")
        if self.received_at is not None and utc(self.received_at) > self.available_at:
            raise ValueError("Data cannot be available before receipt")
        if self.processing_monotonic_ns is not None and self.processing_monotonic_ns < 0:
            raise ValueError("Invalid monotonic processing timestamp")


@dataclass(frozen=True)
class Candle:
    symbol: str
    timing: Timing
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    quote_volume: Decimal
    price_type: str = "LAST"
    zero_volume_confirmed: bool = False

    def __post_init__(self):
        if not self.symbol or self.timing.record_type != "interval":
            raise ValueError("Candle requires symbol and interval timing")
        for v in (self.open, self.high, self.low, self.close):
            require_decimal(v, positive=True)
        require_decimal(self.quote_volume, nonnegative=True)
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Inconsistent OHLC")
        if self.price_type not in ("LAST", "MARK"):
            raise ValueError("Unknown candle price type")
        if self.quote_volume == 0 and not self.zero_volume_confirmed:
            raise ValueError("Zero volume must be explicitly confirmed by the source")

    @property
    def duration(self) -> timedelta:
        return self.timing.interval_end - self.timing.interval_start


@dataclass(frozen=True)
class Mark:
    symbol: str
    price: Decimal
    timing: Timing

    def __post_init__(self):
        require_decimal(self.price, positive=True)
        if not self.symbol or self.timing.record_type != "snapshot":
            raise ValueError("Mark requires an identified snapshot")
