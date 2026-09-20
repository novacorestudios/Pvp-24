"""Strict exchange fixture for full pinned-framework lifecycle smoke only.

No public feed, venue fidelity or operational readiness is claimed. Unsupported
exchange access raises; every native order attempt fails and is counted.
"""

import pandas as pd


class OfflineExchange:
    name = "Binance"
    id = "binance"
    markets = {
        "BTC/USDT:USDT": {
            "symbol": "BTC/USDT:USDT",
            "base": "BTC",
            "quote": "USDT",
            "settle": "USDT",
            "active": True,
            "swap": True,
            "linear": True,
            "spot": False,
        }
    }

    def __init__(self):
        self.native_order_attempts = 0
        self.refreshes = 0
        self.closed = False

    def validate_config(self, config):
        from pvb24.integrations.freqtrade_bridge import require_executor_config

        require_executor_config(config)

    def get_proxy_coin(self):
        return "USDT"

    def get_markets(self, *args, **kwargs):
        return self.markets

    def market_is_tradable(self, market):
        return market["active"] and market["linear"] and market["swap"]

    def get_pair_quote_currency(self, pair):
        return self.markets[pair]["quote"]

    def get_option(self, name, default=None):
        return {"ohlcv_has_history": True, "funding_fee_timeframe": "8h"}.get(name, default)

    def exchange_has(self, feature):
        return feature == "fetchOHLCV"

    def reload_markets(self, *args, **kwargs):
        pass

    def refresh_latest_ohlcv(self, pairs, *args, **kwargs):
        self.refreshes += 1
        return {}

    def klines(self, *args, **kwargs):
        # Native OHLCVs intentionally cannot create Alpha or trades. Normalized
        # synthetic Decimal inputs enter the shared core separately in the smoke.
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    def ws_connection_reset(self):
        pass

    def create_order(self, *args, **kwargs):
        self.native_order_attempts += 1
        raise AssertionError("Native exchange orders are forbidden in shared PAPER smoke")

    def create_stoploss(self, *args, **kwargs):
        self.native_order_attempts += 1
        raise AssertionError("Native stop orders are forbidden in shared PAPER smoke")

    def close(self):
        self.closed = True
