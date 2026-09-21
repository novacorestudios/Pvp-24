import hashlib
import json
from pathlib import Path

import pytest

from pvb24.data.security_master_audit import compile_security_master_obligations
from pvb24.ids import digest


def write_report(path, value):
    unhashed = dict(value)
    unhashed.pop("evidence_hash", None)
    value["evidence_hash"] = digest(unhashed)
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def fixture(tmp_path):
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
        "delisting_event_count": 2,
        "delisting_events": [
            {
                "symbol": "AAAUSDT",
                "event_at": "2024-03-01T00:00:00+00:00",
                "available_at": "2024-02-20T00:00:00+00:00",
                "boundary_status": "CONSISTENT_EVENT_BOUNDARY_ONLY",
                "security_transition_emitted": False,
                "source": "source-c",
                "revision_id": "c" * 64,
            },
            {
                "symbol": "CCCUSDT",
                "event_at": "2024-04-01T00:00:00+00:00",
                "available_at": "2024-03-20T00:00:00+00:00",
                "boundary_status": "CONSISTENT_EVENT_BOUNDARY_ONLY",
                "security_transition_emitted": False,
                "source": "source-d",
                "revision_id": "d" * 64,
            },
        ],
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
        "historical_universe_complete": False,
        "security_history_complete": False,
    }
    path = Path(tmp_path) / "m11v.json"
    return path, write_report(path, value)


def test_audit_emits_only_evidence_backed_transitions(tmp_path):
    path, sha = fixture(tmp_path)
    report = compile_security_master_obligations(path, sha)
    assert report["symbol_count"] == 3
    assert report["confirmed_active_transition_count"] == 1
    assert report["confirmed_inactive_transition_count"] == 1
    assert report["unresolved_listing_count"] == 1
    assert report["unpaired_delisting_count"] == 1
    assert report["full_security_rows_emitted"] == 0
    assert report["security_history_complete"] is False
    assert report["historical_universe_complete"] is False


def test_unresolved_listing_never_materializes_active_transition(tmp_path):
    path, sha = fixture(tmp_path)
    report = compile_security_master_obligations(path, sha)
    assert [row["symbol"] for row in report["confirmed_active_transitions"]] == ["AAAUSDT"]
    assert report["unresolved_listings"][0]["symbol"] == "BBBUSDT"


def test_delisting_without_prior_listing_never_invents_trading_start(tmp_path):
    path, sha = fixture(tmp_path)
    report = compile_security_master_obligations(path, sha)
    row = report["unpaired_delistings"][0]
    assert row["symbol"] == "CCCUSDT"
    assert row["blocking_obligation"] == "ACQUIRE_TRADING_START_BEFORE_DELISTING"
    assert all(
        transition["symbol"] != "CCCUSDT" for transition in report["confirmed_inactive_transitions"]
    )


def test_all_symbols_keep_classification_and_change_stream_obligations(tmp_path):
    path, sha = fixture(tmp_path)
    report = compile_security_master_obligations(path, sha)
    for row in report["symbol_obligations"]:
        assert "ACQUIRE_CAUSAL_CLASSIFICATION_HISTORY" in row["obligations"]
        assert "PROVE_COMPLETE_CHANGE_STREAM" in row["obligations"]
        assert row["full_security_history_complete"] is False


def test_pin_and_evidence_hash_are_rechecked(tmp_path):
    path, sha = fixture(tmp_path)
    with pytest.raises(ValueError, match="hash changed"):
        compile_security_master_obligations(path, "0" * 64)

    value = json.loads(path.read_text())
    value["evidence_hash"] = "0" * 64
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
    changed_sha = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        compile_security_master_obligations(path, changed_sha)


def test_final_test_and_noncausal_listing_fail_closed(tmp_path):
    path, _ = fixture(tmp_path)
    value = json.loads(path.read_text())
    value["listing_candidates"][0]["event_at"] = "2025-07-01T00:00:00+00:00"
    sha = write_report(path, value)
    with pytest.raises(ValueError, match="Final Test"):
        compile_security_master_obligations(path, sha)

    path, _ = fixture(tmp_path)
    value = json.loads(path.read_text())
    value["listing_candidates"][0]["available_at"] = "2024-01-03T00:00:00+00:00"
    sha = write_report(path, value)
    with pytest.raises(ValueError, match="available no later"):
        compile_security_master_obligations(path, sha)
