"""Versioned requalification of retained announcement evidence.

This module never fetches mutable current announcement bodies. It replays the exact
content-addressed source bytes preserved by M11T, keeps the original qualification
report immutable, and emits a separate PRELIMINARY successor report with explicit
lineage. Previously-qualified semantics are not allowed to drift.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from pvb24.data.announcement_qualification import (
    QUALIFIED,
    SEMANTIC_UNQUALIFIED,
    load_inventory,
    qualify_candidate,
    retained_source_fetch,
    validate_qualification_summary,
)
from pvb24.data.announcement_qualification import (
    SCHEMA as QUALIFICATION_SCHEMA,
)
from pvb24.data.announcements import strict_json
from pvb24.ids import canonical, digest

SCHEMA = "PVB24_RETAINED_ANNOUNCEMENT_REQUALIFICATION_V1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _source_report(root: Path, expected_sha256: str) -> dict:
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError("Explicit source qualification SHA-256 required")
    path = root / "reports" / f"{expected_sha256}.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned source qualification report hash changed")
    report = strict_json(raw)
    validate_qualification_summary(report)
    if (
        report.get("schema") != QUALIFICATION_SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("source_fetch_complete") is not True
        or report.get("historical_universe_complete") is not False
        or report.get("security_master_complete") is not False
        or report.get("lifecycle_complete") is not False
        or report.get("performance_run") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
    ):
        raise ValueError("Locked PRELIMINARY retained qualification report required")
    statuses = {row.get("status") for row in report["results"]}
    if not statuses.issubset({QUALIFIED, SEMANTIC_UNQUALIFIED}):
        raise ValueError("Requalification requires fully retained semantic source outcomes")
    if any(row.get("source_retained") is not True for row in report["results"]):
        raise ValueError("Every requalification source must be retained")
    return report


def _without_transport_fields(row: dict) -> dict:
    return {
        key: value for key, value in row.items() if key not in ("retrieved_at", "source_object")
    }


def _change_record(recorded: dict, replayed: dict) -> dict:
    return {
        "code": recorded["code"],
        "kind": recorded["kind"],
        "source_sha256": recorded["source_sha256"],
        "old_status": recorded["status"],
        "new_status": replayed["status"],
        "old_reason": recorded.get("reason"),
        "new_reason": replayed.get("reason"),
        "old_facts_hash": recorded.get("facts_hash"),
        "new_facts_hash": replayed.get("facts_hash"),
    }



def validate_requalification_summary(report: dict) -> dict:
    """Recompute successor qualification counts, hashes, lineage, and locked readiness flags."""

    if (
        report.get("schema") != SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("qualification_replayed_from_retained_bytes") is not True
        or report.get("requested_window_complete") is not False
        or report.get("upper_boundary_coverage_proven") is not False
        or report.get("historical_publication_times_verified") is not False
        or report.get("historical_universe_complete") is not False
        or report.get("security_master_complete") is not False
        or report.get("lifecycle_complete") is not False
        or report.get("performance_run") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
    ):
        raise ValueError("Locked PRELIMINARY retained requalification report required")

    for field in (
        "durable_bundle_sha256",
        "source_qualification_report_sha256",
        "source_results_hash",
        "source_review_requests_hash",
        "inventory_report_sha256",
    ):
        if not isinstance(report.get(field), str) or not _SHA256.fullmatch(report[field]):
            raise ValueError(f"Valid requalification lineage hash required: {field}")

    results = report.get("results")
    if (
        not isinstance(results, list)
        or report.get("candidate_count") != len(results)
        or report.get("source_bytes_reverified_count") != len(results)
        or report.get("results_hash") != digest(results)
    ):
        raise ValueError("Requalification result count/hash mismatch")

    codes = set()
    counts = Counter()
    for row in results:
        code = row.get("code")
        status = row.get("status")
        source_hash = row.get("source_sha256")
        if not isinstance(code, str) or not code or code in codes:
            raise ValueError("Unique requalification article code required")
        codes.add(code)
        if status not in (QUALIFIED, SEMANTIC_UNQUALIFIED):
            raise ValueError("Unsupported requalification result status")
        counts[status] += 1
        if (
            row.get("source_retained") is not True
            or not isinstance(source_hash, str)
            or not _SHA256.fullmatch(source_hash)
            or row.get("source_object") != f"objects/{source_hash}.json"
        ):
            raise ValueError("Content-addressed retained requalification source required")

    if report.get("status_counts") != dict(sorted(counts.items())):
        raise ValueError("Requalification status counts mismatch")

    requests = [row["review_request"] for row in results if row["status"] == QUALIFIED]
    if (
        report.get("review_requests") != requests
        or report.get("review_requests_hash") != digest(requests)
    ):
        raise ValueError("Requalification review request summary mismatch")

    changes = report.get("changes")
    if (
        not isinstance(changes, list)
        or report.get("changed_result_count") != len(changes)
        or report.get("change_hash") != digest(changes)
    ):
        raise ValueError("Requalification change summary mismatch")
    promoted = [
        row for row in changes if row.get("old_status") != QUALIFIED and row.get("new_status") == QUALIFIED
    ]
    reason_only = [
        row
        for row in changes
        if row.get("old_status") == row.get("new_status")
        and row.get("old_reason") != row.get("new_reason")
    ]
    if report.get("status_promoted_to_qualified_count") != len(promoted):
        raise ValueError("Requalification promotion count mismatch")
    if report.get("reason_only_change_count") != len(reason_only):
        raise ValueError("Requalification reason-only count mismatch")

    unhashed = dict(report)
    requalification_hash = unhashed.pop("requalification_hash", None)
    if requalification_hash != digest(unhashed):
        raise ValueError("Requalification report hash mismatch")
    return report

def requalify_retained_qualification(
    *,
    inventory_root,
    qualification_root,
    source_report_sha256: str,
    durable_bundle_sha256: str,
) -> dict:
    """Replay exact retained bytes into a separate, lineage-bound qualification report."""

    if not isinstance(durable_bundle_sha256, str) or not _SHA256.fullmatch(durable_bundle_sha256):
        raise ValueError("Explicit durable bundle SHA-256 required")

    qualification_root = Path(qualification_root)
    source = _source_report(qualification_root, source_report_sha256)
    inventory = load_inventory(
        inventory_root,
        source["inventory_report"],
        expected_sha256=source["inventory_report_sha256"],
    )
    if inventory.get("inventory_hash") != source.get("inventory_hash"):
        raise ValueError("Retained qualification/inventory identities disagree")

    candidates = {row["code"]: row for row in inventory["candidates"]}
    recorded = {row["code"]: row for row in source["results"]}
    if (
        len(candidates) != len(inventory["candidates"])
        or len(recorded) != len(source["results"])
        or set(candidates) != set(recorded)
    ):
        raise ValueError("Requalification candidate inventory changed")

    fetch = retained_source_fetch(qualification_root, source_report_sha256)
    results = []
    changes = []
    source_bytes_reverified = 0

    for candidate in inventory["candidates"]:
        prior = recorded[candidate["code"]]
        raw = fetch(candidate["article_url"])
        replayed = qualify_candidate(candidate, raw)
        source_bytes_reverified += 1

        if replayed.get("source_retained") is not True:
            raise ValueError("Retained replay unexpectedly lost source qualification")
        if replayed.get("source_sha256") != prior.get("source_sha256"):
            raise ValueError("Retained replay source revision changed")

        replayed = {
            **replayed,
            "source_object": f"objects/{replayed['source_sha256']}.json",
        }
        prior_semantics = _without_transport_fields(prior)
        replayed_semantics = _without_transport_fields(replayed)

        if prior.get("status") == QUALIFIED:
            if canonical(prior_semantics) != canonical(replayed_semantics):
                raise ValueError("Previously qualified announcement semantics changed")
        elif canonical(prior_semantics) != canonical(replayed_semantics):
            changes.append(_change_record(prior, replayed))

        results.append(replayed)

    counts = Counter(row["status"] for row in results)
    requests = [row["review_request"] for row in results if row["status"] == QUALIFIED]
    promoted = [
        row for row in changes if row["old_status"] != QUALIFIED and row["new_status"] == QUALIFIED
    ]
    reason_only = [
        row
        for row in changes
        if row["old_status"] == row["new_status"] and row["old_reason"] != row["new_reason"]
    ]

    report = {
        "schema": SCHEMA,
        "quality": "PRELIMINARY",
        "durable_bundle_sha256": durable_bundle_sha256,
        "source_qualification_report_sha256": source_report_sha256,
        "source_results_hash": source["results_hash"],
        "source_review_requests_hash": source["review_requests_hash"],
        "inventory_report": source["inventory_report"],
        "inventory_report_sha256": source["inventory_report_sha256"],
        "inventory_hash": source["inventory_hash"],
        "window_start": source.get("window_start"),
        "window_end": source.get("window_end"),
        "candidate_count": len(results),
        "source_bytes_reverified_count": source_bytes_reverified,
        "prior_status_counts": source["status_counts"],
        "status_counts": dict(sorted(counts.items())),
        "results": results,
        "results_hash": digest(results),
        "review_requests": requests,
        "review_requests_hash": digest(requests),
        "changed_result_count": len(changes),
        "status_promoted_to_qualified_count": len(promoted),
        "reason_only_change_count": len(reason_only),
        "changes": changes,
        "change_hash": digest(changes),
        "qualification_replayed_from_retained_bytes": True,
        "requested_window_complete": False,
        "upper_boundary_coverage_proven": False,
        "historical_publication_times_verified": False,
        "historical_universe_complete": False,
        "security_master_complete": False,
        "lifecycle_complete": False,
        "performance_run": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    report["requalification_hash"] = digest(report)
    normalized = json.loads(canonical(report))
    validate_requalification_summary(normalized)
    return normalized
