from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from pvb24.data.announcement_qualification import (
    QUALIFIED,
    load_inventory,
    qualify_candidate,
)
from pvb24.data.announcement_recovery import recover_retained_lifecycle_facts
from pvb24.data.historical_metadata_evidence import compile_partial_historical_metadata
from pvb24.ids import canonical, digest

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


def _jsonable(value):
    return json.loads(canonical(value))


def _qualification_replay(root, report_sha256, inventory_root):
    root = Path(root)
    report_path = root / "reports" / f"{report_sha256}.json"
    raw_report = report_path.read_bytes()
    if hashlib.sha256(raw_report).hexdigest() != report_sha256:
        raise ValueError("Pinned qualification report hash changed")
    report = json.loads(raw_report)
    inventory = load_inventory(
        inventory_root,
        report["inventory_report"],
        expected_sha256=report["inventory_report_sha256"],
    )
    candidates = {row["code"]: row for row in inventory["candidates"]}
    if len(candidates) != len(inventory["candidates"]):
        raise ValueError("Unique replay candidate identities required")

    recorded_semantics = []
    replayed_semantics = []
    changes = []
    verified_sources = 0
    for recorded_row in report["results"]:
        candidate = candidates.get(recorded_row["code"])
        if candidate is None:
            raise ValueError("Qualification replay candidate missing")
        if recorded_row.get("source_retained") is not True:
            raise ValueError("Qualification replay requires retained source bytes")
        source_object = recorded_row.get("source_object")
        source_sha = recorded_row.get("source_sha256")
        if source_object != f"objects/{source_sha}.json":
            raise ValueError("Content-addressed qualification source required")
        source_path = root / source_object
        source = source_path.read_bytes()
        if hashlib.sha256(source).hexdigest() != source_sha:
            raise ValueError("Retained qualification source hash changed")
        verified_sources += 1

        replayed = qualify_candidate(candidate, source)
        recorded = {
            key: value
            for key, value in recorded_row.items()
            if key not in ("retrieved_at", "source_object")
        }
        recorded_semantics.append(recorded)
        replayed_semantics.append(replayed)
        if canonical(replayed) != canonical(recorded):
            changes.append(
                {
                    "code": recorded_row["code"],
                    "title": recorded_row["title"],
                    "kind": recorded_row["kind"],
                    "source_sha256": source_sha,
                    "old_status": recorded_row.get("status"),
                    "new_status": replayed.get("status"),
                    "old_reason": recorded_row.get("reason"),
                    "new_reason": replayed.get("reason"),
                    "old_facts_hash": recorded_row.get("facts_hash"),
                    "new_facts_hash": replayed.get("facts_hash"),
                    "old_facts": _jsonable(recorded_row.get("facts")),
                    "new_facts": _jsonable(replayed.get("facts")),
                }
            )

    replayed_counts = Counter(row["status"] for row in replayed_semantics)
    replayed_requests = [
        row["review_request"] for row in replayed_semantics if row["status"] == QUALIFIED
    ]
    summary = {
        "report_sha256": report_sha256,
        "candidate_count": report["candidate_count"],
        "source_bytes_verified_count": verified_sources,
        "status_counts": report["status_counts"],
        "source_fetch_complete": report["source_fetch_complete"],
        "results_hash": report["results_hash"],
        "review_requests_hash": report["review_requests_hash"],
        "qualified_review_request_count": len(report["review_requests"]),
        "changed_result_count": len(changes),
        "changed_codes": [row["code"] for row in changes],
        "replayed_status_counts": dict(sorted(replayed_counts.items())),
        "replayed_review_requests_hash": digest(replayed_requests),
        "recorded_semantic_hash": digest(recorded_semantics),
        "replayed_semantic_hash": digest(replayed_semantics),
        "change_hash": digest(changes),
    }
    return summary, changes


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
        "remaining_semantic_unqualified_count": report["remaining_semantic_unqualified_count"],
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
    qualification_actual, qualification_changes = _qualification_replay(
        qualification_root,
        qualification_expected["report_sha256"],
        inventory_root,
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
        qualification_expected["report_sha256"],
    )
    recovery_actual = _recovery_summary(recovery_report)
    mismatches.extend(_subset_mismatches("recovery", baseline["recovery"], recovery_actual))

    lifecycle_reports = sorted(Path(lifecycle_root, "reports").glob("*.json"))
    if len(lifecycle_reports) != 1:
        raise ValueError("Exactly one durable lifecycle report required")
    lifecycle_pin = lifecycle_reports[0]
    lifecycle_sha = lifecycle_pin.stem
    if _file_sha256(lifecycle_pin) != lifecycle_sha:
        raise ValueError("Durable lifecycle report filename/hash mismatch")

    compilation_report = compile_partial_historical_metadata(
        Path(qualification_root) / "reports" / f"{qualification_expected['report_sha256']}.json",
        qualification_expected["report_sha256"],
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
        "qualification_changes": qualification_changes,
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
