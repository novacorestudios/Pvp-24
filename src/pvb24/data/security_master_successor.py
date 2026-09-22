"""Build the V6 Security Master obligation audit from requalified lifecycle evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pvb24.ids import canonical, digest

SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V6"
BASE_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V5"
DELTA_SCHEMA = "PVB24_REQUALIFIED_SECURITY_MASTER_DELTA_V1"
CONSISTENT = "CONSISTENT_EVENT_BOUNDARY_ONLY"
UNKNOWN = "UNKNOWN"
CONTRADICTED = "CONTRADICTED_BY_ARCHIVE_ACTIVITY"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _load(path, expected_sha256, label):
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError(f"Explicit {label} SHA-256 pin required")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError(f"Pinned {label} file hash changed")
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
        raise ValueError("Locked PRELIMINARY V5 Security Master audit required")
    unhashed = dict(report)
    recorded = unhashed.pop("audit_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("V5 Security Master audit hash mismatch")
    if report.get("selected_active_transition_count") != len(
        report.get("selected_active_transitions", [])
    ):
        raise ValueError("V5 active transition count mismatch")
    if report.get("selected_inactive_transition_count") != len(
        report.get("selected_inactive_transitions", [])
    ):
        raise ValueError("V5 inactive transition count mismatch")
    return report


def _validate_delta(report, base_sha256, base):
    if (
        report.get("schema") != DELTA_SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("security_history_complete") is not False
        or report.get("historical_universe_complete") is not False
        or report.get("full_security_rows_emitted") != 0
        or report.get("complete_attestation_emitted") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
        or report.get("inputs", {}).get("base_security_master_sha256") != base_sha256
        or report.get("inputs", {}).get("base_security_master_audit_hash") != base["audit_hash"]
    ):
        raise ValueError("Locked PRELIMINARY requalified Security Master delta required")
    unhashed = dict(report)
    recorded = unhashed.pop("delta_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("Requalified Security Master delta hash mismatch")

    collection_counts = (
        ("base_active_corroborated_count", "base_active_corroborated"),
        ("base_active_unknown_boundary_count", "base_active_unknown_boundaries"),
        ("base_active_contradicted_count", "base_active_contradicted"),
        ("exact_listing_without_base_active_count", "exact_listings_without_base_active"),
        ("unknown_listing_without_base_active_count", "unknown_listings_without_base_active"),
        ("base_inactive_corroborated_count", "base_inactive_corroborated"),
        ("exact_delisting_unpaired_count", "exact_delistings_unpaired"),
    )
    for count_field, rows_field in collection_counts:
        rows = report.get(rows_field)
        if not isinstance(rows, list) or report.get(count_field) != len(rows):
            raise ValueError(f"Requalified Security Master delta count mismatch: {rows_field}")
    return report


def _identity(row):
    return row["symbol"], row["effective_from"]


def _unique_map(rows, label):
    result = {}
    for row in rows:
        key = _identity(row)
        if key in result:
            raise ValueError(f"Duplicate {label} identity")
        result[key] = row
    return result


def compile_security_master_successor(
    base_path,
    base_sha256,
    delta_path,
    delta_sha256,
):
    base = _validate_base(_load(base_path, base_sha256, "base Security Master"))
    delta = _validate_delta(
        _load(delta_path, delta_sha256, "requalified Security Master delta"),
        base_sha256,
        base,
    )

    exact = _unique_map(delta["base_active_corroborated"], "exact active delta")
    unknown = _unique_map(delta["base_active_unknown_boundaries"], "unknown active delta")
    contradicted = _unique_map(
        delta["base_active_contradicted"], "contradicted active delta"
    )
    if set(exact) & set(unknown) or set(exact) & set(contradicted) or set(unknown) & set(
        contradicted
    ):
        raise ValueError("Overlapping requalified active boundary states")

    active = []
    rejected = []
    for row in base["selected_active_transitions"]:
        key = _identity(row)
        if key in contradicted:
            rejected.append(
                {
                    "symbol": row["symbol"],
                    "effective_from": row["effective_from"],
                    "prior_transition": row,
                    "requalified_boundary_evidence": contradicted[key],
                    "blocking_obligation": "REJECT_CONTRADICTED_LISTING_START",
                }
            )
            continue

        updated = dict(row)
        if key in exact:
            evidence = exact[key]
            if evidence.get("status") != CONSISTENT:
                raise ValueError("Exact active delta status changed")
            updated["boundary_reconciled"] = True
            updated["requalified_boundary_status"] = CONSISTENT
            updated["requalified_boundary_evidence"] = evidence
            updated["boundary_reconciliation_is_retrospective"] = True
        elif key in unknown:
            evidence = unknown[key]
            if evidence.get("status") != UNKNOWN:
                raise ValueError("Unknown active delta status changed")
            updated["requalified_boundary_status"] = UNKNOWN
            updated["requalified_boundary_evidence"] = evidence
            updated["boundary_reconciliation_is_retrospective"] = True
        active.append(updated)

    if len(rejected) != delta["base_active_contradicted_count"]:
        raise ValueError("Every contradicted selected start must be rejected")

    active.sort(key=lambda row: (row["symbol"], row["effective_from"]))
    reconciled_active_count = sum(row["boundary_reconciled"] for row in active)
    if (
        len(active) != delta["recommended_successor_active_transition_count"]
        or reconciled_active_count
        != delta["recommended_successor_archive_reconciled_active_count"]
        or len(active) - reconciled_active_count
        != delta["recommended_successor_announcement_only_active_count"]
    ):
        raise ValueError("Successor active transition counts disagree with delta")

    exact_inactive = _unique_map(delta["base_inactive_corroborated"], "exact inactive delta")
    inactive = []
    for row in base["selected_inactive_transitions"]:
        updated = dict(row)
        evidence = exact_inactive.get(_identity(row))
        if evidence is not None:
            if evidence.get("status") != CONSISTENT:
                raise ValueError("Exact inactive delta status changed")
            updated["requalified_boundary_status"] = CONSISTENT
            updated["requalified_boundary_evidence"] = evidence
            updated["boundary_reconciliation_is_retrospective"] = True
        inactive.append(updated)

    unknown_rows = [
        *delta["base_active_unknown_boundaries"],
        *delta["unknown_listings_without_base_active"],
    ]
    unresolved = _unique_map(unknown_rows, "unresolved requalified listing")
    unresolved_listings = [
        {
            "symbol": row["symbol"],
            "event_at": row["effective_from"],
            "available_at": row["available_at"],
            "source": row["source"],
            "revision_id": row["article_source_sha256"],
            "article_code": row["article_code"],
            "requalified_boundary_status": UNKNOWN,
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        }
        for row in unresolved.values()
    ]
    unresolved_listings.sort(key=lambda row: (row["symbol"], row["event_at"]))

    obligations = {row["symbol"]: dict(row) for row in base["symbol_obligations"]}
    for row in obligations.values():
        row["obligations"] = list(row["obligations"])
    for row in unresolved_listings:
        item = obligations.get(row["symbol"])
        if item is None:
            raise ValueError("Unresolved listing symbol missing base obligation row")
        item["has_unresolved_listing_boundary"] = True
        item["obligations"] = sorted(
            {*item["obligations"], "RESOLVE_LISTING_BOUNDARY"}
        )
    for row in rejected:
        item = obligations.get(row["symbol"])
        if item is None:
            raise ValueError("Rejected listing symbol missing base obligation row")
        item["has_selected_trading_start"] = False
        item["has_unresolved_listing_boundary"] = True
        item["obligations"] = sorted(
            {
                *item["obligations"],
                "REJECT_CONTRADICTED_LISTING_START",
                "RESOLVE_LISTING_BOUNDARY",
            }
        )

    successor = {
        **base,
        "schema": SCHEMA,
        "inputs": {
            **base["inputs"],
            "base_v5_security_master_sha256": base_sha256,
            "base_v5_security_master_audit_hash": base["audit_hash"],
            "requalified_security_master_delta_sha256": delta_sha256,
            "requalified_security_master_delta_hash": delta["delta_hash"],
            "requalification_hash": delta["inputs"]["requalification_hash"],
            "requalified_lifecycle_reconciliation_hash": delta["inputs"][
                "lifecycle_reconciliation_hash"
            ],
        },
        "selected_active_transition_count": len(active),
        "selected_active_transitions": active,
        "archive_reconciled_active_transition_count": reconciled_active_count,
        "announcement_only_active_transition_count": len(active) - reconciled_active_count,
        "selected_inactive_transition_count": len(inactive),
        "selected_inactive_transitions": inactive,
        "unresolved_listing_count": len(unresolved_listings),
        "unresolved_listings": unresolved_listings,
        "requalified_exact_listing_count": delta["exact_listing_count"],
        "requalified_unknown_listing_count": delta["unknown_listing_count"],
        "requalified_contradicted_listing_count": delta["contradicted_listing_count"],
        "requalified_exact_delisting_count": delta["exact_delisting_count"],
        "requalified_active_newly_reconciled_count": delta[
            "base_active_newly_reconciled_count"
        ],
        "rejected_active_transition_count": len(rejected),
        "rejected_active_transitions": rejected,
        "requalified_exact_delisting_unpaired_count": delta[
            "exact_delisting_unpaired_count"
        ],
        "requalified_exact_delistings_unpaired": delta["exact_delistings_unpaired"],
        "symbol_obligations": [
            obligations[symbol] for symbol in sorted(obligations)
        ],
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
    successor.pop("audit_hash", None)
    successor["audit_hash"] = digest(successor)
    return json.loads(canonical(successor))
