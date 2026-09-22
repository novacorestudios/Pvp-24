import hashlib
import json
from pathlib import Path

from pvb24.data.security_master_v7 import compile_security_master_v7
from pvb24.ids import digest


def write(path, value):
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def fixture(tmp_path):
    active = [
        {
            "symbol": "AAAUSDT",
            "effective_from": "2020-01-02T08:00:00.000000Z",
            "boundary_reconciled": False,
        },
        {
            "symbol": "BBBUSDT",
            "effective_from": "2020-01-03T08:00:00.000000Z",
            "boundary_reconciled": False,
        },
    ]
    unresolved_source = [
        *active,
        {
            "symbol": "CCCUSDT",
            "effective_from": "2020-01-04T08:00:00.000000Z",
            "boundary_reconciled": False,
        },
    ]
    unresolved = [
        {
            "symbol": row["symbol"],
            "event_at": row["effective_from"],
            "available_at": "2020-01-01T00:00:00.000000Z",
            "source": f"https://example.test/{row['symbol']}",
            "revision_id": row["symbol"][0].lower() * 64,
            "article_code": row["symbol"].lower(),
            "requalified_boundary_status": "UNKNOWN",
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        }
        for row in unresolved_source
    ]
    base = {
        "schema": "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V6",
        "inputs": {},
        "selected_active_transition_count": 2,
        "selected_active_transitions": active,
        "archive_reconciled_active_transition_count": 0,
        "announcement_only_active_transition_count": 2,
        "unresolved_listing_count": 3,
        "unresolved_listings": unresolved,
        "symbol_obligations": [
            {
                "symbol": row["symbol"],
                "has_listing_evidence": True,
                "has_selected_trading_start": True,
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
            for row in unresolved_source
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
    base_ref = write(Path(tmp_path) / "v6.json", base)

    resolved = {
        "symbol": "AAAUSDT",
        "event_at": active[0]["effective_from"],
        "available_at": unresolved[0]["available_at"],
        "source": unresolved[0]["source"],
        "article_code": unresolved[0]["article_code"],
        "article_source_sha256": unresolved[0]["revision_id"],
        "event_day_status": "ACQUIRED",
        "event_day_attempt": "attempts/a.json",
        "event_day_url": "https://data.example/a",
        "first_interval_start": "2020-01-02T08:05:00.000000Z",
        "first_active_interval_start": "2020-01-02T08:05:00.000000Z",
        "boundary_day_status": "UNAVAILABLE",
        "prior_day_absence_used_as_proof": False,
        "resolution": "ANNOUNCED_EXACT_POST_LAUNCH_ACTIVITY_CORROBORATED",
        "exact_time_source": "OFFICIAL_RETAINED_ANNOUNCEMENT",
        "archive_claim": "NON_CONTRADICTORY_POST_LAUNCH_ACTIVITY_ONLY",
        "archive_proves_exact_launch": False,
    }
    remaining = {
        "symbol": "BBBUSDT",
        "event_at": active[1]["effective_from"],
        "available_at": unresolved[1]["available_at"],
        "source": unresolved[1]["source"],
        "article_code": unresolved[1]["article_code"],
        "article_source_sha256": unresolved[1]["revision_id"],
        "event_day_status": "UNAVAILABLE",
        "event_day_attempt": "attempts/b.json",
        "event_day_url": "https://data.example/b",
        "first_interval_start": None,
        "first_active_interval_start": None,
        "boundary_day_status": "UNAVAILABLE",
        "prior_day_absence_used_as_proof": False,
        "resolution": "UNKNOWN",
        "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
    }
    resolved_without_active = {
        **resolved,
        "symbol": "CCCUSDT",
        "event_at": unresolved[2]["event_at"],
        "source": unresolved[2]["source"],
        "article_code": unresolved[2]["article_code"],
        "article_source_sha256": unresolved[2]["revision_id"],
    }
    refinement = {
        "schema": "PVB24_LISTING_BOUNDARY_REFINEMENT_V1",
        "quality": "PRELIMINARY",
        "inputs": {
            "security_master_v6_sha256": base_ref[1],
            "security_master_v6_audit_hash": base["audit_hash"],
            "lifecycle_sha256": "c" * 64,
            "lifecycle_reconciliation_hash": "d" * 64,
        },
        "input_unresolved_listing_count": 3,
        "resolved_announcement_boundary_count": 2,
        "resolved_announcement_boundaries": [resolved, resolved_without_active],
        "remaining_unresolved_listing_count": 1,
        "remaining_unresolved_listings": [remaining],
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
    refinement["refinement_hash"] = digest(refinement)
    refinement_ref = write(Path(tmp_path) / "refinement.json", refinement)
    return base_ref, refinement_ref


def test_v7_removes_only_resolved_boundary_obligation_without_archive_overclaim(tmp_path):
    base, refinement = fixture(tmp_path)
    report = compile_security_master_v7(
        base[0],
        base[1],
        refinement[0],
        refinement[1],
    )

    assert report["schema"] == "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V7"
    assert report["selected_active_transition_count"] == 2
    assert report["archive_reconciled_active_transition_count"] == 0
    assert report["announcement_only_active_transition_count"] == 2
    assert report["announcement_boundary_corroborated_count"] == 2
    assert report["announcement_boundary_corroborated_active_count"] == 1
    assert report["announcement_boundary_corroborated_without_active_count"] == 1
    assert report["unresolved_listing_count"] == 1

    aaa = next(row for row in report["selected_active_transitions"] if row["symbol"] == "AAAUSDT")
    assert aaa["boundary_reconciled"] is False
    assert aaa["archive_proves_exact_launch"] is False
    assert aaa["listing_boundary_resolution"] == (
        "ANNOUNCED_EXACT_POST_LAUNCH_ACTIVITY_CORROBORATED"
    )

    aaa_obligations = next(
        row for row in report["symbol_obligations"] if row["symbol"] == "AAAUSDT"
    )
    bbb_obligations = next(
        row for row in report["symbol_obligations"] if row["symbol"] == "BBBUSDT"
    )
    assert "RESOLVE_LISTING_BOUNDARY" not in aaa_obligations["obligations"]
    ccc_obligations = next(
        row for row in report["symbol_obligations"] if row["symbol"] == "CCCUSDT"
    )
    assert "RESOLVE_LISTING_BOUNDARY" in bbb_obligations["obligations"]
    assert "RESOLVE_LISTING_BOUNDARY" not in ccc_obligations["obligations"]
    assert "MATERIALIZE_REQUALIFIED_ACTIVE_TRANSITION" in ccc_obligations["obligations"]
    assert report["historical_universe_complete"] is False
    assert report["final_test_access"] == "LOCKED"
