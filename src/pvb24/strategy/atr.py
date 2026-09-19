from dataclasses import dataclass
from decimal import Decimal, localcontext

from pvb24.decimal_math import CONTEXT, ZERO, D, require_decimal


@dataclass
class WilderATR:
    count: int = 0
    seed_sum: Decimal = ZERO
    value: Decimal | None = None

    def update(self, high: Decimal, low: Decimal, previous_close: Decimal) -> Decimal | None:
        for x in (high, low, previous_close):
            require_decimal(x, positive=True)
        if high < low:
            raise ValueError("Invalid range")
        with localcontext(CONTEXT):
            tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
            self.count += 1
            if self.value is None:
                self.seed_sum += tr
                if self.count == 24:
                    self.value = self.seed_sum / 24
            else:
                self.value = (23 * self.value + tr) / 24
            return self.value

    def checkpoint(self):
        return {"count": self.count, "seed_sum": self.seed_sum, "value": self.value}

    @classmethod
    def restore(cls, state):
        count = state["count"]
        seed_sum = D(state["seed_sum"])
        value = None if state["value"] is None else D(state["value"])
        if count < 0 or (count < 24) != (value is None) or seed_sum < 0:
            raise ValueError("Invalid ATR checkpoint")
        if value is not None and value < 0:
            raise ValueError("Invalid ATR checkpoint")
        return cls(count, seed_sum, value)
