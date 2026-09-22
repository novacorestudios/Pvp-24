"""Corroborate unresolved listing announcements with official ancillary monthly archives.

MARK1M and funding archives can corroborate that a contract existed after an announced launch,
but they do not prove the first executable trade or prove inactivity before the launch. This
module therefore never treats missing or pre-event ancillary rows as trading-boundary evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from pvb24.data.acquisition import acquire, load_acquired, public_bytes
from pvb24.data.archive import ArchiveRequest, records
from pvb24.ids import canonical, digest
from pvb24.types import utc

SCHEMA = "PVB24_ANCILLARY_LISTING_BOUNDARY_EVIDENCE_V1"
SECURITY_MASTER_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V8"
CORROBORATED = "ANNOUNCED_EXACT_ANCILLARY_POST_LAUNCH_CORROBORATED"
UNKNOWN = "UNKNOWN"
SOURCE_FAILURE = "SOURCE_FAILURE"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _load(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError("Explicit V8 Security Master SHA-256 pin required")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned V8 Security Master hash changed")
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
        raise ValueError("Locked PRELIMINARY V8 Security Master audit required")
    unhashed = dict(report)
    recorded = unhashed.pop("audit_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("V8 Security Master audit hash mismatch")
    unresolved = report.get("unresolved_listings")
    if not isinstance(unresolved, list) or report.get("unresolved_listing_count") != len(
        unresolved
    ):
        raise ValueError("V8 unresolved listing count mismatch")
    return report


def _month(event_at):
    return utc(datetime.fromisoformat(event_at)).strftime("%Y-%m")


def _request_key(request):
    return request.symbol, request.month, request.kind, request.interval


def _acquire_sources(security_master, output_root, fetch):
    requests = {}
    for row in security_master["unresolved_listings"]:
        month = _month(row["event_at"])
        for request in (
            ArchiveRequest(row["symbol"], "markPriceKlines", month, "1m"),
            ArchiveRequest(row["symbol"], "fundingRate", month),
        ):
            requests[_request_key(request)] = request

    sources = {}
    failures = []
    root = Path(output_root) / "archive"
    for key in sorted(requests):
        request = requests[key]
        result, attempt = acquire(request, root, fetch=fetch)
        source = {
            "symbol": request.symbol,
            "month": request.month,
            "kind": request.kind,
            "interval": request.interval,
            "url": request.url,
            "checksum_url": request.url + ".CHECKSUM",
            "attempt": attempt,
            "status": result["status"],
            "archive_revision_sha256": result.get("actual_sha256"),
            "archive_object": result.get("archive_object"),
            "checksum_object": result.get("checksum_object"),
        }
        decoded = []
        if result["status"] == "ACQUIRED":
            loaded_request, archive, checksum = load_acquired(root, attempt)
            if loaded_request != request:
                raise ValueError("Ancillary acquisition request identity changed")
            decoded = list(records(request, archive, checksum))
            source["row_count"] = len(decoded)
        else:
            source["row_count"] = None
        sources[key] = (source, decoded)
        if result["status"] in ("HTTP_ERROR", "INVALID_OR_FAILED"):
            failures.append(
                {
                    "symbol": request.symbol,
                    "month": request.month,
                    "kind": request.kind,
                    "status": result["status"],
                    "attempt": attempt,
                }
            )
    return sources, failures


def _relative_summary(source, decoded, event):
    before_count = 0
    first_after = None
    first_after_available = None
    for row in decoded:
        if source["kind"] == "fundingRate":
            timestamp = row.calculated_at
            available_at = row.available_at
        else:
            timestamp = row.timing.interval_start
            available_at = row.timing.available_at
        if timestamp < event:
            before_count += 1
        elif first_after is None:
            first_after = timestamp
            first_after_available = available_at
    return {
        **source,
        "pre_event_row_count": before_count,
        "first_at_or_after_event": first_after,
        "first_at_or_after_event_available_at": first_after_available,
        "pre_event_rows_used_as_trade_evidence": False,
        "archive_proves_exact_launch": False,
    }


def compile_ancillary_listing_boundary_evidence(
    security_master_path,
    security_master_sha256,
    output_root,
    *,
    fetch=public_bytes,
):
    security_master = _load(security_master_path, security_master_sha256)
    sources, failures = _acquire_sources(security_master, output_root, fetch)

    results = []
    for item in security_master["unresolved_listings"]:
        event = utc(datetime.fromisoformat(item["event_at"]))
        month = _month(item["event_at"])
        summaries = []
        for kind, interval in (("markPriceKlines", "1m"), ("fundingRate", None)):
            source, decoded = sources[(item["symbol"], month, kind, interval)]
            summaries.append(_relative_summary(source, decoded, event))

        failed = any(row["status"] in ("HTTP_ERROR", "INVALID_OR_FAILED") for row in summaries)
        supporting = [
            row
            for row in summaries
            if row["status"] == "ACQUIRED" and row["first_at_or_after_event"] is not None
        ]
        if failed:
            status = SOURCE_FAILURE
        elif supporting:
            status = CORROBORATED
        else:
            status = UNKNOWN

        result = {
            "symbol": item["symbol"],
            "event_at": item["event_at"],
            "available_at": item["available_at"],
            "source": item["source"],
            "article_code": item["article_code"],
            "article_source_sha256": item["revision_id"],
            "status": status,
            "ancillary_sources": summaries,
            "supporting_source_count": len(supporting),
            "supporting_source_kinds": sorted(row["kind"] for row in supporting),
            "announcement_exact_time_corroborated": status == CORROBORATED,
            "ancillary_proves_first_executable_trade": False,
            "pre_event_ancillary_used_as_inactivity_proof": False,
            "historical_publication_times_verified": False,
            "historical_universe_complete": False,
        }
        if status == UNKNOWN:
            result["blocking_obligation"] = "RESOLVE_LISTING_BOUNDARY"
        elif status == SOURCE_FAILURE:
            result["blocking_obligation"] = "RETRY_ANCILLARY_ARCHIVE_SOURCE"
        results.append(result)

    results.sort(key=lambda row: (row["symbol"], row["event_at"]))
    counts = Counter(row["status"] for row in results)
    report = {
        "schema": SCHEMA,
        "quality": "PRELIMINARY",
        "inputs": {
            "security_master_v8_sha256": security_master_sha256,
            "security_master_v8_audit_hash": security_master["audit_hash"],
        },
        "input_unresolved_listing_count": security_master["unresolved_listing_count"],
        "ancillary_request_count": len(sources),
        "result_count": len(results),
        "status_counts": dict(sorted(counts.items())),
        "results": results,
        "results_hash": digest(results),
        "source_failure_count": len(failures),
        "source_failures": failures,
        "ancillary_proves_first_executable_trade": False,
        "pre_event_ancillary_used_as_inactivity_proof": False,
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
        raise ValueError("Ancillary listing-boundary partition mismatch")
    report["evidence_hash"] = digest(report)
    return json.loads(canonical(report))
