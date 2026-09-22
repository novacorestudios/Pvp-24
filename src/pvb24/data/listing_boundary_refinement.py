"""Refine unresolved listing boundaries without overstating archive certainty.

An official announcement may provide an exact launch timestamp while the first recorded trade
occurs minutes later. This module only removes the boundary obligation when the checksum-verified
event-day archive contains no row before the announced launch and later contains activity.
A missing prior-day archive remains UNKNOWN and is never used as proof of inactivity.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from pvb24.ids import canonical, digest
from pvb24.types import utc

SCHEMA = "PVB24_LISTING_BOUNDARY_REFINEMENT_V1"
SECURITY_MASTER_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V6"
LIFECYCLE_SCHEMA = "PVB24_REQUALIFIED_LIFECYCLE_ARCHIVE_ACTIVITY_V1"
UNKNOWN = "UNKNOWN"
RESOLVED = "ANNOUNCED_EXACT_POST_LAUNCH_ACTIVITY_CORROBORATED"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _load(path, expected_sha256, label):
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError(f"Explicit {label} SHA-256 pin required")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError(f"Pinned {label} hash changed")
    return json.loads(raw)


def _validate_security_master(report):
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
        raise ValueError("Locked PRELIMINARY V6 Security Master audit required")
    unhashed = dict(report)
    recorded = unhashed.pop("audit_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("V6 Security Master audit hash mismatch")
    unresolved = report.get("unresolved_listings")
    if (
        not isinstance(unresolved, list)
        or report.get("unresolved_listing_count") != len(unresolved)
    ):
        raise ValueError("V6 unresolved listing count mismatch")
    return report


def _validate_lifecycle(report, security_master):
    if (
        report.get("schema") != LIFECYCLE_SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("source_failures") != []
        or report.get("historical_universe_complete") is not False
        or report.get("security_master_complete") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
        or report.get("reconciliation_hash")
        != security_master["inputs"]["requalified_lifecycle_reconciliation_hash"]
    ):
        raise ValueError("Source-clean locked requalified lifecycle evidence required")
    rows = report.get("reconciliations")
    if (
        not isinstance(rows, list)
        or report.get("reconciliation_count") != len(rows)
        or report.get("reconciliation_hash") != digest(rows)
    ):
        raise ValueError("Lifecycle reconciliation count/hash mismatch")
    counts = Counter(row.get("status") for row in rows)
    if report.get("status_counts") != dict(sorted(counts.items())):
        raise ValueError("Lifecycle reconciliation status counts mismatch")
    return report


def _identity(row):
    return row["symbol"], row["event_at"]


def _post_launch_corroboration(row):
    if row.get("kind") != "LISTING" or row.get("status") != UNKNOWN:
        return False
    if row.get("contradictions") != []:
        return False

    event_day = row.get("event_day")
    boundary_day = row.get("boundary_day")
    if not isinstance(event_day, dict) or not isinstance(boundary_day, dict):
        raise ValueError("Lifecycle observations required")

    if (
        event_day.get("status") != "ACQUIRED"
        or type(event_day.get("active_rows")) is not int
        or event_day["active_rows"] <= 0
        or event_day.get("missing_object_means_inactive") is not False
        or boundary_day.get("status") != "UNAVAILABLE"
        or boundary_day.get("missing_object_means_inactive") is not False
    ):
        return False

    first_interval = event_day.get("first_interval_start")
    first_active = event_day.get("first_active_interval_start")
    if not isinstance(first_interval, str) or not isinstance(first_active, str):
        return False

    event = utc(datetime.fromisoformat(row["event_at"]))
    if utc(datetime.fromisoformat(first_interval)) < event:
        return False
    if utc(datetime.fromisoformat(first_active)) <= event:
        return False
    if event_day.get("internal_gaps") != []:
        return False

    notes = set(row.get("notes", []))
    return {
        "EVENT_DAY_ACTIVITY_STARTS_AFTER_ANNOUNCED_LAUNCH",
        "BOUNDARY_ARCHIVE_OBJECT_MISSING_IS_UNKNOWN",
    }.issubset(notes)


def compile_listing_boundary_refinement(
    security_master_path,
    security_master_sha256,
    lifecycle_path,
    lifecycle_sha256,
):
    security_master = _validate_security_master(
        _load(security_master_path, security_master_sha256, "V6 Security Master")
    )
    lifecycle = _validate_lifecycle(
        _load(lifecycle_path, lifecycle_sha256, "requalified lifecycle"),
        security_master,
    )

    lifecycle_rows = {}
    for row in lifecycle["reconciliations"]:
        if row.get("kind") != "LISTING":
            continue
        key = _identity(row)
        if key in lifecycle_rows:
            raise ValueError("Duplicate lifecycle listing identity")
        lifecycle_rows[key] = row

    resolved = []
    remaining = []
    for item in security_master["unresolved_listings"]:
        key = _identity(item)
        row = lifecycle_rows.get(key)
        if row is None:
            raise ValueError("Unresolved Security Master listing lacks lifecycle evidence")
        if (
            row.get("article_code") != item.get("article_code")
            or row.get("article_source_sha256") != item.get("revision_id")
            or row.get("status") != UNKNOWN
        ):
            raise ValueError("Unresolved listing/lifecycle lineage mismatch")

        event_day = row["event_day"]
        evidence = {
            "symbol": item["symbol"],
            "event_at": item["event_at"],
            "available_at": item["available_at"],
            "source": item["source"],
            "article_code": item["article_code"],
            "article_source_sha256": item["revision_id"],
            "event_day_status": event_day["status"],
            "event_day_attempt": event_day["attempt"],
            "event_day_url": event_day["url"],
            "first_interval_start": event_day.get("first_interval_start"),
            "first_active_interval_start": event_day.get("first_active_interval_start"),
            "boundary_day_status": row["boundary_day"]["status"],
            "prior_day_absence_used_as_proof": False,
        }
        if _post_launch_corroboration(row):
            resolved.append(
                {
                    **evidence,
                    "resolution": RESOLVED,
                    "exact_time_source": "OFFICIAL_RETAINED_ANNOUNCEMENT",
                    "archive_claim": "NON_CONTRADICTORY_POST_LAUNCH_ACTIVITY_ONLY",
                    "archive_proves_exact_launch": False,
                }
            )
        else:
            remaining.append(
                {
                    **evidence,
                    "resolution": UNKNOWN,
                    "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
                }
            )

    resolved.sort(key=lambda row: (row["symbol"], row["event_at"]))
    remaining.sort(key=lambda row: (row["symbol"], row["event_at"]))
    report = {
        "schema": SCHEMA,
        "quality": "PRELIMINARY",
        "inputs": {
            "security_master_v6_sha256": security_master_sha256,
            "security_master_v6_audit_hash": security_master["audit_hash"],
            "lifecycle_sha256": lifecycle_sha256,
            "lifecycle_reconciliation_hash": lifecycle["reconciliation_hash"],
        },
        "input_unresolved_listing_count": security_master["unresolved_listing_count"],
        "resolved_announcement_boundary_count": len(resolved),
        "resolved_announcement_boundaries": resolved,
        "remaining_unresolved_listing_count": len(remaining),
        "remaining_unresolved_listings": remaining,
        "prior_day_absence_used_as_proof": False,
        "archive_proves_exact_launch": False,
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
    if len(resolved) + len(remaining) != security_master["unresolved_listing_count"]:
        raise ValueError("Listing boundary refinement partition mismatch")
    report["refinement_hash"] = digest(report)
    return json.loads(canonical(report))
