from datetime import timedelta
from types import SimpleNamespace

import pytest

from pvb24.integrations.account_reconciliation_adapter import ReconciliationPolicy
from pvb24.operational_runtime import OperationalRuntime


def test_reconciliation_policy_is_explicit():
    policy = ReconciliationPolicy(timedelta(seconds=2), timedelta(seconds=1), True)
    assert policy.require_verified is True
    with pytest.raises(ValueError):
        ReconciliationPolicy(timedelta(seconds=-1), timedelta(0))


def test_runtime_guard_blocks_until_bound_reconciliation_is_ready():
    runtime = OperationalRuntime.__new__(OperationalRuntime)
    runtime._started = True
    runtime._closed = False
    runtime._recovered = True
    runtime._reconciled = False
    runtime.reconciliation = object()
    runtime.config = {
        "dry_run": True,
        "live_enabled": False,
        "trading_mode": "futures",
        "margin_mode": "isolated",
        "exchange": {"name": "binance"},
        "force_entry_enable": False,
        "order_time_in_force": {"entry": "IOC"},
        "order_types": {
            "entry": "limit",
            "stoploss": "market",
            "stoploss_price_type": "last",
        },
        "timeframe": "1h",
        "max_open_trades": 3,
        "trailing_stop": False,
        "position_adjustment_enable": False,
        "minimal_roi": {},
        "pvb24": {"operational_ready": False, "quality_mode": "VERIFIED"},
    }
    runtime.bridge = SimpleNamespace(local_session=None, _guard=lambda: None)
    with pytest.raises(RuntimeError, match="reconciliation must complete"):
        runtime._guard()


def test_reconciliation_result_controls_runtime_gate(monkeypatch):
    runtime = OperationalRuntime.__new__(OperationalRuntime)
    runtime._started = True
    runtime._closed = False
    runtime._recovered = True
    runtime._reconciled = False
    runtime.config = {}
    runtime.bridge = SimpleNamespace(local_session=None, _guard=lambda: None)
    monkeypatch.setattr("pvb24.operational_runtime.require_executor_config", lambda config: None)
    results = iter(
        [
            SimpleNamespace(entry_gate_ready=False),
            SimpleNamespace(entry_gate_ready=True),
        ]
    )
    runtime.reconciliation = SimpleNamespace(
        reconcile=lambda observed, now, reduction_models=None: next(results)
    )
    assert runtime.reconcile_account("observation", "now").entry_gate_ready is False
    assert runtime._reconciled is False
    assert runtime.reconcile_account("observation", "now").entry_gate_ready is True
    assert runtime._reconciled is True


def test_reconciliation_requires_restart_recovery_first(monkeypatch):
    runtime = OperationalRuntime.__new__(OperationalRuntime)
    runtime._started = True
    runtime._closed = False
    runtime._recovered = False
    runtime.config = {}
    runtime.bridge = SimpleNamespace(local_session=None, _guard=lambda: None)
    runtime.reconciliation = object()
    monkeypatch.setattr("pvb24.operational_runtime.require_executor_config", lambda config: None)
    with pytest.raises(RuntimeError, match="recovery must complete"):
        runtime.reconcile_account("observation", "now")


def test_reconciliation_gate_keeps_evidence_and_protective_pump_available(monkeypatch):
    runtime = OperationalRuntime.__new__(OperationalRuntime)
    runtime._started = True
    runtime._closed = False
    runtime._recovered = True
    runtime._reconciled = False
    runtime.reconciliation = object()
    runtime.config = {}
    delivered = []
    runtime.bridge = SimpleNamespace(
        local_session=object(),
        _guard=lambda: None,
        deliver=lambda value: delivered.append(value) or "delivered",
    )
    runtime.execution = SimpleNamespace(
        pump=lambda *, max_actions=100, max_events=100: ("pumped", max_actions, max_events)
    )
    monkeypatch.setattr("pvb24.operational_runtime.require_executor_config", lambda config: None)

    assert runtime.deliver("fresh-evidence") == "delivered"
    assert delivered == ["fresh-evidence"]
    assert runtime.pump(max_actions=7, max_events=9) == ("pumped", 7, 9)

    with pytest.raises(RuntimeError, match="reconciliation must complete"):
        runtime.dispatch_local_entry("cid", "inputs", "book")


def test_reconciliation_gate_blocks_new_strategy_cycle(monkeypatch):
    runtime = OperationalRuntime.__new__(OperationalRuntime)
    runtime._started = True
    runtime._closed = False
    runtime._recovered = True
    runtime._reconciled = False
    runtime.reconciliation = object()
    runtime.config = {}
    runtime.bridge = SimpleNamespace(local_session=None, _guard=lambda: None)
    monkeypatch.setattr("pvb24.operational_runtime.require_executor_config", lambda config: None)

    with pytest.raises(RuntimeError, match="reconciliation must complete"):
        runtime.cycle("universe", "signal-time", "inputs", "now")
