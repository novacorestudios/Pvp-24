"""Fail-closed packaging preflight for a deployable PVB-24 PAPER process.

This module validates immutable repository/runtime wiring only. It does not
connect to an exchange, run strategy performance, or authorize LIVE trading.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pvb24.integrations.freqtrade_bridge import require_executor_config


@dataclass(frozen=True)
class PreflightReport:
    strategy_executor: str
    config: str
    manifest: str
    strategy_config: str
    live_enabled: bool
    paper_ready: bool
    checks: tuple[str, ...]


def _load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def require_operational_package(root: str | Path) -> PreflightReport:
    """Validate the checked-out package without weakening readiness gates."""
    root = Path(root).resolve()
    config_path = root / "integrations/freqtrade/config.pvb24.paper.json"
    manifest_path = root / "config/manifest.json"
    strategy_config_path = root / "config/pvb24_v1.json"
    strategy_path = root / "integrations/freqtrade/strategies/PVB24Executor.py"

    for path in (config_path, manifest_path, strategy_config_path, strategy_path):
        if not path.is_file():
            raise ValueError(f"Required operational package file missing: {path.relative_to(root)}")

    config = _load_object(config_path)
    manifest = _load_object(manifest_path)
    strategy_config = _load_object(strategy_config_path)

    pvb24 = config.get("pvb24")
    if not isinstance(pvb24, dict):
        raise ValueError("PAPER config requires a pvb24 control block")
    if pvb24.get("operational_ready") is not False:
        raise ValueError("Packaging preflight cannot promote operational readiness")
    if pvb24.get("execution_transport") != "BLOCKED_UNTIL_QUALIFIED":
        raise ValueError("Execution transport must remain blocked until qualified")
    if pvb24.get("config_purpose") != "SHARED_STRATEGY_LOAD_AND_PARITY_ONLY":
        raise ValueError("PAPER config purpose changed outside the qualified operational scope")

    require_executor_config(config)

    canonical = json.dumps(
        strategy_config, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != manifest.get("config_hash"):
        raise ValueError("Frozen strategy configuration checksum mismatch")
    if strategy_config.get("mode") != "PAPER" or strategy_config.get("live_enabled") is not False:
        raise ValueError("Frozen strategy configuration must remain PAPER-only")
    if strategy_config.get("timezone") != "UTC":
        raise ValueError("Frozen strategy configuration must remain UTC")
    if strategy_config.get("freqtrade") != manifest.get("freqtrade"):
        raise ValueError("Frozen strategy and manifest Freqtrade pins differ")

    signal = strategy_config.get("signal", {})
    risk = strategy_config.get("risk", {})
    execution = strategy_config.get("execution", {})
    exit_config = strategy_config.get("exit", {})
    if signal.get("timeframe_seconds") != 3600 or config.get("timeframe") != "1h":
        raise ValueError("Operational timeframe differs from frozen strategy")
    if risk.get("max_positions") != config.get("max_open_trades"):
        raise ValueError("Operational position capacity differs from frozen strategy")
    if (
        execution.get("entry_type") != "LIMIT"
        or execution.get("entry_tif") != "IOC"
        or execution.get("margin_mode") != "ISOLATED"
        or exit_config.get("stop_reference") != "CONTRACT_PRICE"
    ):
        raise ValueError("Operational execution controls differ from frozen strategy")

    if config.get("strategy") != "PVB24Executor":
        raise ValueError("PAPER config must select PVB24Executor")
    if manifest.get("branch") != "build/pvb24-v1":
        raise ValueError("Operational package must remain bound to build/pvb24-v1")
    if manifest.get("freeze_status") != "FROZEN_BEFORE_PERFORMANCE":
        raise ValueError("Frozen pre-performance provenance is required")
    if manifest.get("performance_runs") != 0:
        raise ValueError("Packaging preflight cannot follow a performance run")
    if manifest.get("live_enabled") is not False:
        raise ValueError("LIVE must remain disabled")
    if manifest.get("paper_ready") is not False:
        raise ValueError("Packaging preflight cannot promote PAPER readiness")
    if not manifest.get("source_sha256") or not manifest.get("config_hash"):
        raise ValueError("Frozen source/config provenance is required")

    executor = strategy_path.read_text(encoding="utf-8")
    if "class PVB24Executor" not in executor:
        raise ValueError("Pinned PVB24Executor strategy class is missing")

    return PreflightReport(
        strategy_executor=str(strategy_path.relative_to(root)),
        config=str(config_path.relative_to(root)),
        manifest=str(manifest_path.relative_to(root)),
        strategy_config=str(strategy_config_path.relative_to(root)),
        live_enabled=False,
        paper_ready=False,
        checks=(
            "paper-config-fail-closed",
            "frozen-config-hash-verified",
            "paper-mode-pinned",
            "utc-timebase-pinned",
            "operational-controls-cross-checked",
            "strategy-executor-present",
            "strategy-selection-pinned",
            "execution-transport-blocked",
            "operational-readiness-not-promoted",
            "frozen-provenance-present",
            "performance-not-run",
            "live-disabled",
            "paper-readiness-not-promoted",
        ),
    )
