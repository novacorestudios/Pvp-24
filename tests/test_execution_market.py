from dataclasses import replace
from datetime import timedelta

import pytest
from test_data import NOW, candle

from pvb24.decimal_math import D
from pvb24.execution.book import Book
from pvb24.execution.market import EntryBounds, minute_inputs, preliminary_proxy, preview_ioc
from pvb24.types import Quality, Side


def book():
    b = Book("BTCUSDT")
    b.snapshot(
        100,
        [(D("99.98"), D(10)), (D("99.9"), D(10))],
        [(D(100), D(2)), (D("100.08"), D(2)), (D("100.2"), D(10))],
        NOW,
        NOW,
    )
    b.update(99, 101, 98, [], [], NOW, NOW)
    return b


def bounds(side=Side.LONG, **kwargs):
    values = dict(
        symbol="BTCUSDT",
        side=side,
        signal_time=NOW,
        signal_close=D(100),
        channel=D("99.5") if side is Side.LONG else D("100.5"),
        atr_previous=D(1),
        tick=D("0.01"),
    )
    return EntryBounds(**(values | kwargs))


def preview(b=None, bound=None, **kwargs):
    args = dict(
        book=b or book(),
        bounds=bound or bounds(),
        quantity=D(5),
        recent_quote_volume=D(1000000),
        decision=NOW,
        sent=NOW,
    )
    return preview_ioc(**(args | kwargs))


def test_snapshot_needs_bridge_then_previous_sequence_continuity():
    b = Book("BTCUSDT")
    b.snapshot(100, [(D(99), D(1))], [(D(100), D(1))], NOW, NOW)
    assert not b.fresh(NOW)
    b.update(99, 101, 98, [], [], NOW, NOW)
    assert b.fresh(NOW)
    with pytest.raises(ValueError, match="sequence gap"):
        b.update(102, 103, 99, [], [], NOW, NOW)
    assert not b.fresh(NOW)
    with pytest.raises(ValueError, match="Snapshot required"):
        b.update(103, 104, 103, [], [], NOW, NOW)


def test_depth_is_absolute_zero_delete_and_missing_delete_is_normal():
    b = book()
    b.update(102, 102, 101, [(D("99.9"), D(3)), (D(50), D(0))], [(D("100.2"), D(0))], NOW, NOW)
    assert b.bids[D("99.9")] == 3
    assert D("100.2") not in b.asks


def test_invalid_update_crossed_book_and_malformed_numbers_fail_closed():
    b = book()
    with pytest.raises(ValueError, match="crossed"):
        b.update(102, 102, 101, [(D(101), D(3))], [], NOW, NOW)
    assert not b.fresh(NOW)
    b = book()
    with pytest.raises(TypeError):
        b.update(102, 102, 101, [(99.0, D(3))], [], NOW, NOW)
    assert not b.fresh(NOW)


def test_both_event_and_receipt_age_inclusive_and_no_future_book():
    b = book()
    assert b.fresh(NOW + timedelta(milliseconds=500))
    assert not b.fresh(NOW + timedelta(microseconds=500001))
    assert not b.fresh(NOW - timedelta(microseconds=1))
    b.update(102, 102, 101, [], [], NOW, NOW + timedelta(milliseconds=400))
    assert not b.fresh(NOW + timedelta(milliseconds=600))  # receipt fresh, event stale


def test_worst_fill_cap_and_partial_ioc_without_chasing():
    r = preview()
    assert r.reason == "ACCEPTED"
    assert r.limit == D("100.10")
    assert r.sweep.filled == 4 and r.sweep.requested == 5
    assert r.sweep.vwap == D("100.04")
    assert all(f.price <= r.limit for f in r.sweep.fills)


def test_consumed_depth_cannot_be_reused_until_that_level_is_updated():
    b = book()
    first = b.sweep(Side.LONG, D(4), D("100.1"), consume=True)
    assert first.filled == 4
    assert b.sweep(Side.LONG, D(4), D("100.1")).filled == 0
    b.update(102, 102, 101, [(D("99.9"), D(20))], [], NOW, NOW)
    assert b.sweep(Side.LONG, D(4), D("100.1")).filled == 0
    assert not b.update(102, 102, 101, [], [(D(100), D(999))], NOW, NOW)
    assert b.sweep(Side.LONG, D(4), D("100.1")).filled == 0
    b.update(103, 103, 102, [], [(D(100), D(3))], NOW, NOW)
    assert b.sweep(Side.LONG, D(4), D("100.1")).filled == 3


@pytest.mark.parametrize("haircut,filled", [("0.5", "2"), ("0.75", "1")])
def test_depth_haircut_consumption_is_not_repeated(haircut, filled):
    b = book()
    assert b.sweep(Side.LONG, D(10), D("100.1"), consume=True, haircut=D(haircut)).filled == D(
        filled
    )
    assert b.sweep(Side.LONG, D(10), D("100.1"), haircut=D(haircut)).filled == 0


def test_short_cap_rounds_up_and_long_cap_rounds_down_without_widening():
    assert bounds(tick=D("0.03")).ioc_limit(D(100)) == D("100.08")
    short = bounds(Side.SHORT, tick=D("0.03"))
    assert short.ioc_limit(D("99.98")) == D("99.9")
    assert preview(bound=short).sweep.filled == 5
    with pytest.raises(ValueError, match="marketable"):
        bounds(tick=D(1)).ioc_limit(D("100.01"))


def test_spread_participation_chasing_and_deadline_rejections():
    b = book()
    b.update(102, 102, 101, [(D("99.98"), D(0))], [], NOW, NOW)
    assert preview(b=b).reason == "SPREAD"
    assert preview(recent_quote_volume=D(100)).reason == "PARTICIPATION"
    assert preview(bound=bounds(channel=D(100))).reason == "BREAKOUT_OR_CHASING"
    assert preview(bound=bounds(signal_close=D(101))).reason == "BREAKOUT_OR_CHASING"
    assert preview(sent=NOW + timedelta(seconds=91)).reason == "IDENTITY_OR_DEADLINE"
    assert bounds().timely(NOW, NOW + timedelta(seconds=90))
    assert not bounds().timely(NOW, NOW + timedelta(seconds=90, microseconds=1))


def test_proxy_floor_stop_multiplier_and_no_verified_book_claim():
    long = preliminary_proxy(D(100), D(1), Side.LONG, D(0), D(1000000))
    short = preliminary_proxy(D(100), D(1), Side.SHORT, D(0), D(1000000))
    stop = preliminary_proxy(D(100), D(1), Side.SHORT, D(0), D(1000000), stop_exit=True)
    assert long.price == D("100.05") and short.price == D("99.95")
    assert stop.price == D("99.925")
    assert long.impact == D("0.00025") and long.stop_slippage == D("0.00075")
    assert long.quality is Quality.PRELIMINARY and len(long.unverified) == 4


def test_proxy_quantity_changes_impact_and_zero_volume_rejected():
    a = preliminary_proxy(D(100), D(1), Side.LONG, D("0.1"), D(10000))
    b = preliminary_proxy(D(100), D(4), Side.LONG, D("0.1"), D(10000))
    assert b.impact == 2 * a.impact
    with pytest.raises(ValueError):
        preliminary_proxy(D(100), D(1), Side.LONG, D(0), D(0))


def minutes():
    return [
        candle(NOW - timedelta(minutes=i), timedelta(minutes=1), volume="1000")
        for i in range(16, 0, -1)
    ]


def test_minute_proxy_requires_16_closes_uses_only_15_volumes_no_future():
    rows = minutes()
    decision = NOW + timedelta(seconds=2)
    rows[0] = replace(rows[0], quote_volume=D(999999))
    assert minute_inputs(rows, "BTCUSDT", decision) == (D(0), D(15000))
    future = candle(NOW, timedelta(minutes=1), volume="9999999")
    assert minute_inputs(rows + [future], "BTCUSDT", decision) == (D(0), D(15000))
    for missing in (rows[1:], rows[:-1], rows[:5] + rows[6:]):
        with pytest.raises(ValueError):
            minute_inputs(missing, "BTCUSDT", decision)
    with pytest.raises(ValueError):
        minute_inputs(rows, "BTCUSDT", NOW + timedelta(seconds=1))
