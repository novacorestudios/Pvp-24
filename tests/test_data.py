from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from pvb24.data.availability import (
    order_timely,
    preliminary_entry_minute,
    preliminary_timing,
    timely_signal,
)
from pvb24.data.candles import causal_candles, warmup_complete
from pvb24.data.contract_rules import ContractRules, rules_at
from pvb24.data.schemas import Candle, Timing
from pvb24.data.universe import Security, build_universe
from pvb24.decimal_math import D
from pvb24.types import Quality

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def candle(start, duration=timedelta(hours=1), symbol="BTCUSDT", volume="60000000"):
    return Candle(
        symbol,
        preliminary_timing(start, start + duration, "synthetic-fixture", "v1"),
        D(100),
        D(101),
        D(99),
        D(100),
        D(volume),
    )


def security(symbol="BTCUSDT"):
    return Security(
        symbol,
        NOW - timedelta(days=300),
        NOW - timedelta(days=300),
        NOW - timedelta(days=300),
        "CRYPTO",
        True,
        "synthetic-fixture",
        "v1",
        True,
    )


def daily(symbol="BTCUSDT", volume="60000000"):
    return [
        candle(NOW - timedelta(days=i), timedelta(days=1), symbol, volume) for i in range(30, 0, -1)
    ]


def rules():
    return ContractRules(
        "BTCUSDT",
        NOW,
        NOW,
        "synthetic-fixture",
        "v1",
        D("0.1"),
        D("0.001"),
        D("0.001"),
        D(5),
        D(100),
        D(1),
        (),
        False,
        False,
    )


def test_period_data_cannot_be_available_before_close_or_receipt():
    with pytest.raises(ValueError):
        Timing(NOW, NOW, NOW + timedelta(hours=1), NOW, None, "fixture", "v1")
    with pytest.raises(ValueError):
        Timing(NOW, NOW, NOW, NOW, NOW + timedelta(seconds=1), "fixture", "v1", "snapshot")


def test_zero_is_not_missing_and_requires_source_confirmation():
    with pytest.raises(ValueError, match="Zero volume"):
        candle(NOW, volume="0")
    c = candle(NOW)
    zero = replace(c, quote_volume=D(0), zero_volume_confirmed=True)
    assert zero.quote_volume == 0
    with pytest.raises(TypeError):
        replace(c, close=100.0)


def test_no_current_candle_or_future_available_at():
    history = [candle(NOW + timedelta(hours=i)) for i in range(3)]
    decision = NOW + timedelta(hours=1, seconds=1)
    assert causal_candles(history, "BTCUSDT", timedelta(hours=1), decision) == []
    decision += timedelta(seconds=1)
    assert causal_candles(history, "BTCUSDT", timedelta(hours=1), decision) == history[:1]


def test_future_append_and_late_revision_do_not_change_past():
    c = candle(NOW)
    decision = NOW + timedelta(hours=1, seconds=2)
    corrected = replace(
        c,
        high=D(200),
        timing=replace(c.timing, available_at=NOW + timedelta(days=1), revision_id="v2"),
    )
    before = causal_candles([c], "BTCUSDT", timedelta(hours=1), decision)
    after = causal_candles(
        [c, corrected, candle(NOW + timedelta(hours=1))], "BTCUSDT", timedelta(hours=1), decision
    )
    assert before == after
    assert causal_candles(
        [c, corrected], "BTCUSDT", timedelta(hours=1), NOW + timedelta(days=1)
    ) == [corrected]


def test_same_time_conflicting_revision_fails_closed():
    c = candle(NOW)
    with pytest.raises(ValueError, match="Ambiguous"):
        causal_candles(
            [c, replace(c, high=D(200))], "BTCUSDT", timedelta(hours=1), NOW + timedelta(hours=2)
        )


def test_last_and_mark_are_never_mixed():
    last = candle(NOW)
    mark = replace(last, price_type="MARK", high=D(200))
    assert causal_candles(
        [last, mark], "BTCUSDT", timedelta(hours=1), NOW + timedelta(hours=2)
    ) == [last]


def test_gap_requires_full_new_30_day_window():
    rows = [candle(NOW + timedelta(hours=i)) for i in range(1500) if i != 750]
    first = [x for x in rows if x.timing.interval_end <= NOW + timedelta(hours=750)]
    assert warmup_complete(first, NOW + timedelta(hours=750))
    almost = [x for x in rows if x.timing.interval_end <= NOW + timedelta(hours=1470)]
    assert not warmup_complete(almost, NOW + timedelta(hours=1470))
    enough = [x for x in rows if x.timing.interval_end <= NOW + timedelta(hours=1471)]
    assert warmup_complete(enough, NOW + timedelta(hours=1471))


def test_exact_inclusive_deadlines_and_strict_next_minute():
    c = candle(NOW - timedelta(hours=1))
    assert timely_signal([c.timing], NOW, NOW + timedelta(seconds=30))
    assert not timely_signal([c.timing], NOW, NOW + timedelta(seconds=30, microseconds=1))
    assert order_timely(NOW, NOW + timedelta(seconds=90), NOW + timedelta(seconds=30))
    assert not order_timely(NOW, NOW + timedelta(seconds=91), NOW + timedelta(seconds=30))
    assert preliminary_entry_minute(NOW) == NOW + timedelta(minutes=1)
    assert preliminary_entry_minute(NOW + timedelta(seconds=2)) == NOW + timedelta(minutes=1)


def test_contract_rules_are_point_in_time():
    r = rules()
    revised = replace(r, tick=D(1), available_at=NOW + timedelta(days=1), revision_id="v2")
    assert rules_at([r, revised], "BTCUSDT", NOW) == r
    assert rules_at([r, revised], "BTCUSDT", NOW + timedelta(days=1)) == revised
    assert rules_at([r], "BTCUSDT", NOW - timedelta(seconds=1)) is None


def test_universe_is_historical_and_future_metadata_cannot_leak():
    decision = NOW + timedelta(minutes=5)
    base = build_universe([security()], daily(), decision, security_history_complete=True)
    future_delisting = replace(
        security(),
        active=False,
        available_at=NOW + timedelta(days=1),
        revision_id="v2",
        delisting_announcement_at=NOW + timedelta(days=1),
    )
    future_listing = replace(security("FUTUREUSDT"), available_at=NOW + timedelta(days=1))
    expanded = build_universe(
        [security(), future_delisting, future_listing],
        daily(),
        decision,
        security_history_complete=True,
    )
    assert expanded == base
    assert base.symbols == ("BTCUSDT",) and base.quality is Quality.VERIFIED


def test_universe_stale_grace_and_no_previous_list():
    u = build_universe(
        [security()], daily(), NOW + timedelta(minutes=5), security_history_complete=True
    )
    assert not u.allows("BTCUSDT", NOW)
    assert u.allows("BTCUSDT", NOW + timedelta(days=1, hours=1, minutes=5))
    assert not u.allows("BTCUSDT", NOW + timedelta(days=1, hours=1, minutes=5, microseconds=1))


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"classification": "STABLECOIN"}, "CLASSIFICATION_INELIGIBLE"),
        ({"classification": "UNKNOWN"}, "CLASSIFICATION_INELIGIBLE"),
        ({"trading_start": NOW - timedelta(days=89)}, "LISTING_AGE"),
        ({"active": False}, "INACTIVE"),
        ({"delisting_announcement_at": NOW}, "DELISTING_ANNOUNCED"),
    ],
)
def test_security_exclusion_reason_is_visible(change, reason):
    u = build_universe(
        [replace(security(), **change)],
        daily(),
        NOW + timedelta(minutes=5),
        security_history_complete=True,
    )
    assert not u.symbols and reason in u.excluded[0][1]


def test_volume_threshold_missing_day_and_survivorship_label():
    sec = [security()]
    d = NOW + timedelta(minutes=5)
    assert (
        build_universe(sec, daily(volume="50000000"), d, security_history_complete=False).quality
        is Quality.PRELIMINARY
    )
    assert not build_universe(
        sec, daily(volume="49999999"), d, security_history_complete=True
    ).symbols
    assert not build_universe(sec, daily()[:-1], d, security_history_complete=True).symbols


def test_deterministic_top20_without_current_ticker_ranking():
    names = [f"C{i:02d}USDT" for i in range(23)]
    rows = [row for name in names for row in daily(name)]
    u = build_universe(
        [security(x) for x in reversed(names)],
        list(reversed(rows)),
        NOW + timedelta(minutes=5),
        security_history_complete=True,
    )
    assert u.symbols == tuple(names[:20])
