"""Sequence-consistent USD-M L2 replay with non-reusable consumed depth."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.decimal_math import CONTEXT, ZERO, require_decimal
from pvb24.types import Side, utc


@dataclass(frozen=True)
class LevelFill:
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True)
class Sweep:
    requested: Decimal
    filled: Decimal
    vwap: Decimal | None
    fills: tuple[LevelFill, ...]


class Book:
    def __init__(self, symbol: str):
        if not symbol:
            raise ValueError("Book symbol required")
        self.symbol = symbol
        self.bids = {}
        self.asks = {}
        self.sequence = None
        self.synced = False
        self.event_time = None
        self.received_at = None

    @staticmethod
    def _levels(rows):
        levels = {}
        for price, quantity in rows:
            require_decimal(price, positive=True)
            require_decimal(quantity, nonnegative=True)
            if price in levels:
                raise ValueError("Duplicate book price")
            levels[price] = quantity
        return levels

    def _times(self, event_time, received_at):
        if utc(event_time) > utc(received_at):
            raise ValueError("Clock-normalized receipt precedes event")
        if self.received_at is not None and received_at < self.received_at:
            raise ValueError("Out-of-order local receipt")

    def snapshot(self, sequence: int, bids, asks, event_time: datetime, received_at: datetime):
        self.synced = False
        self.sequence = None
        self._times(event_time, received_at)
        if type(sequence) is not int or sequence < 0:
            raise ValueError("Invalid snapshot sequence")
        b, a = self._levels(bids), self._levels(asks)
        self.bids = {p: q for p, q in b.items() if q > 0}
        self.asks = {p: q for p, q in a.items() if q > 0}
        self.sequence = sequence
        self.event_time, self.received_at = event_time, received_at
        self.synced = False  # requires the initial websocket bridge

    def update(
        self,
        first: int,
        final: int,
        previous: int,
        bids,
        asks,
        event_time: datetime,
        received_at: datetime,
    ):
        if any(type(x) is not int or x < 0 for x in (first, final, previous)) or first > final:
            self.synced = False
            self.sequence = None
            raise ValueError("Invalid update sequence")
        if self.sequence is None:
            raise ValueError("Snapshot required")
        if final < self.sequence or (self.synced and final == self.sequence):
            return False
        try:
            self._times(event_time, received_at)
            b, a = self._levels(bids), self._levels(asks)
        except (ValueError, TypeError):
            self.synced = False
            self.sequence = None
            raise
        connected = previous == self.sequence if self.synced else first <= self.sequence <= final
        if not connected:
            self.sequence = None
            self.synced = False
            raise ValueError("Book sequence gap: fresh snapshot required")
        for target, updates in ((self.bids, b), (self.asks, a)):
            for price, quantity in updates.items():
                if quantity == 0:
                    target.pop(price, None)
                else:
                    # Only a later explicit absolute update replenishes this level.
                    target[price] = quantity
        self.sequence = final
        self.synced = True
        self.event_time, self.received_at = event_time, received_at
        if not self.bids or not self.asks or max(self.bids) >= min(self.asks):
            self.synced = False
            self.sequence = None
            raise ValueError("Empty or crossed book: resnapshot required")
        return True

    def fresh(self, now: datetime) -> bool:
        now = utc(now)
        return self.synced and all(
            time is not None and timedelta(0) <= now - time <= timedelta(milliseconds=500)
            for time in (self.event_time, self.received_at)
        )

    @property
    def best_bid(self):
        return max(self.bids)

    @property
    def best_ask(self):
        return min(self.asks)

    def sweep(
        self,
        side: Side,
        quantity: Decimal,
        limit: Decimal,
        *,
        consume=False,
        haircut: Decimal = ZERO,
    ) -> Sweep:
        require_decimal(quantity, positive=True)
        require_decimal(limit, positive=True)
        require_decimal(haircut, nonnegative=True)
        if haircut >= 1 or not isinstance(side, Side) or type(consume) is not bool:
            raise ValueError("Invalid sweep")
        if not self.synced:
            raise ValueError("Sequence-consistent book required")
        levels = self.asks if side is Side.LONG else self.bids
        with localcontext(CONTEXT):
            remaining = quantity
            fills = []
            for price in sorted(levels, reverse=side is Side.SHORT):
                if side.sign * (price - limit) > 0:
                    break
                take = min(remaining, levels[price] * (1 - haircut))
                if take <= 0:
                    continue
                fills.append(LevelFill(price, take))
                remaining -= take
                if remaining == 0:
                    break
            if consume:
                for fill in fills:
                    # Haircut removes proportionally from usable depth. Consume the
                    # corresponding original units so repeated sweeps cannot reuse it.
                    if fill.quantity == levels[fill.price] * (1 - haircut):
                        del levels[fill.price]
                    else:
                        levels[fill.price] -= fill.quantity / (1 - haircut)
            filled = quantity - remaining
            vwap = sum((f.price * f.quantity for f in fills), ZERO) / filled if filled else None
            return Sweep(quantity, filled, vwap, tuple(fills))
