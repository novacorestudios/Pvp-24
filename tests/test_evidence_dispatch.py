from scripts.dispatch_evidence_workflows import matching_workflows


def test_scope_matches_common_dependency_for_every_workflow():
    scopes = {
        "common": ["scripts/verify_provenance.py"],
        "workflows": [
            {"workflow": "a.yml", "patterns": ["src/a.py"]},
            {"workflow": "b.yml", "patterns": ["src/b.py"]},
        ],
    }
    rows = matching_workflows(scopes, ["scripts/verify_provenance.py"])
    assert [row["workflow"] for row in rows] == ["a.yml", "b.yml"]


def test_scope_only_dispatches_affected_workflow():
    scopes = {
        "common": ["common.py"],
        "workflows": [
            {"workflow": "a.yml", "patterns": ["src/a.py"]},
            {"workflow": "b.yml", "patterns": ["src/b.py"]},
        ],
    }
    rows = matching_workflows(scopes, ["src/b.py", "README.md"])
    assert rows == [{"workflow": "b.yml", "matched_paths": ["src/b.py"]}]
