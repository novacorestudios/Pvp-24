"""Pinned source-only settlement diagnostics. OHLC never becomes a point Mark.

This module creates no funding payments, schedules, or position eligibility.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pvb24.data.acquisition import load_acquired
from pvb24.data.archive import ArchiveRequest, records
from pvb24.data.funding_dataset import load_history
from pvb24.data.funding_history import epoch_ms
from pvb24.decimal_math import D
from pvb24.ids import digest


def audit_settlement_marks(coverage_path, expected_hash, history_root, samples=()):
    """Replay explicitly selected REST evidence and bounded Mark archive samples.

    Samples are (archive_root, content-addressed attempt) pairs. Candle open-price
    comparisons are diagnostics only: a bucket identity is not a point observation
    timestamp, and the frozen candle availability is after the interval finishes.
    """
    payload = Path(coverage_path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ValueError("Funding coverage selection hash changed")
    coverage = json.loads(payload)
    if coverage["final_test_access"] != "LOCKED":
        raise ValueError("Final Test must remain LOCKED")
    months, histories, seen = [], {}, set()
    for item in coverage["coverage"]:
        request = ArchiveRequest(**item["request"])
        identity = (request.symbol, request.month)
        if request.kind != "fundingRate" or identity in seen:
            raise ValueError("Unique funding month selection required")
        seen.add(identity)
        selected = item["history"]
        if selected["status"] != "ACQUIRED":
            raise ValueError("Explicit acquired funding history required")
        if selected["report"] != "reports/" + selected["report_hash"] + ".json":
            raise ValueError("Funding report path differs from pin")
        source, report = load_history(
            history_root,
            selected["report_hash"] + ".json",
            expected_report_hash=selected["report_hash"],
        )
        if source != request or report["data_hash"] != selected["data_hash"]:
            raise ValueError("Funding source selection changed")
        rows = [row["record"] for row in report["rows"]]
        missing = [row["funding_time"] for row in rows if row["mark_price"] is None]
        histories[identity] = rows
        months.append(
            {
                "symbol": request.symbol,
                "month": request.month,
                "history_report_sha256": selected["report_hash"],
                "history_data_hash": report["data_hash"],
                "rows": len(rows),
                "source_mark_present": len(rows) - len(missing),
                "missing_settlement_times_ms": [
                    epoch_ms(datetime.fromisoformat(t)) for t in missing
                ],
                "first_missing_time": min(missing) if missing else None,
                "last_missing_time": max(missing) if missing else None,
                "missing_exact_minute_times": sum(
                    datetime.fromisoformat(t).second == 0
                    and datetime.fromisoformat(t).microsecond == 0
                    for t in missing
                ),
            }
        )
    if not months:
        raise ValueError("Nonempty explicit funding selection required")
    diagnostics, sample_seen = [], set()
    for root, attempt in samples:
        request, raw, checksum = load_acquired(root, attempt)
        identity = (request.symbol, request.month)
        if (
            request.kind != "markPriceKlines"
            or request.interval != "1m"
            or identity not in histories
            or identity in sample_seen
        ):
            raise ValueError("Unique selected-month 1m Mark sample required")
        sample_seen.add(identity)
        candles = list(records(request, raw, checksum))
        opens = {c.timing.interval_start: c for c in candles}
        matched, equal, unequal, late = [], [], [], []
        for row in histories[identity]:
            time = datetime.fromisoformat(row["funding_time"])
            candle = opens.get(time)  # No rounding, nearest join, interpolation or close.
            if candle is None:
                continue
            matched.append(row["funding_time"])
            if candle.timing.available_at > datetime.fromisoformat(row["available_at"]):
                late.append(row["funding_time"])
            if row["mark_price"] is not None:
                (equal if candle.open == D(row["mark_price"]) else unequal).append(
                    row["funding_time"]
                )
        diagnostics.append(
            {
                "symbol": request.symbol,
                "month": request.month,
                "attempt": attempt,
                "archive_sha256": hashlib.sha256(raw).hexdigest(),
                "source": request.url,
                "candle_rows": len(candles),
                "funding_rows": len(histories[identity]),
                "exact_open_time_matches": len(matched),
                "matched_bars_unavailable_at_funding_availability": len(late),
                "known_mark_equal_open_times": equal,
                "known_mark_unequal_open_times": unequal,
                "qualified_settlement_prices": 0,
                "reason": "OHLC_HAS_NO_POINT_OBSERVATION_TIME_OR_SETTLEMENT_ASSOCIATION",
            }
        )
    report = {
        "schema": "PVB24_SETTLEMENT_MARK_AUDIT_V1",
        "funding_coverage_sha256": expected_hash,
        "months": months,
        "source_mark_present": sum(m["source_mark_present"] for m in months),
        "source_mark_missing": sum(len(m["missing_settlement_times_ms"]) for m in months),
        "archive_samples": diagnostics,
        "archive_derived_settlement_prices": 0,
        "quality": "PRELIMINARY",
        "settlement_pricing_complete": all(not m["missing_settlement_times_ms"] for m in months),
        "historical_publication_times_verified": False,
        "funding_schedule_complete": False,
        "position_eligibility_verified": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    report["audit_hash"] = digest(report)
    return report
