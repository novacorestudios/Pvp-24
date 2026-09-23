"""Fail-closed orchestration for the shared PVB-24 runtime.

This coordinator owns lifecycle wiring only.  It does not implement Alpha,
change frozen controls, or authorize an execution transport.
"""

from dataclasses import dataclass

from pvb24.integrations.execution_adapter import ExecutionAdapter
from pvb24.integrations.freqtrade_bridge import SharedPaperBridge, require_executor_config


@dataclass(frozen=True)
class RuntimeCycle:
    batch: object
    plan: object


class OperationalRuntime:
    """Wire recovery, market delivery, signals and planning through one authority."""

    def __init__(self, config, journal, scope):
        require_executor_config(config)
        self.config = config
        self.bridge = SharedPaperBridge(config, journal, scope)
        self.execution = ExecutionAdapter(self.bridge)
        self._started = False
        self._closed = False

    def start(self):
        if self._closed:
            raise RuntimeError("Runtime is closed")
        if self._started:
            raise RuntimeError("Runtime already started")
        require_executor_config(self.config)
        self._started = True
        return self

    def _guard(self):
        if not self._started or self._closed:
            raise RuntimeError("Runtime is not active")
        require_executor_config(self.config)
        self.bridge._guard()

    def bind_local_paper_model(
        self, backend, clock, *, max_protection_ack_age=None, protection_policy_id=None
    ):
        self._guard()
        self.bridge.bind_local_model(
            backend,
            clock,
            max_protection_ack_age=max_protection_ack_age,
            protection_policy_id=protection_policy_id,
        )

    def deliver(self, delivery):
        self._guard()
        return self.bridge.deliver(delivery)

    def cycle(self, universe, signal_time, inputs, now):
        self._guard()
        batch = self.bridge.evaluate(universe, signal_time, now)
        plan = self.bridge.plan(batch, inputs, now)
        return RuntimeCycle(batch, plan)

    def dispatch_local_entry(self, client_id, inputs, book):
        self._guard()
        return self.execution.submit_entry(client_id, inputs, book)

    def pump(self, *, max_actions=100, max_events=100):
        self._guard()
        if self.bridge.local_session is None:
            return None
        return self.execution.pump(max_actions=max_actions, max_events=max_events)

    def close(self):
        if self._closed:
            return
        self.bridge.close_local()
        self._closed = True
        self._started = False

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()
