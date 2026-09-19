"""Exact canonical-record decoders shared by offline and paper boundaries."""

from datetime import datetime

from pvb24.accounting.ledger import FillRecord, FundingPayment
from pvb24.data.schemas import Candle, Mark, Timing
from pvb24.decimal_math import D
from pvb24.types import Fill, Side


def timing(raw):
    values = dict(raw)
    for key in ("event_time", "interval_start", "interval_end", "available_at", "received_at"):
        if values[key] is not None:
            values[key] = datetime.fromisoformat(values[key])
    return Timing(**values)


def candle(raw):
    values = dict(raw, timing=timing(raw["timing"]))
    for key in ("open", "high", "low", "close", "quote_volume"):
        values[key] = D(values[key])
    return Candle(**values)


def mark(raw):
    return Mark(raw["symbol"], D(raw["price"]), timing(raw["timing"]))


def fill_record(raw):
    values = dict(raw["fill"])
    values["side"] = Side(values["side"])
    for key in ("quantity", "price", "fee"):
        values[key] = D(values[key])
    for key in ("event_time", "received_at"):
        values[key] = datetime.fromisoformat(values[key])
    return FillRecord(Fill(**values), raw["exchange_sequence"], raw["liquidation"])


def funding(raw):
    values = dict(raw)
    values["side"] = Side(values["side"])
    for key in ("eligible_quantity", "mark_price", "final_rate"):
        values[key] = D(values[key])
    for key in ("settlement_time", "available_at"):
        values[key] = datetime.fromisoformat(values[key])
    return FundingPayment(**values)
