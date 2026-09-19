from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pvb24.data.candles import causal_candles, contiguous
from pvb24.data.schemas import Candle
from pvb24.decimal_math import D, median
from pvb24.ids import digest
from pvb24.types import Quality, utc


@dataclass(frozen=True)
class Security:
    symbol: str
    trading_start: datetime
    effective_from: datetime
    available_at: datetime
    classification: str
    active: bool
    source: str
    revision_id: str
    historical_verified: bool
    contract_type: str = "PERPETUAL"
    quote_asset: str = "USDT"
    delisting_announcement_at: datetime | None = None

    def __post_init__(self):
        for t in (self.trading_start, self.effective_from, self.available_at):
            utc(t)
        if self.delisting_announcement_at is not None:
            utc(self.delisting_announcement_at)
        if not self.symbol or not self.source or not self.revision_id:
            raise ValueError("Security master provenance required")
        if self.classification not in ("CRYPTO", "STABLECOIN", "NON_CRYPTO", "UNKNOWN"):
            raise ValueError("Unknown classification")


@dataclass(frozen=True)
class Universe:
    universe_id: str
    decision_time: datetime
    valid_until: datetime
    symbols: tuple[str, ...]
    medians: tuple[tuple[str, Decimal], ...]
    excluded: tuple[tuple[str, tuple[str, ...]], ...]
    quality: Quality
    input_hash: str

    def allows(self, symbol: str, when: datetime) -> bool:
        return self.decision_time <= utc(when) <= self.valid_until and symbol in self.symbols


def build_universe(
    securities: list[Security],
    daily: list[Candle],
    decision: datetime,
    *,
    security_history_complete: bool,
) -> Universe:
    decision = utc(decision)
    day = decision.replace(hour=0, minute=0, second=0, microsecond=0)
    if not day + timedelta(minutes=5) <= decision <= day + timedelta(hours=1, minutes=5):
        raise ValueError("Universe refresh must occur in its scheduled grace window")
    known = {}
    for item in securities:
        if item.available_at > decision or item.effective_from > decision:
            continue
        old = known.get(item.symbol)
        if old and (old.effective_from, old.available_at) == (
            item.effective_from,
            item.available_at,
        ):
            if old != item:
                raise ValueError("Ambiguous security revision")
        if old is None or (old.effective_from, old.available_at) < (
            item.effective_from,
            item.available_at,
        ):
            known[item.symbol] = item
    eligible, excluded, provenance = [], [], []
    for symbol, security in sorted(known.items()):
        reasons = []
        if not security.active:
            reasons.append("INACTIVE")
        if security.classification != "CRYPTO":
            reasons.append("CLASSIFICATION_INELIGIBLE")
        if security.contract_type != "PERPETUAL" or security.quote_asset != "USDT":
            reasons.append("UNSUPPORTED_CONTRACT")
        if decision - security.trading_start < timedelta(days=90):
            reasons.append("LISTING_AGE")
        if (
            security.delisting_announcement_at is not None
            and security.delisting_announcement_at <= decision
        ):
            reasons.append("DELISTING_ANNOUNCED")
        candles = causal_candles(daily, symbol, timedelta(days=1), decision, end_at=day)
        candles = [x for x in candles if x.timing.interval_start >= day - timedelta(days=30)]
        complete = (
            len(candles) == 30
            and contiguous(candles, timedelta(days=1))
            and candles[0].timing.interval_start == day - timedelta(days=30)
            and candles[-1].timing.interval_end == day
        )
        volume = None
        if not complete:
            reasons.append("DATA_GAP")
        else:
            volume = median([x.quote_volume for x in candles])
            if volume < D("50000000"):
                reasons.append("LOW_LIQUIDITY")
        provenance.append({"security": security, "daily": candles})
        if reasons:
            excluded.append((symbol, tuple(reasons)))
        else:
            eligible.append((symbol, volume))
    eligible.sort(key=lambda x: (x[1].copy_negate(), x[0]))
    chosen = eligible[:20]
    excluded.extend((symbol, ("RANK_BELOW_TOP20",)) for symbol, _ in eligible[20:])
    quality = (
        Quality.VERIFIED
        if security_history_complete
        and known
        and all(x.historical_verified for x in known.values())
        else Quality.PRELIMINARY
    )
    input_hash = digest(provenance)
    identity = {"decision": decision, "inputs": input_hash, "members": chosen, "quality": quality}
    return Universe(
        digest(identity),
        decision,
        day + timedelta(days=1, hours=1, minutes=5),
        tuple(x[0] for x in chosen),
        tuple(chosen),
        tuple(excluded),
        quality,
        input_hash,
    )
