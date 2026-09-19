"""Fail-closed paper configuration checks; no exchange calls."""


def require_paper(config: dict) -> None:
    if config.get("dry_run") is not True or config.get("live_enabled") is not False:
        raise ValueError("PVB24 requires dry_run=true and live_enabled=false")
    if config.get("trading_mode") != "futures" or config.get("margin_mode") != "isolated":
        raise ValueError("Only isolated futures are authorized")
    if config.get("exchange", {}).get("name") != "binance":
        raise ValueError("Only Binance USD-M is authorized")
    exchange = config["exchange"]
    for key in ("key", "api_key", "secret", "password", "uid", "privateKey"):
        if exchange.get(key):
            raise ValueError("Trading credentials are not permitted in PAPER configuration")
    if config.get("force_entry_enable") is not False:
        raise ValueError("Forced entries are prohibited")
    if config.get("order_time_in_force", {}).get("entry") != "IOC":
        raise ValueError("Entry must use IOC")
    order_types = config.get("order_types", {})
    if order_types.get("entry") != "limit" or order_types.get("stoploss") != "market":
        raise ValueError("Entry LIMIT and protective MARKET stop are required")
    if order_types.get("stoploss_price_type") != "last":
        raise ValueError("Stop trigger must use LAST/CONTRACT_PRICE")
