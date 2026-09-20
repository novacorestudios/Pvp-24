import json
from datetime import timedelta

import pytest
from test_paper_actions import action, position
from test_paper_dispatch import state
from test_paper_venue import setup
from test_paper_venue_actions import opened

from pvb24.accounting.coordinator import save_tx
from pvb24.accounting.ledger import LedgerStore
from pvb24.ids import canonical
from pvb24.integrations.paper_dispatch import PaperDispatch
from pvb24.integrations.paper_session import PaperSession
from pvb24.integrations.paper_venue import L2PaperVenue
from pvb24.state import Conflict, Journal
from pvb24.types import Quality


def test_page_budget_never_skips_terminal_and_does_not_clear_reconciliation_gate(tmp_path):
    db, host, venue, cid, inputs, book, now = setup(tmp_path)
    with host:
        session = PaperSession(host)
        host.dispatch_entry(cid, inputs, book)
        assert db.snapshot("account-gate:reference")[1]["ready"] is False
        result = session.recover(max_events=1)
        assert result.consumed == 1 and not result.caught_up and result.unresolved == (cid,)
        assert state(db, cid) == "ACKNOWLEDGED"
        result = session.recover(max_events=1)
        assert result.consumed == 1 and result.caught_up and not result.unresolved
        assert state(db, cid) == "FILLED"
        version = db.snapshot(session.stream)[0]
        assert session.recover().consumed == 0
        assert db.snapshot(session.stream)[0] == version
        assert len(LedgerStore(db, "reference").read()[1].fills) == 1
        assert db.snapshot("account-gate:reference")[1]["ready"] is False
    venue.close()
    db.close()


def test_lost_reply_reopen_recovers_receipt_cursor_and_fill_once(tmp_path):
    db, host, venue, cid, inputs, book, now = setup(tmp_path)
    session = PaperSession(host)
    submit = venue.submit_entry

    def lost(ticket):
        submit(ticket)
        raise TimeoutError("Lost durable receipt")

    venue.submit_entry = lost
    with host, pytest.raises(TimeoutError):
        session.dispatch_entry(cid, inputs, book)
    original = canonical(venue.events_after())
    assert state(db, cid) == "UNKNOWN"
    venue.close()
    db.close()
    db = Journal(tmp_path / "planning.sqlite")
    venue = L2PaperVenue(
        tmp_path / "venue.sqlite",
        instance_id="SYNTHETIC_TEST_ONLY",
        scope="reference",
        manifest_id="SYNTHETIC_L2_ONLY",
        clock=lambda: now[0],
    )
    with PaperDispatch(db, "reference", Quality.PRELIMINARY, venue, lambda: now[0]) as host:
        result = PaperSession(host).recover()
        assert result.caught_up and not result.unresolved and result.consumed == 2
        assert canonical(venue.events_after()) == original
        assert state(db, cid) == "FILLED"
        assert len(LedgerStore(db, "reference").read()[1].fills) == 1
        with pytest.raises(Conflict, match="never resend"):
            host.dispatch_entry(cid, inputs, book)
    venue.close()
    db.close()


def test_crash_after_account_commit_before_cursor_replays_receipt_without_duplicate_effects(
    tmp_path, monkeypatch
):
    db, host, venue, cid, inputs, book, _ = setup(tmp_path)
    session = PaperSession(host)
    append = Journal.append_tx

    def crash(tx, event_id, payload):
        if event_id.startswith(session.stream + ":"):
            raise KeyboardInterrupt("Crash before cursor commit")
        return append(tx, event_id, payload)

    with host:
        host.dispatch_entry(cid, inputs, book)
        monkeypatch.setattr(Journal, "append_tx", staticmethod(crash))
        with pytest.raises(KeyboardInterrupt):
            session.recover()
        assert db.snapshot(session.stream)[1]["cursor"] == 0
        assert len(LedgerStore(db, "reference").read()[1].fills) == 1
        actions_before = list(
            db.db.execute("SELECT client_id FROM intents WHERE purpose='PROTECT'")
        )
        monkeypatch.setattr(Journal, "append_tx", staticmethod(append))
        result = PaperSession(host).recover()
        assert result.caught_up and result.consumed == 2
        assert len(LedgerStore(db, "reference").read()[1].fills) == 1
        assert (
            list(db.db.execute("SELECT client_id FROM intents WHERE purpose='PROTECT'"))
            == actions_before
        )
    venue.close()
    db.close()


def test_account_failure_does_not_advance_cursor_and_retry_keeps_source_economics(
    tmp_path, monkeypatch
):
    db, host, venue, cid, inputs, book, _ = setup(tmp_path)
    session = PaperSession(host)
    append = Journal.append_tx

    def fail(tx, event_id, payload):
        if event_id.startswith("paper-evidence:"):
            raise RuntimeError("Fail after nested account effects")
        return append(tx, event_id, payload)

    with host:
        host.dispatch_entry(cid, inputs, book)
        original = canonical(venue.events_after())
        monkeypatch.setattr(Journal, "append_tx", staticmethod(fail))
        with pytest.raises(RuntimeError):
            session.recover()
        assert db.snapshot(session.stream)[1]["cursor"] == 0
        assert not LedgerStore(db, "reference").read()[1].fills
        assert db.snapshot("account-gate:reference")[1]["ready"] is False
        monkeypatch.setattr(Journal, "append_tx", staticmethod(append))
        assert session.recover().consumed == 2
        assert canonical(venue.events_after()) == original
    venue.close()
    db.close()


def test_absent_lookup_keeps_unknown_reserves_and_never_resubmits(tmp_path):
    db, host, venue, cid, inputs, book, _ = setup(tmp_path)
    session = PaperSession(host)
    reserved = db.snapshot("portfolio:reference")

    def unavailable(ticket):
        raise TimeoutError("No known venue outcome")

    venue.submit_entry = unavailable
    with host:
        with pytest.raises(TimeoutError):
            session.dispatch_entry(cid, inputs, book)
        result = session.recover()
        assert result.caught_up and result.unresolved == (cid,) and result.cursor == 0
        assert db.snapshot("portfolio:reference") == reserved
        with pytest.raises(Conflict, match="recovery must finish"):
            session.dispatch_entry(cid, inputs, book)
        assert state(db, cid) == "UNKNOWN" and not venue.events_after()
    venue.close()
    db.close()


@pytest.mark.parametrize("corruption", ["truncated", "changed", "missing_receipt"])
def test_source_anchor_detects_replaced_or_truncated_history_and_missing_account_proof(
    tmp_path, corruption
):
    db, host, venue, cid, inputs, book, _ = setup(tmp_path)
    with host:
        session = PaperSession(host)
        session.dispatch_entry(cid, inputs, book)
        checkpoint = db.snapshot(session.stream)
        sequence, event = venue.events_after()[-1]
        if corruption == "truncated":
            venue.journal.db.execute("DELETE FROM events WHERE seq=?", (sequence,))
        elif corruption == "changed":
            payload = json.loads(canonical(event))
            payload["data_json"] = canonical({"changed": True})
            venue.journal.db.execute(
                "UPDATE events SET payload=? WHERE seq=?", (canonical(payload), sequence)
            )
        else:
            db.db.execute(
                "DELETE FROM events WHERE event_id=?",
                ("paper-evidence:reference:" + event.event_id,),
            )
        with pytest.raises(Conflict, match="cursor|committed account evidence"):
            PaperSession(host).recover()
        assert db.snapshot(session.stream) == checkpoint
        assert db.snapshot("account-gate:reference")[1]["ready"] is False
    venue.close()
    db.close()


def test_stop_recovery_and_pending_exit_remain_dispatchable_while_entry_paused(tmp_path):
    db, host, venue, sid, stop, now, _ = opened(tmp_path, thin_bid=True)
    with host:
        session = PaperSession(host)
        now[0] += timedelta(milliseconds=1)
        session.dispatch_action(stop)
        assert position(db, sid).protected
        assert not session.recover().unresolved  # a confirmed active stop is not an unknown order
        close = action(db, sid, now, "close", lambda p: p.close())
        session.dispatch_action(close)
        assert session.recover().unresolved == (close,)
        residual_stop = db.db.execute(
            "SELECT client_id FROM intents WHERE purpose='PROTECT' AND state='PREPARED'"
        ).fetchone()[0]
        session.dispatch_action(residual_stop)
        assert position(db, sid).protected and state(db, residual_stop) == "ACKNOWLEDGED"
        assert state(db, close) == "UNKNOWN"
    venue.close()
    db.close()


@pytest.mark.parametrize("outcome", ["UNKNOWN", "ACKNOWLEDGED"])
def test_other_unsettled_entry_blocks_dispatch_even_if_old_account_gate_is_ready(tmp_path, outcome):
    db, host, venue, cid, inputs, book, now = setup(tmp_path)
    other, _ = db.prepare_intent("reference", "unsettled", "ENTRY", {"synthetic": True})
    assert db.claim_dispatch(other)
    if outcome == "ACKNOWLEDGED":
        db.reconcile_intent(other, outcome, {"order": "synthetic"})
    with db.transaction() as tx:
        save_tx(tx, "account-gate:reference", {"ready": True, "safety_paused": False})
    with host, pytest.raises(Conflict, match="Unresolved execution evidence"):
        host.dispatch_entry(cid, inputs, book)
    assert state(db, cid) == "PREPARED" and not venue.events_after()
    venue.close()
    db.close()
