"""Freqtrade host for shared PVB24 signal/intent planning; transport remains gated."""

from freqtrade.strategy import IStrategy
from pandas import DataFrame

from pvb24.integrations.freqtrade_bridge import SharedPaperBridge, require_executor_config


class PVB24Executor(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    startup_candle_count = 720
    process_only_new_candles = True
    minimal_roi = {}
    trailing_stop = False
    position_adjustment_enable = False
    use_exit_signal = False
    # Freqtrade's required schema placeholder; never the PVB24 protective stop.
    # Native entry/exit paths are disabled below, so no trade uses this number.
    stoploss = -0.99

    def __init__(self, config):
        require_executor_config(config)
        super().__init__(config)
        self.shared = None

    def bot_start(self, **kwargs):
        require_executor_config(self.config)
        if self.timeframe != "1h" or self.startup_candle_count != 720:
            raise ValueError("Frozen timeframe/warmup cannot be overridden")

    def bot_loop_start(self, current_time, **kwargs):
        require_executor_config(self.config)
        if self.shared is not None and self.shared.local_session is not None:
            return self.shared.pump_local()

    def bind_local_paper_model(self, backend, clock):
        if self.shared is None:
            raise RuntimeError("Shared account must be initialized first")
        self.shared.bind_local_model(backend, clock)

    def dispatch_local_entry(self, client_id, inputs, book):
        if self.shared is None:
            raise RuntimeError("Shared account must be initialized first")
        return self.shared.dispatch_local_entry(client_id, inputs, book)

    def close_local_paper(self):
        if self.shared is not None:
            self.shared.close_local()

    def bind_shared_account(self, journal, scope):
        if self.shared is not None:
            raise ValueError("Shared account authority already bound")
        self.shared = SharedPaperBridge(self.config, journal, scope)

    def shared_batch(self, universe, signal_time, now):
        if self.shared is None:
            raise RuntimeError("Shared account must be initialized and reconciled first")
        return self.shared.evaluate(universe, signal_time, now)

    def plan_shared_batch(self, batch, inputs, now):
        if self.shared is None:
            raise RuntimeError("Shared account must be initialized and reconciled first")
        return self.shared.plan(batch, inputs, now)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Normalized causal Decimal candles enter shared.deliver, not this native
        # float-valued dataframe. There is no second Alpha implementation here.
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    def confirm_trade_entry(self, *args, **kwargs) -> bool:
        # Native Freqtrade entry must not duplicate the shared intent authority.
        return False

    def confirm_trade_exit(self, *args, **kwargs) -> bool:
        return False
