from dataclasses import replace
from datetime import timedelta

import pytest
from test_paper_actions import action, position, wire_backend
from test_paper_dispatch import prepared, state

from pvb24.accounting.coordinator import AccountCoordinator
from pvb24.accounting.ledger import FillRecord, LedgerStore
from pvb24.decimal_math import ZERO, D
from pvb24.ids import canonical
from pvb24.integrations.paper_dispatch import PaperDispatch
from pvb24.integrations.paper_evidence import PaperEvent, PaperEvidence
from pvb24.state import Conflict, Journal
from pvb24.types import Fill, Quality, Side


def event(backend, cid, now, name, kind, payload):
    return PaperEvent(
        name,
        backend.instance_id,
        cid,
        kind,
        now[0],
        now[0],
        Quality.PRELIMINARY,
        canonical(payload),
    )


def started(tmp_path):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    wire_backend(backend)
    host.dispatch_entry(cid, inputs, book)
    return db, host, backend, cid, now, PaperEvidence(host)


def fill_event(backend, cid, ticket, now, name, quantity, price="101.21"):
    fill = Fill(
        name,
        backend.orders[cid].order_id,
        ticket.signal_id,
        ticket.symbol,
        ticket.side,
        quantity,
        D(price),
        D("0.1"),
        now[0],
        now[0],
        reduce_only=ticket.reduce_only,
    )
    return event(backend, cid, now, name, "FILL", {"record": FillRecord(fill)})


def terminal(backend, cid, now, name, outcome, cumulative):
    return event(
        backend,
        cid,
        now,
        name,
        "TERMINAL",
        {
            "venue_order_id": backend.orders[cid].order_id,
            "outcome": outcome,
            "cumulative_fill_quantity": cumulative,
        },
    )


def active(service, host, backend, cid, now):
    host.dispatch_action(cid)
    t = backend.actions[-1]
    return service.ingest(
        event(
            backend,
            cid,
            now,
            "active:" + cid,
            "STOP_ACTIVE",
            {
                "venue_order_id": backend.orders[cid].order_id,
                "quantity": t.quantity,
                "stop": t.stop_price,
                "reduce_only": True,
                "reference": "CONTRACT_PRICE",
            },
        )
    )


def cancel_event(backend, cid, target, now, cumulative=ZERO, outcome="CANCELED"):
    return event(
        backend,
        cid,
        now,
        "cancel:" + cid,
        "CANCEL_CONFIRMED",
        {
            "request_order_id": backend.orders[cid].order_id,
            "target_client_id": target,
            "venue_order_id": backend.orders[target].order_id,
            "outcome": outcome,
            "cumulative_fill_quantity": cumulative,
        },
    )


def test_owned_entry_replacement_cancel_exit_and_flat_cash_proof(tmp_path):
    db, host, backend, cid, now, service = started(tmp_path)
    with host:
        t = backend.calls[0]
        result = service.ingest(fill_event(backend, cid, t, now, "entry", t.quantity))
        service.ingest(terminal(backend, cid, now, "entry-end", "FILLED", t.quantity))
        old = result["action_ids"][0]
        active(service, host, backend, old, now)
        next_stop = position(db, t.signal_id).effective_stop + D("0.01")
        new = action(db, t.signal_id, now, "trail", lambda p: p.tighten_stop(next_stop, D(101)))
        result = active(service, host, backend, new, now)
        cancel = result["action_ids"][0]
        held = db.snapshot("portfolio:reference")
        host.dispatch_action(cancel)
        assert state(db, old) == "ACKNOWLEDGED"
        proof = cancel_event(backend, cancel, old, now)
        service.ingest(proof)
        assert state(db, old) == "CANCELED" and state(db, cancel) == "ACKNOWLEDGED"
        assert position(db, t.signal_id).protected
        assert db.snapshot("portfolio:reference") == held
        assert service.ingest(proof) == {"action_ids": []}
        now[0] += timedelta(milliseconds=1)
        close = action(db, t.signal_id, now, "close", lambda p: p.close())
        host.dispatch_action(close)
        exit_ticket = backend.actions[-1]
        service.ingest(fill_event(backend, close, exit_ticket, now, "exit", t.quantity, "102"))
        service.ingest(terminal(backend, close, now, "exit-end", "FILLED", t.quantity))
        assert position(db, t.signal_id).remaining == 0
        view = LedgerStore(db, "reference").read()[1].view(now[0])
        assert view.cash == D(1000) + view.realized_gross - view.fees + view.funding
        assert AccountCoordinator(db, "reference").reconcile_flat(now[0], view.cash, "paper-flat")
        assert db.snapshot("portfolio:reference")[1]["exposures"] == []
    db.close()


def test_cancel_fill_race_waits_for_actual_fill_and_retains_partial_position(tmp_path):
    db, host, backend, cid, now, service = started(tmp_path)
    with host:
        t = backend.calls[0]
        cancel, _ = db.prepare_intent(
            "reference",
            t.signal_id,
            "CANCEL_ENTRY",
            {"target_client_id": cid, "reason": "GLOBAL_RISK_PAUSE"},
        )
        host.dispatch_action(cancel)
        proof = cancel_event(backend, cancel, cid, now, D(1))
        held = db.snapshot("portfolio:reference")
        with pytest.raises(Conflict, match="missing or inconsistent fill"):
            service.ingest(proof)
        assert state(db, cancel) == "UNKNOWN" and state(db, cid) == "ACKNOWLEDGED"
        assert not position(db, t.signal_id).terminal
        service.ingest(fill_event(backend, cid, t, now, "racing-fill", D(1)))
        result = service.ingest(proof)
        assert result == {"action_ids": []}
        assert state(db, cid) == "CANCELED" and position(db, t.signal_id).remaining == 1
        assert position(db, t.signal_id).terminal
        assert db.snapshot("portfolio:reference") == held
    db.close()


@pytest.mark.parametrize("case", ["order", "position", "side", "timing", "future", "source"])
def test_unowned_inconsistent_or_future_fill_is_not_booked(tmp_path, case):
    db, host, backend, cid, now, service = started(tmp_path)
    with host:
        t = backend.calls[0]
        proof = fill_event(backend, cid, t, now, "bad", t.quantity)
        import json

        raw = json.loads(proof.data_json)
        if case == "order":
            raw["record"]["fill"]["order_id"] = "foreign"
        elif case == "position":
            raw["record"]["fill"]["position_id"] = "foreign"
        elif case == "side":
            raw["record"]["fill"]["side"] = "SHORT"
        elif case == "timing":
            raw["record"]["fill"]["event_time"] = (now[0] - timedelta(seconds=1)).isoformat()
        elif case == "future":
            proof = replace(proof, available_at=now[0] + timedelta(seconds=1))
        else:
            proof = replace(proof, instance_id="foreign")
        proof = replace(proof, data_json=canonical(raw))
        with pytest.raises((Conflict, ValueError)):
            service.ingest(proof)
        assert position(db, t.signal_id).remaining == 0
        assert not LedgerStore(db, "reference").read()[1].fills
    db.close()


def test_stop_rejection_triggers_owned_safety_close(tmp_path):
    db, host, backend, cid, now, service = started(tmp_path)
    with host:
        t = backend.calls[0]
        result = service.ingest(fill_event(backend, cid, t, now, "entry", t.quantity))
        stop = result["action_ids"][0]
        host.dispatch_action(stop)
        result = service.ingest(terminal(backend, stop, now, "rejected-stop", "REJECTED", D(0)))
        assert position(db, t.signal_id).safety_paused
        assert state(db, stop) == "REJECTED"
        host.dispatch_action(result["action_ids"][0])
        assert backend.actions[-1].quantity == t.quantity
        assert backend.actions[-1].purpose == "EXIT_MARKET"
    db.close()


def test_fill_receipt_survives_restart_and_changed_economics_fail_closed(tmp_path):
    db, host, backend, cid, now, service = started(tmp_path)
    t = backend.calls[0]
    proof = fill_event(backend, cid, t, now, "entry", t.quantity)
    result = service.ingest(proof)
    host.close()
    db.close()
    db = Journal(tmp_path / "planning.sqlite")
    with PaperDispatch(db, "reference", Quality.PRELIMINARY, backend, lambda: now[0]) as host:
        service = PaperEvidence(host)
        assert service.ingest(proof) == result
        changed = fill_event(backend, cid, t, now, "entry", t.quantity, "102")
        with pytest.raises(Conflict, match="Changed PAPER execution event"):
            service.ingest(changed)
        assert position(db, t.signal_id).entry_vwap == D("101.21")
        assert db.snapshot("account-gate:reference")[1]["ready"] is False
    db.close()


def test_receipt_failure_rolls_back_nested_account_fill_and_leaves_entry_paused(
    tmp_path, monkeypatch
):
    db, host, backend, cid, now, service = started(tmp_path)
    original = Journal.append_tx

    def fail(tx, event_id, payload):
        if event_id.startswith("paper-evidence:"):
            raise RuntimeError("failed evidence receipt")
        return original(tx, event_id, payload)

    monkeypatch.setattr(Journal, "append_tx", staticmethod(fail))
    with host:
        t = backend.calls[0]
        with pytest.raises(RuntimeError):
            service.ingest(fill_event(backend, cid, t, now, "entry", t.quantity))
        assert not LedgerStore(db, "reference").read()[1].fills
        assert position(db, t.signal_id).remaining == 0
        assert db.snapshot("account-gate:reference")[1]["ready"] is False
        assert (
            db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='PROTECT'").fetchone()[0] == 0
        )
    db.close()


def test_authoritative_overfill_is_retained_and_forces_safety_close(tmp_path):
    db, host, backend, cid, now, service = started(tmp_path)
    with host:
        t = backend.calls[0]
        result = service.ingest(fill_event(backend, cid, t, now, "overfill", t.quantity + D(1)))
        p = position(db, t.signal_id)
        assert p.remaining == t.quantity + D(1) and p.safety_paused
        assert len(result["action_ids"]) == 1
        assert state(db, cid) == "ACKNOWLEDGED"
    db.close()


def test_forced_liquidation_has_explicit_owned_position_and_visible_cash_loss(tmp_path):
    db, host, backend, cid, now, service = started(tmp_path)
    with host:
        t = backend.calls[0]
        service.ingest(fill_event(backend, cid, t, now, "entry", t.quantity))
        service.ingest(terminal(backend, cid, now, "entry-end", "FILLED", t.quantity))
        now[0] += timedelta(milliseconds=1)
        f = Fill(
            "forced-fill",
            "forced-order",
            t.signal_id,
            t.symbol,
            Side.SHORT,
            t.quantity,
            D(75),
            D(1),
            now[0],
            now[0],
            reduce_only=True,
        )
        proof = event(
            backend, cid, now, "forced", "LIQUIDATION", {"record": FillRecord(f, liquidation=True)}
        )
        result = service.ingest(proof)
        assert service.ingest(proof) == result
        view = LedgerStore(db, "reference").read()[1].view(now[0])
        assert view.liquidation_count == 1 and view.realized_gross < 0 and view.fees == D("1.1")
        assert view.cash == D(1000) + view.realized_gross - view.fees
        assert position(db, t.signal_id).remaining == 0
    db.close()
