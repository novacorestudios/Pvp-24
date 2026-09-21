"""Fail-closed pre-Final historical-evaluation readiness gate.

The gate is deliberately separate from the backtester.  A performance runner must
first pass this gate with a content-pinned coverage manifest.  Partial source
coverage is useful research evidence, but it never silently becomes permission to
compute or publish a strategy performance result.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pvb24.ids import canonical

SCHEMA = "PVB24_HISTORICAL_EVALUATION_READINESS_V1"
ATTESTATION_SCHEMA = "PVB24_CAPABILITY_ATTESTATION_V1"
PROFILE = "PRELIMINARY_PRE_FINAL_V1"
WINDOW_START = datetime(2020, 1, 1, tzinfo=UTC)
WINDOW_END = datetime(2025, 7, 1, tzinfo=UTC)

REQUIRED_CAPABILITIES = (
    "HISTORICAL_UNIVERSE",
    "SECURITY_MASTER",
    "CONTRACT_RULES",
    "LIFECYCLE",
    "LAST_1H",
    "LAST_1M",
    "MARK_1M",
    "FUNDING_SETTLEMENT_PRICING",
    "FUNDING_SCHEDULE",
    "FUNDING_RESERVE",
    "LIQUIDATION_RULES",
)


class CoverageStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class HistoricalEvaluationBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class EvidenceResult:
    path: str
    git_blob_sha: str
    schema: str
    sha256: str


def _time(value):
    if not isinstance(value, str):
        raise TypeError("ISO timestamp string required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed.astimezone(UTC)


def _safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("Evidence path required")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Evidence path must remain inside repository root")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved_root not in resolved.parents:
        raise ValueError("Evidence path escaped repository root")
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError("Evidence must be a regular repository file")
    return resolved


def _git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode()
    return hashlib.sha1(header + raw).hexdigest()  # noqa: S324 - Git object identity by design.


def _lookup(payload, path):
    value = payload
    if not isinstance(path, list) or not path or any(not isinstance(key, str) for key in path):
        raise ValueError("Evidence check path must be a nonempty string list")
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError("Evidence check path is missing: " + "/".join(path))
        value = value[key]
    return value


def _validate_checks(payload, checks):
    if not isinstance(checks, list) or not checks:
        raise ValueError("Pinned evidence requires at least one semantic check")
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"path", "equals"}:
            raise ValueError("Evidence checks require exact path/equals fields")
        actual = _lookup(payload, check["path"])
        if actual != check["equals"]:
            raise ValueError(
                "Evidence semantic check failed: "
                + "/".join(check["path"])
                + f" expected={check['equals']!r} actual={actual!r}"
            )


def _validate_evidence(root: Path, evidence: dict) -> tuple[dict, EvidenceResult]:
    required = {"path", "git_blob_sha", "schema", "checks"}
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise ValueError("Evidence pin requires exact path/git_blob_sha/schema/checks fields")
    path = _safe_file(root, evidence["path"])
    raw = path.read_bytes()
    blob_sha = _git_blob_sha(raw)
    if blob_sha != evidence["git_blob_sha"]:
        raise ValueError("Pinned evidence Git blob identity changed: " + evidence["path"])
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Pinned readiness evidence must be JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema") != evidence["schema"]:
        raise ValueError("Pinned evidence schema changed: " + evidence["path"])
    if payload.get("final_test_access") != "LOCKED":
        raise ValueError("Readiness evidence must preserve Final Test LOCKED")
    _validate_checks(payload, evidence["checks"])
    return payload, EvidenceResult(
        evidence["path"],
        blob_sha,
        evidence["schema"],
        hashlib.sha256(raw).hexdigest(),
    )


def _validate_complete_attestation(name, payload):
    if payload.get("schema") != ATTESTATION_SCHEMA:
        raise ValueError("COMPLETE capability requires dedicated capability attestation")
    if payload.get("capability") != name or payload.get("complete") is not True:
        raise ValueError("COMPLETE attestation identity/flag mismatch")
    if payload.get("final_test_access") != "LOCKED":
        raise ValueError("COMPLETE attestation must keep Final Test LOCKED")
    if payload.get("quality") not in ("PRELIMINARY", "VERIFIED"):
        raise ValueError("Explicit attestation quality required")
    if payload.get("gaps") != []:
        raise ValueError("COMPLETE capability cannot retain evidence gaps")
    start = _time(payload.get("coverage_start"))
    end = _time(payload.get("coverage_end"))
    if start > WINDOW_START or end < WINDOW_END:
        raise ValueError("COMPLETE capability does not span the entire pre-Final window")


def evaluate_readiness(root, manifest_path):
    root = Path(root)
    manifest_path = _safe_file(root, str(manifest_path))
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest)
    required_top = {
        "schema",
        "profile",
        "window_start",
        "window_end",
        "final_test_access",
        "performance_run",
        "operational_ready",
        "capabilities",
    }
    if not isinstance(manifest, dict) or set(manifest) != required_top:
        raise ValueError("Readiness manifest schema fields are not exact")
    if manifest["schema"] != SCHEMA or manifest["profile"] != PROFILE:
        raise ValueError("Unsupported historical evaluation readiness profile")
    if manifest["final_test_access"] != "LOCKED":
        raise ValueError("Final Test must remain LOCKED before historical evaluation")
    if manifest["performance_run"] is not False or manifest["operational_ready"] is not False:
        raise ValueError("Readiness input cannot pre-authorize performance or operations")
    if _time(manifest["window_start"]) != WINDOW_START or _time(manifest["window_end"]) != WINDOW_END:
        raise ValueError("Pre-Final evaluation window is frozen and cannot be widened")

    rows = manifest["capabilities"]
    if not isinstance(rows, list):
        raise TypeError("Capability matrix must be a list")
    names = [row.get("name") for row in rows if isinstance(row, dict)]
    if tuple(sorted(names)) != tuple(sorted(REQUIRED_CAPABILITIES)) or len(names) != len(set(names)):
        raise ValueError("Capability matrix must contain each required capability exactly once")

    results = []
    blocked = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "status", "gaps", "evidence"}:
            raise ValueError("Capability row fields are not exact")
        name = row["name"]
        try:
            status = CoverageStatus(row["status"])
        except ValueError as exc:
            raise ValueError("Unknown capability coverage status") from exc
        gaps = row["gaps"]
        if not isinstance(gaps, list) or any(not isinstance(gap, str) or not gap for gap in gaps):
            raise ValueError("Capability gaps must be explicit nonempty strings")

        evidence_result = None
        payload = None
        if status is CoverageStatus.MISSING:
            if row["evidence"] is not None or not gaps:
                raise ValueError("MISSING capability requires gaps and no fabricated evidence")
        else:
            if row["evidence"] is None:
                raise ValueError("PARTIAL/COMPLETE capability requires pinned evidence")
            payload, evidence_result = _validate_evidence(root, row["evidence"])
            if status is CoverageStatus.PARTIAL and not gaps:
                raise ValueError("PARTIAL capability must state its remaining gaps")
            if status is CoverageStatus.COMPLETE:
                if gaps:
                    raise ValueError("COMPLETE capability cannot state remaining gaps")
                _validate_complete_attestation(name, payload)

        if status is not CoverageStatus.COMPLETE:
            blocked.append(name)
        results.append(
            {
                "name": name,
                "status": status,
                "gaps": tuple(gaps),
                "evidence": evidence_result,
            }
        )

    return json.loads(
        canonical(
            {
                "schema": "PVB24_HISTORICAL_EVALUATION_READINESS_REPORT_V1",
                "profile": PROFILE,
                "window_start": WINDOW_START,
                "window_end": WINDOW_END,
                "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
                "capabilities": results,
                "blocked_capabilities": sorted(blocked),
                "ready_for_performance_run": not blocked,
                "performance_run": False,
                "operational_ready": False,
                "final_test_access": "LOCKED",
            }
        )
    )


def require_performance_ready(root, manifest_path):
    report = evaluate_readiness(root, manifest_path)
    if not report["ready_for_performance_run"]:
        raise HistoricalEvaluationBlocked(
            "Historical evaluation blocked by: " + ", ".join(report["blocked_capabilities"])
        )
    return report
