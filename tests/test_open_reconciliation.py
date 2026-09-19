from dataclasses import replace
from datetime import timedelta
from decimal import localcontext

import pytest
from test_account_coordinator import setup, terminal
from test_account_risk_service import entry_id, service
from test_accounting import mark, record
from test_data import NOW
from test_sizing import rules

from pvb24.accounting.ledger import LedgerStore, ReconciliationRequired
from pvb24.accounting.reconciliation import AccountObservation, OpenReconciler, PositionObservation
from pvb24.decimal_math import CONTEXT, D
from pvb24.execution.protection import Protection
from pvb24.types import Quality, Side

TIME = NOW + timedelta(minutes=1)


def prepared(tmp_path, quantity="4.5", fee="0.1"):
    db, reservations, c = setup(tmp_path)
    risk = service(db)
    risk.sample(NOW, [])
    assert db.claim_dispatch(entry_id(db))
    c.confirmed_fill(record(quantity=quantity, fee=fee))
    terminal(c)
    state = Protection.restore(db.snapshot("protection:paper:signal")[1])
    action = next(a for a in state.actions.values() if a.purpose == "PROTECT")
    c.protection_event(
        "signal",
        "stop-confirmed",
        "synthetic-stop-ack",
        lambda p: p.confirm_stop(
            action.sequence,
            action.quantity,
            action.stop,
            reduce_only=True,
            reference="CONTRACT_PRICE",
        ),
        NOW + timedelta(seconds=2),
    )
    risk.sample(TIME, [mark("100", TIME)])
    return db, reservations, c


def observation(db, quantity="4.5", collateral="149.9", time=TIME):
    cash = LedgerStore(db, "paper").read()[1].view(time).cash
    return AccountObservation(
        time,
        time,
        cash,
        cash - D(150),
        (
            PositionObservation(
                "signal", D(quantity), D(150), D(collateral), 3, mark("100", time), rules()
            ),
        ),
        Quality.PRELIMINARY,
        "synthetic-account",
        "v1",
    )


def reconcile(db, observed, time=TIME, **kwargs):
    return OpenReconciler(db, "paper").reconcile(
        observed,
        time,
        max_account_age=timedelta(seconds=1),
        max_mark_age=timedelta(seconds=1),
        require_verified=False,
        **kwargs,
    )


def test_open_reconciliation_freezes_actual_fill_risk_and_releases_unfilled_reservation(tmp_path):
    db, reservations, _ = prepared(tmp_path, quantity="2")
    previous = reservations.read()[1].reserved_risk
    result = reconcile(db, observation(db, quantity="2"))
    assert result.entry_gate_ready and result.action_ids == ()
    exposure = result.portfolio.exposures[0]
    assert not exposure.pending and exposure.initial_quantity == 2
    assert exposure.reserved_risk < previous
    assert exposure.valuation_price == 100 and exposure.initial_margin_commitment == 150
    assert result.portfolio.equity == D("999.9")
    assert reconcile(db, observation(db, quantity="2")).action_ids == ()
    db.close()


def test_only_confirmed_partial_exit_releases_original_risk_proportionally(tmp_path):
    db, _, c = prepared(tmp_path)
    original = reconcile(db, observation(db)).portfolio.exposures[0]
    c.confirmed_fill(record("exit", "1", "100", side=Side.SHORT, reduce=True, seconds=61))
    later = NOW + timedelta(seconds=62)
    result = reconcile(db, observation(db, quantity="3.5", collateral="149.8", time=later), later)
    actual = result.portfolio.exposures[0]
    assert actual.initial_quantity == original.initial_quantity
    assert actual.initial_reserved_risk == original.initial_reserved_risk
    with localcontext(CONTEXT):
        assert actual.reserved_risk == original.initial_reserved_risk * D("3.5") / D("4.5")
    db.close()


def test_actual_collateral_buffer_breach_requests_full_close_when_projection_unknown(tmp_path):
    db, _, _ = prepared(tmp_path)
    observed = observation(db, collateral="5")
    result = reconcile(db, observed)
    assert not result.entry_gate_ready and len(result.action_ids) == 1
    assert any("REDUCTION_ECONOMICS_UNKNOWN_CLOSE" in reason for reason in result.reasons)
    repeated = reconcile(db, observed)
    assert repeated.action_ids == () and not repeated.entry_gate_ready
    db.close()


def test_postfill_risk_minimum_breach_closes_and_stays_blocked_while_exit_unknown(tmp_path):
    db, _, _ = prepared(tmp_path, quantity="0.5")
    observed = observation(db, quantity="0.5")
    result = reconcile(db, observed)
    assert not result.entry_gate_ready
    assert "signal:POST_FILL_POSITION_LIMIT" in result.reasons
    assert len(result.action_ids) == 1
    again = reconcile(db, observed)
    assert not again.entry_gate_ready and again.action_ids == ()
    assert "signal:EXIT_OUTCOME_PENDING" in again.reasons
    db.close()


@pytest.mark.parametrize("case", ["cash", "quantity", "foreign", "stale", "future"])
def test_bad_account_proof_persists_pause_without_touching_foreign_positions(tmp_path, case):
    db, _, _ = prepared(tmp_path)
    observed = observation(db)
    reconcile(db, observed)
    if case == "cash":
        observed = replace(observed, cash=D(999))
    elif case == "quantity":
        observed = replace(observed, positions=(replace(observed.positions[0], quantity=D(4)),))
    elif case == "foreign":
        observed = replace(
            observed, positions=(replace(observed.positions[0], position_id="foreign"),)
        )
    elif case == "stale":
        observed = replace(observed, event_time=TIME - timedelta(seconds=2))
    else:
        observed = replace(observed, available_at=TIME + timedelta(seconds=1))
    with pytest.raises(ReconciliationRequired):
        reconcile(db, observed)
    assert not db.snapshot("account-gate:paper")[1]["ready"]
    assert (
        db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='EXIT_MARKET'").fetchone()[0] == 0
    )
    db.close()


def test_verified_mode_does_not_promote_synthetic_account_evidence(tmp_path):
    db, _, _ = prepared(tmp_path)
    with pytest.raises(ReconciliationRequired, match="VERIFIED"):
        OpenReconciler(db, "paper").reconcile(
            observation(db),
            TIME,
            max_account_age=timedelta(seconds=1),
            max_mark_age=timedelta(seconds=1),
        )
    db.close()


def test_current_minute_risk_sample_required_before_account_entry_gate_reopens(tmp_path):
    db, _, _ = prepared(tmp_path)
    later = TIME + timedelta(minutes=1)
    with pytest.raises(ReconciliationRequired, match="Current minute"):
        reconcile(db, observation(db, time=later), later)
    db.close()


def test_acknowledged_trailing_tightening_never_releases_initial_risk(tmp_path):
    db, _, c = prepared(tmp_path)
    original = reconcile(db, observation(db)).portfolio.exposures[0]
    c.protection_event(
        "signal",
        "trail",
        "synthetic-causal-trailing-proposal",
        lambda p: p.tighten_stop(D(99), D(100)),
        TIME + timedelta(seconds=1),
    )
    state = Protection.restore(db.snapshot("protection:paper:signal")[1])
    latest = max(
        (a for a in state.actions.values() if a.purpose == "PROTECT"), key=lambda a: a.sequence
    )
    c.protection_event(
        "signal",
        "trail-ack",
        "synthetic-stop-ack",
        lambda p: p.confirm_stop(
            latest.sequence,
            latest.quantity,
            latest.stop,
            reduce_only=True,
            reference="CONTRACT_PRICE",
        ),
        TIME + timedelta(seconds=2),
    )
    later = TIME + timedelta(seconds=3)
    current = reconcile(db, observation(db, time=later), later).portfolio.exposures[0]
    assert current.initial_reserved_risk == original.initial_reserved_risk
    assert current.reserved_risk == original.reserved_risk
    state = Protection.restore(db.snapshot("protection:paper:signal")[1])
    assert state.initial_stop == 98 and state.effective_stop == 99
    with pytest.raises(ValueError, match="widen"):
        state.tighten_stop(D("98.5"), D(100))
    db.close()
