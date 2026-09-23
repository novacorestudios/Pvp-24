import json
from pathlib import Path

import pytest

from pvb24.operational_preflight import require_operational_package


ROOT = Path(__file__).resolve().parents[1]


def test_repository_operational_package_is_fail_closed():
    report = require_operational_package(ROOT)
    assert report.strategy_executor == "integrations/freqtrade/strategies/PVB24Executor.py"
    assert report.live_enabled is False
    assert report.paper_ready is False
    assert "performance-not-run" in report.checks


def _copy_package(tmp_path):
    for relative in (
        "integrations/freqtrade/config.pvb24.paper.json",
        "config/manifest.json",
        "integrations/freqtrade/strategies/PVB24Executor.py",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def test_preflight_rejects_live_enablement(tmp_path):
    _copy_package(tmp_path)
    path = tmp_path / "config/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["live_enabled"] = True
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="LIVE must remain disabled"):
        require_operational_package(tmp_path)


def test_preflight_rejects_paper_readiness_promotion(tmp_path):
    _copy_package(tmp_path)
    path = tmp_path / "config/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["paper_ready"] = True
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="cannot promote PAPER readiness"):
        require_operational_package(tmp_path)


def test_preflight_rejects_missing_strategy_executor(tmp_path):
    _copy_package(tmp_path)
    (tmp_path / "integrations/freqtrade/strategies/PVB24Executor.py").unlink()
    with pytest.raises(ValueError, match="Required operational package file missing"):
        require_operational_package(tmp_path)
