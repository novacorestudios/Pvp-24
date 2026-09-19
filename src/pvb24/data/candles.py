from datetime import datetime, timedelta
from itertools import pairwise

from pvb24.data.availability import available
from pvb24.data.schemas import Candle
from pvb24.ids import canonical


def causal_candles(
    rows: list[Candle],
    symbol: str,
    duration: timedelta,
    decision_time: datetime,
    *,
    price_type="LAST",
    end_at: datetime | None = None,
) -> list[Candle]:
    selected = {}
    for row in rows:
        if row.symbol != symbol or row.duration != duration or row.price_type != price_type:
            continue
        if not available(row.timing, decision_time):
            continue
        if end_at is not None and row.timing.interval_end > end_at:
            continue
        key = row.timing.interval_start
        old = selected.get(key)
        if old is not None and old.timing.available_at == row.timing.available_at:
            if canonical(old) != canonical(row):
                raise ValueError("Ambiguous same-time candle revision")
        if old is None or old.timing.available_at < row.timing.available_at:
            selected[key] = row
    return [selected[k] for k in sorted(selected)]


def contiguous(rows: list[Candle], duration: timedelta) -> bool:
    return (
        bool(rows)
        and all(x.duration == duration for x in rows)
        and all(
            left.timing.interval_end == right.timing.interval_start
            for left, right in pairwise(rows)
        )
    )


def warmup_complete(rows: list[Candle], signal_time: datetime) -> bool:
    required = rows[-720:]
    return (
        len(required) == 720
        and contiguous(required, timedelta(hours=1))
        and required[-1].timing.interval_end == signal_time
    )
