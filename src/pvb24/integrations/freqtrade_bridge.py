"""Shared signal/intent boundary for the pinned Freqtrade strategy loader.

No native dataframe Alpha, float-to-Decimal market coercion or network dispatch.
The pinned native dry-run create_order drops IOC/reduceOnly arguments; it cannot
serve as the PVB24 execution model without a separately validated transport.
"""

from pvb24.execution.planner import EntryPlanner
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

    def _guard(self):
        require_executor_config(self.config)
        if (
            Quality(self.config.get("pvb24", {}).get("quality_mode", "VERIFIED"))
            is not self.quality
        ):
            raise ValueError("Account quality mode cannot change after binding")

    def deliver(self, delivery):
        self._guard()
        return self.account(delivery)

    def evaluate(self, universe, signal_time, now):
        self._guard()
        return self.signals.evaluate(universe, signal_time, now)

    def plan(self, batch, inputs, now):
        self._guard()
        return self.planner.plan(batch, inputs, now)

    def dispatch(self, *args, **kwargs):
        raise RuntimeError(
            "PVB24 PAPER transport is not qualified; native dry-run is not substituted"
        )
