import hashlib
import json
from pathlib import Path

from pvb24.data.security_master_successor import compile_security_master_successor
from pvb24.ids import digest


def write(path, value):
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
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
    base = {
        "schema": "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V5",
        "availability_model": "PER_SOURCE_POINT_IN_TIME_V1",
        "point_in_time_source_availability_preserved": True,
        "inputs": {},
        "symbol_count": 3,
        "symbols": ["AAAUSDT", "BBBUSDT", "CCCUSDT"],
        "selected_active_transition_count": 3,
        "selected_active_transitions": active,
        "archive_reconciled_active_transition_count": 0,
        "announcement_only_active_transition_count": 3,
        "selected_inactive_transition_count": 0,
        "selected_inactive_transitions": [],
        "archive_reconciled_inactive_transition_count": 0,
        "announcement_only_inactive_transition_count": 0,
        "unresolved_listing_count": 0,
        "unresolved_listings": [],
        "listing_start_conflict_count": 0,
        "listing_start_conflicts": [],
        "unpaired_delisting_count": 0,
        "unpaired_delistings": [],
        "ambiguous_delisting_count": 0,
        "ambiguous_delistings": [],
        "delisting_revision_conflict_count": 0,
        "delisting_revision_conflicts": [],
        "symbol_obligations": [
            {
                "symbol": symbol,
                "has_listing_evidence": True,
                "has_selected_trading_start": True,
                "has_unresolved_listing_boundary": False,
                "has_delisting_evidence": False,
                "has_paired_inactive_transition": False,
                "obligations": [
                    "ACQUIRE_CAUSAL_CLASSIFICATION_HISTORY",
                    "PROVE_COMPLETE_CHANGE_STREAM",
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
    base_ref = write(Path(tmp_path) / "base.json", base)

    def item(symbol, when, status):
        return {
            "symbol": symbol,
            "kind": "LISTING",
            "effective_from": when,
            "article_code": symbol.lower(),
            "article_source_sha256": "a" * 64,
            "source": f"https://example.test/{symbol}",
            "available_at": "2024-01-01T00:00:00.000000Z",
            "status": status,
        }

    exact = item(
        "AAAUSDT",
        "2024-01-02T00:00:00.000000Z",
        "CONSISTENT_EVENT_BOUNDARY_ONLY",
    )
    exact["base_boundary_reconciled"] = False
    unknown = item("BBBUSDT", "2024-01-03T00:00:00.000000Z", "UNKNOWN")
    contradicted = item(
        "CCCUSDT",
        "2024-01-04T00:00:00.000000Z",
        "CONTRADICTED_BY_ARCHIVE_ACTIVITY",
    )
    contradicted["contradictions"] = ["EVENT_DAY_ACTIVITY_PRECEDES_ANNOUNCED_LAUNCH"]
    contradicted["blocking_obligation"] = "REJECT_CONTRADICTED_LISTING_START"

    delta = {
        "schema": "PVB24_REQUALIFIED_SECURITY_MASTER_DELTA_V1",
        "quality": "PRELIMINARY",
        "inputs": {
            "base_security_master_sha256": base_ref[1],
            "base_security_master_audit_hash": base["audit_hash"],
            "requalification_sha256": "b" * 64,
            "requalification_hash": "c" * 64,
            "lifecycle_sha256": "d" * 64,
            "lifecycle_reconciliation_hash": "e" * 64,
        },
        "exact_listing_count": 1,
        "unknown_listing_count": 1,
        "contradicted_listing_count": 1,
        "exact_delisting_count": 0,
        "base_active_corroborated_count": 1,
        "base_active_corroborated": [exact],
        "base_active_newly_reconciled_count": 1,
        "base_active_unknown_boundary_count": 1,
        "base_active_unknown_boundaries": [unknown],
        "base_active_contradicted_count": 1,
        "base_active_contradicted": [contradicted],
        "exact_listing_without_base_active_count": 0,
        "exact_listings_without_base_active": [],
        "unknown_listing_without_base_active_count": 0,
        "unknown_listings_without_base_active": [],
        "base_inactive_corroborated_count": 0,
        "base_inactive_corroborated": [],
        "exact_delisting_unpaired_count": 0,
        "exact_delistings_unpaired": [],
        "recommended_successor_active_transition_count": 2,
        "recommended_successor_archive_reconciled_active_count": 1,
        "recommended_successor_announcement_only_active_count": 1,
        "classification_history_complete": False,
        "rename_relisting_history_complete": False,
        "source_window_coverage_complete": False,
        "historical_publication_times_verified": False,
        "security_change_stream_complete": False,
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "complete_attestation_emitted": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    delta["delta_hash"] = digest(delta)
    delta_ref = write(Path(tmp_path) / "delta.json", delta)
    return base_ref, delta_ref


def test_successor_marks_exact_unknown_and_rejects_contradicted_start(tmp_path):
    base, delta = fixture(tmp_path)
    report = compile_security_master_successor(
        base[0],
        base[1],
        delta[0],
        delta[1],
    )

    assert report["schema"] == "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V6"
    assert report["selected_active_transition_count"] == 2
    assert report["archive_reconciled_active_transition_count"] == 1
    assert report["announcement_only_active_transition_count"] == 1
    assert report["unresolved_listing_count"] == 1
    assert report["rejected_active_transition_count"] == 1

    aaa = next(row for row in report["selected_active_transitions"] if row["symbol"] == "AAAUSDT")
    bbb = next(row for row in report["selected_active_transitions"] if row["symbol"] == "BBBUSDT")
    assert aaa["boundary_reconciled"] is True
    assert aaa["requalified_boundary_status"] == "CONSISTENT_EVENT_BOUNDARY_ONLY"
    assert bbb["requalified_boundary_status"] == "UNKNOWN"

    ccc = next(row for row in report["symbol_obligations"] if row["symbol"] == "CCCUSDT")
    assert ccc["has_selected_trading_start"] is False
    assert "REJECT_CONTRADICTED_LISTING_START" in ccc["obligations"]
    assert report["security_history_complete"] is False
    assert report["historical_universe_complete"] is False
    assert report["final_test_access"] == "LOCKED"
