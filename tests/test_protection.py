import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_data import NOW

from pvb24.decimal_math import D
from pvb24.execution.protection import Protection, ProtectionStore
from pvb24.ids import canonical
from pvb24.state import Conflict, Journal
from pvb24.types import Fill, Side, SymbolState


def position(side=Side.LONG):
    return Protection("signal", "BTCUSDT", side, D(5), D(1), D("0.1"))


def fill(name="f1", qty="2", price="100", side=Side.LONG, reduce=False, seconds=0):
    time = NOW + timedelta(seconds=seconds)
    return Fill(
        name,
        "entry" if not reduce else "exit",
        "signal",
        "BTCUSDT",
        side,
        D(qty),
        D(price),
        D("0.01"),
        time,
        time + timedelta(milliseconds=20),
        reduce,
    )


def ack(p, action):
    return p.confirm_stop(
        action.sequence, action.quantity, action.stop, reduce_only=True, reference="CONTRACT_PRICE"
    )


def test_zero_fill_consumes_signal_but_no_six_hour_cooldown():
    p = position()
    p.entry_terminal()
    assert p.state is SymbolState.READY
    assert p.first_fill_time is None and p.full_exit_time is None
    assert p.cooldown_finished(NOW)
    assert p.remaining == 0


@pytest.mark.parametrize("side,stop", [(Side.LONG, "98"), (Side.SHORT, "102")])
def test_each_partial_fill_protected_and_replacement_confirmed_before_cancel(side, stop):
    p = position(side)
    (first,) = p.fill(fill(side=side))
    assert first.quantity == 2 and first.stop == D(stop) and first.reduce_only
    assert not p.protected  # a request is not proof of protection
    assert ack(p, first) == () and p.protected
    (second,) = p.fill(fill("f2", "3", side=side, seconds=1))
    assert second.quantity == 5 and not p.protected
    cancels = ack(p, second)
    assert p.protected and len(cancels) == 1
    assert cancels[0].target_sequence == first.sequence
    assert p.confirm_cancel(first.sequence) == ()
    assert p.protected
    assert p.remaining == 5 and p.entry_vwap == 100


def test_old_ack_arriving_after_new_one_is_canceled_without_erasing_new_protection():
    p = position()
    (a,) = p.fill(fill())
    (b,) = p.fill(fill("f2", "3", seconds=1))
    assert ack(p, b) == () and p.protected
    (cancel,) = ack(p, a)
    assert cancel.target_sequence == a.sequence and p.protected


def test_cancel_fill_race_retains_late_fill_and_does_not_chase_remainder():
    p = position()
    p.entry_terminal()
    actions = p.fill(fill())
    assert p.terminal and p.state is SymbolState.OPEN
    assert p.entry_quantity == 2 and actions[0].purpose == "PROTECT"
    assert all(a.purpose != "ENTRY" for a in actions)
    assert p.fill(fill()) == ()
    with pytest.raises(Conflict):
        p.fill(replace(fill(), quantity=D(3)))


def test_vwap_initial_risk_freezes_after_entry_and_stop_never_widens():
    p = position()
    p.fill(fill(qty="2", price="100.1"))
    old = p.effective_stop
    p.fill(fill("f2", "3", "99.9", seconds=1))
    p.entry_terminal()
    assert p.entry_vwap == D("99.98")
    assert p.initial_stop == D("97.9")
    assert p.effective_stop == old == D("98.1")
    initial = p.initial_price_risk
    p.fill(fill("exit1", "1", "105", Side.SHORT, True, 10))
    assert p.initial_price_risk == initial
    assert p.entry_vwap == D("99.98")


def test_protection_failure_requests_reduce_only_full_close_and_pause():
    p = position()
    (a,) = p.fill(fill())
    (close,) = p.confirm_stop(
        a.sequence, a.quantity, a.stop, reduce_only=True, reference="MARK_PRICE"
    )
    assert close.purpose == "EXIT_MARKET" and close.quantity == 2 and close.reduce_only
    assert p.safety_paused and p.remaining == 2
    assert p.state is SymbolState.OPEN  # global pause does not erase position
    assert p.close(D(100))[0].quantity == 2


def test_unexpected_loss_of_last_stop_closes_position():
    p = position()
    (a,) = p.fill(fill())
    ack(p, a)
    (close,) = p.confirm_cancel(a.sequence)
    assert p.safety_paused and close.quantity == 2


def test_full_exit_actual_timestamp_starts_cooldown_and_late_entry_closes_safely():
    p = position()
    (a,) = p.fill(fill())
    ack(p, a)
    p.entry_terminal()
    (cancel,) = p.fill(fill("exit", "2", "99", Side.SHORT, True, 10))
    assert cancel.purpose == "CANCEL_PROTECTION"
    assert p.state is SymbolState.COOLDOWN and p.full_exit_time == NOW + timedelta(seconds=10)
    assert not p.cooldown_finished(NOW + timedelta(hours=6, seconds=9))
    assert p.cooldown_finished(NOW + timedelta(hours=6, seconds=10))
    (close,) = p.fill(fill("late", "1", seconds=1))
    assert p.remaining == 1 and p.safety_paused and close.quantity == 1
    assert p.state is SymbolState.OPEN


def test_overfill_anomaly_preserves_evidence_and_requires_reconciliation():
    p = position()
    p.fill(fill())
    (reconcile,) = p.fill(fill("exit", "3", side=Side.SHORT, reduce=True))
    assert p.safety_paused and reconcile.purpose == "RECONCILE"
    assert "exit" in p.fills and p.remaining == -1
    assert p.close() == ()  # never pretend to issue an entry to reverse the anomaly


def test_restart_checkpoint_retains_fills_actions_protection_and_idempotency():
    p = position()
    (a,) = p.fill(fill())
    ack(p, a)
    q = Protection.restore(json.loads(canonical(p.checkpoint())))
    assert canonical(q.checkpoint()) == canonical(p.checkpoint())
    assert q.protected and q.fill(fill()) == ()
    assert q.fill(fill("f2", "3", seconds=1)) == p.fill(fill("f2", "3", seconds=1))


def test_store_atomically_preserves_fill_state_and_protective_intent(tmp_path):
    path = tmp_path / "protection.sqlite"
    db = Journal(path)
    store = ProtectionStore(db, "paper")
    store.initialize(position())
    ids = store.apply("signal", "fill1", fill(), lambda p: p.fill(fill()))
    assert len(ids) == 1
    db.close()
    db = Journal(path)
    store = ProtectionStore(db, "paper")
    assert store.apply("signal", "fill1", fill(), lambda p: p.fill(fill())) == ()
    _, snapshot = db.snapshot("protection:paper:signal")
    assert Protection.restore(snapshot).remaining == 2
    assert db.claim_dispatch(ids[0]) and not db.claim_dispatch(ids[0])
    db.close()


def test_transaction_failure_does_not_leave_fill_without_protection_intent(tmp_path, monkeypatch):
    db = Journal(tmp_path / "protection.sqlite")
    store = ProtectionStore(db, "paper")
    store.initialize(position())

    def fail(*args, **kwargs):
        raise RuntimeError("injected write failure")

    monkeypatch.setattr(Journal, "prepare_intent_tx", staticmethod(fail))
    with pytest.raises(RuntimeError):
        store.apply("signal", "fill1", fill(), lambda p: p.fill(fill()))
    _, snapshot = db.snapshot("protection:paper:signal")
    assert Protection.restore(snapshot).remaining == 0
    assert db.db.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 0
    assert (
        db.db.execute(
            "SELECT COUNT(*) FROM events WHERE event_id LIKE 'protection-event:%'"
        ).fetchone()[0]
        == 0
    )
    db.close()
