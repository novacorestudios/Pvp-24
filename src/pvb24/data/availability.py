from datetime import datetime, timedelta

from pvb24.data.schemas import Timing
from pvb24.types import utc


def available(timing: Timing, decision: datetime) -> bool:
    return timing.available_at <= utc(decision) and timing.interval_end <= decision


def preliminary_timing(start: datetime, end: datetime, source: str, revision: str) -> Timing:
    return Timing(end, start, end, end + timedelta(seconds=2), None, source, revision)


def timely_signal(timings: list[Timing], signal_time: datetime, decision_time: datetime) -> bool:
    if not timings or utc(decision_time) < utc(signal_time):
        return False
    deadline = signal_time + timedelta(seconds=30)
    return decision_time <= deadline and all(
        available(t, decision_time) and t.available_at <= deadline for t in timings
    )


def order_timely(signal_time: datetime, order_sent_at: datetime, decision_time: datetime) -> bool:
    return utc(decision_time) <= utc(order_sent_at) <= utc(signal_time) + timedelta(seconds=90)


def preliminary_entry_minute(decision_time: datetime) -> datetime:
    return utc(decision_time).replace(second=0, microsecond=0) + timedelta(minutes=1)
