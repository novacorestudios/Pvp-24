from types import SimpleNamespace

import pytest

from pvb24.operational_runtime import OperationalRuntime


class Bridge:
    def __init__(self, session):
        self.local_session = session
        self.guards = 0
        self.closed = 0

    def _guard(self):
        self.guards += 1

    def close_local(self):
        self.closed += 1


class Execution:
    def __init__(self, recoveries):
        self.recoveries = iter(recoveries)
        self.calls = 0

    def recover(self, *, max_events=100):
        self.calls += 1
        return next(self.recoveries)


def runtime(session, recoveries=()):
    value = OperationalRuntime.__new__(OperationalRuntime)
    value.config = {
        "dry_run": True,
        "live_enabled": False,
        "timeframe": "1h",
        "max_open_trades": 3,
        "trailing_stop": False,
        "position_adjustment_enable": False,
        "minimal_roi": {},
        "pvb24": {"operational_ready": False, "quality_mode": "VERIFIED"},
    }
    value.bridge = Bridge(session)
    value.execution = Execution(recoveries)
    value._started = True
    value._closed = False
    value._recovered = False
    return value


def test_restart_blocks_operation_until_execution_recovery_finishes(monkeypatch):
    value = runtime(object(), [SimpleNamespace(caught_up=False, unresolved=())])
    monkeypatch.setattr("pvb24.operational_runtime.require_executor_config", lambda config: None)
    result = value.recover(max_events=7)
    assert not result.ready and value.execution.calls == 1
    with pytest.raises(RuntimeError, match="recovery must complete"):
        value._guard()


def test_restart_stays_blocked_for_unresolved_execution(monkeypatch):
    recovery = SimpleNamespace(caught_up=True, unresolved=("client-id",))
    value = runtime(object(), [recovery])
    monkeypatch.setattr("pvb24.operational_runtime.require_executor_config", lambda config: None)
    assert value.recover().ready is False
    with pytest.raises(RuntimeError, match="recovery must complete"):
        value._guard()


def test_restart_unlocks_only_after_caught_up_without_unresolved(monkeypatch):
    recovery = SimpleNamespace(caught_up=True, unresolved=())
    value = runtime(object(), [recovery])
    monkeypatch.setattr("pvb24.operational_runtime.require_executor_config", lambda config: None)
    result = value.recover()
    assert result.ready is True
    value._guard()


def test_runtime_without_bound_transport_has_no_execution_recovery_debt(monkeypatch):
    value = runtime(None)
    monkeypatch.setattr("pvb24.operational_runtime.require_executor_config", lambda config: None)
    result = value.recover()
    assert result.ready is True and result.execution is None
    value._guard()
