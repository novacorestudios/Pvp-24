from dataclasses import replace
from datetime import timedelta

import pytest
from test_data import NOW, candle

from pvb24.decimal_math import D
from pvb24.execution.market import EntryBounds
from pvb24.ids import canonical
from pvb24.replay.events import Event, Kind, Replay, ordered_batch
from pvb24.replay.preliminary import (
    FrozenEntry,
    MinuteOpen,
    adverse_bar_exit,
    entry_at_open,
)
from pvb24.types import Quality, Side


def event(name, kind=Kind.ENTRY_DECISION, seconds=0, available=None, seq=None, domain=None):
    time = NOW + timedelta(seconds=seconds)
    return Event(
        name,
        kind,
        time,
        available or time,
        "synthetic",
        Quality.PRELIMINARY,
        canonical({"name": name}),
        seq,
        domain,
    )


def test_replay_uses_availability_before_exchange_time_without_future_reordering():
    old = event("late", seconds=0, available=NOW + timedelta(seconds=20))
    new = event("known", seconds=10)
    replay = Replay(Quality.PRELIMINARY)
    replay.add([old, new])
    replay.run(NOW + timedelta(seconds=15), lambda d: d.event.event_id)
    assert [x["event_id"] for x in replay.trace] == ["known"]
    replay.run(NOW + timedelta(seconds=20), lambda d: d.event.event_id)
    assert [x["event_id"] for x in replay.trace] == ["known", "late"]


def test_complete_exchange_sequence_overrides_priority_but_unrelated_domains_do_not():
    stop = event("stop", Kind.PROTECTIVE_FILL, seq=1, domain="orders")
    liquidation = event("liq", Kind.LIQUIDATION, seq=2, domain="orders")
    ordered = ordered_batch([liquidation, stop])
    assert [d.event.event_id for d in ordered] == ["stop", "liq"]
    assert not sum(d.ambiguous_event_count for d in ordered)
    ordered = ordered_batch([liquidation, replace(stop, sequence_domain="another-feed")])
    assert [d.event.event_id for d in ordered] == ["liq", "stop"]
    assert sum(d.ambiguous_event_count for d in ordered) == 1


def test_equal_time_conservative_precedence_and_ambiguity_counter():
    kinds = [
        Kind.ENTRY_DECISION,
        Kind.TRAILING,
        Kind.EXIT_DECISION,
        Kind.ACCOUNT_RISK,
        Kind.FUNDING,
        Kind.REDUCE_FILL,
        Kind.PROTECTIVE_FILL,
        Kind.LIQUIDATION,
    ]
    replay = Replay(Quality.PRELIMINARY)
    replay.add(event(k.name, k) for k in kinds)
    replay.run(NOW, lambda d: d.event.kind.name)
    assert [r["output"] for r in replay.trace] == [k.name for k in reversed(kinds)]
    assert replay.ambiguous_event_count == 1


def test_reordered_input_and_future_append_do_not_change_historical_trace():
    rows = [event("b"), event("a"), event("c", seconds=3)]
    first, second = Replay(Quality.PRELIMINARY), Replay(Quality.PRELIMINARY)
    first.add(rows)
    second.add(list(reversed(rows)) + [event("future", seconds=100)])
    for replay in (first, second):
        replay.run(NOW + timedelta(seconds=3), lambda d: d.event.payload)
    assert first.trace_hash == second.trace_hash
    first.add(rows)  # duplicate input is inert even after sealing
    first.run(NOW + timedelta(seconds=3), lambda d: pytest.fail("redelivery"))
    assert first.trace_hash == second.trace_hash
    with pytest.raises(ValueError, match="watermark"):
        first.add([event("unseen")])
    with pytest.raises(ValueError, match="revised"):
        first.add([replace(rows[0], source="revision")])


def test_failed_callback_cannot_silently_retry_after_partial_effects():
    replay = Replay(Quality.PRELIMINARY)
    replay.add([event("one")])
    with pytest.raises(ZeroDivisionError):
        replay.run(NOW, lambda d: 1 / 0)
    with pytest.raises(RuntimeError, match="recovery"):
        replay.run(NOW, lambda d: None)


def test_verified_replay_never_promotes_preliminary_inputs():
    replay = Replay(Quality.VERIFIED)
    with pytest.raises(ValueError, match="promote"):
        replay.add([event("one")])
    assert replay.events == {}


def order(side=Side.LONG, decision_seconds=2, quantity="1"):
    return FrozenEntry(
        EntryBounds(
            "BTCUSDT",
            side,
            NOW,
            D(100),
            D("99.5") if side is Side.LONG else D("100.5"),
            D(2),
            D("0.01"),
        ),
        NOW + timedelta(seconds=decision_seconds),
        D(quantity),
        D(0),
        D(1000000),
        NOW + timedelta(seconds=2),
    )


def opening(price="100", minutes=1):
    time = NOW + timedelta(minutes=minutes)
    return MinuteOpen("BTCUSDT", time, time, D(price), "synthetic-open-proxy", "v1")


@pytest.mark.parametrize("side", [Side.LONG, Side.SHORT])
def test_preliminary_entry_first_open_strictly_after_decision_with_adverse_slippage(side):
    request = order(side)
    result = entry_at_open(request, opening(), NOW + timedelta(minutes=1))
    assert result.reason == "MODELED_FULL_FILL"
    assert side.sign * (result.proxy.price - D(100)) > 0
    assert result.fill_time > request.decision_time
    assert result.quality is Quality.PRELIMINARY and "partial_fills" in result.unverified
    assert (
        entry_at_open(request, opening(minutes=0), NOW).reason == "FIRST_POST_DECISION_OPEN_MISSING"
    )
    assert entry_at_open(request, opening(minutes=2), NOW + timedelta(minutes=2)).proxy is None
    exact = order(side, decision_seconds=60)
    assert exact.expected_open == NOW + timedelta(minutes=2)
    assert (
        entry_at_open(exact, opening(minutes=2), NOW + timedelta(minutes=2)).reason
        == "ORDER_DEADLINE"
    )


def test_minute_open_has_no_future_extrema_or_volume_and_cannot_be_used_early():
    with pytest.raises(ValueError, match="unavailable"):
        entry_at_open(order(), opening(), NOW + timedelta(seconds=59))
    with pytest.raises(ValueError, match="future"):
        replace(order(), inputs_available_at=NOW + timedelta(seconds=3))
    assert (
        entry_at_open(order(), opening("101"), NOW + timedelta(minutes=1)).reason
        == "BREAKOUT_OR_CHASING"
    )
    assert (
        entry_at_open(order(quantity="20"), opening(), NOW + timedelta(minutes=1)).reason
        == "PARTICIPATION"
    )


def bars(open_price="100", low="97", high="103", mark_low="90", mark_high="110"):
    row = candle(NOW, duration=timedelta(minutes=1))
    last = replace(row, open=D(open_price), close=D(100), low=D(low), high=D(high))
    mark = replace(last, open=D(100), low=D(mark_low), high=D(mark_high), price_type="MARK")
    return last, mark


def bar_exit(last, mark, side=Side.LONG, **kwargs):
    return adverse_bar_exit(
        last,
        mark,
        side,
        stop=D(98) if side is Side.LONG else D(102),
        liquidation=D(92) if side is Side.LONG else D(108),
        stop_effective_at=kwargs.get("effective", NOW),
        first_fill_time=kwargs.get("fill", NOW),
        now=last.timing.available_at,
    )


@pytest.mark.parametrize("side", [Side.LONG, Side.SHORT])
def test_unresolved_bar_liquidation_precedes_stop_and_counts_ambiguity(side):
    result = bar_exit(*bars(), side)
    assert result.reason == "MODELED_LIQUIDATION" and result.ambiguous_event_count == 1
    assert result.quality is Quality.PRELIMINARY


def test_last_stop_and_mark_liquidation_are_separate_and_gaps_use_worse_open():
    last, mark = bars(open_price="97", low="96", mark_low="99", mark_high="101")
    result = bar_exit(last, mark)
    assert result.reason == "MODELED_STOP" and result.reference_price == 97
    last, mark = bars(open_price="103", high="104", mark_low="99", mark_high="101")
    result = bar_exit(last, mark, Side.SHORT)
    assert result.reason == "MODELED_STOP" and result.reference_price == 103
    with pytest.raises(ValueError, match="Separate"):
        bar_exit(last, last)


def test_no_prefill_or_pre_ack_bar_extrema_can_trigger_new_stop():
    assert bar_exit(*bars(), effective=NOW + timedelta(seconds=30)).reason == "FINER_DATA_REQUIRED"
    assert bar_exit(*bars(), fill=NOW + timedelta(seconds=1)).reason == "FINER_DATA_REQUIRED"
    last, mark = bars()
    with pytest.raises(ValueError, match="Future"):
        adverse_bar_exit(
            last,
            mark,
            Side.LONG,
            stop=D(98),
            liquidation=D(92),
            first_fill_time=NOW,
            stop_effective_at=NOW,
            now=NOW,
        )
