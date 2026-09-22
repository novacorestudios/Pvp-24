from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pvb24.data.announcement_qualification import load_qualification
from pvb24.data.announcement_recovery import recover_retained_lifecycle_facts
from pvb24.data.historical_metadata_evidence import compile_partial_historical_metadata

BASELINE_SCHEMA = "PVB24_DURABLE_REPLAY_BASELINE_V1"
REPORT_SCHEMA = "PVB24_DURABLE_REPLAY_COMPARISON_V1"


def _file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_sha256(value) -> str:
    encoded = (json.dumps(value, indent=2) + "\n").encode()
    return hashlib.sha256(encoded).hexdigest()


def _subset_mismatches(name, expected, actual):
    mismatches = []
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            mismatches.append(
                {
                    "section": name,
                    "field": key,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )
    return mismatches


def _qualification_summary(report, report_sha256):
    return {
        "report_sha256": report_sha256,
        "candidate_count": report["candidate_count"],
        "status_counts": report["status_counts"],
        "source_fetch_complete": report["source_fetch_complete"],
        "results_hash": report["results_hash"],
        "review_requests_hash": report["review_requests_hash"],
        "qualified_review_request_count": len(report["review_requests"]),
    }


def _recovery_summary(report):
    return {
        "output_sha256": _json_sha256(report),
        "recovery_hash": report["recovery_hash"],
        "prior_qualified_count_replayed_identically": report[
            "prior_qualified_count_replayed_identically"
        ],
        "recovered_article_count": report["recovered_article_count"],
        "recovered_fact_count": report["recovered_fact_count"],
        "recovered_symbol_count": report["recovered_symbol_count"],
        "recovered_listing_fact_count": report["recovered_listing_fact_count"],
        "recovered_delisting_fact_count": report["recovered_delisting_fact_count"],
        "retrospective_count": report["retrospective_count"],
        "remaining_semantic_unqualified_count": report[
            "remaining_semantic_unqualified_count"
        ],
    }


def _compilation_summary(report):
    return {
        "output_sha256": _json_sha256(report),
        "evidence_hash": report["evidence_hash"],
        "listing_candidate_count": report["listing_candidate_count"],
        "unresolved_listing_count": report["unresolved_listing_count"],
        "delisting_event_count": report["delisting_event_count"],
        "tick_field_event_count": report["tick_field_event_count"],
        "historical_universe_complete": report["historical_universe_complete"],
    }


def replay_durable_evidence_chain(
    *,
    baseline_path,
    bundle_sha256,
    inventory_root,
    qualification_root,
    lifecycle_root,
    tick_path,
    tick_sha256,
):
    baseline = json.loads(Path(baseline_path).read_text())
    if baseline.get("schema") != BASELINE_SCHEMA:
        raise ValueError("Unexpected durable replay baseline schema")

    mismatches = []
    if baseline.get("durable_bundle_sha256") != bundle_sha256:
        mismatches.append(
            {
                "section": "durable_bundle",
                "field": "sha256",
                "expected": baseline.get("durable_bundle_sha256"),
                "actual": bundle_sha256,
            }
        )

    qualification_expected = baseline["qualification"]
    qualification_sha = qualification_expected["report_sha256"]
    qualification_report = load_qualification(
        qualification_root,
        f"reports/{qualification_sha}.json",
        expected_sha256=qualification_sha,
        inventory_root=inventory_root,
    )
    qualification_actual = _qualification_summary(
        qualification_report,
        _file_sha256(
            Path(qualification_root) / "reports" / f"{qualification_sha}.json"
        ),
    )
    mismatches.extend(
        _subset_mismatches(
            "qualification",
            qualification_expected,
            qualification_actual,
        )
    )

    recovery_report = recover_retained_lifecycle_facts(
        qualification_root,
        qualification_sha,
    )
    recovery_actual = _recovery_summary(recovery_report)
    mismatches.extend(
        _subset_mismatches("recovery", baseline["recovery"], recovery_actual)
    )

    lifecycle_pin = next(
        Path(lifecycle_root, "reports").glob("*.json"),
        None,
    )
    if lifecycle_pin is None:
        raise ValueError("Durable lifecycle report missing")
    lifecycle_sha = lifecycle_pin.stem
    if _file_sha256(lifecycle_pin) != lifecycle_sha:
        raise ValueError("Durable lifecycle report filename/hash mismatch")

    compilation_report = compile_partial_historical_metadata(
        Path(qualification_root) / "reports" / f"{qualification_sha}.json",
        qualification_sha,
        lifecycle_pin,
        lifecycle_sha,
        tick_path,
        tick_sha256,
    )
    compilation_actual = _compilation_summary(compilation_report)
    mismatches.extend(
        _subset_mismatches(
            "compilation",
            baseline["compilation"],
            compilation_actual,
        )
    )

    return {
        "schema": REPORT_SCHEMA,
        "durable_bundle_sha256": bundle_sha256,
        "qualification": qualification_actual,
        "recovery": recovery_actual,
        "compilation": compilation_actual,
        "all_match": not mismatches,
        "mismatches": mismatches,
        "strategy_changed": False,
        "final_test_access": "LOCKED",
        "live_enabled": False,
    }


def write_replay_report(path, report):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    if target.exists() and target.read_bytes() != encoded:
        raise ValueError("Refusing to replace different durable replay comparison")
    target.write_bytes(encoded)
