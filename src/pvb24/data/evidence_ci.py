from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

CI_SCHEMA = "PVB24_EVIDENCE_CI_QUALIFICATION_V1"
ARTIFACT_SCHEMA = "PVB24_EVIDENCE_ARTIFACT_QUALIFICATION_V1"
CI_WORKFLOW_NAME = "PVB-24 CI"
REQUIRED_JOBS = ("governance", "freqtrade-smoke")
ALLOWED_EVENTS = ("push", "workflow_dispatch")
RUN_RE = re.compile(r"/actions/runs/(?P<run_id>\d+)/job/")


def canonical_bytes(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _api_json(repository: str, endpoint: str, token: str):
    url = f"https://api.github.com/repos/{repository}/{endpoint.lstrip('/')}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "pvb24-evidence-ci-qualification",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _run_id(check):
    match = RUN_RE.search(check.get("details_url") or "")
    return int(match.group("run_id")) if match else None


def _candidate_run_ids(check_runs):
    by_run = {}
    for check in check_runs:
        name = check.get("name")
        if name not in REQUIRED_JOBS:
            continue
        run_id = _run_id(check)
        if run_id is None:
            continue
        by_run.setdefault(run_id, {})[name] = check
    return sorted(by_run.items(), reverse=True)


def select_qualified_ci(check_runs, run_lookup, *, sha, branch):
    for run_id, checks in _candidate_run_ids(check_runs):
        if set(checks) != set(REQUIRED_JOBS):
            continue
        if any(
            row.get("status") != "completed" or row.get("conclusion") != "success"
            for row in checks.values()
        ):
            continue
        run = run_lookup(run_id)
        if (
            run.get("name") != CI_WORKFLOW_NAME
            or run.get("head_sha") != sha
            or run.get("head_branch") != branch
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("event") not in ALLOWED_EVENTS
        ):
            continue
        return {
            "run": run,
            "checks": checks,
        }
    return None


def qualify_same_sha_ci(
    *,
    repository,
    sha,
    branch,
    token,
    wait_seconds=300,
    poll_seconds=5,
    api_get=_api_json,
):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Exact 40-character source SHA required")
    if branch != "build/pvb24-v1":
        raise ValueError("Evidence qualification is restricted to build/pvb24-v1")
    deadline = time.monotonic() + max(0, wait_seconds)
    last_checks = []

    while True:
        payload = api_get(repository, f"commits/{sha}/check-runs?per_page=100", token)
        last_checks = payload.get("check_runs", [])
        cache = {}

        def run_lookup(run_id, cache=cache):
            if run_id not in cache:
                cache[run_id] = api_get(repository, f"actions/runs/{run_id}", token)
            return cache[run_id]

        selected = select_qualified_ci(last_checks, run_lookup, sha=sha, branch=branch)
        if selected is not None:
            run = selected["run"]
            checks = selected["checks"]
            return {
                "schema": CI_SCHEMA,
                "repository": repository,
                "branch": branch,
                "source_sha": sha,
                "ci_workflow_name": CI_WORKFLOW_NAME,
                "ci_run_id": run["id"],
                "ci_run_attempt": run.get("run_attempt"),
                "ci_event": run["event"],
                "ci_conclusion": run["conclusion"],
                "required_jobs": [
                    {
                        "name": name,
                        "check_run_id": checks[name].get("id"),
                        "conclusion": checks[name]["conclusion"],
                    }
                    for name in REQUIRED_JOBS
                ],
                "qualified": True,
            }

        if time.monotonic() >= deadline:
            states = [
                {
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "conclusion": row.get("conclusion"),
                    "run_id": _run_id(row),
                }
                for row in last_checks
                if row.get("name") in REQUIRED_JOBS
            ]
            raise ValueError(
                "No successful same-SHA PVB-24 CI run with all required jobs: "
                + json.dumps(states, sort_keys=True)
            )
        time.sleep(max(1, poll_seconds))


def write_ci_attestation(path, value):
    if value.get("schema") != CI_SCHEMA or value.get("qualified") is not True:
        raise ValueError("Qualified same-SHA CI attestation required")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical_bytes(value))


def load_ci_attestation(path, *, expected_sha=None):
    value = json.loads(Path(path).read_text())
    if (
        value.get("schema") != CI_SCHEMA
        or value.get("qualified") is not True
        or value.get("branch") != "build/pvb24-v1"
        or value.get("ci_workflow_name") != CI_WORKFLOW_NAME
        or value.get("ci_conclusion") != "success"
        or [row.get("name") for row in value.get("required_jobs", [])] != list(REQUIRED_JOBS)
        or any(row.get("conclusion") != "success" for row in value["required_jobs"])
    ):
        raise ValueError("Invalid evidence CI qualification")
    if expected_sha is not None and value.get("source_sha") != expected_sha:
        raise ValueError("Evidence CI qualification SHA mismatch")
    return value


def _safe_relative(path: Path, root: Path):
    relative = path.relative_to(root).as_posix()
    value = PurePosixPath(relative)
    if value.is_absolute() or any(part in ("", ".", "..") for part in value.parts):
        raise ValueError("Unsafe evidence artifact path")
    return relative


def _artifact_files(root, manifest_name):
    root = Path(root)
    if not root.is_dir():
        raise ValueError("Evidence artifact root must be a directory")
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlinks are not allowed in qualified evidence artifacts")
        if not path.is_file():
            continue
        relative = _safe_relative(path, root)
        if relative == manifest_name:
            continue
        rows.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    if not rows:
        raise ValueError("Qualified evidence artifact must contain at least one payload file")
    return rows


def qualify_artifact_root(
    *, root, ci_attestation_path, manifest_name="evidence-qualification.json"
):
    ci = load_ci_attestation(ci_attestation_path)
    files = _artifact_files(Path(root), manifest_name)
    value = {
        "schema": ARTIFACT_SCHEMA,
        "producer_repository": ci["repository"],
        "producer_branch": ci["branch"],
        "producer_sha": ci["source_sha"],
        "ci_run_id": ci["ci_run_id"],
        "ci_run_attempt": ci["ci_run_attempt"],
        "ci_required_jobs": ci["required_jobs"],
        "file_count": len(files),
        "files": files,
        "payload_hash": sha256_bytes(canonical_bytes(files)),
        "qualified": True,
        "final_test_access": "LOCKED",
        "live_enabled": False,
    }
    target = Path(root) / manifest_name
    target.write_bytes(canonical_bytes(value))
    return value


def verify_artifact_root(
    *,
    root,
    ci_attestation_path,
    manifest_name="evidence-qualification.json",
    expected_sha=None,
):
    ci = load_ci_attestation(ci_attestation_path, expected_sha=expected_sha)
    target = Path(root) / manifest_name
    value = json.loads(target.read_text())
    files = _artifact_files(Path(root), manifest_name)
    if (
        value.get("schema") != ARTIFACT_SCHEMA
        or value.get("qualified") is not True
        or value.get("producer_repository") != ci["repository"]
        or value.get("producer_branch") != ci["branch"]
        or value.get("producer_sha") != ci["source_sha"]
        or value.get("ci_run_id") != ci["ci_run_id"]
        or value.get("ci_required_jobs") != ci["required_jobs"]
        or value.get("file_count") != len(files)
        or value.get("files") != files
        or value.get("payload_hash") != sha256_bytes(canonical_bytes(files))
        or value.get("final_test_access") != "LOCKED"
        or value.get("live_enabled") is not False
    ):
        raise ValueError("Evidence artifact qualification or payload hash changed")
    return value
