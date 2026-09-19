from dataclasses import replace
from datetime import timedelta

import pytest
from test_entry_planner import setup

from pvb24.accounting.ledger import LedgerStore
from pvb24.accounting.risk_service import AccountRiskService
from pvb24.decimal_math import D
from pvb24.execution.planner import EntryPlanner
from pvb24.execution.protection import Protection
from pvb24.replay.events import Kind
from pvb24.replay.preliminary import MinuteOpen
from pvb24.replay.venue import PreliminaryVenue
from pvb24.state import Conflict, Journal
from pvb24.types import Quality


def planned(tmp_path):
    db, _, _, _, batch, sources = setup(tmp_path)
    result = EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(
        batch, sources, batch.decision_time
    )
    cid = result[0]["client_id"]
    venue = PreliminaryVenue(db, "reference")
    request = venue.freeze_entry(cid, sigma=D(0), available_at=batch.decision_time)
    opening = MinuteOpen(
        "BTCUSDT", request.expected_open, request.expected_open, D("101.21"), "synthetic-open", "v1"
    )
    AccountRiskService(db, "reference").sample(opening.time, [])
    return db, venue, cid, request, opening


def test_signal_to_entry_protection_hold_exit_and_cash_identity_across_restart(tmp_path):
    db, venue, cid, request, opening = planned(tmp_path)
    result = venue.execute_entry(cid, opening)
    assert result["reason"] == "MODELED_FULL_FILL" and result["quality"] == "PRELIMINARY"
    assert "partial_fills" in result["unverified"]
    signal = result["fill"]["position_id"]
    position = Protection.restore(db.snapshot("protection:reference:" + signal)[1])
    assert position.remaining == request.quantity and position.terminal and not position.protected
    assert position.entry_vwap == D("101.3")  # adverse tick rounding after proxy slippage
    protection_id = result["action_ids"][0]
    ack_time = opening.time + timedelta(milliseconds=1)
    venue.acknowledge_protection(protection_id, ack_time)
    assert Protection.restore(db.snapshot("protection:reference:" + signal)[1]).protected
    db.close()
    db = Journal(tmp_path / "planning.sqlite")
    venue = PreliminaryVenue(db, "reference")
    assert venue.execute_entry(cid, opening) == result
    later = opening.time + timedelta(hours=72)
    exit_request = venue._deliver(
        "hold", Kind.EXIT_DECISION, {"type": "TIMER", "position_id": signal}, later, later
    )
    exit_open = MinuteOpen(
        "BTCUSDT",
        later + timedelta(minutes=1),
        later + timedelta(minutes=1),
        D(110),
        "synthetic-open",
        "v1",
    )
    closed = venue.execute_exit(
        exit_request["action_ids"][0],
        exit_open,
        sigma=D(0),
        recent_quote_volume=D(1000000),
        inputs_available_at=later,
    )
    view = LedgerStore(db, "reference").read()[1].view(exit_open.available_at)
    assert view.positions[0].quantity == 0
    assert view.cash == D(1000) + view.realized_gross - view.fees + view.funding
    assert D(closed["fill"]["price"]) < exit_open.price
    assert (
        venue.execute_exit(
            exit_request["action_ids"][0],
            exit_open,
            sigma=D(0),
            recent_quote_volume=D(1000000),
            inputs_available_at=later,
        )
        == closed
    )
    db.close()


def test_unknown_entry_is_reconciliation_only_not_resubmitted(tmp_path):
    db, venue, cid, _, opening = planned(tmp_path)
    assert db.claim_dispatch(cid)
    with pytest.raises(Conflict, match="reconciliation"):
        venue.execute_entry(cid, opening)
    assert not LedgerStore(db, "reference").read()[1].fills
    db.close()


def test_gap_price_rejects_unsent_entry_without_fee_or_cooldown(tmp_path):
    db, venue, cid, _, opening = planned(tmp_path)
    result = venue.execute_entry(cid, replace(opening, price=D(110)))
    assert result["reason"] == "BREAKOUT_OR_CHASING" and result["fill"] is None
    signal = db.db.execute("SELECT signal_id FROM intents WHERE client_id=?", (cid,)).fetchone()[0]
    position = Protection.restore(db.snapshot("protection:reference:" + signal)[1])
    assert position.terminal and position.full_exit_time is None and position.remaining == 0
    assert not LedgerStore(db, "reference").read()[1].fills
    assert (
        db.db.execute("SELECT state FROM intents WHERE client_id=?", (cid,)).fetchone()[0]
        == "CANCELED"
    )
    db.close()


def test_unreconciled_account_cancels_unsent_entry(tmp_path):
    db, venue, cid, _, opening = planned(tmp_path)
    with db.transaction() as tx:
        from pvb24.accounting.coordinator import save_tx

        gate = db.snapshot("account-gate:reference")[1]
        gate["ready"] = False
        save_tx(tx, "account-gate:reference", gate)
    result = venue.execute_entry(cid, opening)
    assert result["reason"] == "ACCOUNT_OR_RISK_GATE" and result["fill"] is None
    db.close()


def test_synthetic_fill_failure_rolls_back_claim_cash_and_receipt(tmp_path, monkeypatch):
    db, venue, cid, _, opening = planned(tmp_path)
    original = Journal.append_tx

    def fail_result(tx, event_id, payload):
        if event_id.startswith("sim-result:"):
            raise RuntimeError("crash at synthetic commit")
        return original(tx, event_id, payload)

    monkeypatch.setattr(Journal, "append_tx", staticmethod(fail_result))
    with pytest.raises(RuntimeError, match="crash"):
        venue.execute_entry(cid, opening)
    assert not LedgerStore(db, "reference").read()[1].fills
    assert (
        db.db.execute("SELECT state FROM intents WHERE client_id=?", (cid,)).fetchone()[0]
        == "PREPARED"
    )
    assert db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='PROTECT'").fetchone()[0] == 0
    db.close()


def test_simulation_inputs_cannot_be_refit_after_future_information(tmp_path):
    db, venue, cid, request, opening = planned(tmp_path)
    with pytest.raises(ValueError, match="future"):
        venue.freeze_entry(cid, sigma=D(0), available_at=opening.time)
    with pytest.raises(Conflict, match="already frozen"):
        venue.freeze_entry(cid, sigma=D("0.1"), available_at=request.inputs_available_at)
    assert venue.freeze_entry(cid, sigma=D(0), available_at=request.inputs_available_at) == request
    db.close()
