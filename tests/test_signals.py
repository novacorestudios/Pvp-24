import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from pvb24.data.availability import preliminary_timing
from pvb24.data.schemas import Candle
from pvb24.data.universe import Universe
from pvb24.decimal_math import D
from pvb24.ids import canonical
from pvb24.strategy.atr import WilderATR
from pvb24.strategy.signals import Indicators, decide, rank_signals, signal_batch
from pvb24.types import Quality, Side

START = datetime(2024, 1, 1, tzinfo=UTC)


def candle(index, close="100", volume="100", symbol="BTCUSDT", high=None, low=None):
    start = START + timedelta(hours=index)
    c = D(close)
    return Candle(
        symbol,
        preliminary_timing(start, start + timedelta(hours=1), "synthetic-signal-fixture", "v1"),
        D(100),
        D(high) if high is not None else max(D(101), c),
        D(low) if low is not None else min(D(99), c),
        c,
        D(volume),
    )


def warmed(symbol="BTCUSDT"):
    engine = Indicators(symbol)
    for i in range(720):
        c = candle(i, symbol=symbol)
        engine.push(c, c.timing.available_at)
    return engine


def universe(when, symbols=("BTCUSDT",)):
    return Universe(
        "synthetic-universe",
        when - timedelta(hours=1),
        when + timedelta(days=1),
        symbols,
        tuple((x, D("60000000")) for x in symbols),
        (),
        Quality.PRELIMINARY,
        "synthetic-inputs",
    )


def next_frame(engine, index=720, **kwargs):
    c = candle(index, symbol=engine.symbol, **kwargs)
    return engine.push(c, c.timing.available_at)


def test_atr_golden_seed_then_wilder_not_sma():
    atr = WilderATR()
    for _ in range(23):
        assert atr.update(D(101), D(99), D(100)) is None
    assert atr.update(D(101), D(99), D(100)) == D(2)
    assert atr.update(D(125), D(99), D(100)) == D(3)
    assert WilderATR.restore(json.loads(canonical(atr.checkpoint()))).value == D(3)


@pytest.mark.parametrize("side,close", [(Side.LONG, "101.21"), (Side.SHORT, "98.79")])
def test_golden_breakout_and_long_short_symmetry(side, close):
    engine = warmed()
    frame = next_frame(engine, close=close, volume="150")
    signal = decide(frame, side, universe(frame.evaluated_at), frame.evaluated_at)
    assert signal.accepted
    assert frame.channel_high == D(101) and frame.channel_low == D(99)
    assert frame.atr_previous == D(2) and frame.rvol == D("1.5")
    assert not decide(
        frame,
        Side.SHORT if side is Side.LONG else Side.LONG,
        universe(frame.evaluated_at),
        frame.evaluated_at,
    ).accepted


@pytest.mark.parametrize("side,close", [(Side.LONG, "101.2"), (Side.SHORT, "98.8")])
def test_breakout_price_equality_is_not_strict_breakout(side, close):
    frame = next_frame(warmed(), close=close, volume="150")
    assert (
        "NO_NEW_BREAKOUT"
        in decide(frame, side, universe(frame.evaluated_at), frame.evaluated_at).rejection_codes
    )


def test_current_high_and_current_volume_are_excluded_from_references():
    engine = warmed()
    frame = next_frame(engine, close="102", high="300", volume="1000")
    assert frame.channel_high == D(101)
    assert frame.atr_previous == D(2)
    assert frame.atr_current > frame.atr_previous
    assert frame.rvol == D(10)


def test_rejected_low_volume_transition_cannot_be_chased_next_hour():
    engine = warmed()
    a = next_frame(engine, close="102", volume="100")
    assert (
        "LOW_RVOL" in decide(a, Side.LONG, universe(a.evaluated_at), a.evaluated_at).rejection_codes
    )
    b = next_frame(engine, index=721, close="104", volume="1000")
    assert b.previous_long is True and b.current_long is True
    assert (
        "NO_NEW_BREAKOUT"
        in decide(b, Side.LONG, universe(b.evaluated_at), b.evaluated_at).rejection_codes
    )


def test_unknown_previous_state_is_not_false():
    engine = Indicators("BTCUSDT")
    frame = next_frame(engine, index=0, close="102", volume="150")
    decision = decide(frame, Side.LONG, universe(frame.evaluated_at), frame.evaluated_at)
    assert not decision.accepted and "DATA_GAP" in decision.rejection_codes


def test_no_future_input_and_no_backdated_decisions():
    engine = warmed()
    c = candle(720, close="102", volume="150")
    with pytest.raises(ValueError, match="DATA_NOT_AVAILABLE"):
        engine.push(c, c.timing.interval_end)
    frame = engine.push(c, c.timing.available_at + timedelta(seconds=1))
    assert (
        "DATA_NOT_AVAILABLE"
        in decide(
            frame, Side.LONG, universe(frame.evaluated_at), c.timing.available_at
        ).rejection_codes
    )
    with pytest.raises(ValueError, match="backwards"):
        engine.push(c, c.timing.available_at)


def test_restart_checkpoint_preserves_atr_transition_and_same_candle_idempotency():
    engine = warmed()
    restored = Indicators.restore(json.loads(canonical(engine.checkpoint())))
    prior = restored.rows[-1]
    assert restored.push(prior, prior.timing.available_at) == engine.last_frame
    frame = next_frame(engine, close="102", volume="150")
    assert next_frame(restored, close="102", volume="150") == frame
    assert restored.atr.count == engine.atr.count


def test_appending_future_changes_no_emitted_signal():
    engine = warmed()
    frame = next_frame(engine, close="102", volume="150")
    u = universe(frame.evaluated_at)
    decision = decide(frame, Side.LONG, u, frame.evaluated_at)
    frozen = canonical(decision)
    for i in range(721, 745):
        next_frame(engine, i, close="99", volume="1000")
    assert canonical(decision) == frozen
    assert decide(frame, Side.LONG, u, frame.evaluated_at) == decision


def test_cooldown_pending_and_position_are_entry_gates_only():
    frame = next_frame(warmed(), close="102", volume="150")
    u = universe(frame.evaluated_at)
    for status in (
        {"has_position": True},
        {"pending_entry": True},
        {"cooldown_end": frame.evaluated_at + timedelta(seconds=1)},
    ):
        assert not decide(frame, Side.LONG, u, frame.evaluated_at, **status).accepted
    assert decide(frame, Side.LONG, u, frame.evaluated_at, cooldown_end=frame.evaluated_at).accepted


def test_gap_preserves_atr_origin_but_blocks_signals():
    engine = warmed()
    count = engine.atr.count
    frame = next_frame(engine, 721, close="102", volume="150")
    assert engine.atr.count == count  # No invented true range across missing hour.
    assert frame.previous_long is None and not frame.warmup_ok
    assert not decide(frame, Side.LONG, universe(frame.evaluated_at), frame.evaluated_at).accepted


def test_simultaneous_ranking_and_batch_wait_for_missing_symbol():
    frame = next_frame(warmed(), close="102", volume="150")
    other = replace(frame, candle=replace(frame.candle, symbol="ETHUSDT"))
    u = universe(frame.evaluated_at, ("BTCUSDT", "ETHUSDT"))
    st = frame.candle.timing.interval_end
    assert signal_batch({"BTCUSDT": frame}, u, st, frame.evaluated_at) is None
    batch = signal_batch({"BTCUSDT": frame}, u, st, st + timedelta(seconds=30))
    assert batch.missing_symbols == ("ETHUSDT",) and len(batch.ranked) == 1
    complete = signal_batch({"ETHUSDT": other, "BTCUSDT": frame}, u, st, frame.evaluated_at)
    assert [x.symbol for x in complete.ranked] == ["BTCUSDT", "ETHUSDT"]
    higher = replace(complete.ranked[1], frame=replace(other, rvol=D(2)))
    assert rank_signals([complete.ranked[0], higher])[0] == higher
    assert not signal_batch({"BTCUSDT": frame}, u, st, st + timedelta(seconds=31)).ranked
