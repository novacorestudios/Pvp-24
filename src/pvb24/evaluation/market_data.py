"""Compile complete market-data capability attestations from pinned archive evidence.

This module never decides the historical universe. It accepts obligations only when they are
bound to a COMPLETE historical-universe attestation, then verifies every required monthly
archive and its retained source objects before allowing LAST_1H, LAST_1M or MARK_1M to become
COMPLETE.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pvb24.data.acquisition import load_acquired
from pvb24.data.archive import FINAL_START, ArchiveRequest
from pvb24.data.dataset import dataset_hash
from pvb24.evaluation.readiness import ATTESTATION_SCHEMA, WINDOW_END, WINDOW_START
from pvb24.ids import canonical, digest

SCHEMA = "PVB24_MARKET_DATA_COVERAGE_OBLIGATIONS_V1"
REPORT_SCHEMA = "PVB24_MARKET_DATA_CAPABILITY_REPORT_V1"
CAPABILITIES = {
    "LAST_1H": ("klines", "1h"),
    "LAST_1M": ("klines", "1m"),
    "MARK_1M": ("markPriceKlines", "1m"),
}


@dataclass(frozen=True)
class Obligation:
    symbol: str
    start: datetime
    end: datetime

    def __post_init__(self):
        if not self.symbol.isalnum() or not self.symbol.endswith("USDT"):
            raise ValueError("Explicit USD-M USDT obligation symbol required")
        if self.start.utcoffset() is None or self.end.utcoffset() is None:
            raise ValueError("Timezone-aware obligation bounds required")
        start, end = self.start.astimezone(UTC), self.end.astimezone(UTC)
        if start != start.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
            raise ValueError("Obligation start must be a UTC month boundary")
        if end != end.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
            raise ValueError("Obligation end must be an exclusive UTC month boundary")
        if not WINDOW_START <= start < end <= WINDOW_END:
            raise ValueError("Obligation must remain inside the frozen pre-Final window")


def _time(value):
    if not isinstance(value, str):
        raise TypeError("ISO timestamp string required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed.astimezone(UTC)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json_pinned(path, expected_sha256):
    path = Path(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned JSON SHA-256 changed: " + str(path))
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Pinned JSON object required")
    return payload


def _validate_universe_attestation(payload):
    if payload.get("schema") != ATTESTATION_SCHEMA:
        raise ValueError("Historical universe attestation schema required")
    if (
        payload.get("capability") != "HISTORICAL_UNIVERSE"
        or payload.get("complete") is not True
        or payload.get("gaps") != []
        or payload.get("final_test_access") != "LOCKED"
    ):
        raise ValueError("COMPLETE locked historical universe attestation required")
    if payload.get("quality") not in ("PRELIMINARY", "VERIFIED"):
        raise ValueError("Explicit historical universe attestation quality required")
    if _time(payload.get("coverage_start")) > WINDOW_START:
        raise ValueError("Historical universe attestation starts after pre-Final window")
    if _time(payload.get("coverage_end")) < WINDOW_END:
        raise ValueError("Historical universe attestation ends before pre-Final window")


def load_obligations(path, *, expected_sha256, universe_attestation_path, universe_sha256):
    payload = _load_json_pinned(path, expected_sha256)
    if set(payload) != {
        "schema",
        "window_start",
        "window_end",
        "final_test_access",
        "universe_attestation_sha256",
        "obligations",
    }:
        raise ValueError("Market-data obligations schema fields are not exact")
    if (
        payload["schema"] != SCHEMA
        or payload["final_test_access"] != "LOCKED"
        or _time(payload["window_start"]) != WINDOW_START
        or _time(payload["window_end"]) != WINDOW_END
    ):
        raise ValueError("Frozen pre-Final market-data obligation identity required")
    if payload["universe_attestation_sha256"] != universe_sha256:
        raise ValueError("Obligations are not bound to the supplied universe attestation")
    universe = _load_json_pinned(universe_attestation_path, universe_sha256)
    _validate_universe_attestation(universe)

    rows = payload["obligations"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("Nonempty historical market-data obligations required")
    obligations = []
    identities = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"symbol", "start", "end"}:
            raise ValueError("Obligation fields must be symbol/start/end exactly")
        obligation = Obligation(row["symbol"], _time(row["start"]), _time(row["end"]))
        identity = (obligation.symbol, obligation.start, obligation.end)
        if identity in identities:
            raise ValueError("Duplicate market-data obligation")
        identities.add(identity)
        obligations.append(obligation)
    obligations.sort(key=lambda row: (row.symbol, row.start, row.end))
    return tuple(obligations), universe


def _months(obligation):
    current = obligation.start
    while current < obligation.end:
        request = ArchiveRequest(obligation.symbol, "klines", current.strftime("%Y-%m"), "1h")
        yield current.strftime("%Y-%m")
        current = request.end


def required_requests(obligations, capability):
    if capability not in CAPABILITIES:
        raise ValueError("Unsupported market-data capability")
    kind, interval = CAPABILITIES[capability]
    rows = set()
    for obligation in obligations:
        for month in _months(obligation):
            rows.add(ArchiveRequest(obligation.symbol, kind, month, interval))
    return tuple(
        sorted(rows, key=lambda row: (row.symbol, row.month, row.kind, row.interval or ""))
    )


def _load_acquisition(root, report_path, expected_dataset_hash, expected_config_hash):
    root, report_path = Path(root), Path(report_path)
    report = json.loads(report_path.read_text())
    if report.get("schema") != "PVB24_ARCHIVE_ACQUISITION_V1":
        raise ValueError("Archive acquisition report required")
    if report.get("dataset_hash") != expected_dataset_hash:
        raise ValueError("Pinned archive dataset hash changed")
    if dataset_hash(report.get("archives", [])) != expected_dataset_hash:
        raise ValueError("Archive dataset contents differ from pinned hash")
    if report.get("config_hash") != expected_config_hash:
        raise ValueError("Archive report config identity changed")
    if report.get("final_test_access") != "LOCKED":
        raise ValueError("Final Test must remain LOCKED")
    entries = {}
    for entry in report.get("archives", []):
        request = ArchiveRequest(**entry["request"])
        if request in entries:
            raise ValueError("Duplicate archive revision in selected acquisition report")
        entries[request] = entry
    return report, entries


def qualify_market_data(
    root,
    report_path,
    *,
    expected_dataset_hash,
    expected_config_hash,
    obligations_path,
    obligations_sha256,
    universe_attestation_path,
    universe_sha256,
):
    root = Path(root)
    obligations, universe = load_obligations(
        obligations_path,
        expected_sha256=obligations_sha256,
        universe_attestation_path=universe_attestation_path,
        universe_sha256=universe_sha256,
    )
    report, entries = _load_acquisition(
        root,
        report_path,
        expected_dataset_hash,
        expected_config_hash,
    )

    capabilities = {}
    for capability in CAPABILITIES:
        required = required_requests(obligations, capability)
        missing = []
        invalid = []
        verified = []
        for request in required:
            entry = entries.get(request)
            if entry is None:
                missing.append(request.filename)
                continue
            if (
                entry.get("status") != "ACQUIRED"
                or entry.get("quality") != "PRELIMINARY"
                or entry.get("coverage", {}).get("monthly_bar_grid_complete") is not True
                or entry.get("coverage", {}).get("gaps") != []
            ):
                invalid.append(request.filename)
                continue
            try:
                checked, _, _ = load_acquired(root, entry["attempt"])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                invalid.append(request.filename + ":" + type(exc).__name__)
                continue
            if checked != request:
                invalid.append(request.filename + ":REQUEST_MISMATCH")
                continue
            verified.append(request.filename)

        complete = not missing and not invalid and len(verified) == len(required)
        gaps = []
        if missing:
            gaps.append(f"missing_archives={len(missing)}")
        if invalid:
            gaps.append(f"invalid_archives={len(invalid)}")
        capabilities[capability] = {
            "required_archives": len(required),
            "verified_archives": len(verified),
            "missing_archives": missing,
            "invalid_archives": invalid,
            "complete": complete,
            "gaps": gaps,
        }

    result = {
        "schema": REPORT_SCHEMA,
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "final_test_access": "LOCKED",
        "quality": "PRELIMINARY",
        "dataset_hash": expected_dataset_hash,
        "archive_report_sha256": _sha256(report_path),
        "obligations_sha256": obligations_sha256,
        "universe_attestation_sha256": universe_sha256,
        "universe_quality": universe["quality"],
        "capabilities": capabilities,
        "performance_run": False,
        "operational_ready": False,
    }
    result["report_hash"] = digest(result)
    return json.loads(canonical(result))


def complete_attestations(report):
    if not isinstance(report, dict) or report.get("schema") != REPORT_SCHEMA:
        raise ValueError("Market-data capability report required")
    attestations = {}
    for capability in CAPABILITIES:
        row = report["capabilities"].get(capability)
        if not isinstance(row, dict) or row.get("complete") is not True:
            continue
        if row.get("missing_archives") or row.get("invalid_archives") or row.get("gaps"):
            raise ValueError("Complete market-data capability retains gaps")
        attestations[capability] = {
            "schema": ATTESTATION_SCHEMA,
            "capability": capability,
            "complete": True,
            "coverage_start": report["window_start"],
            "coverage_end": report["window_end"],
            "quality": "PRELIMINARY",
            "gaps": [],
            "final_test_access": "LOCKED",
            "source_report_hash": report["report_hash"],
            "dataset_hash": report["dataset_hash"],
            "obligations_sha256": report["obligations_sha256"],
            "universe_attestation_sha256": report["universe_attestation_sha256"],
        }
    return json.loads(canonical(attestations))
