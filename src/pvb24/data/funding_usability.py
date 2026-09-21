"""Exact-source funding economics gated by independent boundary eligibility evidence.

Funding-history rows can prove a final rate and source-associated settlement Mark for a
particular timestamp. They do not prove the funding calendar, absence of missing settlements,
or which owned position quantity was eligible at that boundary. This module keeps those
questions separate and never synthesizes FundingSettlement intervals.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from pvb24.accounting.ledger import FundingPayment
from pvb24.decimal_math import D, require_decimal
from pvb24.ids import canonical, digest
from pvb24.types import Side, utc


@dataclass(frozen=True)
class FundingEligibilityEvidence:
    """Independent proof of an owned position quantity at one exact funding boundary."""

    position_id: str
    symbol: str
    side: Side
    eligible_quantity: Decimal
    settlement_time: datetime
    available_at: datetime
    source: str
    revision_id: str
    boundary_verified: bool

    def __post_init__(self):
        if not all((self.position_id, self.symbol, self.source, self.revision_id)):
            raise ValueError("Funding eligibility identity/provenance required")
        if not isinstance(self.side, Side):
            raise TypeError("Explicit funding eligibility side required")
        require_decimal(self.eligible_quantity, nonnegative=True)
        if utc(self.available_at) < utc(self.settlement_time):
            raise ValueError("Eligibility evidence cannot predate its settlement boundary")
        if type(self.boundary_verified) is not bool or not self.boundary_verified:
            raise ValueError("Exact boundary eligibility must be independently verified")


def _source_row(entry):
    if not isinstance(entry, dict) or set(entry) != {"record", "source", "revision_id"}:
        raise ValueError("Exact funding source wrapper required")
    if not isinstance(entry["source"], str) or not entry["source"]:
        raise ValueError("Funding source URL/identity required")
    if not isinstance(entry["revision_id"], str) or not entry["revision_id"]:
        raise ValueError("Funding source revision required")
    row = entry["record"]
    required = {
        "symbol",
        "funding_time",
        "rate",
        "mark_price",
        "rate_type",
        "available_at",
    }
    if not isinstance(row, dict) or set(row) != required:
        raise ValueError("Exact funding source record schema required")
    if not isinstance(row["symbol"], str) or not row["symbol"]:
        raise ValueError("Funding symbol required")
    settlement = utc(datetime.fromisoformat(row["funding_time"]))
    available = utc(datetime.fromisoformat(row["available_at"]))
    if available < settlement:
        raise ValueError("Funding source cannot be available before settlement")
    if row["rate_type"] != "Regular":
        raise ValueError("Only explicit Regular funding rows are ledger-usable")
    if row["mark_price"] is None:
        raise ValueError("Exact source-associated settlement Mark required")
    rate, mark = D(row["rate"]), D(row["mark_price"])
    require_decimal(rate)
    require_decimal(mark, positive=True)
    return row, settlement, available, rate, mark


def funding_payment_from_exact_source(entry, eligibility: FundingEligibilityEvidence):
    """Build one accounting payment only when economics and eligibility both match exactly.

    The result is suitable for PRELIMINARY accounting at max(source, eligibility)
    availability. It does not create or imply FundingCoverage/FundingSettlement schedule
    evidence and therefore cannot qualify the 30-day reserve-rate calendar by itself.
    """
    if not isinstance(eligibility, FundingEligibilityEvidence):
        raise TypeError("Independent FundingEligibilityEvidence required")
    row, settlement, source_available, rate, mark = _source_row(entry)
    if row["symbol"] != eligibility.symbol or settlement != utc(eligibility.settlement_time):
        raise ValueError("Funding economics and eligibility boundary must match exactly")
    available = max(source_available, utc(eligibility.available_at))
    evidence_hash = digest(eligibility)
    event_id = digest(
        [
            "PVB24_EXACT_FUNDING_PAYMENT_V1",
            entry["source"],
            entry["revision_id"],
            row,
            evidence_hash,
        ]
    )
    return FundingPayment(
        event_id=event_id,
        position_id=eligibility.position_id,
        side=eligibility.side,
        eligible_quantity=eligibility.eligible_quantity,
        mark_price=mark,
        final_rate=rate,
        settlement_time=settlement,
        available_at=available,
        source=entry["source"] + "#" + entry["revision_id"],
        eligibility_evidence=evidence_hash,
    )


def qualify_history_rows(rows):
    """Classify source economics without pretending missing eligibility/schedule are solved."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("Nonempty exact funding source rows required")
    seen = set()
    exact_economics = 0
    missing_mark = 0
    unsupported_type = 0
    symbols = set()
    first = last = None
    for entry in rows:
        if not isinstance(entry, dict) or "record" not in entry:
            raise ValueError("Funding source wrapper required")
        row = entry["record"]
        if not isinstance(row, dict):
            raise ValueError("Funding source record required")
        symbol = row.get("symbol")
        stamp = row.get("funding_time")
        rate_type = row.get("rate_type")
        identity = (symbol, stamp, rate_type)
        if identity in seen:
            raise ValueError("Duplicate exact funding source identity")
        seen.add(identity)
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("Funding symbol required")
        time = utc(datetime.fromisoformat(stamp))
        symbols.add(symbol)
        first = time if first is None or time < first else first
        last = time if last is None or time > last else last
        if rate_type != "Regular":
            unsupported_type += 1
            continue
        if row.get("mark_price") is None:
            missing_mark += 1
            continue
        _source_row(entry)
        exact_economics += 1
    return {
        "schema": "PVB24_FUNDING_SETTLEMENT_USABILITY_V1",
        "rows": len(rows),
        "symbols": sorted(symbols),
        "first_settlement_time": first,
        "last_settlement_time": last,
        "exact_source_economics_rows": exact_economics,
        "missing_settlement_mark_rows": missing_mark,
        "unsupported_rate_type_rows": unsupported_type,
        "conditionally_ledger_usable_rows": exact_economics,
        "unconditional_ledger_usable_rows": 0,
        "requires_independent_position_eligibility": True,
        "historical_publication_times_verified": False,
        "funding_schedule_complete": False,
        "funding_reserve_coverage_qualified": False,
        "position_eligibility_verified": False,
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "final_test_access": "LOCKED",
        "input_hash": digest(rows),
    }


def canonical_qualification(rows):
    return canonical(qualify_history_rows(rows))
