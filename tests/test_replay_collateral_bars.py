from dataclasses import replace
from datetime import timedelta
from decimal import localcontext

import pytest
from test_accounting import mark
from test_data import candle
from test_preliminary_venue import planned
from test_sizing import rules

from pvb24.accounting.ledger import LedgerStore, ReconciliationRequired
from pvb24.accounting.reconciliation import OpenReconciler
from pvb24.accounting.risk_service import AccountRiskService
from pvb24.decimal_math import CONTEXT, D
from pvb24.execution.protection import Protection
from pvb24.replay.bar_execution import resolve_bar
from pvb24.replay.collateral import SyntheticCollateral
from pvb24.replay.preliminary import MinuteOpen
from pvb24.state import Conflict
from pvb24.types import Quality


def opened(tmp_path):
    db, venue, cid, request, opening = planned(tmp_path)
    model = SyntheticCollateral(db, "reference")
    model.freeze(policy=model.POLICY, manifest_id="SYNTHETIC-TEST-MANIFEST")
    result = venue.execute_entry(cid, opening)
    venue.acknowledge_protection(result["action_ids"][0], opening.time + timedelta(milliseconds=1))
    return db, venue, result["fill"]["position_id"], opening, model


def test_preliminary_observation_reconciles_actual_filled_economics_and_current_risk(tmp_path):
    db, _, signal, opening, model = opened(tmp_path)
    time = opening.time + timedelta(minutes=1)
    marks = [mark("101.3", time)]
    AccountRiskService(db, "reference").sample(time, marks)
    observed = model.observe(time, marks, {"BTCUSDT": rules()}, max_mark_age=timedelta(seconds=1))
    position = observed.positions[0]
    balance = LedgerStore(db, "reference").read()[1].view(time).positions[0]
    with localcontext(CONTEXT):
        assert position.isolated_collateral == position.initial_margin_commitment - balance.fees
        assert observed.free_collateral == D(1000) - position.initial_margin_commitment
    result = OpenReconciler(db, "reference").reconcile(
        observed,
        time,
        max_account_age=timedelta(seconds=1),
        max_mark_age=timedelta(seconds=1),
        require_verified=False,
    )
    assert result.entry_gate_ready and result.portfolio.exposures[0].position_id == signal
    assert observed.quality is Quality.PRELIMINARY
    db.close()


def test_partial_exit_releases_basis_margin_without_inventing_new_collateral(tmp_path):
    db, venue, signal, opening, model = opened(tmp_path)
    p = Protection.restore(db.snapshot("protection:reference:" + signal)[1])
    request_time = opening.time + timedelta(seconds=2)
    ids = venue.coordinator.protection_event(
        signal,
        "synthetic-reduction",
        "synthetic-known-reduction",
        lambda position: position.close(p.remaining / 2),
        request_time,
    )
    time = opening.time + timedelta(minutes=1)
    executable = MinuteOpen("BTCUSDT", time, time, D(110), "synthetic", "v1")
    venue.execute_exit(
        ids[0],
        executable,
        sigma=D(0),
        recent_quote_volume=D(1000000),
        inputs_available_at=request_time,
    )
    observed = model.observe(
        time, [mark("110", time)], {"BTCUSDT": rules()}, max_mark_age=timedelta(seconds=1)
    )
    balance = LedgerStore(db, "reference").read()[1].view(time).positions[0]
    position = observed.positions[0]
    with localcontext(CONTEXT):
        assert (
            position.initial_margin_commitment == balance.remaining_cost_basis / position.leverage
        )
        assert (
            position.isolated_collateral
            == position.initial_margin_commitment + balance.realized_gross - balance.fees
        )
    assert position.isolated_collateral > position.initial_margin_commitment
    db.close()


def test_collateral_policy_cannot_be_changed_after_observing_outcome(tmp_path):
    db, _, _, _, model = opened(tmp_path)
    with pytest.raises(Conflict, match="already frozen"):
        model.freeze(policy=model.POLICY, manifest_id="changed")
    with pytest.raises(ValueError, match="Explicit"):
        model.freeze(policy="invented-model", manifest_id="synthetic")
    db.close()


def bars(opening, liquidation=False):
    start = opening.time + timedelta(minutes=1)
    last = replace(
        candle(start, timedelta(minutes=1)), open=D(96), low=D(95), high=D(101), close=D(100)
    )
    mark_bar = replace(last, open=D(100), low=D(40) if liquidation else D(95), price_type="MARK")
    return last, mark_bar


def resolve(venue, signal, last, mark_bar, **kwargs):
    return resolve_bar(
        venue,
        signal,
        last,
        mark_bar,
        liquidation_price=D(60),
        sigma=D(0),
        recent_quote_volume=D(1000000),
        inputs_available_at=last.timing.interval_start,
        all_in_liquidation_fee_rate=D("0.01"),
        liquidation_terms_available_at=last.timing.interval_start,
        model_manifest_id="SYNTHETIC-TEST-MANIFEST",
        **kwargs,
    )


def test_gap_stop_executes_worse_than_open_instead_of_old_trigger_and_survives_restart(tmp_path):
    db, venue, signal, opening, _ = opened(tmp_path)
    last, mark_bar = bars(opening)
    result = resolve(venue, signal, last, mark_bar)
    assert result["reason"] == "MODELED_STOP" and D(result["fill"]["price"]) == D("95.9")
    assert result["ambiguous_event_count"] == 0
    assert (
        LedgerStore(db, "reference").read()[1].view(last.timing.available_at).positions[0].quantity
        == 0
    )
    assert resolve(venue, signal, last, mark_bar) == result
    db.close()


def test_ambiguous_bar_keeps_liquidation_loss_fee_and_count_visible_once(tmp_path):
    db, venue, signal, opening, _ = opened(tmp_path)
    last, mark_bar = bars(opening, liquidation=True)
    result = resolve(venue, signal, last, mark_bar)
    assert result["reason"] == "MODELED_LIQUIDATION" and result["ambiguous_event_count"] == 1
    assert D(result["fill"]["price"]) == 40
    assert db.snapshot("replay-account:reference")[1]["ambiguous_event_count"] == 1
    view = LedgerStore(db, "reference").read()[1].view(last.timing.available_at)
    assert view.liquidation_count == 1 and view.realized_gross < 0
    assert result["quality"] == "PRELIMINARY"
    assert resolve(venue, signal, last, mark_bar) == result
    assert db.snapshot("replay-account:reference")[1]["ambiguous_event_count"] == 1
    db.close()


def test_partial_protection_bar_requires_finer_data_without_hiding_a_result(tmp_path):
    db, venue, signal, opening, _ = opened(tmp_path)
    last = candle(opening.time, timedelta(minutes=1))
    mark_bar = replace(last, price_type="MARK")
    with pytest.raises(ReconciliationRequired, match="Intrabar protection"):
        resolve(venue, signal, last, mark_bar)
    assert len(LedgerStore(db, "reference").read()[1].fills) == 1
    db.close()
