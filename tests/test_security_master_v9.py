import hashlib
import json
from pathlib import Path

from pvb24.data.security_master_v9 import compile_security_master_v9
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
        }
    ]
    unresolved = [
        {
            "symbol": symbol,
            "event_at": event,
            "available_at": "2020-12-01T00:00:00.000000Z",
            "source": f"https://example.test/{symbol}",
            "revision_id": symbol[0].lower() * 64,
            "article_code": symbol.lower(),
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        }
        for symbol, event in (
            ("AAAUSDT", "2020-12-22T07:00:00.000000Z"),
            ("BBBUSDT", "2020-12-23T07:00:00.000000Z"),
            ("CCCUSDT", "2020-12-24T07:00:00.000000Z"),
        )
    ]
    base = {
        "schema": "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V8",
        "inputs": {},
        "selected_active_transition_count": 1,
        "selected_active_transitions": active,
        "archive_reconciled_active_transition_count": 0,
        "announcement_only_active_transition_count": 1,
        "unresolved_listing_count": 3,
        "unresolved_listings": unresolved,
        "symbol_obligations": [
            {
                "symbol": symbol,
                "has_listing_evidence": True,
                "has_selected_trading_start": symbol == "AAAUSDT",
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
    base_ref = write(Path(tmp_path) / "v8.json", base)

    def result(item, status):
        return {
            "symbol": item["symbol"],
            "event_at": item["event_at"],
            "available_at": item["available_at"],
            "source": item["source"],
            "article_code": item["article_code"],
            "article_source_sha256": item["revision_id"],
            "status": status,
            "ancillary_sources": [],
            "supporting_source_count": 1 if status.startswith("ANNOUNCED") else 0,
            "supporting_source_kinds": ["markPriceKlines"]
            if status.startswith("ANNOUNCED")
            else [],
            "announcement_exact_time_corroborated": status.startswith("ANNOUNCED"),
            "ancillary_proves_first_executable_trade": False,
            "pre_event_ancillary_used_as_inactivity_proof": False,
            "historical_publication_times_verified": False,
            "historical_universe_complete": False,
        }

    rows = [
        result(unresolved[0], "ANNOUNCED_EXACT_ANCILLARY_POST_LAUNCH_CORROBORATED"),
        result(unresolved[1], "ANNOUNCED_EXACT_ANCILLARY_POST_LAUNCH_CORROBORATED"),
        {
            **result(unresolved[2], "UNKNOWN"),
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        },
    ]
    ancillary = {
        "schema": "PVB24_ANCILLARY_LISTING_BOUNDARY_EVIDENCE_V1",
        "quality": "PRELIMINARY",
        "inputs": {
            "security_master_v8_sha256": base_ref[1],
            "security_master_v8_audit_hash": base["audit_hash"],
        },
        "input_unresolved_listing_count": 3,
        "ancillary_request_count": 6,
        "result_count": 3,
        "status_counts": {
            "ANNOUNCED_EXACT_ANCILLARY_POST_LAUNCH_CORROBORATED": 2,
            "UNKNOWN": 1,
        },
        "results": rows,
        "results_hash": digest(rows),
        "source_failure_count": 0,
        "source_failures": [],
        "ancillary_proves_first_executable_trade": False,
        "pre_event_ancillary_used_as_inactivity_proof": False,
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
    ancillary["evidence_hash"] = digest(ancillary)
    ancillary_ref = write(Path(tmp_path) / "ancillary.json", ancillary)
    return base_ref, ancillary_ref


def test_v9_removes_only_corroborated_boundary_obligations(tmp_path):
    base, ancillary = fixture(tmp_path)
    report = compile_security_master_v9(
        base[0],
        base[1],
        ancillary[0],
        ancillary[1],
    )

    assert report["schema"] == "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V9"
    assert report["unresolved_listing_count"] == 1
    assert report["ancillary_boundary_corroborated_count"] == 2
    assert report["ancillary_boundary_corroborated_active_count"] == 1
    assert report["ancillary_boundary_corroborated_without_active_count"] == 1

    aaa = next(row for row in report["selected_active_transitions"] if row["symbol"] == "AAAUSDT")
    assert aaa["boundary_reconciled"] is False
    assert aaa["ancillary_proves_first_executable_trade"] is False

    aaa_o = next(row for row in report["symbol_obligations"] if row["symbol"] == "AAAUSDT")
    bbb_o = next(row for row in report["symbol_obligations"] if row["symbol"] == "BBBUSDT")
    ccc_o = next(row for row in report["symbol_obligations"] if row["symbol"] == "CCCUSDT")
    assert "RESOLVE_LISTING_BOUNDARY" not in aaa_o["obligations"]
    assert "RESOLVE_LISTING_BOUNDARY" not in bbb_o["obligations"]
    assert "MATERIALIZE_REQUALIFIED_ACTIVE_TRANSITION" in bbb_o["obligations"]
    assert "RESOLVE_RELISTING_OR_DUPLICATE_START_SEMANTICS" in bbb_o["obligations"]
    assert "RESOLVE_LISTING_BOUNDARY" in ccc_o["obligations"]
    assert report["historical_universe_complete"] is False
    assert report["final_test_access"] == "LOCKED"
