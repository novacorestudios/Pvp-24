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


def test_reconciliation_result_controls_runtime_gate():
    runtime = OperationalRuntime.__new__(OperationalRuntime)
    runtime._started = True
    runtime._closed = False
    runtime._recovered = True
    runtime._reconciled = False
    runtime.bridge = SimpleNamespace()
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


def test_reconciliation_requires_restart_recovery_first():
    runtime = OperationalRuntime.__new__(OperationalRuntime)
    runtime._started = True
    runtime._closed = False
    runtime._recovered = False
    runtime.reconciliation = object()
    with pytest.raises(RuntimeError, match="recovery must complete"):
        runtime.reconcile_account("observation", "now")
