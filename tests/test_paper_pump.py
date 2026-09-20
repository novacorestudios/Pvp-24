import json
from datetime import timedelta

import pytest
from test_freqtrade_bridge import config
from test_paper_actions import action, position
from test_paper_dispatch import state
from test_paper_venue_actions import opened

from pvb24.accounting.ledger import LedgerStore
from pvb24.decimal_math import D
from pvb24.integrations.freqtrade_bridge import SharedPaperBridge
from pvb24.integrations.paper_pump import retire_stale
from pvb24.integrations.paper_session import PaperSession
from pvb24.state import Conflict


def test_pump_activates_replacement_before_cancel_and_closes_with_all_stop_cleanup(tmp_path):
    db, host, venue, sid, stop, now, _ = opened(tmp_path)
    with host:
        session = PaperSession(host)
        result = session.pump_actions()
        assert result.dispatched == (stop,) and position(db, sid).protected
        replacement = action(
            db, sid, now, "trail", lambda p: p.tighten_stop(p.effective_stop + D("0.01"), D(101))
        )
        result = session.pump_actions()
        assert result.dispatched[0] == replacement and len(result.dispatched) == 2
        assert state(db, stop) == "CANCELED" and position(db, sid).protected
        now[0] += timedelta(milliseconds=1)
        close = action(db, sid, now, "close", lambda p: p.close())
        result = session.pump_actions()
        assert result.dispatched[0] == close
        assert state(db, close) == "FILLED" and state(db, replacement) == "CANCELED"
        assert position(db, sid).remaining == 0
        assert not result.deferred and not result.recovery.unresolved
        before = db.snapshot("portfolio:reference")
        assert session.pump_actions().dispatched == ()
        assert db.snapshot("portfolio:reference") == before  # no inferred reserve release
    venue.close()
    db.close()


def test_stale_unsent_stop_is_retired_without_submission_or_losing_tighter_protection(tmp_path):
    db, host, venue, sid, old, now, _ = opened(tmp_path)
    with host:
        replacement = action(
            db, sid, now, "trail", lambda p: p.tighten_stop(p.effective_stop + D("0.01"), D(101))
        )
        result = PaperSession(host).pump_actions()
        assert result.retired == (old,) and result.dispatched == (replacement,)
        assert state(db, old) == "CANCELED" and venue.lookup(old) is None
        assert position(db, sid).protected
        proof = json.loads(
            db.db.execute(
                "SELECT payload FROM events WHERE event_id=?", ("paper-retired:" + old,)
            ).fetchone()[0]
        )
        assert proof["never_dispatched"] and proof["reason"] == "STOP_PROPOSAL_SUPERSEDED"
    venue.close()
    db.close()


def test_exit_priority_retires_unsent_stop_only_after_confirmed_flat(tmp_path):
    db, host, venue, sid, stop, now, _ = opened(tmp_path)
    with host:
        close = action(db, sid, now, "close", lambda p: p.close())
        result = PaperSession(host).pump_actions()
        assert result.dispatched == (close,) and result.retired == (stop,)
        assert venue.lookup(stop) is None and position(db, sid).remaining == 0
    venue.close()
    db.close()


def test_partial_exit_keeps_same_unknown_request_and_dispatches_residual_protection(tmp_path):
    db, host, venue, sid, stop, now, _ = opened(tmp_path, thin_bid=True)
    with host:
        close = action(db, sid, now, "close", lambda p: p.close())
        session = PaperSession(host)
        result = session.pump_actions()
        assert result.dispatched[0] == close and stop in result.retired
        assert position(db, sid).protected and result.recovery.unresolved == (close,)
        assert not retire_stale(session, close)  # UNKNOWN can never be locally retired
        assert not session.pump_actions().dispatched
    venue.close()
    db.close()


def test_exit_superseded_by_partial_reduction_gets_new_bounded_successor_identity(tmp_path):
    db, host, venue, sid, stop, now, _ = opened(tmp_path, thin_bid=True)
    with host:
        session = PaperSession(host)
        session.pump_actions()
        old_quantity = position(db, sid).remaining
        full = action(db, sid, now, "full-close", lambda p: p.close())
        partial = action(db, sid, now, "partial-close", lambda p: p.close(D(1)))
        session.dispatch_action(partial)
        assert position(db, sid).remaining == old_quantity - 1
        assert retire_stale(session, full)
        assert state(db, full) == "CANCELED" and venue.lookup(full) is None
        successors = db.db.execute(
            "SELECT client_id,payload FROM intents WHERE purpose='EXIT_MARKET' AND state='PREPARED'"
        ).fetchall()
        assert len(successors) == 1 and successors[0]["client_id"] != full
        assert D(json.loads(successors[0]["payload"])["quantity"]) == old_quantity - 1
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
            source_event_id="refill",
        )
        session.pump_actions()
        assert position(db, sid).remaining == 0 and state(db, stop) == "CANCELED"
    venue.close()
    db.close()


def test_pump_handles_crossed_stop_refusal_then_safety_close(tmp_path):
    db, host, venue, sid, stop, now, _ = opened(tmp_path)
    with host:
        now[0] += timedelta(milliseconds=1)
        venue.publish_last(
            "BTCUSDT", D(90), event_time=now[0], available_at=now[0], source_event_id="gap"
        )
        result = PaperSession(host).pump_actions()
        assert result.dispatched[0] == stop and len(result.dispatched) == 2
        assert state(db, stop) == "REJECTED" and position(db, sid).remaining == 0
        assert db.snapshot("account-gate:reference")[1]["safety_paused"] is True
    venue.close()
    db.close()


def test_bounded_pump_resumes_after_budget_and_lost_stop_response_without_resend(tmp_path):
    db, host, venue, sid, stop, now, _ = opened(tmp_path)
    submit = venue.submit_action

    def lost(ticket):
        submit(ticket)
        raise TimeoutError("Lost stop reply")

    venue.submit_action = lost
    with host:
        session = PaperSession(host)
        with pytest.raises(TimeoutError):
            session.pump_actions(max_actions=1)
        assert state(db, stop) == "UNKNOWN"
        venue.submit_action = submit
        result = PaperSession(host).pump_actions(max_actions=1)
        assert not result.dispatched and position(db, sid).protected
        replacement = action(
            db, sid, now, "trail", lambda p: p.tighten_stop(p.effective_stop + D("0.01"), D(101))
        )
        result = session.pump_actions(max_actions=1)
        assert result.dispatched == (replacement,) and state(db, stop) == "ACKNOWLEDGED"
        assert len(session.pump_actions(max_actions=1).dispatched) == 1
        assert state(db, stop) == "CANCELED"
    venue.close()
    db.close()


def test_cancel_already_terminal_is_retired_using_proof_without_second_request(tmp_path):
    db, host, venue, sid, stop, now, _ = opened(tmp_path)
    with host:
        session = PaperSession(host)
        session.pump_actions()
        action(
            db, sid, now, "trail", lambda p: p.tighten_stop(p.effective_stop + D("0.01"), D(101))
        )
        session.pump_actions(max_actions=1)
        cancel = db.db.execute(
            "SELECT client_id FROM intents WHERE purpose='CANCEL_PROTECTION' AND state='PREPARED'"
        ).fetchone()[0]
        now[0] += timedelta(milliseconds=1)
        venue.publish_last(
            "BTCUSDT", D(90), event_time=now[0], available_at=now[0], source_event_id="gap"
        )
        result = session.pump_actions()
        assert cancel in result.retired and venue.lookup(cancel) is None
        assert position(db, sid).remaining == 0
    venue.close()
    db.close()


def test_bridge_local_mode_is_explicit_unique_guarded_and_closable(tmp_path):
    db, host, venue, sid, _, now, _ = opened(tmp_path)
    cfg = config()
    bridge = SharedPaperBridge(cfg, db, "reference")
    with pytest.raises(ValueError, match="Explicit LOCAL"):
        bridge.bind_local_model(venue, lambda: now[0])
    cfg["pvb24"]["execution_transport"] = "LOCAL_PRELIMINARY_L2"
    with pytest.raises(Conflict, match="Another PAPER authority"):
        bridge.bind_local_model(venue, lambda: now[0])
    host.close()
    bridge.bind_local_model(venue, lambda: now[0])
    with pytest.raises(ValueError, match="already bound"):
        bridge.bind_local_model(venue, lambda: now[0])
    bridge.pump_local()
    assert position(db, sid).protected
    cfg["pvb24"]["operational_ready"] = True
    with pytest.raises(ValueError, match="not yet qualified"):
        bridge.pump_local()
    cfg["pvb24"]["operational_ready"] = False
    cfg["pvb24"]["execution_transport"] = "NATIVE_DRY_RUN"
    with pytest.raises(ValueError, match="configuration changed"):
        bridge.pump_local()
    bridge.close_local()
    cfg["pvb24"]["execution_transport"] = "LOCAL_PRELIMINARY_L2"
    with pytest.raises(Conflict, match="closed"):
        bridge.pump_local()
    assert LedgerStore(db, "reference").read()[1].fills
    venue.close()
    db.close()
