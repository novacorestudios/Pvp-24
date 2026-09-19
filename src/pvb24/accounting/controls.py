"""Minute equity risk overlay; daily reset never clears hard/safety pauses."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.decimal_math import CONTEXT, D, require_decimal
from pvb24.types import utc


@dataclass(frozen=True)
class RiskStatus:
    time: datetime
    equity: Decimal | None
    peak: Decimal
    daily_return: Decimal | None
    drawdown: Decimal | None
    risk_fraction: Decimal
    entries_allowed: bool
    daily_paused: bool
    hard_paused: bool
    safety_paused: bool
    data_paused: bool
    missing_samples: int


class EquityControl:
    def __init__(self, start: datetime, initial_equity: Decimal):
        start = self._minute(start)
        require_decimal(initial_equity, positive=True)
        self.peak = initial_equity
        self.recovery_peak = None
        self.day = start.date()
        self.day_start_equity = initial_equity
        self.daily_paused = False
        self.hard_paused = False
        self.safety_paused = False
        self.data_paused = False
        self.last_time = start - timedelta(minutes=1)
        self.last_status = None
        self.missing_samples = 0

    @staticmethod
    def _minute(time):
        time = utc(time)
        if time.second or time.microsecond:
            raise ValueError("Risk samples require UTC minute boundaries")
        return time

    def pause_safety(self):
        self.safety_paused = True
        if self.last_status is not None:
            self.last_status = replace(self.last_status, safety_paused=True, entries_allowed=False)

    def sample(self, time: datetime, equity: Decimal | None) -> RiskStatus:
        time = self._minute(time)
        if equity is not None:
            require_decimal(equity)
        if time == self.last_time and self.last_status is not None:
            if equity != self.last_status.equity:
                raise ValueError("Cannot silently revise a historical equity sample")
            return self.last_status
        if time <= self.last_time:
            raise ValueError("Equity sampling cannot move backwards")
        elapsed = time - self.last_time
        self.missing_samples += (elapsed.days * 86400 + elapsed.seconds) // 60 - 1
        new_day = time.date() != self.day
        if new_day:
            self.day = time.date()
            self.daily_paused = False
            # No replacement of an unknown midnight baseline by a later convenient value.
            self.day_start_equity = equity if time.hour == 0 and time.minute == 0 else None
        self.data_paused = equity is None or self.day_start_equity is None
        daily_return = drawdown = None
        with localcontext(CONTEXT):
            if equity is None:
                self.missing_samples += 1
            else:
                self.peak = max(self.peak, equity)
                drawdown = 1 - equity / self.peak
                if self.day_start_equity is not None and self.day_start_equity > 0:
                    daily_return = equity / self.day_start_equity - 1
                    self.daily_paused |= daily_return <= D("-0.04")
                else:
                    self.data_paused = True
                if self.recovery_peak is None and drawdown >= D("0.10"):
                    self.recovery_peak = self.peak
                if self.recovery_peak is not None and equity >= self.recovery_peak:
                    self.recovery_peak = None
                self.hard_paused |= drawdown >= D("0.15") or equity <= 0
            fraction = D("0.005") if self.recovery_peak is not None else D("0.01")
        self.last_time = time
        self.last_status = RiskStatus(
            time,
            equity,
            self.peak,
            daily_return,
            drawdown,
            fraction,
            not (self.daily_paused or self.hard_paused or self.safety_paused or self.data_paused),
            self.daily_paused,
            self.hard_paused,
            self.safety_paused,
            self.data_paused,
            self.missing_samples,
        )
        return self.last_status

    def checkpoint(self):
        return dict(
            peak=self.peak,
            recovery_peak=self.recovery_peak,
            day=self.day.isoformat(),
            day_start_equity=self.day_start_equity,
            daily_paused=self.daily_paused,
            hard_paused=self.hard_paused,
            safety_paused=self.safety_paused,
            data_paused=self.data_paused,
            last_time=self.last_time,
            last_status=None if self.last_status is None else asdict(self.last_status),
            missing_samples=self.missing_samples,
        )

    @classmethod
    def restore(cls, payload):
        from datetime import date

        p = dict(payload)
        p["last_time"] = datetime.fromisoformat(p["last_time"])
        result = cls(p["last_time"], D(p["peak"]))
        for key in ("peak", "recovery_peak", "day_start_equity"):
            p[key] = None if p[key] is None else D(p[key])
        p["day"] = date.fromisoformat(p["day"])
        status = p["last_status"]
        if status is not None:
            status = dict(status)
            status["time"] = datetime.fromisoformat(status["time"])
            for key in ("equity", "peak", "daily_return", "drawdown", "risk_fraction"):
                status[key] = None if status[key] is None else D(status[key])
            p["last_status"] = RiskStatus(**status)
        for key, value in p.items():
            setattr(result, key, value)
        return result
