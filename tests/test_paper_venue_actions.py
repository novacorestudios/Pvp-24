from datetime import timedelta

import pytest
from test_paper_actions import action, position
from test_paper_dispatch import prepared, state

from pvb24.accounting.ledger import LedgerStore
from pvb24.decimal_math import D
from pvb24.integrations.paper_dispatch import OrderRejected, PaperDispatch
from pvb24.integrations.paper_evidence import PaperEvidence
from pvb24.integrations.paper_venue import L2PaperVenue
from pvb24.state import Conflict, Journal
from pvb24.types import Quality


def drain(host, venue, cursor):
    results = []
    for sequence, event in venue.events_after(cursor[0]):
        results.append(PaperEvidence(host).ingest(event))
        cursor[0] = sequence
    return results


def opened(tmp_path, *, thin_bid=False):
    db, host, _, cid, inputs, book, now = prepared(tmp_path)
    host.close()
    if thin_bid:
        book.bids = {D("101.20"): D(1)}
    venue = L2PaperVenue(
        tmp_path / "venue.sqlite",
        instance_id="SYNTHETIC_TEST_ONLY",
        scope="reference",
        manifest_id="SYNTHETIC_ACTIONS",
        clock=lambda: now[0],
        max_last_age=timedelta(seconds=1),
    )
    venue.install_book(book, source_event_id="book")
    venue.set_terms(
        inputs.rules,
        entry_fee_rate=D("0.0005"),
        exit_fee_rate=D("0.0005"),
        available_at=now[0],
        source_revision="terms",
    )
    venue.publish_last(
        book.symbol, D("101.21"), event_time=now[0], available_at=now[0], source_event_id="last"
    )
    host = PaperDispatch(db, "reference", Quality.PRELIMINARY, venue, lambda: now[0])
    host.dispatch_entry(cid, inputs, book)
    cursor = [0]
    stop = drain(host, venue, cursor)[0]["action_ids"][0]
    sid = db.db.execute("SELECT signal_id FROM intents WHERE client_id=?", (cid,)).fetchone()[0]
    return db, host, venue, sid, stop, now, cursor


def active(db, host, venue, stop, now, cursor):
    now[0] += timedelta(milliseconds=1)
    host.dispatch_action(stop)
    result = drain(host, venue, cursor)
    assert state(db, stop) == "ACKNOWLEDGED"
    return result


def test_durable_stop_replacement_cancel_market_exit_and_visible_fees(tmp_path):
    db, host, venue, sid, stop, now, cursor = opened(tmp_path)
    with host:
        active(db, host, venue, stop, now, cursor)
        assert position(db, sid).protected
        next_price = position(db, sid).effective_stop + D("0.01")
        replacement = action(db, sid, now, "trail", lambda p: p.tighten_stop(next_price, D(101)))
        result = active(db, host, venue, replacement, now, cursor)
        cancel = result[0]["action_ids"][0]
        host.dispatch_action(cancel)
        drain(host, venue, cursor)
        assert state(db, stop) == "CANCELED" and state(db, cancel) == "ACKNOWLEDGED"
        assert position(db, sid).protected
        close = action(db, sid, now, "close", lambda p: p.close())
        host.dispatch_action(close)
        drain(host, venue, cursor)
        assert state(db, close) == "FILLED" and position(db, sid).remaining == 0
        view = LedgerStore(db, "reference").read()[1].view(now[0])
        assert view.fees > 0 and view.cash == D(1000) + view.realized_gross - view.fees
    venue.close()
    db.close()


def test_stop_uses_last_and_fills_at_executable_gap_book_not_stop_price(tmp_path):
    db, host, venue, sid, stop, now, cursor = opened(tmp_path)
    with host:
        active(db, host, venue, stop, now, cursor)
        stop_price = position(db, sid).effective_stop
        now[0] += timedelta(milliseconds=1)
        venue.update_book(
            "BTCUSDT",
            first=12,
            final=12,
            previous=11,
            bids=[(D("101.20"), D(0)), (D(95), D(100))],
            asks=[(D("101.21"), D(0)), (D("95.01"), D(100))],
            event_time=now[0],
            received_at=now[0],
            source_event_id="gap-book",
        )
        assert state(db, stop) == "ACKNOWLEDGED" and not venue.events_after(cursor[0])
        venue.publish_last(
            "BTCUSDT", D(95), event_time=now[0], available_at=now[0], source_event_id="gap-last"
        )
        drain(host, venue, cursor)
        assert state(db, stop) == "FILLED" and position(db, sid).remaining == 0
        fills = LedgerStore(db, "reference").read()[1].fills.values()
        reduced = [r.fill for r in fills if r.fill.reduce_only]
        assert len(reduced) == 1 and reduced[0].price == 95 < stop_price
    venue.close()
    db.close()


def test_partial_market_exit_remains_pending_and_later_depth_finishes_without_resend(tmp_path):
    db, host, venue, sid, _, now, cursor = opened(tmp_path, thin_bid=True)
    with host:
        close = action(db, sid, now, "close", lambda p: p.close())
        initial = position(db, sid).remaining
        host.dispatch_action(close)
        drain(host, venue, cursor)
        assert position(db, sid).remaining == initial - 1
        assert state(db, close) == "UNKNOWN"
        assert venue.journal.snapshot("model-order:" + close)[1]["outcome"] == "PENDING"
        with pytest.raises(Conflict, match="never resend"):
            host.dispatch_action(close)
        now[0] += timedelta(milliseconds=1)
        venue.update_book(
            "BTCUSDT",
            first=12,
            final=12,
            previous=11,
            bids=[(D("101.20"), D(100))],
            asks=[],
            event_time=now[0],
            received_at=now[0],
            source_event_id="replenish-bid",
        )
        drain(host, venue, cursor)
        assert position(db, sid).remaining == 0 and state(db, close) == "FILLED"
        assert (
            len(
                [
                    f
                    for f in LedgerStore(db, "reference").read()[1].fills.values()
                    if f.fill.reduce_only
                ]
            )
            == 2
        )
    venue.close()
    db.close()


def test_crossed_stop_is_refused_then_shared_core_emits_emergency_exit(tmp_path):
    db, host, venue, sid, stop, now, cursor = opened(tmp_path)
    with host:
        crossed = position(db, sid).effective_stop - D("0.01")
        now[0] += timedelta(milliseconds=1)
        venue.publish_last(
            "BTCUSDT", crossed, event_time=now[0], available_at=now[0], source_event_id="crossed"
        )
        response = host.dispatch_action(stop)
        assert isinstance(response, OrderRejected) and response.reason == "STOP_ALREADY_CROSSED"
        close = drain(host, venue, cursor)[0]["action_ids"][0]
        assert position(db, sid).safety_paused
        host.dispatch_action(close)
        drain(host, venue, cursor)
        assert position(db, sid).remaining == 0
    venue.close()
    db.close()


def test_stop_fill_can_win_cancel_race_without_reversing_cash_or_quantity(tmp_path):
    db, host, venue, sid, old, now, cursor = opened(tmp_path)
    with host:
        active(db, host, venue, old, now, cursor)
        price = position(db, sid).effective_stop + D("0.01")
        new = action(db, sid, now, "trail", lambda p: p.tighten_stop(price, D(101)))
        cancel = active(db, host, venue, new, now, cursor)[0]["action_ids"][0]
        submit = venue.submit_action

        def racing(ticket):
            now[0] += timedelta(milliseconds=1)
            venue.publish_last(
                "BTCUSDT", D(95), event_time=now[0], available_at=now[0], source_event_id="race"
            )
            return submit(ticket)

        venue.submit_action = racing
        host.dispatch_action(cancel)
        drain(host, venue, cursor)
        assert state(db, old) == "FILLED" and state(db, new) == "CANCELED"
        assert state(db, cancel) == "ACKNOWLEDGED" and position(db, sid).remaining == 0
        view = LedgerStore(db, "reference").read()[1].view(now[0])
        assert view.positions[0].quantity == 0
    venue.close()
    db.close()


def test_active_stop_and_pending_exit_survive_backend_reopen(tmp_path):
    db, host, venue, sid, stop, now, cursor = opened(tmp_path, thin_bid=True)
    active(db, host, venue, stop, now, cursor)
    close = action(db, sid, now, "close", lambda p: p.close())
    host.dispatch_action(close)
    drain(host, venue, cursor)
    host.close()
    venue.close()
    db.close()
    db = Journal(tmp_path / "planning.sqlite")
    venue = L2PaperVenue(
        tmp_path / "venue.sqlite",
        instance_id="SYNTHETIC_TEST_ONLY",
        scope="reference",
        manifest_id="SYNTHETIC_ACTIONS",
        clock=lambda: now[0],
        max_last_age=timedelta(seconds=1),
    )
    with PaperDispatch(db, "reference", Quality.PRELIMINARY, venue, lambda: now[0]) as host:
        assert host.lookup(stop) is not None and host.lookup(close) is not None
        now[0] += timedelta(milliseconds=1)
        venue.update_book(
            "BTCUSDT",
            first=12,
            final=12,
            previous=11,
            bids=[(D("101.20"), D(100))],
            asks=[],
            event_time=now[0],
            received_at=now[0],
            source_event_id="restart-bid",
        )
        drain(host, venue, cursor)
        assert state(db, close) == "FILLED" and position(db, sid).remaining == 0
    venue.close()
    db.close()


def test_stale_last_cannot_activate_new_protection_and_policy_cannot_change(tmp_path):
    db, host, venue, _, stop, now, cursor = opened(tmp_path)
    with host:
        now[0] += timedelta(seconds=2)
        response = host.dispatch_action(stop)
        assert isinstance(response, OrderRejected) and response.reason == "LAST_SOURCE_UNAVAILABLE"
        drain(host, venue, cursor)
        assert state(db, stop) == "REJECTED"
        venue.max_last_age = timedelta(days=1)
        with pytest.raises(Conflict, match="policy changed"):
            venue.lookup(stop)
    venue.close()
    db.close()


def test_pre_activation_trade_does_not_retroactively_hit_stop_and_clock_is_monotonic(tmp_path):
    db, host, venue, _, stop, now, cursor = opened(tmp_path)
    before = now[0]
    with host:
        active(db, host, venue, stop, now, cursor)
        now[0] += timedelta(milliseconds=1)
        venue.publish_last(
            "BTCUSDT",
            D(95),
            event_time=before,
            available_at=now[0],
            source_event_id="late-old-last",
        )
        assert not venue.events_after(cursor[0])
        assert venue.journal.snapshot("model-order:" + stop)[1]["outcome"] == "OPEN"
        now[0] = before
        with pytest.raises(Conflict, match="clock moved backwards"):
            venue.publish_last(
                "BTCUSDT",
                D(95),
                event_time=now[0],
                available_at=now[0],
                source_event_id="clock-back",
            )
    venue.close()
    db.close()


def test_lost_stop_reply_recovers_active_evidence_without_second_order(tmp_path):
    db, host, venue, sid, stop, now, cursor = opened(tmp_path)
    submit = venue.submit_action

    def lost(ticket):
        submit(ticket)
        raise TimeoutError("Stop committed before lost reply")

    venue.submit_action = lost
    with host:
        with pytest.raises(TimeoutError):
            host.dispatch_action(stop)
        assert state(db, stop) == "UNKNOWN" and not position(db, sid).protected
        assert host.lookup(stop) is not None
        drain(host, venue, cursor)
        assert position(db, sid).protected and state(db, stop) == "ACKNOWLEDGED"
        with pytest.raises(Conflict, match="never resend"):
            host.dispatch_action(stop)
        assert (
            venue.journal.db.execute(
                "SELECT COUNT(*) FROM snapshots WHERE stream LIKE 'model-order:%'"
            ).fetchone()[0]
            == 2
        )
    venue.close()
    db.close()
