"""Build Security Master V8 from official monthly listing-boundary evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pvb24.ids import canonical, digest

SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V8"
BASE_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V7"
MONTHLY_SCHEMA = "PVB24_MONTHLY_LISTING_BOUNDARY_EVIDENCE_V1"
EXACT = "CONSISTENT_FIRST_MONTHLY_ACTIVITY_AT_ANNOUNCED_LAUNCH"
POST = "ANNOUNCED_EXACT_POST_LAUNCH_MONTHLY_ACTIVITY_CORROBORATED"
CONTRADICTED = "CONTRADICTED_BY_PRE_EVENT_MONTHLY_ACTIVITY"
UNKNOWN = "UNKNOWN"
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
        raise ValueError("Locked PRELIMINARY V7 Security Master audit required")
    unhashed = dict(report)
    recorded = unhashed.pop("audit_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("V7 Security Master audit hash mismatch")
    return report


def _validate_monthly(report, base_sha256, base):
    if (
        report.get("schema") != MONTHLY_SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("security_history_complete") is not False
        or report.get("historical_universe_complete") is not False
        or report.get("full_security_rows_emitted") != 0
        or report.get("complete_attestation_emitted") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
        or report.get("source_failure_count") != 0
        or report.get("source_failures") != []
        or report.get("archive_proves_exact_launch") is not False
        or report.get("prior_missing_daily_archive_used_as_inactivity_proof") is not False
        or report.get("inputs", {}).get("security_master_v7_sha256") != base_sha256
        or report.get("inputs", {}).get("security_master_v7_audit_hash") != base["audit_hash"]
    ):
        raise ValueError("Source-clean locked monthly boundary evidence required")
    rows = report.get("results")
    if (
        not isinstance(rows, list)
        or report.get("result_count") != len(rows)
        or report.get("results_hash") != digest(rows)
        or report.get("input_unresolved_listing_count") != base["unresolved_listing_count"]
    ):
        raise ValueError("Monthly boundary evidence count/hash mismatch")
    unhashed = dict(report)
    recorded = unhashed.pop("evidence_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("Monthly boundary evidence hash mismatch")
    return report


def _identity(row):
    return row["symbol"], row["event_at"]


def compile_security_master_v8(
    base_path,
    base_sha256,
    monthly_path,
    monthly_sha256,
):
    base = _validate_base(_load(base_path, base_sha256, "V7 Security Master"))
    monthly = _validate_monthly(
        _load(monthly_path, monthly_sha256, "monthly boundary evidence"),
        base_sha256,
        base,
    )

    base_unresolved = {_identity(row): row for row in base["unresolved_listings"]}
    monthly_rows = {}
    for row in monthly["results"]:
        key = _identity(row)
        if key in monthly_rows or key not in base_unresolved:
            raise ValueError("Unique V7 unresolved monthly identity required")
        monthly_rows[key] = row
    if set(monthly_rows) != set(base_unresolved):
        raise ValueError("Monthly evidence does not cover every V7 unresolved identity")

    corroborated = {
        key: row for key, row in monthly_rows.items() if row["status"] in (EXACT, POST)
    }
    contradicted = {
        key: row for key, row in monthly_rows.items() if row["status"] == CONTRADICTED
    }
    unknown = {
        key: row for key, row in monthly_rows.items() if row["status"] == UNKNOWN
    }
    if len(corroborated) + len(contradicted) + len(unknown) != len(monthly_rows):
        raise ValueError("Unsupported monthly boundary state")

    active = []
    active_keys = {
        (row["symbol"], row["effective_from"]) for row in base["selected_active_transitions"]
    }
    applied = set()
    for source in base["selected_active_transitions"]:
        row = dict(source)
        key = (row["symbol"], row["effective_from"])
        evidence = corroborated.get(key)
        if evidence is not None:
            row["monthly_listing_boundary_status"] = evidence["status"]
            row["monthly_listing_boundary_evidence"] = evidence
            row["monthly_archive_proves_exact_launch"] = False
            applied.add(key)
        active.append(row)

    corroborated_without_active = [
        corroborated[key] for key in sorted(set(corroborated) - active_keys)
    ]

    unresolved_listings = []
    for key in sorted(unknown):
        unresolved_listings.append(
            {
                **base_unresolved[key],
                "monthly_boundary_status": UNKNOWN,
                "monthly_boundary_evidence": unknown[key],
            }
        )

    remaining_symbols = {row["symbol"] for row in unresolved_listings}
    corroborated_symbols = {row["symbol"] for row in corroborated.values()}
    contradicted_symbols = {row["symbol"] for row in contradicted.values()}
    corroborated_without_active_symbols = {
        row["symbol"] for row in corroborated_without_active
    }

    obligations = []
    for source in base["symbol_obligations"]:
        row = dict(source)
        row["obligations"] = list(row["obligations"])
        symbol = row["symbol"]

        if (
            symbol in corroborated_symbols | contradicted_symbols
            and symbol not in remaining_symbols
        ):
            row["obligations"] = [
                item
                for item in row["obligations"]
                if item != "RESOLVE_LISTING_BOUNDARY"
            ]
            row["has_unresolved_listing_boundary"] = False

        if symbol in remaining_symbols:
            row["has_unresolved_listing_boundary"] = True
            row["obligations"].append("RESOLVE_LISTING_BOUNDARY")

        if symbol in corroborated_without_active_symbols:
            row["obligations"].extend(
                [
                    "MATERIALIZE_REQUALIFIED_ACTIVE_TRANSITION",
                    "RESOLVE_RELISTING_OR_DUPLICATE_START_SEMANTICS",
                ]
            )

        if symbol in contradicted_symbols:
            row["obligations"].extend(
                [
                    "REJECT_CONTRADICTED_LISTING_START",
                    "RESOLVE_RELISTING_OR_DUPLICATE_START_SEMANTICS",
                ]
            )

        row["obligations"] = sorted(set(row["obligations"]))
        obligations.append(row)
    obligations.sort(key=lambda row: row["symbol"])

    report = {
        **base,
        "schema": SCHEMA,
        "inputs": {
            **base["inputs"],
            "base_v7_security_master_sha256": base_sha256,
            "base_v7_security_master_audit_hash": base["audit_hash"],
            "monthly_listing_boundary_sha256": monthly_sha256,
            "monthly_listing_boundary_evidence_hash": monthly["evidence_hash"],
        },
        "selected_active_transitions": active,
        "unresolved_listing_count": len(unresolved_listings),
        "unresolved_listings": unresolved_listings,
        "monthly_boundary_corroborated_count": len(corroborated),
        "monthly_boundary_corroborated_active_count": len(applied),
        "monthly_boundary_corroborated_without_active_count": len(
            corroborated_without_active
        ),
        "monthly_boundary_corroborated": [
            corroborated[key] for key in sorted(corroborated)
        ],
        "monthly_boundary_corroborated_without_active": corroborated_without_active,
        "monthly_boundary_contradicted_count": len(contradicted),
        "monthly_boundary_contradicted": [
            contradicted[key] for key in sorted(contradicted)
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
