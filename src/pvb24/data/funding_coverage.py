"""Bounded monthly source comparisons, including explicit unavailable periods.

This is a coverage audit, not a funding calendar or FundingCoverage attestation.
"""

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from pvb24.data.acquisition import acquire, load_acquired, object_write, public_bytes
from pvb24.data.archive import ArchiveRequest, records
from pvb24.data.funding_dataset import load_history
from pvb24.data.funding_history import acquire_history, compare_archive, public_history
from pvb24.ids import canonical, digest


def monthly_requests(symbol, first_month, last_month):
    first = ArchiveRequest(symbol, "fundingRate", first_month)
    last = ArchiveRequest(symbol, "fundingRate", last_month)
    count = (last.start.year - first.start.year) * 12 + last.start.month - first.start.month + 1
    if not 1 <= count <= 120:
        raise ValueError("An ordered, bounded 1..120-month selection is required")
    result, current = [], first
    for _ in range(count):
        result.append(current)
        current = (
            ArchiveRequest(symbol, "fundingRate", current.end.strftime("%Y-%m"))
            if current != last
            else current
        )
    return tuple(result)


def audit_month(request, root, *, archive_fetch=public_bytes, history_fetch=public_history):
    request.__post_init__()
    if request.kind != "fundingRate":
        raise ValueError("Funding source request required")
    root = Path(root)
    archive, attempt = acquire(request, root / "archives", fetch=archive_fetch)
    history, path = acquire_history(request, root / "history", fetch=history_fetch)
    result = reconstruct_month(request, root, archive, attempt, history, path)
    encoded = canonical(result).encode()
    name = object_write(root / "months", encoded, ".json")
    return json.loads(encoded), name


def reconstruct_month(request, root, archive, attempt, history, path):
    """Recompute the comparison from the selected evidence, with no network I/O."""
    request.__post_init__()
    history_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if history["status"] == "ACQUIRED":
        source, history = load_history(
            root / "history", path.name, expected_report_hash=history_hash
        )
        if source != request:
            raise ValueError("Funding history request changed")
    comparison, discontinuities, first, last = None, None, None, None
    if archive["status"] == "ACQUIRED":
        source, raw, checksum = load_acquired(root / "archives", attempt)
        if source != request:
            raise ValueError("Funding archive request changed")
        archive_rows = list(records(source, raw, checksum))
        discontinuities = len(archive["coverage"]["funding_interval_discontinuities"])
        first, last = archive_rows[0].calculated_at, archive_rows[-1].calculated_at
        if history["status"] == "ACQUIRED":
            comparison = compare_archive(archive_rows, history)
    matched = (
        comparison is not None
        and comparison["archive_rows"] > 0
        and not any(
            comparison[k]
            for k in ("rate_mismatches", "archive_only", "history_only", "unsupported_rate_rows")
        )
    )
    result = {
        "schema": "PVB24_MONTHLY_FUNDING_SOURCE_AUDIT_V1",
        "request": asdict(request),
        "start": request.start,
        "end_exclusive": request.end,
        "status": "MATCHED_TIME_RATE" if matched else "INCOMPLETE_OR_MISMATCHED",
        "archive": {
            "status": archive["status"],
            "attempt": attempt,
            "source_sha256": archive.get("actual_sha256"),
            "url": request.url,
            "rows": archive.get("coverage", {}).get("rows"),
            "http_status": archive.get("http_status"),
            "error": archive.get("error"),
        },
        "history": {
            "status": history["status"],
            "report": "reports/" + path.name,
            "report_hash": history_hash,
            "data_hash": history["data_hash"],
            "pages": history["pages"],
            "rows": len(history["rows"]) if history["status"] == "ACQUIRED" else None,
            "settlement_mark_complete": history["settlement_mark_complete"],
            "regular_type_complete": history["regular_type_complete"],
            "error": history.get("error"),
        },
        "comparison": comparison,
        "archive_interval_discontinuities": discontinuities,
        "first_archive_time": first,
        "last_archive_time": last,
        "quality": "PRELIMINARY",
        "funding_schedule_complete": False,
        "position_eligibility_verified": False,
        "historical_publication_times_verified": False,
        "final_test_access": "LOCKED",
        "operational_ready": False,
    }
    return json.loads(canonical(result))


def read_owned(root, reference, directory):
    if not re.fullmatch(re.escape(directory) + r"/[0-9a-f]{64}\.json", reference):
        raise ValueError("Owned content-addressed funding evidence required")
    path = Path(root) / reference
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() + ".json" != path.name:
        raise ValueError("Selected funding evidence hash changed")
    return json.loads(payload), path


def resume_results(root, summary_path, *, expected_hash, requests, config_hash):
    """Resume only a pinned selection; never discover or silently retry revisions."""
    for request in requests:
        request.__post_init__()
    payload = Path(summary_path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ValueError("Funding resume summary hash changed")
    summary = json.loads(payload)
    if summary.get("config_hash") != config_hash:
        raise ValueError("Funding resume config differs from frozen baseline")
    if [r["request"] for r in summary["coverage"]] != [asdict(r) for r in requests]:
        raise ValueError("Funding resume request selection changed")
    root, results = Path(root), []
    for row in summary["coverage"]:
        if row["status"] == "NOT_COMPLETED":
            continue
        monthly, path = read_owned(root, row["monthly_report"], "months")
        request = ArchiveRequest(**monthly["request"])
        archive, _ = read_owned(root / "archives", monthly["archive"]["attempt"], "attempts")
        history, history_path = read_owned(
            root / "history", monthly["history"]["report"], "reports"
        )
        if ArchiveRequest(**archive["request"]) != request or (
            history["symbol"],
            history["month"],
        ) != (request.symbol, request.month):
            raise ValueError("Funding resume source identities disagree")
        checked = reconstruct_month(
            request, root, archive, monthly["archive"]["attempt"], history, history_path
        )
        if canonical(monthly) != canonical(checked):
            raise ValueError("Funding resume monthly result differs from source evidence")
        results.append((checked, path.name))
    rebuilt = summarize(requests, results)
    if any(canonical(summary.get(k)) != canonical(v) for k, v in rebuilt.items()):
        raise ValueError("Funding resume coverage differs from revalidated selection")
    return results


def summarize(requests, results):
    """Every requested period stays visible even when its acquisition has not finished."""
    for request in requests:
        request.__post_init__()
    if not requests or len(set(requests)) != len(requests):
        raise ValueError("Unique explicit funding coverage requests required")
    rows = {}
    for result, name in results:
        request = ArchiveRequest(**result["request"])
        if request not in requests or request in rows or digest(result) + ".json" != name:
            raise ValueError("Funding result differs from requested, pinned coverage selection")
        rows[request] = {"monthly_report": "months/" + name, **result}
    coverage = [rows.get(r, {"request": asdict(r), "status": "NOT_COMPLETED"}) for r in requests]
    matched = sum(r["status"] == "MATCHED_TIME_RATE" for r in coverage)
    return {
        "schema": "PVB24_FUNDING_SOURCE_COVERAGE_V1",
        "requested_months": len(requests),
        "completed_months": len(rows),
        "matched_months": matched,
        "coverage": coverage,
        "source_time_rate_comparison_complete": matched == len(requests),
        "coverage_scope": "EXPLICIT_SYMBOL_MONTH_SELECTION_NOT_HISTORICAL_UNIVERSE",
        "data_hash": digest(coverage),
        "funding_schedule_complete": False,
        "historical_publication_times_verified": False,
        "position_eligibility_verified": False,
        "performance_run": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
