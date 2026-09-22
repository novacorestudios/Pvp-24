from pathlib import Path

import pytest
import yaml


SCOPES = Path("config/evidence-workflow-scopes.json")


def workflow_paths():
    import json

    value = json.loads(SCOPES.read_text())
    return [Path(row["workflow"]) for row in value["workflows"]]


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda path: path.name)
def test_evidence_workflow_is_post_ci_dispatch_only(path):
    raw = path.read_text()
    value = yaml.safe_load(raw)
    trigger = value.get("on")
    assert isinstance(trigger, dict)
    assert set(trigger) == {"workflow_dispatch"}
    dispatch = trigger["workflow_dispatch"]
    assert dispatch["inputs"]["source_sha"]["required"] is True
    assert dispatch["inputs"]["source_sha"]["type"] == "string"

    assert "github.ref == 'refs/heads/build/pvb24-v1'" in raw
    assert "ref: ${{ inputs.source_sha }}" in raw
    assert "scripts/verify_evidence_ci.py" in raw
    assert '--sha "${{ inputs.source_sha }}"' in raw
    assert "scripts/qualify_evidence_artifact.py create" in raw
    assert "scripts/qualify_evidence_artifact.py verify" in raw
    assert '--expected-sha "${{ inputs.source_sha }}"' in raw


def test_scope_file_covers_every_evidence_workflow_file():
    import json

    value = json.loads(SCOPES.read_text())
    scoped = {row["workflow"] for row in value["workflows"]}
    actual = {
        path.as_posix()
        for path in Path(".github/workflows").glob("*.yml")
        if path.name != "ci.yml"
    }
    assert scoped == actual


def test_scope_common_dependencies_include_ci_policy_contract():
    import json

    value = json.loads(SCOPES.read_text())
    required = {
        "src/pvb24/data/evidence_ci.py",
        "scripts/verify_evidence_ci.py",
        "scripts/qualify_evidence_artifact.py",
        "scripts/dispatch_evidence_workflows.py",
        "tests/test_evidence_ci.py",
        "tests/test_evidence_dispatch.py",
        "tests/test_evidence_workflow_policy.py",
        "config/evidence-workflow-scopes.json",
        "scripts/verify_provenance.py",
        "src/pvb24/ids.py",
        "src/pvb24/types.py",
        "pyproject.toml",
    }
    assert required <= set(value["common"])
