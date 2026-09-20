from datetime import timedelta

import pytest
from test_paper_dispatch import prepared, state

from pvb24.accounting.coordinator import AccountCoordinator
from pvb24.accounting.ledger import FillRecord
from pvb24.decimal_math import D
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, digest
from pvb24.integrations.paper_actions import ACTION_CONTRACT
from pvb24.integrations.paper_dispatch import OrderAccepted, PaperDispatch
from pvb24.replay.account import AccountReplay
from pvb24.replay.events import Delivery, Event, Kind
from pvb24.state import Conflict, Journal
from pvb24.types import Fill, Quality, Side


def wire_backend(backend):
    backend.action_contract = ACTION_CONTRACT
    backend.actions = []

    def submit(ticket):
        reader = Journal(backend.path)
        assert state(reader, ticket.client_id) == "UNKNOWN"
        reader.close()
        backend.actions.append(ticket)
        response = OrderAccepted(
            ticket.client_id,
            "action-" + str(len(backend.actions)),
            digest(ticket),
            ticket.prepared_at,
        )
        backend.orders[ticket.client_id] = response
        if backend.fail:
            raise TimeoutError("Action accepted; reply lost")
        return response

    backend.submit_action = submit


def deliver(db, now, name, kind, payload):
    event = Event(name, kind, now, now, "synthetic-paper", Quality.PRELIMINARY, canonical(payload))
    return AccountReplay(db, "reference", Quality.PRELIMINARY)(
        Delivery(event, "CONSERVATIVE_PRIORITY", 0)
    )


def opened(tmp_path):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    wire_backend(backend)
    response = host.dispatch_entry(cid, inputs, book)
    ticket = backend.calls[0]
    now[0] += timedelta(milliseconds=1)
    fill = Fill(
        "entry-fill",
        response.order_id,
        ticket.signal_id,
        ticket.symbol,
        ticket.side,
        ticket.quantity,
        D("101.21"),
        D("0.1"),
        now[0],
        now[0],
    )
    result = deliver(db, now[0], "entry-fill", Kind.ENTRY_FILL, FillRecord(fill))
    deliver(
        db,
        now[0],
        "entry-terminal",
        Kind.ORDER_OUTCOME,
        {"position_id": ticket.signal_id, "operation": "ENTRY_TERMINAL", "outcome": "FILLED"},
    )
    return db, host, backend, ticket.signal_id, result["action_ids"][0], now


def position(db, sid):
    return Protection.restore(db.snapshot("protection:reference:" + sid)[1])


def confirm_stop(db, host, backend, cid, now):
    host.dispatch_action(cid)
    ticket = backend.actions[-1]
    assert state(db, cid) == "UNKNOWN"  # acceptance alone is not active protection
    return deliver(
        db,
        now[0],
        "active:" + cid,
        Kind.ORDER_OUTCOME,
        {
            "position_id": ticket.signal_id,
            "operation": "STOP_ACK",
            "sequence": ticket.sequence,
            "quantity": ticket.quantity,
            "stop": ticket.stop_price,
            "reduce_only": True,
            "reference": "CONTRACT_PRICE",
        },
    )


def action(db, sid, now, name, op):
    return AccountCoordinator(db, "reference").protection_event(sid, name, name, op, now[0])[0]


def test_protection_and_exit_allowed_while_entry_paused_no_false_stop_ack(tmp_path):
    db, host, backend, sid, cid, now = opened(tmp_path)
    with host:
        assert db.snapshot("account-gate:reference")[1]["ready"] is False
        confirm_stop(db, host, backend, cid, now)
        assert position(db, sid).protected and state(db, cid) == "ACKNOWLEDGED"
        ticket = backend.actions[0]
        assert ticket.order_type == "STOP_MARKET" and ticket.reduce_only is True
        assert ticket.stop_reference == "CONTRACT_PRICE" and ticket.side is Side.SHORT
        # Looking up receipt identity must not collide with STOP_ACK core evidence.
        assert host.lookup(cid) == backend.orders[cid]
        exit_id = action(db, sid, now, "close", lambda p: p.protection_failed())
        host.dispatch_action(exit_id)
        assert backend.actions[-1].order_type == "MARKET"
        assert backend.actions[-1].quantity == position(db, sid).remaining
        assert db.snapshot("account-gate:reference")[1]["safety_paused"] is True
        assert position(db, sid).remaining > 0 and state(db, exit_id) == "UNKNOWN"
    db.close()


def test_replacement_must_be_active_before_cancel_and_receipt_does_not_remove_stop(tmp_path):
    db, host, backend, sid, old_id, now = opened(tmp_path)
    with host:
        confirm_stop(db, host, backend, old_id, now)
        old_stop = position(db, sid).effective_stop
        new_id = action(
            db, sid, now, "tighten", lambda p: p.tighten_stop(old_stop + D("0.01"), D(101))
        )
        result = confirm_stop(db, host, backend, new_id, now)
        cancel_id = result["action_ids"][0]
        host.dispatch_action(cancel_id)
        t = backend.actions[-1]
        assert t.order_type == "CANCEL" and t.quantity == 0
        assert t.target_client_id == old_id and t.target_order_id == backend.orders[old_id].order_id
        assert len(position(db, sid).confirmed_stops) == 2
        assert not position(db, sid).canceled_stops
        with pytest.raises(Conflict, match="never resend"):
            host.dispatch_action(cancel_id)
    db.close()


def test_erroneous_cancel_of_only_stop_cannot_reach_backend(tmp_path):
    db, host, backend, sid, stop_id, now = opened(tmp_path)
    with host:
        confirm_stop(db, host, backend, stop_id, now)
        cancel_id = action(
            db,
            sid,
            now,
            "unsafe-upstream-request",
            lambda p: (p._action("CANCEL_PROTECTION", D(0), target_sequence=1),),
        )
        with pytest.raises(Conflict, match="only confirmed protection"):
            host.dispatch_action(cancel_id)
        assert len(backend.actions) == 1 and state(db, cancel_id) == "PREPARED"
    db.close()


def test_exit_pending_quantities_prevent_duplicate_closure_under_different_ids(tmp_path):
    db, host, backend, sid, _, now = opened(tmp_path)
    with host:
        first = action(db, sid, now, "first", lambda p: p.close(D(1)))
        host.dispatch_action(first)
        duplicate = action(db, sid, now, "duplicate", lambda p: p.close())
        with pytest.raises(Conflict, match="already reserves"):
            host.dispatch_action(duplicate)
        uncovered = action(db, sid, now, "uncovered", lambda p: p.close(p.remaining - D(1)))
        host.dispatch_action(uncovered)
        assert sum(t.quantity for t in backend.actions) == position(db, sid).remaining
    db.close()


def test_quantity_change_rejects_stale_protection_ticket_instead_of_resizing_id(tmp_path):
    db, host, backend, sid, stop_id, now = opened(tmp_path)
    with host:
        p = position(db, sid)
        fill = Fill(
            "partial-exit",
            "external-confirmed-exit",
            sid,
            p.symbol,
            Side.SHORT,
            D(1),
            D(102),
            D("0.01"),
            now[0],
            now[0],
            reduce_only=True,
        )
        deliver(db, now[0], "partial-exit", Kind.REDUCE_FILL, FillRecord(fill))
        with pytest.raises(Conflict, match="exceeds confirmed remaining"):
            host.dispatch_action(stop_id)
        assert not backend.actions and state(db, stop_id) == "PREPARED"
    db.close()


def test_action_timeout_restart_lookup_preserves_unresolved_stop(tmp_path):
    db, host, backend, sid, cid, now = opened(tmp_path)
    backend.fail = True
    with host, pytest.raises(TimeoutError):
        host.dispatch_action(cid)
    assert state(db, cid) == "UNKNOWN" and not position(db, sid).protected
    db.close()
    db = Journal(tmp_path / "planning.sqlite")
    with PaperDispatch(db, "reference", Quality.PRELIMINARY, backend, lambda: now[0]) as host:
        assert host.lookup(cid) is not None
        assert state(db, cid) == "UNKNOWN" and not position(db, sid).protected
        with pytest.raises(Conflict, match="never resend"):
            host.dispatch_action(cid)
        assert len(backend.actions) == 1
    db.close()


def test_cancel_unknown_entry_requires_lookup_identity_and_keeps_reservation(tmp_path):
    db, host, backend, entry_id, inputs, book, now = prepared(tmp_path)
    wire_backend(backend)
    backend.fail = True
    with host:
        with pytest.raises(TimeoutError):
            host.dispatch_entry(entry_id, inputs, book)
        sid = backend.calls[0].signal_id
        cancel_id, _ = db.prepare_intent(
            "reference",
            sid,
            "CANCEL_ENTRY",
            {"target_client_id": entry_id, "reason": "GLOBAL_RISK_PAUSE"},
        )
        held = db.snapshot("portfolio:reference")
        with pytest.raises(Conflict, match="identity is unresolved"):
            host.dispatch_action(cancel_id)
        host.lookup(entry_id)
        backend.fail = False
        host.dispatch_action(cancel_id)
        assert backend.actions[-1].target_client_id == entry_id
        assert state(db, entry_id) == "ACKNOWLEDGED"
        assert state(db, cancel_id) == "UNKNOWN" and db.snapshot("portfolio:reference") == held
    db.close()


def test_changed_action_contract_and_backdated_action_reject(tmp_path):
    db, host, backend, _, cid, now = opened(tmp_path)
    with host:
        backend.action_contract = "native-dry-run"
        with pytest.raises(ValueError, match="explicitly support"):
            host.dispatch_action(cid)
        backend.action_contract = ACTION_CONTRACT
        now[0] -= timedelta(seconds=1)
        with pytest.raises(Conflict, match="backdate action"):
            host.dispatch_action(cid)
    assert not backend.actions
    db.close()
