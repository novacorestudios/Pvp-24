"""Immutable primitives shared by reference and paper adapters."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pvb24.decimal_math import require_decimal


class Side(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


class Quality(StrEnum):
    PRELIMINARY = "PRELIMINARY"
    VERIFIED = "VERIFIED"


class SymbolState(StrEnum):
    WARMUP = "WARMUP"
    READY = "READY"
    SIGNAL_VALIDATED = "SIGNAL_VALIDATED"
    ENTRY_PENDING = "ENTRY_PENDING"
    OPEN = "OPEN"
    TRAILING = "TRAILING"
    EXIT_PENDING = "EXIT_PENDING"
    COOLDOWN = "COOLDOWN"


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return value.astimezone(UTC)


def timestamp(value: datetime) -> str:
    return utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    position_id: str
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    event_time: datetime
    received_at: datetime
    reduce_only: bool = False

    def __post_init__(self):
        for x in (self.fill_id, self.order_id, self.position_id, self.symbol):
            if not x:
                raise ValueError("Fill identity fields are mandatory")
        if not isinstance(self.side, Side):
            raise TypeError("Side enum required")
        require_decimal(self.quantity, positive=True)
        require_decimal(self.price, positive=True)
        require_decimal(self.fee)
        if utc(self.received_at) < utc(self.event_time):
            raise ValueError("Fill received before exchange event")
