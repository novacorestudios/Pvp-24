import hashlib
import json
from pathlib import Path

from pvb24.data.security_master_v8 import compile_security_master_v8
from pvb24.ids import digest


def write(path, value):
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def fixture(tmp_path):
    active = [
        {
            "symbol": "AAAUSDT",
            "effective_from": "2020-12-22T07:00:00.000000Z",
            "boundary_reconciled": False,
        },
        {
            "symbol": "BBBUSDT",
            "effective_from": "2021-01-01T07:00:00.000000Z",
            "boundary_reconciled": True,
        },
    ]
    unresolved = [
        {
            "symbol": "AAAUSDT",
            "event_at": "2020-12-22T07:00:00.000000Z",
            "available_at": "2020-12-21T00:00:00.000000Z",
            "source": "https://example.test/a",
            "revision_id": "a" * 64,
            "article_code": "a",
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        },
        {
            "symbol": "BBBUSDT",
            "event_at": "2020-12-28T07:00:00.000000Z",
            "available_at": "2020-12-27T00:00:00.000000Z",
            "source": "https://example.test/b",
            "revision_id": "b" * 64,
            "article_code": "b",
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        },
        {
            "symbol": "CCCUSDT",
            "event_at": "2020-12-29T07:00:00.000000Z",
            "available_at": "2020-12-28T00:00:00.000000Z",
            "source": "https://example.test/c",
            "revision_id": "c" * 64,
            "article_code": "c",
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        },
    ]
    base = {
        "schema": "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V7",
        "inputs": {},
        "selected_active_transition_count": len(active),
        "selected_active_transitions": active,
        "archive_reconciled_active_transition_count": 1,
        "announcement_only_active_transition_count": 1,
        "unresolved_listing_count": len(unresolved),
        "unresolved_listings": unresolved,
        "symbol_obligations": [
            {
                "symbol": symbol,
                "has_listing_evidence": True,
                "has_selected_trading_start": symbol != "CCCUSDT",
                "has_unresolved_listing_boundary": True,
                "has_delisting_evidence": False,
                "has_paired_inactive_transition": False,
                "obligations": [
                    "ACQUIRE_CAUSAL_CLASSIFICATION_HISTORY",
                    "PROVE_COMPLETE_CHANGE_STREAM",
                    "RESOLVE_LISTING_BOUNDARY",
                ],
                "full_security_history_complete": False,
            }
            for symbol in ("AAAUSDT", "BBBUSDT", "CCCUSDT")
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
    base["audit_hash"] = digest(base)
    base_ref = write(Path(tmp_path) / "v7.json", base)

    def evidence(item, status):
        return {
            "symbol": item["symbol"],
            "event_at": item["event_at"],
            "available_at": item["available_at"],
            "source": item["source"],
            "article_code": item["article_code"],
            "article_source_sha256": item["revision_id"],
            "status": status,
            "monthly_source": {"status": "ACQUIRED"},
            "pre_event_activity_observed": status
            == "CONTRADICTED_BY_PRE_EVENT_MONTHLY_ACTIVITY",
            "first_pre_event_activity_start": None,
            "first_pre_event_activity_available_at": None,
            "first_activity_at_or_after_event": item["event_at"],
            "announcement_exact_time_corroborated": status
            != "CONTRADICTED_BY_PRE_EVENT_MONTHLY_ACTIVITY",
            "archive_proves_exact_launch": False,
            "monthly_archive_publication_time_verified": False,
            "historical_universe_complete": False,
        }

    rows = [
        evidence(
            unresolved[0],
            "CONSISTENT_FIRST_MONTHLY_ACTIVITY_AT_ANNOUNCED_LAUNCH",
        ),
        evidence(
            unresolved[1],
            "CONTRADICTED_BY_PRE_EVENT_MONTHLY_ACTIVITY",
        ),
        {
            **evidence(unresolved[2], "UNKNOWN"),
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        },
    ]
    monthly = {
        "schema": "PVB24_MONTHLY_LISTING_BOUNDARY_EVIDENCE_V1",
        "quality": "PRELIMINARY",
        "inputs": {
            "security_master_v7_sha256": base_ref[1],
            "security_master_v7_audit_hash": base["audit_hash"],
        },
        "input_unresolved_listing_count": len(unresolved),
        "monthly_source_count": 3,
        "result_count": len(rows),
        "status_counts": {
            "CONSISTENT_FIRST_MONTHLY_ACTIVITY_AT_ANNOUNCED_LAUNCH": 1,
            "CONTRADICTED_BY_PRE_EVENT_MONTHLY_ACTIVITY": 1,
            "UNKNOWN": 1,
        },
        "results": rows,
        "results_hash": digest(rows),
        "source_failure_count": 0,
        "source_failures": [],
        "prior_missing_daily_archive_used_as_inactivity_proof": False,
        "archive_proves_exact_launch": False,
        "historical_publication_times_verified": False,
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
    monthly["evidence_hash"] = digest(monthly)
    monthly_ref = write(Path(tmp_path) / "monthly.json", monthly)
    return base_ref, monthly_ref


def test_v8_resolves_boundary_without_overwriting_relisting_semantics(tmp_path):
    base, monthly = fixture(tmp_path)
    report = compile_security_master_v8(
        base[0],
        base[1],
        monthly[0],
        monthly[1],
    )

    assert report["schema"] == "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V8"
    assert report["unresolved_listing_count"] == 1
    assert report["monthly_boundary_corroborated_count"] == 1
    assert report["monthly_boundary_corroborated_active_count"] == 1
    assert report["monthly_boundary_contradicted_count"] == 1

    aaa = next(row for row in report["selected_active_transitions"] if row["symbol"] == "AAAUSDT")
    assert aaa["boundary_reconciled"] is False
    assert aaa["monthly_archive_proves_exact_launch"] is False

    aaa_obligation = next(
        row for row in report["symbol_obligations"] if row["symbol"] == "AAAUSDT"
    )
    bbb_obligation = next(
        row for row in report["symbol_obligations"] if row["symbol"] == "BBBUSDT"
    )
    ccc_obligation = next(
        row for row in report["symbol_obligations"] if row["symbol"] == "CCCUSDT"
    )
    assert "RESOLVE_LISTING_BOUNDARY" not in aaa_obligation["obligations"]
    assert "RESOLVE_LISTING_BOUNDARY" not in bbb_obligation["obligations"]
    assert "REJECT_CONTRADICTED_LISTING_START" in bbb_obligation["obligations"]
    assert "RESOLVE_RELISTING_OR_DUPLICATE_START_SEMANTICS" in bbb_obligation["obligations"]
    assert "RESOLVE_LISTING_BOUNDARY" in ccc_obligation["obligations"]
    assert report["historical_universe_complete"] is False
    assert report["final_test_access"] == "LOCKED"
