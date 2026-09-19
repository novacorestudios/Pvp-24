import copy
import json
from pathlib import Path

import pytest
from test_entry_planner import setup

from pvb24.execution.planner import EntryPlanner
from pvb24.ids import canonical
from pvb24.integrations.freqtrade_bridge import SharedPaperBridge, require_executor_config

ROOT = Path(__file__).resolve().parents[1]


def config():
    value = json.loads((ROOT / "integrations/freqtrade/config.pvb24.paper.json").read_text())
    value["pvb24"]["quality_mode"] = "PRELIMINARY"
    return value


def test_bridge_delegates_identical_signal_and_intent_logic_and_blocks_transport(tmp_path):
    db, _, _, universe, expected, inputs = setup(tmp_path)
    bridge = SharedPaperBridge(config(), db, "reference")
    batch = bridge.evaluate(universe, expected.decisions[0].signal_time, expected.decision_time)
    assert canonical(batch) == canonical(expected)
    result = bridge.plan(batch, inputs, batch.decision_time)
    assert result == EntryPlanner(db, "reference", bridge.quality).plan(
        batch, inputs, batch.decision_time
    )
    assert result[0]["reason"] == "ACCEPTED"
    with pytest.raises(RuntimeError, match="not qualified"):
        bridge.dispatch(result[0]["client_id"])
    assert (
        db.db.execute(
            "SELECT state FROM intents WHERE client_id=?", (result[0]["client_id"],)
        ).fetchone()[0]
        == "PREPARED"
    )
    db.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("dry_run", False),
        ("live_enabled", True),
        ("timeframe", "5m"),
        ("max_open_trades", 4),
        ("trailing_stop", True),
        ("position_adjustment_enable", True),
        ("minimal_roi", {"0": 0.1}),
    ],
)
def test_executor_rejects_live_and_nonbaseline_config(field, value):
    changed = copy.deepcopy(config())
    changed[field] = value
    with pytest.raises(ValueError):
        require_executor_config(changed)


def test_readiness_flag_cannot_bypass_unqualified_paper_transport():
    changed = config()
    changed["pvb24"]["operational_ready"] = True
    with pytest.raises(ValueError, match="not yet qualified"):
        require_executor_config(changed)


def test_bound_quality_cannot_be_changed_by_mutating_framework_config(tmp_path):
    db, _, _, universe, batch, _ = setup(tmp_path)
    changed = config()
    bridge = SharedPaperBridge(changed, db, "reference")
    changed["pvb24"]["quality_mode"] = "VERIFIED"
    with pytest.raises(ValueError, match="cannot change"):
        bridge.evaluate(universe, batch.decisions[0].signal_time, batch.decision_time)
    db.close()
