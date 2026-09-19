import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_data import NOW, candle

from pvb24.decimal_math import D
from pvb24.ids import canonical
from pvb24.strategy.exits import Entry, Exits
from pvb24.types import Side


def engine(side=Side.LONG, first_fill=None):
    return Exits(
        Entry(
            "position",
            "BTCUSDT",
            side,
            first_fill or NOW + timedelta(minutes=10),
            D(100),
            D(98) if side is Side.LONG else D(102),
            D("99.5") if side is Side.LONG else D(101),
            D(99) if side is Side.LONG else D("100.5"),
            D("0.1"),
        )
    )


def hourly(index, close, high=None, low=None):
    row = candle(NOW + timedelta(hours=index - 1))
    value = D(close)
    return replace(
        row,
        open=value,
        close=value,
        high=D(high) if high else value + D(1),
        low=D(low) if low else value - D(1),
    )


def push(e, index, close, atr="1", last=None, **kwargs):
    row = hourly(index, close, **kwargs)
    return e.push(row, D(atr), row.timing.available_at, D(last or close))


@pytest.mark.parametrize("side,close", [(Side.LONG, "99.5"), (Side.SHORT, "100.5")])
def test_early_failure_inclusive_first_three_eligible_closes(side, close):
    for failure_index in (1, 2, 3):
        e = engine(side)
        for index in range(1, failure_index):
            assert push(e, index, "100").reason is None
        result = push(e, failure_index, close)
        assert result.reason == "EARLY_FAILURE"
        assert result.eligible_close_number == failure_index
    e = engine(side)
    for index in range(1, 4):
        push(e, index, "100")
    assert push(e, 4, close).reason is None


def test_equal_time_and_pre_fill_candles_do_not_count():
    e = engine(first_fill=NOW + timedelta(hours=1))
    row = hourly(1, "1", high="1000", low="1")
    assert e.push(row, D(1), row.timing.available_at, D(100)) is None
    assert e.count == 0
    assert push(e, 2, "100").eligible_close_number == 1


@pytest.mark.parametrize(
    "side,close,stop", [(Side.LONG, "104", "101.1"), (Side.SHORT, "96", "98.9")]
)
def test_trailing_activates_exact_2r_uses_closes_and_is_not_retroactive(side, close, stop):
    e = engine(side)
    old = e.effective_stop
    result = push(e, 1, close, atr="0.99", high="1000", low="1")
    assert result.trailing_active and result.proposed_stop == D(stop)
    assert result.reason is None
    assert e.effective_stop == old
    with pytest.raises(ValueError, match="backdated"):
        e.acknowledge_stop(D(stop), NOW + timedelta(hours=1))
    ack_time = result.decided_at + timedelta(milliseconds=20)
    e.acknowledge_stop(D(stop), ack_time)
    assert e.effective_stop == D(stop) and e.effective_at == ack_time
    with pytest.raises(ValueError, match="backdated"):
        e.acknowledge_stop(D(stop), result.decided_at)


def test_high_low_touches_never_activate_trailing_before_close():
    e = engine()
    result = push(e, 1, "103.999", high="1000", low="1")
    assert not result.trailing_active and result.proposed_stop is None


@pytest.mark.parametrize(
    "side,first,second", [(Side.LONG, "104", "104.5"), (Side.SHORT, "96", "95.5")]
)
def test_expanding_atr_never_widens_confirmed_or_pending_stop(side, first, second):
    e = engine(side)
    a = push(e, 1, first)
    proposed = a.proposed_stop
    assert push(e, 2, second, atr="3").proposed_stop is None
    assert e.proposed_stop == proposed
    e.acknowledge_stop(proposed, NOW + timedelta(hours=2, seconds=3))
    assert push(e, 3, second, atr="5").proposed_stop is None
    assert e.effective_stop == proposed


def test_stop_already_crossed_at_actual_decision_requests_full_exit():
    e = engine()
    result = push(e, 1, "104", last="101")
    assert result.reason == "TRAILING_TRIGGER_CROSSED"
    assert result.proposed_stop is None
    assert e.effective_stop == 98


@pytest.mark.parametrize("side,close", [(Side.LONG, "100.9"), (Side.SHORT, "99.1")])
def test_weak_followthrough_only_on_sixth_close_not_intrabar_mfe(side, close):
    e = engine(side)
    for index in range(1, 6):
        assert push(e, index, close, high="200", low="1").reason is None
    result = push(e, 6, close, high="200", low="1")
    assert result.reason == "WEAK_FOLLOWTHROUGH"
    assert result.close_mfe == D("0.9")


@pytest.mark.parametrize("side,close", [(Side.LONG, "101"), (Side.SHORT, "99")])
def test_exact_half_r_is_not_weak_followthrough(side, close):
    e = engine(side)
    for index in range(1, 7):
        result = push(e, index, close)
    assert result.reason is None and result.close_mfe == 1


def test_maximum_hold_is_actual_first_fill_plus_72h_even_without_candles():
    first = NOW + timedelta(minutes=10, seconds=13)
    e = engine(first_fill=first)
    assert e.timer(first + timedelta(hours=72) - timedelta(microseconds=1)) is None
    result = e.timer(first + timedelta(hours=72))
    assert result.reason == "MAXIMUM_HOLD" and result.decided_at == first + timedelta(hours=72)
    assert e.timer(first + timedelta(hours=80)) == result


def test_gap_is_not_counted_as_next_close_and_timer_still_works():
    e = engine()
    push(e, 1, "100")
    with pytest.raises(ValueError, match="Missing/revised"):
        push(e, 3, "100")
    assert e.count == 1
    assert e.timer(NOW + timedelta(hours=73)).reason == "MAXIMUM_HOLD"


def test_checkpoint_replay_duplicate_and_future_data_do_not_change_past():
    e = engine()
    first = push(e, 1, "104")
    e.acknowledge_stop(first.proposed_stop, first.decided_at + timedelta(milliseconds=20))
    restored = Exits.restore(json.loads(canonical(e.checkpoint())))
    assert canonical(e.checkpoint()) == canonical(restored.checkpoint())
    assert push(restored, 1, "104") == first
    assert restored.count == 1
    a = push(e, 2, "105")
    b = push(restored, 2, "105")
    assert a == b and first.proposed_stop == 101
    future = hourly(3, "110")
    with pytest.raises(ValueError, match="causally"):
        restored.push(future, D(1), a.decided_at, D(110))
    assert restored.count == 2


def test_last_price_and_atr_reject_float_inputs():
    with pytest.raises(TypeError):
        e = engine()
        row = hourly(1, "100")
        e.push(row, 1.0, row.timing.available_at, D(100))
