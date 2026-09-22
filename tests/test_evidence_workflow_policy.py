from pathlib import Path


SCOPES = Path("config/evidence-workflow-scopes.json")
WORKFLOWS = (
    Path(".github/workflows/catalog-anchor-review.yml"),
    Path(".github/workflows/m11t-durable-evidence.yml"),
    Path(".github/workflows/m11t-durable-replay.yml"),
    Path(".github/workflows/m11v-historical-metadata-evidence.yml"),
    Path(".github/workflows/m11w-historical-liquidation-evidence.yml"),
    Path(".github/workflows/m11w-margin-tier-probe.yml"),
    Path(".github/workflows/m11x-listing-conflict-resolution.yml"),
    Path(".github/workflows/m11x-listing-conflict-source.yml"),
    Path(".github/workflows/m11x-retained-listing-recovery.yml"),
    Path(".github/workflows/m11x-reviewed-listing-facts.yml"),
    Path(".github/workflows/m11x-reviewed-listing-source.yml"),
    Path(".github/workflows/m11x-security-master-audit.yml"),
)


def test_evidence_workflows_are_post_ci_dispatch_only():
    for path in WORKFLOWS:
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
    actual = {
        path.as_posix() for path in Path(".github/workflows").glob("*.yml") if path.name != "ci.yml"
    }
    expected = {path.as_posix() for path in WORKFLOWS}
    assert expected == actual

    scope_text = SCOPES.read_text()
    for path in WORKFLOWS:
        assert f'"workflow": "{path.as_posix()}"' in scope_text


def test_scope_common_dependencies_include_ci_policy_contract():
    scope_text = SCOPES.read_text()
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
    for dependency in required:
        assert f'"{dependency}"' in scope_text
