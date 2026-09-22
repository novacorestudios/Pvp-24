"""Build Security Master V9 from official ancillary boundary corroboration."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pvb24.ids import canonical, digest

SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V9"
BASE_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V8"
ANCILLARY_SCHEMA = "PVB24_ANCILLARY_LISTING_BOUNDARY_EVIDENCE_V1"
CORROBORATED = "ANNOUNCED_EXACT_ANCILLARY_POST_LAUNCH_CORROBORATED"
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
        raise ValueError("Locked PRELIMINARY V8 Security Master audit required")
    unhashed = dict(report)
    recorded = unhashed.pop("audit_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("V8 Security Master audit hash mismatch")
    return report


def _validate_ancillary(report, base_sha256, base):
    if (
        report.get("schema") != ANCILLARY_SCHEMA
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
        or report.get("ancillary_proves_first_executable_trade") is not False
        or report.get("pre_event_ancillary_used_as_inactivity_proof") is not False
        or report.get("inputs", {}).get("security_master_v8_sha256") != base_sha256
        or report.get("inputs", {}).get("security_master_v8_audit_hash") != base["audit_hash"]
    ):
        raise ValueError("Source-clean locked ancillary boundary evidence required")
    rows = report.get("results")
    if (
        not isinstance(rows, list)
        or report.get("result_count") != len(rows)
        or report.get("results_hash") != digest(rows)
        or report.get("input_unresolved_listing_count") != base["unresolved_listing_count"]
    ):
        raise ValueError("Ancillary boundary evidence count/hash mismatch")
    unhashed = dict(report)
    recorded = unhashed.pop("evidence_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("Ancillary boundary evidence hash mismatch")
    return report


def _identity(row):
    return row["symbol"], row["event_at"]


def compile_security_master_v9(
    base_path,
    base_sha256,
    ancillary_path,
    ancillary_sha256,
):
    base = _validate_base(_load(base_path, base_sha256, "V8 Security Master"))
    ancillary = _validate_ancillary(
        _load(ancillary_path, ancillary_sha256, "ancillary boundary evidence"),
        base_sha256,
        base,
    )

    base_unresolved = {_identity(row): row for row in base["unresolved_listings"]}
    evidence = {}
    for row in ancillary["results"]:
        key = _identity(row)
        if key in evidence or key not in base_unresolved:
            raise ValueError("Unique V8 unresolved ancillary identity required")
        if row["status"] not in (CORROBORATED, UNKNOWN):
            raise ValueError("Unsupported ancillary boundary state")
        evidence[key] = row
    if set(evidence) != set(base_unresolved):
        raise ValueError("Ancillary evidence does not cover every V8 unresolved identity")

    corroborated = {
        key: row for key, row in evidence.items() if row["status"] == CORROBORATED
    }
    unknown = {key: row for key, row in evidence.items() if row["status"] == UNKNOWN}

    active_keys = {
        (row["symbol"], row["effective_from"]) for row in base["selected_active_transitions"]
    }
    applied = set()
    active = []
    for source in base["selected_active_transitions"]:
        row = dict(source)
        key = (row["symbol"], row["effective_from"])
        item = corroborated.get(key)
        if item is not None:
            row["ancillary_listing_boundary_status"] = item["status"]
            row["ancillary_listing_boundary_evidence"] = item
            row["ancillary_proves_first_executable_trade"] = False
            applied.add(key)
        active.append(row)

    corroborated_without_active = [
        corroborated[key] for key in sorted(set(corroborated) - active_keys)
    ]

    unresolved_listings = [
        {
            **base_unresolved[key],
            "ancillary_boundary_status": UNKNOWN,
            "ancillary_boundary_evidence": unknown[key],
        }
        for key in sorted(unknown)
    ]
    remaining_symbols = {row["symbol"] for row in unresolved_listings}
    corroborated_symbols = {row["symbol"] for row in corroborated.values()}
    without_active_symbols = {row["symbol"] for row in corroborated_without_active}

    obligations = []
    for source in base["symbol_obligations"]:
        row = dict(source)
        row["obligations"] = list(row["obligations"])
        symbol = row["symbol"]

        if symbol in corroborated_symbols and symbol not in remaining_symbols:
            row["obligations"] = [
                item for item in row["obligations"] if item != "RESOLVE_LISTING_BOUNDARY"
            ]
            row["has_unresolved_listing_boundary"] = False
            row["ancillary_boundary_corroborated"] = True
        if symbol in remaining_symbols:
            row["has_unresolved_listing_boundary"] = True
            row["obligations"].append("RESOLVE_LISTING_BOUNDARY")
        if symbol in without_active_symbols:
            row["obligations"].extend(
                [
                    "MATERIALIZE_REQUALIFIED_ACTIVE_TRANSITION",
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
            "base_v8_security_master_sha256": base_sha256,
            "base_v8_security_master_audit_hash": base["audit_hash"],
            "ancillary_listing_boundary_sha256": ancillary_sha256,
            "ancillary_listing_boundary_evidence_hash": ancillary["evidence_hash"],
        },
        "selected_active_transitions": active,
        "unresolved_listing_count": len(unresolved_listings),
        "unresolved_listings": unresolved_listings,
        "ancillary_boundary_corroborated_count": len(corroborated),
        "ancillary_boundary_corroborated_active_count": len(applied),
        "ancillary_boundary_corroborated_without_active_count": len(
            corroborated_without_active
        ),
        "ancillary_boundary_corroborated": [
            corroborated[key] for key in sorted(corroborated)
        ],
        "ancillary_boundary_corroborated_without_active": corroborated_without_active,
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
