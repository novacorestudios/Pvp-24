import json
from pathlib import Path


SCOPES = Path("config/evidence-workflow-scopes.json")


def workflow_paths():
    value = json.loads(SCOPES.read_text())
    return [Path(row["workflow"]) for row in value["workflows"]]


def test_evidence_workflows_are_post_ci_dispatch_only():
    for path in workflow_paths():
        raw = path.read_text()
        trigger = raw.split("\npermissions:", 1)[0].split("on:\n", 1)[1]

        assert "\n  push:" not in trigger, path
        assert "\n  pull_request:" not in trigger, path
        assert "  workflow_dispatch:\n" in trigger, path
        assert "      source_sha:\n" in trigger, path
        assert "        required: true\n" in trigger, path
        assert "        type: string\n" in trigger, path

        assert "github.ref == 'refs/heads/build/pvb24-v1'" in raw, path
        assert "ref: ${{ inputs.source_sha }}" in raw, path
        assert "scripts/verify_evidence_ci.py" in raw, path
        assert '--sha "${{ inputs.source_sha }}"' in raw, path
        assert "scripts/qualify_evidence_artifact.py create" in raw, path
        assert "scripts/qualify_evidence_artifact.py verify" in raw, path
        assert '--expected-sha "${{ inputs.source_sha }}"' in raw, path


def test_scope_file_covers_every_evidence_workflow_file():
    value = json.loads(SCOPES.read_text())
    scoped = {row["workflow"] for row in value["workflows"]}
    actual = {
        path.as_posix() for path in Path(".github/workflows").glob("*.yml") if path.name != "ci.yml"
    }
    assert scoped == actual


def test_scope_common_dependencies_include_ci_policy_contract():
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
