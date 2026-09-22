import json

import pytest

from pvb24.data.evidence_ci import (
    qualify_artifact_root,
    qualify_same_sha_ci,
    verify_artifact_root,
    write_ci_attestation,
)

SHA = "a" * 40


def check(name, run_id, conclusion="success", status="completed", check_id=1):
    return {
        "id": check_id,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "details_url": f"https://github.test/actions/runs/{run_id}/job/99",
    }


def run(run_id, conclusion="success", sha=SHA, branch="build/pvb24-v1"):
    return {
        "id": run_id,
        "name": "PVB-24 CI",
        "head_sha": sha,
        "head_branch": branch,
        "status": "completed",
        "conclusion": conclusion,
        "event": "push",
        "run_attempt": 1,
    }


def test_same_sha_ci_requires_both_jobs_from_same_successful_run():
    calls = []

    def api(repository, endpoint, token):
        calls.append(endpoint)
        if endpoint.startswith("commits/"):
            return {
                "check_runs": [
                    check("governance", 12, check_id=10),
                    check("freqtrade-smoke", 12, check_id=11),
                ]
            }
        assert endpoint == "actions/runs/12"
        return run(12)

    value = qualify_same_sha_ci(
        repository="novacorestudios/Pvp-24",
        sha=SHA,
        branch="build/pvb24-v1",
        token="token",
        wait_seconds=0,
        api_get=api,
    )
    assert value["qualified"] is True
    assert value["ci_run_id"] == 12
    assert value["source_sha"] == SHA
    assert [row["name"] for row in value["required_jobs"]] == [
        "governance",
        "freqtrade-smoke",
    ]
    assert calls == [
        f"commits/{SHA}/check-runs?per_page=100",
        "actions/runs/12",
    ]


def test_red_governance_cannot_be_qualified():
    def api(repository, endpoint, token):
        if endpoint.startswith("commits/"):
            return {
                "check_runs": [
                    check("governance", 13, conclusion="failure"),
                    check("freqtrade-smoke", 13),
                ]
            }
        return run(13, conclusion="failure")

    with pytest.raises(ValueError, match="No successful same-SHA"):
        qualify_same_sha_ci(
            repository="novacorestudios/Pvp-24",
            sha=SHA,
            branch="build/pvb24-v1",
            token="token",
            wait_seconds=0,
            api_get=api,
        )


def test_jobs_from_different_runs_cannot_be_combined():
    def api(repository, endpoint, token):
        if endpoint.startswith("commits/"):
            return {
                "check_runs": [
                    check("governance", 14),
                    check("freqtrade-smoke", 15),
                ]
            }
        raise AssertionError("No incomplete run should be queried")

    with pytest.raises(ValueError, match="No successful same-SHA"):
        qualify_same_sha_ci(
            repository="novacorestudios/Pvp-24",
            sha=SHA,
            branch="build/pvb24-v1",
            token="token",
            wait_seconds=0,
            api_get=api,
        )


def test_artifact_qualification_binds_hashes_and_detects_drift(tmp_path):
    ci = {
        "schema": "PVB24_EVIDENCE_CI_QUALIFICATION_V1",
        "repository": "novacorestudios/Pvp-24",
        "branch": "build/pvb24-v1",
        "source_sha": SHA,
        "ci_workflow_name": "PVB-24 CI",
        "ci_run_id": 16,
        "ci_run_attempt": 1,
        "ci_event": "push",
        "ci_conclusion": "success",
        "required_jobs": [
            {"name": "governance", "check_run_id": 1, "conclusion": "success"},
            {"name": "freqtrade-smoke", "check_run_id": 2, "conclusion": "success"},
        ],
        "qualified": True,
    }
    ci_path = tmp_path / "ci.json"
    write_ci_attestation(ci_path, ci)
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "evidence.json").write_text(json.dumps({"value": 1}) + "\n")

    created = qualify_artifact_root(root=root, ci_attestation_path=ci_path)
    assert created["producer_sha"] == SHA
    assert created["file_count"] == 1
    verified = verify_artifact_root(
        root=root,
        ci_attestation_path=ci_path,
        expected_sha=SHA,
    )
    assert verified["payload_hash"] == created["payload_hash"]

    (root / "evidence.json").write_text(json.dumps({"value": 2}) + "\n")
    with pytest.raises(ValueError, match="qualification or payload hash changed"):
        verify_artifact_root(
            root=root,
            ci_attestation_path=ci_path,
            expected_sha=SHA,
        )
