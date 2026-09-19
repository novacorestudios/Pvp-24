from dataclasses import replace
from datetime import timedelta

import pytest
from test_account_coordinator import setup
from test_account_risk_service import entry_id, service
from test_accounting import mark, payment, record
from test_data import NOW, candle

from pvb24.accounting.ledger import LedgerStore
from pvb24.decimal_math import D
from pvb24.execution.protection import Protection
from pvb24.ids import canonical
from pvb24.replay.account import AccountReplay
from pvb24.replay.events import Delivery, Event, Kind, Replay
from pvb24.state import Conflict, Journal
from pvb24.strategy.exits import Exits
from pvb24.types import Quality, Side


def envelope(name, kind, payload, time=NOW, available=None):
    return Event(
        name, kind, time, available or time, "synthetic", Quality.PRELIMINARY, canonical(payload)
    )


def fill_event(r):
    kind = (
        Kind.LIQUIDATION
        if r.liquidation
        else Kind.REDUCE_FILL
        if r.fill.reduce_only
        else Kind.ENTRY_FILL
    )
    return envelope(r.fill.fill_id, kind, r, r.fill.event_time, r.fill.received_at)


def deliver(runtime, event):
    return runtime(Delivery(event, "CONSERVATIVE_PRIORITY", 0))


def runtime_setup(tmp_path):
    db, reservations, _ = setup(tmp_path)
    service(db).sample(NOW, [])
    runtime = AccountReplay(db, "paper", Quality.PRELIMINARY)
    runtime.freeze_exit_channels("signal", D("99.5"), D(99))
    assert db.claim_dispatch(entry_id(db))
    return db, reservations, runtime


def open_owned(runtime, db):
    result = deliver(runtime, fill_event(record(quantity="4.5", seconds=1)))
    stop_id = result["action_ids"][0]
    deliver(
        runtime,
        envelope(
            "terminal",
            Kind.ORDER_OUTCOME,
            {"position_id": "signal", "operation": "ENTRY_TERMINAL", "outcome": "FILLED"},
            NOW + timedelta(seconds=2),
        ),
    )
    assert db.claim_dispatch(stop_id)
    deliver(
        runtime,
        envelope(
            "stop-ack",
            Kind.ORDER_OUTCOME,
            {
                "position_id": "signal",
                "operation": "STOP_ACK",
                "sequence": 1,
                "quantity": "4.5",
                "stop": "98",
                "reduce_only": True,
                "reference": "CONTRACT_PRICE",
            },
            NOW + timedelta(seconds=3),
        ),
    )


def test_replay_fill_receipt_restarts_without_duplicate_expense_protection_or_output(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    event = fill_event(record(seconds=1))
    first = deliver(runtime, event)
    before = db.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    db.close()
    reopened = Journal(tmp_path / "account.sqlite")
    resumed = AccountReplay(reopened, "paper", Quality.PRELIMINARY)
    assert deliver(resumed, event) == first
    assert reopened.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before
    assert LedgerStore(reopened, "paper").read()[1].view(NOW + timedelta(seconds=2)).cash == D(
        "999.9"
    )
    assert Protection.restore(reopened.snapshot("protection:paper:signal")[1]).remaining == 2
    reopened.close()


def test_replay_receipt_failure_rolls_back_already_nested_fill_and_protection(
    tmp_path, monkeypatch
):
    db, _, runtime = runtime_setup(tmp_path)
    original = Journal.append_tx

    def fail_receipt(connection, key, payload):
        if key.startswith("replay-delivery:"):
            raise RuntimeError("injected crash before delivery commit")
        return original(connection, key, payload)

    monkeypatch.setattr(Journal, "append_tx", staticmethod(fail_receipt))
    with pytest.raises(RuntimeError, match="injected"):
        deliver(runtime, fill_event(record(seconds=1)))
    assert LedgerStore(db, "paper").read()[1].fills == {}
    assert Protection.restore(db.snapshot("protection:paper:signal")[1]).remaining == 0
    assert db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='PROTECT'").fetchone()[0] == 0
    assert db.snapshot("account-gate:paper")[1]["ready"] is False
    db.close()


def test_mark_and_funding_feed_same_ledger_risk_and_repeated_full_replay_is_identical(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    funding = payment()
    m = mark("101", NOW + timedelta(minutes=1))
    rows = [
        envelope("fund", Kind.FUNDING, funding, funding.settlement_time),
        envelope("mark", Kind.OBSERVATION, {"type": "MARK", "record": m}, m.timing.event_time),
        envelope("risk", Kind.ACCOUNT_RISK, {}, m.timing.event_time),
    ]
    replay = Replay(Quality.PRELIMINARY)
    replay.add(rows)
    replay.run(m.timing.available_at, runtime)
    status = replay.trace[-1]["output"]["status"]
    assert D(status["equity"]) == D("1004.2")  # 1000 - .1 fee - .2 funding + 4.5 UPNL
    again = Replay(Quality.PRELIMINARY)
    again.add(reversed(rows))
    again.run(m.timing.available_at, AccountReplay(db, "paper", Quality.PRELIMINARY))
    assert again.trace_hash == replay.trace_hash
    assert LedgerStore(db, "paper").read()[1].view(m.timing.available_at).funding == D("-0.2")
    db.close()


def test_terminal_and_stop_ack_require_actual_dispatched_intents(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    deliver(runtime, fill_event(record(quantity="4.5", seconds=1)))
    event = envelope(
        "stop-ack",
        Kind.ORDER_OUTCOME,
        {
            "position_id": "signal",
            "operation": "STOP_ACK",
            "sequence": 1,
            "quantity": "4.5",
            "stop": "98",
            "reduce_only": True,
            "reference": "CONTRACT_PRICE",
        },
        NOW + timedelta(seconds=2),
    )
    with pytest.raises(Conflict, match="never dispatched"):
        deliver(runtime, event)
    assert not Protection.restore(db.snapshot("protection:paper:signal")[1]).protected
    db.close()


def test_continuous_hold_timer_closes_once_without_reset_on_restart(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    time = NOW + timedelta(hours=72, seconds=1)
    event = envelope("timer", Kind.EXIT_DECISION, {"type": "TIMER", "position_id": "signal"}, time)
    result = deliver(runtime, event)
    assert result["decision"]["reason"] == "MAXIMUM_HOLD" and len(result["action_ids"]) == 1
    runtime = AccountReplay(db, "paper", Quality.PRELIMINARY)
    later = replace(
        event,
        event_id="later",
        event_time=time + timedelta(seconds=1),
        available_at=time + timedelta(seconds=1),
    )
    assert deliver(runtime, later)["action_ids"] == []
    assert (
        db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='EXIT_MARKET'").fetchone()[0] == 1
    )
    db.close()


def test_shared_hourly_indicators_and_exit_engine_create_early_failure_close(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    for index in range(25):
        bar = candle(NOW - timedelta(hours=25 - index))
        deliver(
            runtime,
            envelope(
                "warmup:" + str(index),
                Kind.OBSERVATION,
                {"type": "HOURLY_LAST", "record": bar},
                bar.timing.event_time,
                bar.timing.available_at,
            ),
        )
    # Warmup's final candle becomes available at NOW+2 seconds, so fill after it.
    result = deliver(runtime, fill_event(record(quantity="4.5", seconds=3)))
    deliver(
        runtime,
        envelope(
            "terminal",
            Kind.ORDER_OUTCOME,
            {"position_id": "signal", "operation": "ENTRY_TERMINAL", "outcome": "FILLED"},
            NOW + timedelta(seconds=4),
        ),
    )
    assert result["action_ids"]
    bar = replace(candle(NOW), open=D(99), close=D(99), low=D(98))
    rows = [
        envelope(
            "close-input",
            Kind.OBSERVATION,
            {"type": "HOURLY_LAST", "record": bar},
            bar.timing.event_time,
            bar.timing.available_at,
        ),
        envelope(
            "close",
            Kind.EXIT_DECISION,
            {"type": "HOURLY_CLOSE", "position_id": "signal", "last_price": "99"},
            bar.timing.interval_end,
            bar.timing.available_at,
        ),
    ]
    replay = Replay(Quality.PRELIMINARY)
    replay.add(reversed(rows))
    replay.run(bar.timing.available_at, runtime)
    result = replay.trace[-1]["output"]
    assert result["decision"]["reason"] == "EARLY_FAILURE"
    assert len(result["action_ids"]) == 1
    assert Exits.restore(db.snapshot("exits:paper:signal")[1]).count == 1
    db.close()


def test_prior_risk_close_is_not_duplicated_by_later_hold_timer(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    time = NOW + timedelta(hours=72)
    m = mark("60", time)
    deliver(runtime, envelope("mark", Kind.OBSERVATION, {"type": "MARK", "record": m}, time))
    assert deliver(runtime, envelope("risk", Kind.ACCOUNT_RISK, {}, time))["status"]["hard_paused"]
    later = time + timedelta(seconds=1)
    result = deliver(
        runtime,
        envelope("hold", Kind.EXIT_DECISION, {"type": "TIMER", "position_id": "signal"}, later),
    )
    assert result["action_ids"] == []
    assert (
        db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='EXIT_MARKET'").fetchone()[0] == 1
    )
    db.close()


def test_bad_envelope_and_changed_delivery_fail_closed(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    event = fill_event(record(seconds=1))
    with pytest.raises(ValueError, match="timing"):
        deliver(runtime, replace(event, available_at=NOW + timedelta(seconds=2)))
    assert not LedgerStore(db, "paper").read()[1].fills
    deliver(runtime, event)
    with pytest.raises(Conflict, match="Changed"):
        deliver(runtime, replace(event, source="different"))
    db.close()


def test_nested_savepoint_error_can_rollback_only_inner_work(tmp_path):
    db = Journal(tmp_path / "nested.sqlite")
    with db.transaction() as outer:
        Journal.append_tx(outer, "outer", {})
        with pytest.raises(RuntimeError):
            with db.transaction() as inner:
                Journal.append_tx(inner, "inner", {})
                raise RuntimeError("inner failure")
        Journal.append_tx(outer, "after", {})
    assert [r[0] for r in db.db.execute("SELECT event_id FROM events ORDER BY seq")] == [
        "outer",
        "after",
    ]
    db.close()


def test_partial_exit_terminal_reissues_only_confirmed_uncovered_remainder(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    time = NOW + timedelta(hours=72, seconds=1)
    result = deliver(
        runtime,
        envelope("timer", Kind.EXIT_DECISION, {"type": "TIMER", "position_id": "signal"}, time),
    )
    cid = result["action_ids"][0]
    assert db.claim_dispatch(cid)
    sequence = Protection.restore(db.snapshot("protection:paper:signal")[1]).sequence
    partial = record("partial", "2", "100", side=Side.SHORT, reduce=True, seconds=72 * 3600 + 2)
    deliver(runtime, fill_event(partial))
    outcome = envelope(
        "exit-terminal",
        Kind.ORDER_OUTCOME,
        {
            "position_id": "signal",
            "operation": "EXIT_TERMINAL",
            "outcome": "CANCELED",
            "sequence": sequence,
            "venue_order_id": partial.fill.order_id,
            "cumulative_fill_quantity": "2",
        },
        time + timedelta(seconds=2),
    )
    result = deliver(runtime, outcome)
    assert len(result["action_ids"]) == 1
    p = Protection.restore(db.snapshot("protection:paper:signal")[1])
    assert p.actions[p.sequence].purpose == "EXIT_MARKET" and p.actions[p.sequence].quantity == D(
        "2.5"
    )
    assert deliver(runtime, outcome) == result
    db.close()


def test_liquidation_event_remains_visible_in_integrated_ledger(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    liquidated = record("liq", "4.5", "80", "1", Side.SHORT, True, 10, liquidation=True)
    deliver(runtime, fill_event(liquidated))
    view = LedgerStore(db, "paper").read()[1].view(NOW + timedelta(seconds=11))
    assert view.liquidation_count == 1 and view.cash == D("908.9")
    assert view.positions[0].quantity == 0
    db.close()


def test_terminal_entry_cannot_hide_missing_confirmed_quantity(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    deliver(runtime, fill_event(record(quantity="2", seconds=1)))
    from pvb24.accounting.ledger import ReconciliationRequired

    with pytest.raises(ReconciliationRequired, match="all confirmed"):
        deliver(
            runtime,
            envelope(
                "terminal",
                Kind.ORDER_OUTCOME,
                {"position_id": "signal", "operation": "ENTRY_TERMINAL", "outcome": "FILLED"},
                NOW + timedelta(seconds=2),
            ),
        )
    assert not Protection.restore(db.snapshot("protection:paper:signal")[1]).terminal
    assert (
        LedgerStore(db, "paper").read()[1].view(NOW + timedelta(seconds=3)).positions[0].quantity
        == 2
    )
    db.close()
