from dataclasses import replace
from datetime import timedelta
from decimal import localcontext

import pytest
from test_accounting import mark
from test_entry_planner import setup

from pvb24.accounting.coordinator import AccountCoordinator
from pvb24.accounting.ledger import FillRecord, LedgerStore, ReconciliationRequired
from pvb24.accounting.reconciliation import AccountObservation, OpenReconciler, PositionObservation
from pvb24.accounting.risk_service import AccountRiskService
from pvb24.decimal_math import CONTEXT, ZERO, D
from pvb24.execution.planner import EntryPlanner
from pvb24.execution.protection import Protection
from pvb24.types import Fill, Quality, Side


def batch_with_first_fill(tmp_path, *, other_dispatched=False):
    db, reservations, _, _, batch, inputs = setup(tmp_path, ("BTCUSDT", "ETHUSDT"))
    result = EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(
        batch, inputs, batch.decision_time
    )
    assert all(r["reason"] == "ACCEPTED" for r in result)
    first, other = result
    original = reservations.read()[1]
    assert db.claim_dispatch(first["client_id"])
    if other_dispatched:
        assert db.claim_dispatch(other["client_id"])
    now = batch.decision_time + timedelta(seconds=1)
    entry = first["sizing"]["entry"]
    quantity, price = D(entry["quantity"]), D(entry["costs"]["entry"])
    with localcontext(CONTEXT):
        fee = quantity * price * D(entry["quote"]["entry_fee_rate"])
    fill = Fill(
        "entry",
        "order",
        first["signal_id"],
        first["symbol"],
        Side(first["side"]),
        quantity,
        price,
        fee,
        now,
        now,
    )
    coordinator = AccountCoordinator(db, "reference")
    coordinator.confirmed_fill(FillRecord(fill))
    coordinator.protection_event(
        first["signal_id"], "terminal", "filled", lambda p: p.entry_terminal(), now
    )
    p = Protection.restore(db.snapshot("protection:reference:" + first["signal_id"])[1])
    stop = next(iter(p.actions.values()))
    coordinator.protection_event(
        first["signal_id"],
        "stop",
        "active",
        lambda p: p.confirm_stop(
            stop.sequence, stop.quantity, stop.stop, reduce_only=True, reference="CONTRACT_PRICE"
        ),
        now,
    )

    def observation(time):
        cash = LedgerStore(db, "reference").read()[1].view(time).cash
        margin = D(entry["initial_margin"])
        return AccountObservation(
            time,
            time,
            cash,
            cash - margin,
            (
                PositionObservation(
                    first["signal_id"],
                    quantity,
                    margin,
                    margin - fee,
                    entry["leverage"],
                    mark(str(price), time),
                    inputs[first["symbol"]].rules,
                ),
            ),
            Quality.PRELIMINARY,
            "synthetic",
            time.isoformat(),
        )

    return db, reservations, first, other, original, now, observation


def reconcile(db, observed):
    return OpenReconciler(db, "reference").reconcile(
        observed,
        observed.available_at,
        max_account_age=timedelta(seconds=1),
        max_mark_age=timedelta(seconds=1),
        require_verified=False,
    )


def test_first_fill_preserves_other_valid_batch_entry_and_all_local_commitments(tmp_path):
    db, reservations, first, other, original, now, observe = batch_with_first_fill(tmp_path)
    result = reconcile(db, observe(now))
    assert result.entry_gate_ready and result.portfolio.slots == 2
    pending = next(p for p in result.portfolio.exposures if p.position_id == other["signal_id"])
    assert pending == next(p for p in original.exposures if p.position_id == other["signal_id"])
    assert (
        db.db.execute(
            "SELECT state FROM intents WHERE client_id=?", (other["client_id"],)
        ).fetchone()[0]
        == "PREPARED"
    )
    a, b = first["sizing"]["entry"], other["sizing"]["entry"]
    with localcontext(CONTEXT):
        open_reserves = D(a["quantity"]) * sum(
            (D(a["costs"][k]) for k in ("exit_fee", "stop_slippage", "funding")), ZERO
        )
        pending_commitment = D(b["initial_margin"]) + D(b["quantity"]) * sum(
            (D(b["costs"][k]) for k in ("entry_fee", "exit_fee", "stop_slippage", "funding")), ZERO
        )
        assert (
            result.portfolio.free_collateral
            == observe(now).free_collateral - open_reserves - pending_commitment
        )
    assert (
        reconcile(db, observe(now)).portfolio == result.portfolio
    )  # no repeated reserve deduction
    assert reservations.read()[1] == result.portfolio
    assert db.claim_dispatch(other["client_id"])
    db.close()


def test_expired_unsent_entry_is_canceled_without_fee_or_cooldown(tmp_path):
    db, _, _, other, _, now, observe = batch_with_first_fill(tmp_path)
    now = now.replace(second=0, microsecond=0) + timedelta(seconds=91)
    observed = observe(now)
    AccountRiskService(db, "reference").sample(
        now.replace(second=0), [mark("101.21", now.replace(second=0))]
    )
    result = reconcile(db, observed)
    assert result.entry_gate_ready and result.portfolio.slots == 1
    assert (
        db.db.execute(
            "SELECT state FROM intents WHERE client_id=?", (other["client_id"],)
        ).fetchone()[0]
        == "CANCELED"
    )
    p = Protection.restore(db.snapshot("protection:reference:" + other["signal_id"])[1])
    assert p.terminal and p.full_exit_time is None and not p.fills
    db.close()


def test_lost_current_capacity_cancels_only_unsent_reservation(tmp_path):
    db, _, first, other, _, now, observe = batch_with_first_fill(tmp_path)
    result = reconcile(db, replace(observe(now), free_collateral=D(1)))
    assert result.portfolio.slots == 1
    assert result.portfolio.exposures[0].position_id == first["signal_id"]
    assert (
        db.db.execute(
            "SELECT state FROM intents WHERE client_id=?", (other["client_id"],)
        ).fetchone()[0]
        == "CANCELED"
    )
    assert not result.action_ids
    db.close()


def test_unknown_other_entry_never_releases_its_reservation(tmp_path):
    db, reservations, _, other, _, now, observe = batch_with_first_fill(
        tmp_path, other_dispatched=True
    )
    before = reservations.read()
    with pytest.raises(ReconciliationRequired, match="unresolved IOC"):
        reconcile(db, observe(now))
    assert reservations.read() == before
    assert (
        db.db.execute(
            "SELECT state FROM intents WHERE client_id=?", (other["client_id"],)
        ).fetchone()[0]
        == "UNKNOWN"
    )
    assert db.snapshot("account-gate:reference")[1]["ready"] is False
    db.close()
