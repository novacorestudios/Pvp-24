"""Build Security Master V7 from conservative listing-boundary refinement."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pvb24.ids import canonical, digest

SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V7"
BASE_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V6"
REFINEMENT_SCHEMA = "PVB24_LISTING_BOUNDARY_REFINEMENT_V1"
RESOLVED = "ANNOUNCED_EXACT_POST_LAUNCH_ACTIVITY_CORROBORATED"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _load(path, expected_sha256, label):
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError(f"Explicit {label} SHA-256 pin required")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError(f"Pinned {label} hash changed")
    return json.loads(raw)


def _validate_base(report):
    if (
        report.get("schema") != BASE_SCHEMA
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
    return report


def _validate_refinement(report, base_sha256, base):
    if (
        report.get("schema") != REFINEMENT_SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("historical_universe_complete") is not False
        or report.get("security_history_complete") is not False
        or report.get("full_security_rows_emitted") != 0
        or report.get("complete_attestation_emitted") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
        or report.get("prior_day_absence_used_as_proof") is not False
        or report.get("archive_proves_exact_launch") is not False
        or report.get("inputs", {}).get("security_master_v6_sha256") != base_sha256
        or report.get("inputs", {}).get("security_master_v6_audit_hash") != base["audit_hash"]
    ):
        raise ValueError("Locked PRELIMINARY listing-boundary refinement required")
    unhashed = dict(report)
    recorded = unhashed.pop("refinement_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("Listing-boundary refinement hash mismatch")
    resolved = report.get("resolved_announcement_boundaries")
    remaining = report.get("remaining_unresolved_listings")
    if (
        not isinstance(resolved, list)
        or report.get("resolved_announcement_boundary_count") != len(resolved)
        or not isinstance(remaining, list)
        or report.get("remaining_unresolved_listing_count") != len(remaining)
        or len(resolved) + len(remaining) != report.get("input_unresolved_listing_count")
        or report.get("input_unresolved_listing_count") != base["unresolved_listing_count"]
    ):
        raise ValueError("Listing-boundary refinement counts changed")
    return report


def _identity(row):
    return row["symbol"], row["event_at"]


def compile_security_master_v7(
    base_path,
    base_sha256,
    refinement_path,
    refinement_sha256,
):
    base = _validate_base(_load(base_path, base_sha256, "V6 Security Master"))
    refinement = _validate_refinement(
        _load(refinement_path, refinement_sha256, "listing-boundary refinement"),
        base_sha256,
        base,
    )

    resolved = {}
    for row in refinement["resolved_announcement_boundaries"]:
        key = _identity(row)
        if key in resolved or row.get("resolution") != RESOLVED:
            raise ValueError("Unique resolved listing-boundary identity required")
        if (
            row.get("prior_day_absence_used_as_proof") is not False
            or row.get("archive_proves_exact_launch") is not False
        ):
            raise ValueError("Resolved boundary overstates archive certainty")
        resolved[key] = row

    remaining = {}
    for row in refinement["remaining_unresolved_listings"]:
        key = _identity(row)
        if key in remaining or row.get("resolution") != "UNKNOWN":
            raise ValueError("Unique remaining listing-boundary identity required")
        remaining[key] = row

    base_unresolved = {_identity(row): row for row in base["unresolved_listings"]}
    if set(resolved) | set(remaining) != set(base_unresolved):
        raise ValueError("V7 refinement identities differ from V6 unresolved listings")
    if set(resolved) & set(remaining):
        raise ValueError("Overlapping V7 listing-boundary states")

    active = []
    applied = set()
    for row in base["selected_active_transitions"]:
        updated = dict(row)
        key = (row["symbol"], row["effective_from"])
        evidence = resolved.get(key)
        if evidence is not None:
            updated["listing_boundary_resolution"] = RESOLVED
            updated["listing_boundary_resolution_evidence"] = evidence
            updated["listing_boundary_exact_time_source"] = (
                "OFFICIAL_RETAINED_ANNOUNCEMENT"
            )
            updated["archive_proves_exact_launch"] = False
            applied.add(key)
        active.append(updated)
    if applied != set(resolved):
        raise ValueError("Every resolved listing boundary must map to one active transition")

    unresolved_listings = []
    for key in sorted(remaining):
        prior = base_unresolved[key]
        evidence = remaining[key]
        unresolved_listings.append(
            {
                **prior,
                "boundary_refinement_status": "UNKNOWN",
                "boundary_refinement_evidence": evidence,
            }
        )

    remaining_symbols = {row["symbol"] for row in unresolved_listings}
    resolved_symbols = {row["symbol"] for row in refinement["resolved_announcement_boundaries"]}
    obligations = []
    for source in base["symbol_obligations"]:
        row = dict(source)
        row["obligations"] = list(row["obligations"])
        symbol = row["symbol"]
        if symbol in resolved_symbols and symbol not in remaining_symbols:
            row["obligations"] = [
                item for item in row["obligations"] if item != "RESOLVE_LISTING_BOUNDARY"
            ]
            row["has_unresolved_listing_boundary"] = False
            row["announcement_boundary_corroborated"] = True
        if symbol in remaining_symbols:
            row["has_unresolved_listing_boundary"] = True
            if "RESOLVE_LISTING_BOUNDARY" not in row["obligations"]:
                row["obligations"].append("RESOLVE_LISTING_BOUNDARY")
        row["obligations"] = sorted(set(row["obligations"]))
        obligations.append(row)
    obligations.sort(key=lambda row: row["symbol"])

    report = {
        **base,
        "schema": SCHEMA,
        "inputs": {
            **base["inputs"],
            "base_v6_security_master_sha256": base_sha256,
            "base_v6_security_master_audit_hash": base["audit_hash"],
            "listing_boundary_refinement_sha256": refinement_sha256,
            "listing_boundary_refinement_hash": refinement["refinement_hash"],
        },
        "selected_active_transitions": active,
        "unresolved_listing_count": len(unresolved_listings),
        "unresolved_listings": unresolved_listings,
        "announcement_boundary_corroborated_count": len(resolved),
        "announcement_boundary_corroborated": refinement[
            "resolved_announcement_boundaries"
        ],
        "symbol_obligations": obligations,
        "classification_history_complete": False,
        "rename_relisting_history_complete": False,
        "source_window_coverage_complete": False,
        "title_filter_recall_verified": False,
        "historical_publication_times_verified": False,
        "security_change_stream_complete": False,
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "complete_attestation_emitted": False,
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    report.pop("audit_hash", None)
    report["audit_hash"] = digest(report)
    return json.loads(canonical(report))
