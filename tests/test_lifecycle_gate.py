from dataclasses import replace
from datetime import timedelta

import pytest
from test_entry_planner import setup
from test_paper_actions import action, confirm_stop, opened, position, wire_backend
from test_paper_dispatch import prepared, state

from pvb24.data.lifecycle import DelistingNotice, LifecycleService, entry_block_reason
from pvb24.execution.planner import EntryPlanner
from pvb24.ids import canonical
from pvb24.replay.account import AccountReplay
from pvb24.replay.events import Delivery, Event, Kind
from pvb24.state import Conflict, Journal
from pvb24.types import Quality


def notice(now, **changes):
    item = DelistingNotice(
        "BTCUSDT",
        now - timedelta(seconds=1),
        now + timedelta(days=7),
        now,
        "synthetic-lifecycle-fixture",
        "revision-1",
        False,
    )
    return replace(item, **changes)


def test_future_notice_cannot_change_current_signals_or_reservations(tmp_path):
    db, _, service, universe, batch, _ = setup(tmp_path)
    now = batch.decision_time
    before = db.snapshot("portfolio:reference")
    with pytest.raises(ValueError, match="not yet available"):
        LifecycleService(db, "reference").announce(notice(now + timedelta(seconds=1)), now)
    assert entry_block_reason(db.db, "reference", "BTCUSDT") is None
    assert service.evaluate(universe, batch.ranked[0].signal_time, now) == batch
    assert db.snapshot("portfolio:reference") == before
    db.close()


def test_notice_immediately_overrides_cached_daily_universe_and_already_ranked_batch(tmp_path):
    db, _, service, universe, batch, sources = setup(tmp_path, ("BTCUSDT", "ETHUSDT"))
    now = batch.decision_time
    result = LifecycleService(db, "reference").announce(notice(now), now)
    assert not result["action_ids"] and not result["canceled_unsent"]
    revised = service.evaluate(universe, batch.ranked[0].signal_time, now)
    assert [s.symbol for s in revised.ranked] == ["ETHUSDT"]
    assert all(
        "DELISTING_ANNOUNCED" in s.rejection_codes
        for s in revised.decisions
        if s.symbol == "BTCUSDT"
    )
    planned = EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(batch, sources, now)
    assert planned[0]["reason"] == "DELISTING_ANNOUNCED" and planned[0]["client_id"] is None
    assert planned[1]["reason"] == "ACCEPTED"
    db.close()


def test_unsent_entry_is_retired_atomically_without_releasing_risk_or_sending_order(tmp_path):
    db, host, backend, cid, inputs, book, clock = prepared(tmp_path)
    before = db.snapshot("portfolio:reference")
    n = notice(clock[0])
    result = LifecycleService(db, "reference").announce(n, clock[0])
    assert result["canceled_unsent"] == [cid] and state(db, cid) == "CANCELED"
    assert not db.snapshot("account-gate:reference")[1]["ready"]
    assert db.snapshot("portfolio:reference") == before
    with host, pytest.raises(Conflict):
        host.dispatch_entry(cid, inputs, book)
    assert not backend.calls and not db.claim_dispatch(cid)
    db.close()
    reopened = Journal(tmp_path / "planning.sqlite")
    assert (
        LifecycleService(reopened, "reference").announce(n, clock[0] + timedelta(seconds=1))
        == result
    )
    assert entry_block_reason(reopened.db, "reference", "BTCUSDT") == "DELISTING_ANNOUNCED"
    reopened.close()


def test_unknown_entry_requests_cancellation_once_without_assuming_outcome_or_freeing_cash(
    tmp_path,
):
    db, host, backend, cid, inputs, book, clock = prepared(tmp_path)
    backend.fail = True
    with pytest.raises(TimeoutError):
        host.dispatch_entry(cid, inputs, book)
    before = db.snapshot("portfolio:reference")
    first = LifecycleService(db, "reference").announce(notice(clock[0]), clock[0])
    second = LifecycleService(db, "reference").announce(
        notice(clock[0], revision_id="revision-2"), clock[0]
    )
    assert len(first["action_ids"]) == 1 and first["action_ids"] == second["action_ids"]
    assert state(db, cid) == "UNKNOWN" and db.snapshot("portfolio:reference") == before
    assert len(backend.calls) == 1 and not first["canceled_unsent"]
    assert (
        db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='CANCEL_ENTRY'").fetchone()[0]
        == 1
    )
    host.close()
    db.close()


def test_existing_risk_cancel_is_reused_and_dispatch_remains_allowed_for_cancellation(tmp_path):
    db, host, backend, cid, inputs, book, clock = prepared(tmp_path)
    wire_backend(backend)
    host.dispatch_entry(cid, inputs, book)
    sid = backend.calls[0].signal_id
    with db.transaction() as tx:
        cancel, _ = Journal.prepare_intent_tx(
            tx,
            "reference",
            sid,
            "CANCEL_ENTRY",
            {"target_client_id": cid, "reason": "GLOBAL_RISK_PAUSE"},
        )
    result = LifecycleService(db, "reference").announce(notice(clock[0]), clock[0])
    assert result["action_ids"] == [cancel]
    with host:
        host.dispatch_action(cancel)
    assert backend.actions[0].purpose == "CANCEL_ENTRY"
    assert state(db, cid) == "ACKNOWLEDGED"  # cancellation request is not confirmation
    db.close()


def test_open_position_protection_and_reduce_only_management_survive_notice(tmp_path):
    db, host, backend, sid, stop, clock = opened(tmp_path)
    with host:
        confirm_stop(db, host, backend, stop, clock)
        before = db.snapshot("protection:reference:" + sid)
        result = LifecycleService(db, "reference").announce(notice(clock[0]), clock[0])
        assert not result["action_ids"] and not result["canceled_unsent"]
        assert db.snapshot("protection:reference:" + sid) == before and position(db, sid).protected
        exit_id = action(db, sid, clock, "explicit-exit", lambda p: p.close(p.remaining))
        host.dispatch_action(exit_id)
        assert backend.actions[-1].reduce_only and backend.actions[-1].purpose == "EXIT_MARKET"
    db.close()


def test_notice_receipt_failure_rolls_back_block_cancel_and_protection(tmp_path, monkeypatch):
    db, host, _, cid, _, _, clock = prepared(tmp_path)
    before = tuple(tuple(row) for row in db.db.execute("SELECT * FROM snapshots ORDER BY stream"))
    original = Journal.append_tx

    def fail(tx, key, payload):
        if key.startswith("delisting-notice:"):
            raise RuntimeError("injected receipt failure")
        return original(tx, key, payload)

    monkeypatch.setattr(Journal, "append_tx", staticmethod(fail))
    with pytest.raises(RuntimeError, match="injected"):
        LifecycleService(db, "reference").announce(notice(clock[0]), clock[0])
    assert state(db, cid) == "PREPARED"
    assert (
        tuple(tuple(row) for row in db.db.execute("SELECT * FROM snapshots ORDER BY stream"))
        == before
    )
    assert entry_block_reason(db.db, "reference", "BTCUSDT") is None
    host.close()
    db.close()


def test_replay_notice_is_atomic_idempotent_and_checks_payload_timing(tmp_path):
    db, _, _, _, batch, _ = setup(tmp_path)
    n = notice(batch.decision_time)
    event = Event(
        "notice",
        Kind.OBSERVATION,
        n.announced_at,
        n.available_at,
        n.source,
        Quality.PRELIMINARY,
        canonical({"type": "DELISTING_NOTICE", "record": n}),
    )
    replay = AccountReplay(db, "reference", Quality.PRELIMINARY)
    delivery = Delivery(event, "CONSERVATIVE_PRIORITY", 0)
    result = replay(delivery)
    assert replay(delivery) == result and result["blocked_symbol"] == "BTCUSDT"
    changed = replace(
        event, event_id="bad-timing", event_time=n.announced_at - timedelta(seconds=1)
    )
    with pytest.raises(ValueError, match="timing differs"):
        replay(Delivery(changed, "CONSERVATIVE_PRIORITY", 0))
    db.close()


def test_changed_revision_and_backdated_entry_evaluation_fail_closed(tmp_path):
    db, _, _, _, batch, _ = setup(tmp_path)
    now = batch.decision_time
    service = LifecycleService(db, "reference")
    service.announce(notice(now), now)
    with pytest.raises(Conflict, match="revision changed"):
        service.announce(notice(now, scheduled_settlement_at=now + timedelta(days=8)), now)
    with pytest.raises(Conflict, match="backdate"):
        entry_block_reason(db.db, "reference", "BTCUSDT", now - timedelta(seconds=1))
    db.close()


def test_lifecycle_latch_blocks_direct_claim_even_if_account_gate_is_ready(tmp_path):
    db, _, _, _, batch, _ = setup(tmp_path)
    now = batch.decision_time
    LifecycleService(db, "reference").announce(notice(now), now)
    with db.transaction() as tx:
        cid, _ = Journal.prepare_intent_tx(
            tx, "reference", "new-bypass", "ENTRY", {"symbol": "BTCUSDT"}
        )
        protect, _ = Journal.prepare_intent_tx(
            tx, "reference", "existing", "PROTECT", {"symbol": "BTCUSDT"}
        )
    assert db.snapshot("account-gate:reference")[1]["ready"]
    assert not db.claim_dispatch(cid) and state(db, cid) == "PREPARED"
    assert db.claim_dispatch(protect)
    db.close()


def test_later_global_pause_reuses_lifecycle_cancellation_without_payload_conflict(tmp_path):
    from pvb24.accounting.coordinator import save_tx
    from pvb24.accounting.risk_service import AccountRiskService

    db, host, _, cid, inputs, book, clock = prepared(tmp_path)
    host.dispatch_entry(cid, inputs, book)
    result = LifecycleService(db, "reference").announce(notice(clock[0]), clock[0])
    # Force a known daily drawdown through the prior-day/start-of-day baseline,
    # without claiming a fill/cashflow that did not occur in this fixture.
    from pvb24.accounting.controls import EquityControl

    control = EquityControl.restore(db.snapshot("equity-control:reference")[1])
    control.day_start_equity = control.day_start_equity * 2
    with db.transaction() as tx:
        save_tx(tx, "equity-control:reference", control.checkpoint())
    _, actions = AccountRiskService(db, "reference").sample(
        clock[0].replace(second=0) + timedelta(minutes=1), []
    )
    assert tuple(result["action_ids"]) == actions
    assert (
        db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='CANCEL_ENTRY'").fetchone()[0]
        == 1
    )
    host.close()
    db.close()
