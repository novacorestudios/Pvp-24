"""Resolve remaining listing-boundary evidence with official monthly Binance Vision data."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from pvb24.data.acquisition import acquire, load_acquired, public_bytes
from pvb24.data.archive import ArchiveRequest, records
from pvb24.decimal_math import D
from pvb24.ids import canonical, digest
from pvb24.types import utc

SCHEMA = "PVB24_MONTHLY_LISTING_BOUNDARY_EVIDENCE_V1"
SECURITY_MASTER_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V7"
UNKNOWN = "UNKNOWN"
EXACT = "CONSISTENT_FIRST_MONTHLY_ACTIVITY_AT_ANNOUNCED_LAUNCH"
POST = "ANNOUNCED_EXACT_POST_LAUNCH_MONTHLY_ACTIVITY_CORROBORATED"
CONTRADICTED = "CONTRADICTED_BY_PRE_EVENT_MONTHLY_ACTIVITY"
SOURCE_FAILURE = "SOURCE_FAILURE"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _load(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError("Explicit V7 Security Master SHA-256 pin required")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned V7 Security Master hash changed")
    report = json.loads(raw)
    if (
        report.get("schema") != SECURITY_MASTER_SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("security_history_complete") is not False
        or report.get("historical_universe_complete") is not False
        or report.get("full_security_rows_emitted") != 0
        or report.get("complete_attestation_emitted") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
    ):
        raise ValueError("Locked PRELIMINARY V7 Security Master audit required")
    unhashed = dict(report)
    recorded = unhashed.pop("audit_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("V7 Security Master audit hash mismatch")
    rows = report.get("unresolved_listings")
    if (
        not isinstance(rows, list)
        or report.get("unresolved_listing_count") != len(rows)
    ):
        raise ValueError("V7 unresolved listing count mismatch")
    return report


def _month(event):
    return utc(datetime.fromisoformat(event)).strftime("%Y-%m")


def _monthly_observation(request, root, result, attempt):
    observation = {
        "symbol": request.symbol,
        "month": request.month,
        "url": request.url,
        "checksum_url": request.url + ".CHECKSUM",
        "attempt": attempt,
        "status": result["status"],
        "archive_revision_sha256": result.get("actual_sha256"),
        "archive_object": result.get("archive_object"),
        "checksum_object": result.get("checksum_object"),
        "row_count": None,
        "active_row_count": None,
        "first_active_interval_start": None,
        "first_active_available_at": None,
        "last_active_interval_start": None,
    }
    if result["status"] != "ACQUIRED":
        return observation, []

    loaded_request, archive, checksum = load_acquired(root, attempt)
    if loaded_request != request:
        raise ValueError("Monthly acquisition request identity changed")
    decoded = list(records(request, archive, checksum))
    active = [row for row in decoded if row.quote_volume > D(0)]
    observation.update(
        row_count=len(decoded),
        active_row_count=len(active),
        first_active_interval_start=(
            active[0].timing.interval_start if active else None
        ),
        first_active_available_at=(active[0].timing.available_at if active else None),
        last_active_interval_start=(
            active[-1].timing.interval_start if active else None
        ),
    )
    return observation, active


def compile_monthly_listing_boundary_evidence(
    security_master_path,
    security_master_sha256,
    output_root,
    *,
    fetch=public_bytes,
):
    security_master = _load(security_master_path, security_master_sha256)
    output_root = Path(output_root)

    requests = {}
    for row in security_master["unresolved_listings"]:
        request = ArchiveRequest(row["symbol"], "klines", _month(row["event_at"]), "1m")
        requests[(request.symbol, request.month)] = request

    observations = {}
    active_rows = {}
    source_failures = []
    for key in sorted(requests):
        request = requests[key]
        result, attempt = acquire(request, output_root / "archive", fetch=fetch)
        observation, active = _monthly_observation(
            request,
            output_root / "archive",
            result,
            attempt,
        )
        observations[key] = observation
        active_rows[key] = active
        if result["status"] in ("HTTP_ERROR", "INVALID_OR_FAILED"):
            source_failures.append(
                {
                    "symbol": request.symbol,
                    "month": request.month,
                    "status": result["status"],
                    "attempt": attempt,
                }
            )

    results = []
    for item in security_master["unresolved_listings"]:
        event = utc(datetime.fromisoformat(item["event_at"]))
        key = (item["symbol"], _month(item["event_at"]))
        observation = observations[key]
        active = active_rows[key]
        before = [row for row in active if row.timing.interval_start < event]
        at_or_after = [row for row in active if row.timing.interval_start >= event]

        if observation["status"] in ("HTTP_ERROR", "INVALID_OR_FAILED"):
            status = SOURCE_FAILURE
        elif observation["status"] != "ACQUIRED" or not active:
            status = UNKNOWN
        elif before:
            status = CONTRADICTED
        elif at_or_after[0].timing.interval_start == event:
            status = EXACT
        else:
            status = POST

        row = {
            "symbol": item["symbol"],
            "event_at": item["event_at"],
            "available_at": item["available_at"],
            "source": item["source"],
            "article_code": item["article_code"],
            "article_source_sha256": item["revision_id"],
            "status": status,
            "monthly_source": observation,
            "pre_event_activity_observed": bool(before),
            "first_pre_event_activity_start": (
                before[0].timing.interval_start if before else None
            ),
            "first_pre_event_activity_available_at": (
                before[0].timing.available_at if before else None
            ),
            "first_activity_at_or_after_event": (
                at_or_after[0].timing.interval_start if at_or_after else None
            ),
            "announcement_exact_time_corroborated": status in (EXACT, POST),
            "archive_proves_exact_launch": False,
            "monthly_archive_publication_time_verified": False,
            "historical_universe_complete": False,
        }
        if status == UNKNOWN:
            row["blocking_obligation"] = "RESOLVE_LISTING_BOUNDARY"
        elif status == CONTRADICTED:
            row["blocking_obligation"] = "RESOLVE_RELISTING_OR_DUPLICATE_START_SEMANTICS"
        elif status == SOURCE_FAILURE:
            row["blocking_obligation"] = "RETRY_MONTHLY_ARCHIVE_SOURCE"
        results.append(row)

    results.sort(key=lambda row: (row["symbol"], row["event_at"]))
    counts = Counter(row["status"] for row in results)
    report = {
        "schema": SCHEMA,
        "quality": "PRELIMINARY",
        "inputs": {
            "security_master_v7_sha256": security_master_sha256,
            "security_master_v7_audit_hash": security_master["audit_hash"],
        },
        "input_unresolved_listing_count": security_master["unresolved_listing_count"],
        "monthly_source_count": len(requests),
        "result_count": len(results),
        "status_counts": dict(sorted(counts.items())),
        "results": results,
        "results_hash": digest(results),
        "source_failure_count": len(source_failures),
        "source_failures": source_failures,
        "prior_missing_daily_archive_used_as_inactivity_proof": False,
        "archive_proves_exact_launch": False,
        "historical_publication_times_verified": False,
        "classification_history_complete": False,
        "rename_relisting_history_complete": False,
        "security_change_stream_complete": False,
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "complete_attestation_emitted": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    if len(results) != security_master["unresolved_listing_count"]:
        raise ValueError("Monthly listing-boundary partition mismatch")
    report["evidence_hash"] = digest(report)
    return json.loads(canonical(report))
