"""Causal completed settlements and explicit coverage; missing is never zero."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.decimal_math import CONTEXT, ZERO, D, nearest_rank, require_decimal
from pvb24.types import Side, utc


@dataclass(frozen=True)
class FundingSettlement:
    symbol: str
    interval_start: datetime
    settlement_time: datetime
    available_at: datetime
    rate: Decimal
    source: str
    revision_id: str

    def __post_init__(self):
        if not self.symbol or not self.source or not self.revision_id:
            raise ValueError("Funding provenance required")
        if not utc(self.interval_start) < utc(self.settlement_time) <= utc(self.available_at):
            raise ValueError("Invalid funding interval or availability")
        require_decimal(self.rate)


@dataclass(frozen=True)
class FundingCoverage:
    """Source adapter attests a complete settlement index through a causal watermark.

    Needed to distinguish a still-running interval from a missing latest settlement.
    This assertion cannot be inferred merely from the last row present.
    """

    symbol: str
    start: datetime
    through: datetime
    available_at: datetime
    source: str
    revision_id: str

    def __post_init__(self):
        if not self.symbol or not self.source or not self.revision_id:
            raise ValueError("Coverage provenance required")
        if not utc(self.start) < utc(self.through) <= utc(self.available_at):
            raise ValueError("Invalid coverage watermark")


def reserve_rate(
    rows: list[FundingSettlement], coverage: FundingCoverage, side: Side, decision: datetime
) -> Decimal:
    """Nearest-rank 95th percentile of signed per-hour rates over prior 30 days."""
    decision = utc(decision)
    if not isinstance(side, Side):
        raise TypeError("Side enum required")
    start = decision - timedelta(days=30)
    if coverage.start > start or coverage.through < decision or coverage.available_at > decision:
        raise ValueError("Incomplete causal funding coverage")
    versions = {}
    for row in rows:
        if row.symbol != coverage.symbol or row.available_at > decision:
            continue
        if not start < row.settlement_time <= decision:
            continue
        previous = versions.get(row.settlement_time)
        if previous is None or row.available_at > previous.available_at:
            versions[row.settlement_time] = row
        elif row.available_at == previous.available_at and row != previous:
            raise ValueError("Conflicting funding revision")
    selected = sorted(versions.values(), key=lambda row: row.settlement_time)
    if not selected or selected[0].interval_start > start:
        raise ValueError("Missing funding history")
    for previous, current in zip(selected, selected[1:], strict=False):
        if previous.settlement_time != current.interval_start:
            raise ValueError("Gap or overlap in funding settlements")
    with localcontext(CONTEXT):
        rates = []
        for row in selected:
            delta = row.settlement_time - row.interval_start
            micros = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
            hours = D(micros) / D(3600000000)
            rates.append(side.sign * row.rate / hours)
        return max(ZERO, nearest_rank(rates, D("0.95")))
