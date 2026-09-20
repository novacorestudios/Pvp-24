"""Shared signal/intent boundary for the pinned Freqtrade strategy loader.

No native dataframe Alpha, float-to-Decimal market coercion or network dispatch.
The pinned native dry-run create_order drops IOC/reduceOnly arguments; it cannot
serve as the PVB24 execution model without a separately validated transport.
"""

from pvb24.execution.planner import EntryPlanner
from pvb24.integrations.paper_dispatch import PaperDispatch
from pvb24.integrations.paper_session import PaperSession
from pvb24.replay.account import AccountReplay
from pvb24.safety import require_paper
from pvb24.strategy.service import SignalService
from pvb24.types import Quality


def require_executor_config(config):
    require_paper(config)
    if (
        config.get("timeframe") != "1h"
        or config.get("max_open_trades") != 3
        or config.get("trailing_stop") is not False
        or config.get("position_adjustment_enable") is not False
        or config.get("minimal_roi") != {}
    ):
        raise ValueError("Freqtrade config differs from frozen strategy controls")
    if config.get("pvb24", {}).get("operational_ready") is not False:
        raise ValueError("Operational PAPER transport is not yet qualified")
    Quality(config.get("pvb24", {}).get("quality_mode", "VERIFIED"))


class SharedPaperBridge:
    def __init__(self, config, journal, scope):
        require_executor_config(config)
        self.config, self.journal, self.scope = config, journal, scope
        self.quality = Quality(config.get("pvb24", {}).get("quality_mode", "VERIFIED"))
        self.account = AccountReplay(journal, scope, self.quality)
        self.signals = SignalService(journal, scope, self.quality)
        self.planner = EntryPlanner(journal, scope, self.quality)
        self.local_session = None

    def _guard(self):
        require_executor_config(self.config)
        if (
            Quality(self.config.get("pvb24", {}).get("quality_mode", "VERIFIED"))
            is not self.quality
        ):
            raise ValueError("Account quality mode cannot change after binding")
        if self.local_session is not None and self.config["pvb24"].get("execution_transport") != (
            "LOCAL_PRELIMINARY_L2"
        ):
            raise ValueError("Bound local PAPER transport configuration changed")

    def bind_local_model(
        self, backend, clock, *, max_protection_ack_age=None, protection_policy_id=None
    ):
        self._guard()
        if self.local_session is not None:
            raise ValueError("Local PAPER authority already bound")
        if self.config["pvb24"].get("execution_transport") != "LOCAL_PRELIMINARY_L2":
            raise ValueError("Explicit LOCAL_PRELIMINARY_L2 research transport required")
        host = PaperDispatch(self.journal, self.scope, self.quality, backend, clock)
        try:
            session = PaperSession(
                host,
                max_protection_ack_age=max_protection_ack_age,
                protection_policy_id=protection_policy_id,
            )
            session.recover()
        except BaseException:
            host.close()
            raise
        self.local_session = session

    def _local(self):
        self._guard()
        if self.local_session is None:
            raise RuntimeError("Local research PAPER model is not bound")
        return self.local_session

    def dispatch_local_entry(self, client_id, inputs, book):
        session = self._local()
        response = session.dispatch_entry(client_id, inputs, book)
        session.pump_actions()
        return response

    def pump_local(self, *, max_actions=100, max_events=100):
        return self._local().pump_actions(max_actions=max_actions, max_events=max_events)

    def close_local(self):
        if self.local_session is not None:
            self.local_session.host.close()

    def _drain_local(self):
        if self.local_session is not None and not self.local_session.recover().caught_up:
            raise RuntimeError("Drain local execution backlog before new core inputs")

    def deliver(self, delivery):
        self._guard()
        self._drain_local()
        return self.account(delivery)

    def evaluate(self, universe, signal_time, now):
        self._guard()
        self._drain_local()
        return self.signals.evaluate(universe, signal_time, now)

    def plan(self, batch, inputs, now):
        self._guard()
        self._drain_local()
        return self.planner.plan(batch, inputs, now)

    def dispatch(self, *args, **kwargs):
        raise RuntimeError(
            "PVB24 PAPER transport is not qualified; native dry-run is not substituted"
        )
