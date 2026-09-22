import hashlib
import json
from pathlib import Path

import pytest

from pvb24.evaluation.readiness import (
    ATTESTATION_SCHEMA,
    REQUIRED_CAPABILITIES,
    HistoricalEvaluationBlocked,
    evaluate_readiness,
    require_performance_ready,
)
from pvb24.ids import canonical

ROOT = Path(__file__).resolve().parents[1]


def git_blob(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def evidence(tmp_path, name, *, complete=True, suffix=""):
    payload = {
        "schema": ATTESTATION_SCHEMA,
        "capability": name,
        "complete": complete,
        "coverage_start": "2020-01-01T00:00:00.000000Z",
        "coverage_end": "2025-07-01T00:00:00.000000Z",
        "quality": "PRELIMINARY",
        "gaps": [] if complete else ["partial fixture"],
        "final_test_access": "LOCKED",
    }
    path = tmp_path / f"{name}{suffix}.json"
    raw = canonical(payload).encode()
    path.write_bytes(raw)
    return {
        "path": path.name,
        "git_blob_sha": git_blob(raw),
        "schema": ATTESTATION_SCHEMA,
        "checks": [{"path": ["capability"], "equals": name}],
    }


def manifest(tmp_path, *, overrides=None):
    overrides = overrides or {}
    capabilities = []
    for name in REQUIRED_CAPABILITIES:
        row = {
            "name": name,
            "status": "COMPLETE",
            "gaps": [],
            "evidence": evidence(tmp_path, name),
        }
        row.update(overrides.get(name, {}))
        capabilities.append(row)
    payload = {
        "schema": "PVB24_HISTORICAL_EVALUATION_READINESS_V1",
        "profile": "PRELIMINARY_PRE_FINAL_V1",
        "window_start": "2020-01-01T00:00:00.000000Z",
        "window_end": "2025-07-01T00:00:00.000000Z",
        "final_test_access": "LOCKED",
        "performance_run": False,
        "operational_ready": False,
        "capabilities": capabilities,
    }
    path = tmp_path / "manifest.json"
    path.write_text(canonical(payload))
    return path


def test_all_complete_pinned_attestations_open_only_pre_final_performance_gate(tmp_path):
    path = manifest(tmp_path)
    report = evaluate_readiness(tmp_path, path.name)
    assert report["ready_for_performance_run"]
    assert report["blocked_capabilities"] == []
    assert report["performance_run"] is False
    assert report["final_test_access"] == "LOCKED"
    assert require_performance_ready(tmp_path, path.name) == report


def test_partial_or_missing_capability_blocks_performance(tmp_path):
    partial = evidence(
        tmp_path,
        "HISTORICAL_UNIVERSE",
        complete=False,
        suffix="-partial",
    )
    path = manifest(
        tmp_path,
        overrides={
            "HISTORICAL_UNIVERSE": {
                "status": "PARTIAL",
                "gaps": ["full historical universe not reconstructed"],
                "evidence": partial,
            },
            "MARK_1M": {
                "status": "MISSING",
                "gaps": ["full pre-Final Mark grid missing"],
                "evidence": None,
            },
        },
    )
    report = evaluate_readiness(tmp_path, path.name)
    assert report["blocked_capabilities"] == ["HISTORICAL_UNIVERSE", "MARK_1M"]
    with pytest.raises(HistoricalEvaluationBlocked, match="HISTORICAL_UNIVERSE, MARK_1M"):
        require_performance_ready(tmp_path, path.name)


def test_complete_status_cannot_be_self_declared_from_partial_source_report(tmp_path):
    raw = canonical(
        {
            "schema": "SOME_SOURCE_REPORT",
            "historical_universe_complete": True,
            "final_test_access": "LOCKED",
        }
    ).encode()
    source = tmp_path / "source.json"
    source.write_bytes(raw)
    path = manifest(
        tmp_path,
        overrides={
            "HISTORICAL_UNIVERSE": {
                "evidence": {
                    "path": source.name,
                    "git_blob_sha": git_blob(raw),
                    "schema": "SOME_SOURCE_REPORT",
                    "checks": [
                        {
                            "path": ["historical_universe_complete"],
                            "equals": True,
                        }
                    ],
                }
            }
        },
    )
    with pytest.raises(ValueError, match="dedicated capability attestation"):
        evaluate_readiness(tmp_path, path.name)


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("final_test_access", "OPEN", "Final Test"),
        ("performance_run", True, "pre-authorize"),
        ("operational_ready", True, "pre-authorize"),
        ("window_end", "2025-07-01T00:00:00.000001Z", "window is frozen"),
    ],
)
def test_manifest_cannot_unlock_holdout_or_pre_authorize_results(
    tmp_path,
    field,
    value,
    match,
):
    path = manifest(tmp_path)
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(canonical(payload))
    with pytest.raises(ValueError, match=match):
        evaluate_readiness(tmp_path, path.name)


def test_changed_evidence_bytes_fail_blob_pin_before_semantic_use(tmp_path):
    path = manifest(tmp_path)
    payload = json.loads(path.read_text())
    evidence_path = tmp_path / payload["capabilities"][0]["evidence"]["path"]
    evidence_path.write_text(evidence_path.read_text() + " ")
    with pytest.raises(ValueError, match="blob identity changed"):
        evaluate_readiness(tmp_path, path.name)


def test_semantic_anchor_mismatch_fails_closed(tmp_path):
    path = manifest(tmp_path)
    payload = json.loads(path.read_text())
    payload["capabilities"][0]["evidence"]["checks"][0]["equals"] = "OTHER"
    path.write_text(canonical(payload))
    with pytest.raises(ValueError, match="semantic check failed"):
        evaluate_readiness(tmp_path, path.name)


def test_duplicate_missing_or_unknown_capability_is_rejected(tmp_path):
    path = manifest(tmp_path)
    payload = json.loads(path.read_text())
    payload["capabilities"][-1]["name"] = payload["capabilities"][0]["name"]
    path.write_text(canonical(payload))
    with pytest.raises(ValueError, match="each required capability exactly once"):
        evaluate_readiness(tmp_path, path.name)


def test_complete_attestation_must_cover_entire_pre_final_window(tmp_path):
    path = manifest(tmp_path)
    payload = json.loads(path.read_text())
    ev = payload["capabilities"][0]["evidence"]
    ev_path = tmp_path / ev["path"]
    attestation = json.loads(ev_path.read_text())
    attestation["coverage_start"] = "2024-01-01T00:00:00.000000Z"
    raw = canonical(attestation).encode()
    ev_path.write_bytes(raw)
    ev["git_blob_sha"] = git_blob(raw)
    path.write_text(canonical(payload))
    with pytest.raises(ValueError, match="entire pre-Final window"):
        evaluate_readiness(tmp_path, path.name)


def test_repository_readiness_matrix_is_pinned_and_blocks_performance_today():
    path = ROOT / "docs/data/11m-pre-final-readiness.json"
    report = evaluate_readiness(ROOT, path.relative_to(ROOT))
    assert not report["ready_for_performance_run"]
    assert set(report["blocked_capabilities"]) == set(REQUIRED_CAPABILITIES)
    with pytest.raises(HistoricalEvaluationBlocked):
        require_performance_ready(ROOT, path.relative_to(ROOT))


def test_repository_readiness_matrix_uses_latest_committed_audit_evidence():
    payload = json.loads((ROOT / "docs/data/11m-pre-final-readiness.json").read_text())
    rows = {row["name"]: row for row in payload["capabilities"]}

    assert all(row["status"] == "PARTIAL" for row in rows.values())
    assert "Only three reviewed announcement articles" not in json.dumps(payload)

    for name in ("HISTORICAL_UNIVERSE", "SECURITY_MASTER", "CONTRACT_RULES", "LIFECYCLE"):
        assert rows[name]["evidence"]["path"] == ("docs/data/11v-historical-metadata-evidence.json")
        assert rows[name]["evidence"]["git_blob_sha"] == (
            "7aadc0469e02f0687b185623e38e13a55e0d7a07"
        )

    assert rows["FUNDING_SCHEDULE"]["evidence"]["path"] == (
        "docs/data/11u-funding-schedule-audit.json"
    )
    assert rows["FUNDING_SCHEDULE"]["evidence"]["git_blob_sha"] == (
        "7e0b4d9fdb52f1be1fbfd99d1de1515ad8463e86"
    )
    assert rows["LIQUIDATION_RULES"]["evidence"]["path"] == (
        "docs/data/11w-historical-liquidation-evidence.json"
    )

    report = evaluate_readiness(ROOT, Path("docs/data/11m-pre-final-readiness.json"))
    assert report["ready_for_performance_run"] is False
    assert set(report["blocked_capabilities"]) == set(REQUIRED_CAPABILITIES)
    assert report["final_test_access"] == "LOCKED"
