import json
from pathlib import Path

from pvb24.data.requalified_security_master import (
    compile_requalified_security_master_delta,
)
from pvb24.ids import canonical, digest


def write(path, value):
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
    import hashlib

    return path, hashlib.sha256(raw).hexdigest()


def fixture(tmp_path):
    active = [
        {
            "symbol": symbol,
            "effective_from": when,
            "boundary_reconciled": False,
        }
        for symbol, when in (
            ("AAAUSDT", "2024-01-02T00:00:00.000000Z"),
            ("BBBUSDT", "2024-01-03T00:00:00.000000Z"),
            ("CCCUSDT", "2024-01-04T00:00:00.000000Z"),
        )
    ]
    inactive = [
        {
            "symbol": "AAAUSDT",
            "effective_from": "2024-03-01T00:00:00.000000Z",
            "boundary_reconciled": True,
        }
    ]
    base = {
        "schema": "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V5",
        "selected_active_transition_count": 3,
        "selected_active_transitions": active,
        "archive_reconciled_active_transition_count": 0,
        "announcement_only_active_transition_count": 3,
        "selected_inactive_transition_count": 1,
        "selected_inactive_transitions": inactive,
        "unpaired_delistings": [],
        "quality": "PRELIMINARY",
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "complete_attestation_emitted": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    base["audit_hash"] = digest(base)

    rows = []
    results = []
    changes = []
    for index, (symbol, when, status) in enumerate(
        (
            ("AAAUSDT", "2024-01-02T00:00:00.000000Z", "CONSISTENT_EVENT_BOUNDARY_ONLY"),
            ("BBBUSDT", "2024-01-03T00:00:00.000000Z", "UNKNOWN"),
            ("CCCUSDT", "2024-01-04T00:00:00.000000Z", "CONTRADICTED_BY_ARCHIVE_ACTIVITY"),
        ),
        start=1,
    ):
        code = str(index) * 32
        source_hash = str(index) * 64
        fact = {
            "symbol": symbol,
            "launch_at": when,
            "contract_type": "PERPETUAL",
            "quote_asset": "USDT",
        }
        article = {
            "code": code,
            "kind": "LISTING",
            "status": "QUALIFIED_PRELIMINARY",
            "article_url": f"https://example.test/{code}",
            "available_at": "2024-01-01T00:00:00.000000Z",
            "source_sha256": source_hash,
            "source_retained": True,
            "source_object": f"objects/{source_hash}.json",
            "facts": [fact],
            "facts_hash": digest([fact]),
            "review_request": {"code": code},
        }
        results.append(article)
        changes.append(
            {
                "code": code,
                "kind": "LISTING",
                "source_sha256": source_hash,
                "old_status": "SEMANTIC_UNQUALIFIED",
                "new_status": "QUALIFIED_PRELIMINARY",
                "old_reason": "legacy",
                "new_reason": None,
                "old_facts_hash": None,
                "new_facts_hash": article["facts_hash"],
            }
        )
        rows.append(
            {
                "article_code": code,
                "article_source_sha256": source_hash,
                "kind": "LISTING",
                "symbol": symbol,
                "event_at": when,
                "fact": fact,
                "status": status,
                "contradictions": (
                    ["EVENT_DAY_ACTIVITY_PRECEDES_ANNOUNCED_LAUNCH"]
                    if status == "CONTRADICTED_BY_ARCHIVE_ACTIVITY"
                    else []
                ),
            }
        )

    requalification = {
        "schema": "PVB24_RETAINED_ANNOUNCEMENT_REQUALIFICATION_V1",
        "quality": "PRELIMINARY",
        "durable_bundle_sha256": "d" * 64,
        "source_qualification_report_sha256": "e" * 64,
        "source_results_hash": "a" * 64,
        "source_review_requests_hash": "b" * 64,
        "inventory_report": "reports/" + "f" * 64 + ".json",
        "inventory_report_sha256": "f" * 64,
        "inventory_hash": "inventory",
        "window_start": "2020-01-01T00:00:00.000000Z",
        "window_end": "2025-07-01T00:00:00.000000Z",
        "candidate_count": len(results),
        "source_bytes_reverified_count": len(results),
        "prior_status_counts": {"SEMANTIC_UNQUALIFIED": len(results)},
        "status_counts": {"QUALIFIED_PRELIMINARY": len(results)},
        "results": results,
        "results_hash": digest(results),
        "review_requests": [row["review_request"] for row in results],
        "review_requests_hash": digest([row["review_request"] for row in results]),
        "changed_result_count": len(changes),
        "status_promoted_to_qualified_count": len(changes),
        "reason_only_change_count": 0,
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
    requalification["requalification_hash"] = digest(requalification)

    lifecycle = {
        "schema": "PVB24_REQUALIFIED_LIFECYCLE_ARCHIVE_ACTIVITY_V1",
        "quality": "PRELIMINARY",
        "source_requalification_hash": requalification["requalification_hash"],
        "qualification_results_hash": requalification["results_hash"],
        "qualification_review_requests_hash": requalification["review_requests_hash"],
        "source_failures": [],
        "reconciliation_count": len(rows),
        "status_counts": {
            "CONSISTENT_EVENT_BOUNDARY_ONLY": 1,
            "CONTRADICTED_BY_ARCHIVE_ACTIVITY": 1,
            "UNKNOWN": 1,
        },
        "reconciliations": rows,
        "reconciliation_hash": digest(rows),
        "historical_universe_complete": False,
        "security_master_complete": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    return write(Path(tmp_path) / "base.json", base), write(
        Path(tmp_path) / "requalification.json", requalification
    ), write(Path(tmp_path) / "lifecycle.json", lifecycle)


def test_delta_corroborates_unknown_and_rejects_contradicted_active(tmp_path):
    base, requalification, lifecycle = fixture(tmp_path)
    report = compile_requalified_security_master_delta(
        base[0],
        base[1],
        requalification[0],
        requalification[1],
        lifecycle[0],
        lifecycle[1],
    )
    assert report["base_active_corroborated_count"] == 1
    assert report["base_active_newly_reconciled_count"] == 1
    assert report["base_active_unknown_boundary_count"] == 1
    assert report["base_active_contradicted_count"] == 1
    assert report["recommended_successor_active_transition_count"] == 2
    assert report["recommended_successor_archive_reconciled_active_count"] == 1
    assert report["recommended_successor_announcement_only_active_count"] == 1
    assert report["historical_universe_complete"] is False
    assert report["final_test_access"] == "LOCKED"
