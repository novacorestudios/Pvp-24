import pytest

from pvb24.operational_runtime import OperationalRuntime


class Config(dict):
    pass


def _config():
    return Config(
        timeframe="1h",
        max_open_trades=3,
        trailing_stop=False,
        position_adjustment_enable=False,
        minimal_roi={},
        dry_run=True,
        live_enabled=False,
        pvb24={
            "operational_ready": False,
            "quality_mode": "VERIFIED",
            "execution_transport": "BLOCKED_UNTIL_QUALIFIED",
        },
    )


def test_runtime_is_fail_closed_before_start():
    runtime = OperationalRuntime.__new__(OperationalRuntime)
    runtime._started = False
    runtime._closed = False
    with pytest.raises(RuntimeError, match="not active"):
        runtime._guard()


def test_runtime_rejects_live_config():
    config = _config()
    config["dry_run"] = False
    with pytest.raises(ValueError):
        OperationalRuntime(config, object(), "paper")


def test_runtime_close_is_idempotent():
    runtime = OperationalRuntime.__new__(OperationalRuntime)
    runtime._started = True
    runtime._closed = False

    class Bridge:
        calls = 0

        def close_local(self):
            self.calls += 1

    runtime.bridge = Bridge()
    runtime.close()
    runtime.close()
    assert runtime.bridge.calls == 1
    assert runtime._closed is True
    assert runtime._started is False
