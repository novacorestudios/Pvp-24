import hashlib
import json
from pathlib import Path

import pytest

from pvb24.data.security_master_audit import compile_security_master_obligations
from pvb24.ids import digest


def write_m11v(path, value):
    unhashed = dict(value)
    unhashed.pop("evidence_hash", None)
    value["evidence_hash"] = digest(unhashed)
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def m11v_fixture(tmp_path):
    value = {
        "schema": "PVB24_PARTIAL_HISTORICAL_METADATA_EVIDENCE_V1",
        "listing_candidate_count": 1,
        "listing_candidates": [
            {
                "symbol": "AAAUSDT",
                "event_at": "2024-01-02T00:00:00+00:00",
                "available_at": "2024-01-01T00:00:00+00:00",
                "boundary_status": "CONSISTENT_EVENT_BOUNDARY_ONLY",
                "classification": "UNKNOWN",
                "historical_verified": False,
                "contract_type": "PERPETUAL",
                "quote_asset": "USDT",
                "source": "source-a",
                "revision_id": "a" * 64,
            }
        ],
        "unresolved_listing_count": 1,
        "unresolved_listings": [
            {
                "symbol": "BBBUSDT",
                "event_at": "2024-01-03T00:00:00+00:00",
                "available_at": "2024-01-01T00:00:00+00:00",
                "boundary_status": "UNKNOWN",
                "classification": "UNKNOWN",
                "historical_verified": False,
                "source": "source-b",
                "revision_id": "b" * 64,
            }
        ],
        "delisting_event_count": 1,
        "delisting_events": [
            {
                "symbol": "AAAUSDT",
                "event_at": "2024-03-01T00:00:00+00:00",
                "available_at": "2024-02-20T00:00:00+00:00",
                "boundary_status": "CONSISTENT_EVENT_BOUNDARY_ONLY",
                "security_transition_emitted": False,
                "source": "source-c",
                "revision_id": "c" * 64,
            }
        ],
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
        "historical_universe_complete": False,
        "security_history_complete": False,
    }
    path = Path(tmp_path) / "m11v.json"
    return path, write_m11v(path, value)


def write_recovery(path, recovered):
    report = {
        "schema": "PVB24_RETAINED_ANNOUNCEMENT_RECOVERY_V2",
        "source_qualification_report_sha256": "e" * 64,
        "source_results_hash": "f" * 64,
        "source_candidate_count": 148,
        "prior_qualified_count_replayed_identically": 28,
        "recovered_article_count": len(recovered),
        "recovered_fact_count": sum(len(row["facts"]) for row in recovered),
        "recovered_symbol_count": len(
            {fact["symbol"] for row in recovered for fact in row["facts"]}
        ),
        "recovered_symbols": sorted(
            {fact["symbol"] for row in recovered for fact in row["facts"]}
        ),
        "recovered_listing_article_count": sum(row["kind"] == "LISTING" for row in recovered),
        "recovered_listing_fact_count": sum(
            len(row["facts"]) for row in recovered if row["kind"] == "LISTING"
        ),
        "recovered_listing_symbol_count": len(
            {
                fact["symbol"]
                for row in recovered
                if row["kind"] == "LISTING"
                for fact in row["facts"]
            }
        ),
        "recovered_listing_symbols": sorted(
            {
                fact["symbol"]
                for row in recovered
                if row["kind"] == "LISTING"
                for fact in row["facts"]
            }
        ),
        "recovered_delisting_article_count": sum(
            row["kind"] == "DELISTING" for row in recovered
        ),
        "recovered_delisting_fact_count": sum(
            len(row["facts"]) for row in recovered if row["kind"] == "DELISTING"
        ),
        "recovered_delisting_symbol_count": len(
            {
                fact["symbol"]
                for row in recovered
                if row["kind"] == "DELISTING"
                for fact in row["facts"]
            }
        ),
        "recovered_delisting_symbols": sorted(
            {
                fact["symbol"]
                for row in recovered
                if row["kind"] == "DELISTING"
                for fact in row["facts"]
            }
        ),
        "recovered": recovered,
        "retrospective_count": 0,
        "retrospective": [],
        "remaining_semantic_unqualified_count": 1,
        "remaining_status_counts": {"SEMANTIC_UNQUALIFIED": 1},
        "remaining_reason_counts": {"still missing": 1},
        "remaining": [{"code": "z", "kind": "LISTING", "new_reason": "still missing"}],
        "classification_history_complete": False,
        "security_change_stream_complete": False,
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    report["recovery_hash"] = digest(report)
    raw = (json.dumps(report, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def recovered_article(kind, code, available, facts):
    return {
        "kind": kind,
        "code": code,
        "title": code,
        "old_reason": "old",
        "recovery_method": "PINNED_RETAINED_BODY_VARIANT_V2",
        "catalog_released_at": "2023-12-01T00:00:00+00:00",
        "published_at": "2023-12-01T00:00:00+00:00",
        "known_updated_at": None,
        "available_at": available,
        "availability_policy": "test",
        "article_url": f"https://example.test/{code}",
        "source_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "body_sha256": "1" * 64,
        "facts": facts,
        "facts_hash": digest(facts),
        "historical_verified": False,
        "source_retained": True,
    }


def compile_with_recovery(tmp_path, recovered):
    m11v, m11v_sha = m11v_fixture(tmp_path)
    recovery = Path(tmp_path) / "recovery.json"
    recovery_sha = write_recovery(recovery, recovered)
    return compile_security_master_obligations(m11v, m11v_sha, recovery, recovery_sha)


def test_integrated_audit_pairs_recovered_start_and_delisting(tmp_path):
    recovered = [
        recovered_article(
            "LISTING",
            "list-ccc",
            "2023-12-10T00:00:00+00:00",
            [
                {
                    "symbol": "CCCUSDT",
                    "launch_at": "2024-01-01T00:00:00+00:00",
                    "max_leverage": 20,
                    "contract_type": "PERPETUAL",
                    "quote_asset": "USDT",
                }
            ],
        ),
        recovered_article(
            "DELISTING",
            "delist-ccc",
            "2024-01-20T00:00:00+00:00",
            [
                {
                    "symbol": "CCCUSDT",
                    "scheduled_settlement_at": "2024-02-01T00:00:00+00:00",
                }
            ],
        ),
    ]
    report = compile_with_recovery(tmp_path, recovered)
    assert report["selected_active_transition_count"] == 2
    assert report["selected_inactive_transition_count"] == 2
    ccc = next(row for row in report["selected_active_transitions"] if row["symbol"] == "CCCUSDT")
    assert ccc["boundary_reconciled"] is False
    inactive = next(
        row for row in report["selected_inactive_transitions"] if row["symbol"] == "CCCUSDT"
    )
    assert inactive["boundary_reconciled"] is False
    assert report["security_history_complete"] is False
    assert report["complete_attestation_emitted"] is False


def test_multiple_recovered_starts_fail_closed_as_relisting_obligation(tmp_path):
    recovered = [
        recovered_article(
            "LISTING",
            "list-1",
            "2023-12-01T00:00:00+00:00",
            [
                {
                    "symbol": "CCCUSDT",
                    "launch_at": "2024-01-01T00:00:00+00:00",
                    "max_leverage": 20,
                    "contract_type": "PERPETUAL",
                    "quote_asset": "USDT",
                }
            ],
        ),
        recovered_article(
            "LISTING",
            "list-2",
            "2024-01-02T00:00:00+00:00",
            [
                {
                    "symbol": "CCCUSDT",
                    "launch_at": "2024-01-03T00:00:00+00:00",
                    "max_leverage": 20,
                    "contract_type": "PERPETUAL",
                    "quote_asset": "USDT",
                }
            ],
        ),
    ]
    report = compile_with_recovery(tmp_path, recovered)
    assert report["listing_start_conflict_count"] == 1
    assert all(row["symbol"] != "CCCUSDT" for row in report["selected_active_transitions"])
    obligation = next(row for row in report["symbol_obligations"] if row["symbol"] == "CCCUSDT")
    assert "RESOLVE_RELISTING_OR_DUPLICATE_START_SEMANTICS" in obligation["obligations"]


def test_unknown_m11v_boundary_remains_blocking_with_recovered_evidence(tmp_path):
    recovered = [
        recovered_article(
            "LISTING",
            "list-bbb",
            "2024-01-01T00:00:00+00:00",
            [
                {
                    "symbol": "BBBUSDT",
                    "launch_at": "2024-01-03T00:00:00+00:00",
                    "max_leverage": 20,
                    "contract_type": "PERPETUAL",
                    "quote_asset": "USDT",
                }
            ],
        )
    ]
    report = compile_with_recovery(tmp_path, recovered)
    assert report["unresolved_listing_count"] == 1
    obligation = next(row for row in report["symbol_obligations"] if row["symbol"] == "BBBUSDT")
    assert "RESOLVE_LISTING_BOUNDARY" in obligation["obligations"]


def test_recovery_pin_and_hash_fail_closed(tmp_path):
    m11v, m11v_sha = m11v_fixture(tmp_path)
    recovery = Path(tmp_path) / "recovery.json"
    recovery_sha = write_recovery(recovery, [])
    with pytest.raises(ValueError, match="recovery report hash changed"):
        compile_security_master_obligations(m11v, m11v_sha, recovery, "0" * 64)

    value = json.loads(recovery.read_text())
    value["recovery_hash"] = "0" * 64
    raw = (json.dumps(value, indent=2) + "\n").encode()
    recovery.write_bytes(raw)
    changed_sha = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="recovery content hash mismatch"):
        compile_security_master_obligations(m11v, m11v_sha, recovery, changed_sha)


def test_final_test_recovery_fact_is_rejected(tmp_path):
    recovered = [
        recovered_article(
            "LISTING",
            "late",
            "2025-06-30T23:00:00+00:00",
            [
                {
                    "symbol": "CCCUSDT",
                    "launch_at": "2025-07-01T00:00:00+00:00",
                    "max_leverage": 20,
                    "contract_type": "PERPETUAL",
                    "quote_asset": "USDT",
                }
            ],
        )
    ]
    with pytest.raises(ValueError, match="Final Test"):
        compile_with_recovery(tmp_path, recovered)
