"""Offline audit of retained funding settlement timing evidence.

This module distinguishes an ex-post complete source query from a causal
FundingCoverage assertion. It never rounds funding timestamps, invents an
eight-hour calendar, or emits risk-engine settlement/coverage objects.
"""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

from pvb24.data.acquisition import load_acquired
from pvb24.data.archive import ArchiveRequest, FundingArchiveRow, records
from pvb24.data.funding_coverage import resume_results
from pvb24.ids import canonical, digest

SCHEMA = "PVB24_FUNDING_SCHEDULE_AUDIT_V1"


def _microseconds(value: timedelta) -> int:
    return (value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds


def audit_funding_schedule(root, summary_path, *, expected_summary_sha256):
    """Revalidate one pinned funding source selection and audit exact settlement spacing.

    Complete REST pagination and matching archive rows are useful ex-post source
    evidence. They do not prove that a historical decision between settlements
    causally knew the next settlement boundary. Consequently this function does
    not emit FundingCoverage and never promotes funding_schedule_complete.
    """
    root, summary_path = Path(root), Path(summary_path)
    payload = summary_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_summary_sha256:
        raise ValueError("Funding source summary hash changed")
    summary = json.loads(payload)
    if (
        summary.get("schema") != "PVB24_FUNDING_SOURCE_COVERAGE_V1"
        or summary.get("final_test_access") != "LOCKED"
    ):
        raise ValueError("Locked funding source coverage summary required")
    coverage = summary.get("coverage")
    if not isinstance(coverage, list) or not coverage:
        raise ValueError("Nonempty explicit funding source coverage required")
    requests = tuple(ArchiveRequest(**row["request"]) for row in coverage)
    if any(request.kind != "fundingRate" for request in requests):
        raise ValueError("Funding-rate source selection required")
    if len(set(requests)) != len(requests):
        raise ValueError("Unique funding source requests required")

    # Revalidate every monthly report, REST page chain, archive/checksum,
    # and time/rate comparison before schedule diagnostics.
    checked = resume_results(
        root,
        summary_path,
        expected_hash=expected_summary_sha256,
        requests=requests,
        config_hash=summary["config_hash"],
    )
    by_request = {ArchiveRequest(**monthly["request"]): monthly for monthly, _ in checked}
    if set(by_request) != set(requests):
        raise ValueError("Funding source selection is not fully revalidated")

    archive_rows = []
    unavailable = []
    matched_months = 0
    for request in requests:
        monthly = by_request[request]
        matched_months += int(monthly["status"] == "MATCHED_TIME_RATE")
        archive = monthly["archive"]
        if archive["status"] == "UNAVAILABLE":
            unavailable.append(request.month)
            continue
        if archive["status"] != "ACQUIRED":
            raise ValueError("Explicit acquired or unavailable funding archive required")
        source, raw, checksum = load_acquired(root / "archives", archive["attempt"])
        if source != request:
            raise ValueError("Funding archive identity changed")
        decoded = list(records(source, raw, checksum))
        if (
            not decoded
            or any(not isinstance(row, FundingArchiveRow) for row in decoded)
            or archive["rows"] != len(decoded)
        ):
            raise ValueError("Funding archive rows differ from revalidated monthly evidence")
        archive_rows.extend(decoded)

    archive_rows.sort(key=lambda row: row.calculated_at)
    if any(
        previous.symbol != current.symbol
        or previous.calculated_at >= current.calculated_at
        for previous, current in zip(archive_rows, archive_rows[1:], strict=False)
    ):
        raise ValueError("Funding archive event index is ambiguous")

    differences = []
    actual_intervals = []
    declared_values = set()
    possible_missing_declared_intervals = 0
    for previous, current in zip(archive_rows, archive_rows[1:], strict=False):
        actual = current.calculated_at - previous.calculated_at
        declared = current.declared_duration
        actual_us, declared_us = _microseconds(actual), _microseconds(declared)
        if actual_us <= 0 or declared_us <= 0:
            raise ValueError("Positive funding intervals required")
        difference = actual_us - declared_us
        differences.append(difference)
        actual_intervals.append(
            {
                "interval_start": previous.calculated_at,
                "settlement_time": current.calculated_at,
                "actual_interval_microseconds": actual_us,
                "declared_interval_microseconds": declared_us,
                "difference_microseconds": difference,
            }
        )
        declared_values.add(current.interval_hours)
        # Diagnostic only: a whole additional declared interval fits between
        # consecutive source events. This never by itself proves a missing row.
        possible_missing_declared_intervals += int(actual_us >= 2 * declared_us)

    result = {
        "schema": SCHEMA,
        "source_summary_sha256": expected_summary_sha256,
        "source_data_hash": summary["data_hash"],
        "requested_months": len(requests),
        "revalidated_months": len(checked),
        "time_rate_matched_months": matched_months,
        "archive_unavailable_months": unavailable,
        "archive_settlement_rows": len(archive_rows),
        "adjacent_archive_pairs": len(actual_intervals),
        "first_archive_settlement": archive_rows[0].calculated_at if archive_rows else None,
        "last_archive_settlement": archive_rows[-1].calculated_at if archive_rows else None,
        "declared_interval_hours": sorted(declared_values),
        "exact_declared_elapsed_pairs": sum(value == 0 for value in differences),
        "nonexact_declared_elapsed_pairs": sum(value != 0 for value in differences),
        "minimum_difference_microseconds": min(differences) if differences else None,
        "maximum_difference_microseconds": max(differences) if differences else None,
        "maximum_absolute_difference_microseconds": (
            max(abs(value) for value in differences) if differences else None
        ),
        "possible_missing_declared_interval_pairs": possible_missing_declared_intervals,
        "actual_interval_index_hash": digest(actual_intervals),
        "timestamp_rounding_applied": False,
        "source_query_reconsumption_complete": len(checked) == len(requests),
        "source_time_rate_comparison_complete": summary["source_time_rate_comparison_complete"],
        "ex_post_settlement_index_corroborated": (
            bool(archive_rows)
            and matched_months == len(requests) - len(unavailable)
            and not possible_missing_declared_intervals
        ),
        "causal_next_settlement_time_verified": False,
        "funding_schedule_complete": False,
        "funding_coverage_attestation_emitted": False,
        "funding_reserve_coverage_qualified": False,
        "reason": "EX_POST_EVENT_INDEX_DOES_NOT_PROVE_CAUSAL_INTER_SETTLEMENT_WATERMARK",
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    result["audit_hash"] = digest(result)
    return json.loads(canonical(result))
