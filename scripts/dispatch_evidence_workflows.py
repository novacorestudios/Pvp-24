import argparse
import fnmatch
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


SCHEMA = "PVB24_EVIDENCE_WORKFLOW_SCOPES_V1"


def load_scopes(path):
    value = json.loads(Path(path).read_text())
    if value.get("schema") != SCHEMA:
        raise ValueError("Unexpected evidence workflow scope schema")
    common = value.get("common")
    workflows = value.get("workflows")
    if not isinstance(common, list) or not isinstance(workflows, list):
        raise ValueError("Evidence workflow scopes required")
    names = [row.get("workflow") for row in workflows]
    if len(names) != len(set(names)) or any(not isinstance(name, str) for name in names):
        raise ValueError("Unique evidence workflow names required")
    return value


def matching_workflows(scopes, changed_paths):
    changed = sorted(set(changed_paths))
    common = scopes["common"]
    matched = []
    for row in scopes["workflows"]:
        patterns = [*common, *row["patterns"]]
        hits = sorted(
            path
            for path in changed
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
        )
        if hits:
            matched.append({"workflow": row["workflow"], "matched_paths": hits})
    return matched


def changed_paths(base, head):
    if set(base) == {"0"}:
        command = ["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", head]
    else:
        command = ["git", "diff", "--name-only", base, head, "--"]
    output = subprocess.check_output(command, text=True)
    return [line.strip() for line in output.splitlines() if line.strip()]


def dispatch(repository, workflow, ref, source_sha, token):
    workflow_id = urllib.parse.quote(workflow, safe="")
    url = f"https://api.github.com/repos/{repository}/actions/workflows/{workflow_id}/dispatches"
    payload = json.dumps({"ref": ref, "inputs": {"source_sha": source_sha}}).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "pvb24-evidence-dispatch",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 204:
            raise ValueError(f"Evidence workflow dispatch failed: {workflow}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--scopes", default="config/evidence-workflow-scopes.json")
    args = parser.parse_args()
    if args.ref != "build/pvb24-v1" or args.source_sha != args.head:
        raise SystemExit("Evidence dispatch requires exact build/pvb24-v1 CI SHA")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN is required")
    scopes = load_scopes(args.scopes)
    changed = changed_paths(args.base, args.head)
    matched = matching_workflows(scopes, changed)
    summary = {
        "source_sha": args.source_sha,
        "changed_paths": changed,
        "dispatch_count": len(matched),
        "dispatches": matched,
    }
    print(json.dumps(summary, indent=2))
    for row in matched:
        dispatch(args.repository, row["workflow"], args.ref, args.source_sha, token)


if __name__ == "__main__":
    main()
