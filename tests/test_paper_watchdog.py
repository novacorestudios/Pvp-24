from datetime import timedelta

import pytest
from test_paper_actions import action, position
from test_paper_dispatch import state
from test_paper_venue import setup

from pvb24.decimal_math import D
from pvb24.integrations.paper_pump import _reserved_exits
from pvb24.integrations.paper_session import PaperSession
from pvb24.state import Conflict

POLICY = {
    "max_protection_ack_age": timedelta(seconds=1),
    "protection_policy_id": "SYNTHETIC_ACK_1S",
}


def unconfirmed(tmp_path, *, pending_exit=False):
    db, host, venue, cid, inputs, book, now = setup(tmp_path)
    session = PaperSession(host, **POLICY)
    session.dispatch_entry(cid, inputs, book)
    sid = db.db.execute("SELECT signal_id FROM intents WHERE client_id=?", (cid,)).fetchone()[0]
    stop = db.db.execute("SELECT client_id FROM intents WHERE purpose='PROTECT'").fetchone()[0]
    submit = venue.submit_action

    def no_stop_reply(ticket):
        if ticket.purpose == "PROTECT":
            raise TimeoutError("No stop outcome known")
        return submit(ticket)

    venue.submit_action = no_stop_reply
    with pytest.raises(TimeoutError):
        session.pump_actions()
    close = None
    if pending_exit:
        close = action(db, sid, now, "already-closing", lambda p: p.close())
        # This fixture deliberately has no exit fee terms: accepted market stays
        # pending and must not be duplicated when the protection timer expires.
        session.dispatch_action(close)
        assert state(db, close) == "UNKNOWN"
    return db, host, venue, session, sid, stop, now, close


def test_timeout_boundary_pauses_and_creates_one_uncovered_exit_without_stop_resend(tmp_path):
    db, host, venue, session, sid, stop, now, _ = unconfirmed(tmp_path)
    with host:
        now[0] += timedelta(seconds=1) - timedelta(microseconds=1)
        assert not session.pump_actions().timed_out
        now[0] += timedelta(microseconds=1)
        result = session.pump_actions()
        assert result.timed_out == (stop,) and len(result.dispatched) == 1
        assert position(db, sid).safety_paused
        assert state(db, stop) == "UNKNOWN" and venue.lookup(stop) is None
        close = result.dispatched[0]
        assert state(db, close) == "UNKNOWN"  # no fabricated fill on stale book/missing fees
        assert db.snapshot("account-gate:reference")[1]["safety_paused"] is True
        again = session.pump_actions()
        assert not again.timed_out and not again.dispatched
        assert (
            _reserved_exits(db.db, "reference", position(db, sid), "")
            == position(db, sid).remaining
        )
    venue.close()
    db.close()


def test_existing_pending_exit_is_not_duplicated_and_restart_does_not_reset_deadline(tmp_path):
    db, host, venue, _, sid, stop, now, close = unconfirmed(tmp_path, pending_exit=True)
    with host:
        now[0] += timedelta(seconds=2)
        restarted = PaperSession(host, **POLICY)
        result = restarted.pump_actions()
        assert result.timed_out == (stop,) and not result.dispatched
        assert position(db, sid).safety_paused and state(db, close) == "UNKNOWN"
        assert (
            db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='EXIT_MARKET'").fetchone()[0]
            == 1
        )
        assert not PaperSession(host, **POLICY).pump_actions().timed_out
    venue.close()
    db.close()


@pytest.mark.parametrize(
    "changed",
    [
        {},
        {**POLICY, "max_protection_ack_age": timedelta(seconds=2)},
        {**POLICY, "protection_policy_id": "different"},
    ],
)
def test_frozen_timeout_policy_cannot_be_removed_or_changed_on_restart(tmp_path, changed):
    db, host, venue, _, _, _, _, _ = unconfirmed(tmp_path)
    with host, pytest.raises(Conflict, match="cannot change or disappear"):
        PaperSession(host, **changed)
    venue.close()
    db.close()


def test_policy_must_be_frozen_before_any_dispatch_and_mutation_is_blocked(tmp_path):
    db, host, venue, cid, inputs, book, _ = setup(tmp_path)
    with host:
        session = PaperSession(host)
        session.dispatch_entry(cid, inputs, book)
        with pytest.raises(Conflict, match="before the first PAPER dispatch"):
            PaperSession(host, **POLICY)
    venue.close()
    db.close()
    other = tmp_path / "frozen"
    other.mkdir()
    db, host, venue, cid, inputs, book, _ = setup(other)
    with host:
        session = PaperSession(host, **POLICY)
        session.watchdog.policy["max_ack_age_microseconds"] += 1
        with pytest.raises(Conflict, match="policy changed"):
            session.dispatch_entry(cid, inputs, book)
        assert state(db, cid) == "PREPARED"
    venue.close()
    db.close()


def test_available_stop_confirmation_is_recovered_before_timeout_decision(tmp_path):
    db, host, venue, cid, inputs, book, now = setup(tmp_path)
    # Entry-only helper's model has no LAST age: recreate it before any request
    # with an explicit synthetic LAST policy.
    from pvb24.integrations.paper_dispatch import PaperDispatch
    from pvb24.integrations.paper_venue import L2PaperVenue
    from pvb24.types import Quality

    host.close()
    venue.close()
    venue = L2PaperVenue(
        tmp_path / "actions.sqlite",
        instance_id="SYNTHETIC_TEST_ONLY",
        scope="reference",
        manifest_id="ACK_RECOVERY",
        clock=lambda: now[0],
        max_last_age=timedelta(seconds=1),
    )
    venue.install_book(book, source_event_id="book")
    venue.set_terms(
        inputs.rules, entry_fee_rate=D("0.0005"), available_at=now[0], source_revision="fees"
    )
    venue.publish_last(
        book.symbol, D("101.21"), event_time=now[0], available_at=now[0], source_event_id="last"
    )
    with PaperDispatch(db, "reference", Quality.PRELIMINARY, venue, lambda: now[0]) as host:
        session = PaperSession(host, **POLICY)
        session.dispatch_entry(cid, inputs, book)
        submit = venue.submit_action

        def lost(ticket):
            submit(ticket)
            raise TimeoutError("Active stop receipt lost")

        venue.submit_action = lost
        with pytest.raises(TimeoutError):
            session.pump_actions()
        now[0] += timedelta(seconds=2)
        result = PaperSession(host, **POLICY).pump_actions()
        assert not result.timed_out and not result.dispatched
        assert (
            db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='EXIT_MARKET'").fetchone()[0]
            == 0
        )
    venue.close()
    db.close()
