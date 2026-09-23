"""Fail-closed orchestration for the shared PVB-24 runtime.

This coordinator owns lifecycle wiring only.  It does not implement Alpha,
change frozen controls, or authorize an execution transport.
"""

from dataclasses import dataclass

from pvb24.integrations.account_reconciliation_adapter import AccountReconciliationAdapter
from pvb24.integrations.execution_adapter import ExecutionAdapter
from pvb24.integrations.freqtrade_bridge import SharedPaperBridge, require_executor_config


@dataclass(frozen=True)
class RuntimeCycle:
    batch: object
    plan: object


@dataclass(frozen=True)
class RuntimeRecovery:
    execution: object | None
    ready: bool


class OperationalRuntime:
    """Wire recovery, market delivery, signals and planning through one authority."""

    def __init__(self, config, journal, scope):
        require_executor_config(config)
        self.config = config
        self.bridge = SharedPaperBridge(config, journal, scope)
        self.execution = ExecutionAdapter(self.bridge)
        self._started = False
        self._closed = False
        self._recovered = False
        self.reconciliation = None
        self._reconciled = False

    def start(self):
        if self._closed:
            raise RuntimeError("Runtime is closed")
        if self._started:
            raise RuntimeError("Runtime already started")
        require_executor_config(self.config)
        self._started = True
        # Core delivery/planning may run without a transport.  Once a durable
        # PAPER session is bound, recovery becomes mandatory before operation.
        self._recovered = self.bridge.local_session is None
        self._reconciled = self.reconciliation is None
        return self

    def _base_guard(self):
        if not self._started or self._closed:
            raise RuntimeError("Runtime is not active")
        require_executor_config(self.config)
        self.bridge._guard()
        if self.bridge.local_session is not None and not self._recovered:
            raise RuntimeError("Runtime recovery must complete before operation")

    def _guard(self):
        self._base_guard()
        if self.reconciliation is not None and not self._reconciled:
            raise RuntimeError("Account reconciliation must complete before operation")

    def bind_local_paper_model(
        self, backend, clock, *, max_protection_ack_age=None, protection_policy_id=None
    ):
        self._base_guard()
        self.bridge.bind_local_model(
            backend,
            clock,
            max_protection_ack_age=max_protection_ack_age,
            protection_policy_id=protection_policy_id,
        )
        self._recovered = False

    def recover(self, *, max_events=100):
        if not self._started or self._closed:
            raise RuntimeError("Runtime is not active")
        require_executor_config(self.config)
        self.bridge._guard()
        if self.bridge.local_session is None:
            self._recovered = True
            return RuntimeRecovery(None, True)
        recovery = self.execution.recover(max_events=max_events)
        self._recovered = recovery.caught_up and not recovery.unresolved
        return RuntimeRecovery(recovery, self._recovered)

    def bind_account_reconciliation(self, policy):
        if not self._started or self._closed:
            raise RuntimeError("Runtime is not active")
        require_executor_config(self.config)
        self.bridge._guard()
        if self.reconciliation is not None:
            raise RuntimeError("Account reconciliation already bound")
        self.reconciliation = AccountReconciliationAdapter(
            self.bridge.journal, self.bridge.scope, policy
        )
        self._reconciled = False

    def reconcile_account(self, observed, now, *, reduction_models=None):
        self._base_guard()
        if not self._recovered:
            raise RuntimeError("Runtime recovery must complete before reconciliation")
        if self.reconciliation is None:
            raise RuntimeError("Account reconciliation is not bound")
        result = self.reconciliation.reconcile(observed, now, reduction_models=reduction_models)
        self._reconciled = result.entry_gate_ready
        return result

    def deliver(self, delivery):
        # Evidence delivery must remain available while new entries are paused by
        # account reconciliation; otherwise stale state could prevent recovery.
        self._base_guard()
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
        # Safety-critical protection/exit actions must continue while the
        # reconciliation entry gate is closed.
        self._base_guard()
        if self.bridge.local_session is None:
            return None
        return self.execution.pump(max_actions=max_actions, max_events=max_events)

    def close(self):
        if self._closed:
            return
        self.bridge.close_local()
        self._closed = True
        self._started = False
        self._recovered = False
        self._reconciled = False

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()
