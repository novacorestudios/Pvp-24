import json
from dataclasses import replace
from datetime import timedelta
from decimal import localcontext

import pytest
from test_data import NOW
from test_protection import fill

from pvb24.accounting.controls import EquityControl
from pvb24.accounting.ledger import (
    FillRecord,
    FundingPayment,
    Ledger,
    LedgerStore,
    OwnedPosition,
    ReconciliationRequired,
    execution_shortfall,
)
from pvb24.data.schemas import Mark, Timing
from pvb24.decimal_math import D
from pvb24.ids import canonical
from pvb24.state import Conflict, Journal
from pvb24.types import Side


def ledger(side=Side.LONG):
    result = Ledger(D(1000))
    result.register(OwnedPosition("signal", "BTCUSDT", side, NOW))
    return result


def record(
    name="entry",
    quantity="2",
    price="100",
    fee="0.1",
    side=Side.LONG,
    reduce=False,
    seconds=0,
    seq=None,
    liquidation=False,
):
    return FillRecord(
        replace(fill(name, quantity, price, side, reduce, seconds), fee=D(fee)), seq, liquidation
    )


def payment(side=Side.LONG):
    return FundingPayment(
        "settlement:1",
        "signal",
        side,
        D(2),
        D(100),
        D("0.001"),
        NOW + timedelta(seconds=10),
        NOW + timedelta(seconds=10),
        "synthetic",
        "synthetic-exchange-eligibility-confirmation",
    )


def mark(price="105", time=NOW, available=None):
    return Mark(
        "BTCUSDT",
        D(price),
        Timing(
            time, time, time, available or time, available or time, "synthetic", "v1", "snapshot"
        ),
    )


@pytest.mark.parametrize("side,exit_price", [(Side.LONG, "105"), (Side.SHORT, "95")])
def test_actual_prices_fees_and_funding_once_reconcile_cash(side, exit_price):
    account = ledger(side)
    entry = record(side=side)
    exit_side = Side.SHORT if side is Side.LONG else Side.LONG
    closing = record("exit", "2", exit_price, "0.2", exit_side, True, 20)
    assert account.ingest_fill(entry) and not account.ingest_fill(entry)
    assert account.ingest_funding(payment(side)) and not account.ingest_funding(payment(side))
    assert account.ingest_fill(closing) and not account.ingest_fill(closing)
    v = account.view(NOW + timedelta(seconds=30))
    assert v.realized_gross == 10 and v.fees == D("0.3")
    assert v.funding == D("-0.2") * side.sign
    assert v.cash == D(1000) + v.realized_gross - v.fees + v.funding
    assert v.equity([], max_mark_age=timedelta(seconds=1)) == v.cash
    assert v.positions[0].quantity == 0 and v.positions[0].remaining_cost_basis == 0


def test_shortfall_diagnostic_does_not_create_another_cash_expense():
    account = ledger()
    entry = record(price="101")
    account.ingest_fill(entry)
    assert execution_shortfall(entry.fill, D(100)) == 2
    v = account.view(NOW + timedelta(seconds=1))
    assert v.cash == D("999.9")  # no notional, margin, risk reserve or shortfall deduction
    assert v.equity([mark("100")], max_mark_age=timedelta(seconds=1)) == D("997.9")


def test_partial_exit_before_final_ioc_fill_uses_remaining_cost_basis():
    account = ledger()
    for r in [
        record(quantity="2"),
        record("exit1", "1", "110", "0.1", Side.SHORT, True, 1),
        record("entry2", "2", "120", seconds=2),
        record("exit2", "3", "130", "0.1", Side.SHORT, True, 3),
    ]:
        account.ingest_fill(r)
    v = account.view(NOW + timedelta(seconds=4))
    # Total sale proceeds 110 + 390 minus entry cost 200 + 240.
    assert v.realized_gross == 60 and v.cash == D("1059.6")
    assert v.positions[0].remaining_cost_basis == 0


def test_late_entry_evidence_reconciles_without_changing_earlier_asof_view():
    account = ledger()
    account.ingest_fill(record("exit", "2", "110", side=Side.SHORT, reduce=True, seconds=2))
    with pytest.raises(ReconciliationRequired):
        account.view(NOW + timedelta(seconds=3))
    late = record()
    late = replace(late, fill=replace(late.fill, received_at=NOW + timedelta(seconds=4)))
    account.ingest_fill(late)
    with pytest.raises(ReconciliationRequired):
        account.view(NOW + timedelta(seconds=3))
    assert account.view(NOW + timedelta(seconds=5)).realized_gross == 20


def test_exchange_sequence_resolves_equal_time_fill_order():
    account = ledger()
    account.ingest_fill(record(seq=1))
    account.ingest_fill(record("exit", "2", "101", side=Side.SHORT, reduce=True, seq=2))
    assert account.view(NOW + timedelta(seconds=1)).realized_gross == 2
    ambiguous = ledger()
    ambiguous.ingest_fill(record())
    ambiguous.ingest_fill(record("exit", "2", "101", side=Side.SHORT, reduce=True))
    with pytest.raises(ReconciliationRequired):
        ambiguous.view(NOW + timedelta(seconds=1))


def test_liquidation_stays_visible_and_rebate_is_signed():
    account = ledger()
    account.ingest_fill(record(fee="-0.01"))
    account.ingest_fill(record("liq", "2", "80", "1", Side.SHORT, True, 1, liquidation=True))
    v = account.view(NOW + timedelta(seconds=2))
    assert v.liquidation_count == 1 and v.realized_gross == -40
    assert v.fees == D("0.99") and v.cash == D("959.01")


def test_conflicting_fill_funding_and_unknown_ownership_fail_closed():
    account = ledger()
    original = record()
    account.ingest_fill(original)
    with pytest.raises(Conflict):
        account.ingest_fill(replace(original, fill=replace(original.fill, fee=D(10))))
    account.ingest_funding(payment())
    with pytest.raises(Conflict):
        account.ingest_funding(replace(payment(), final_rate=D("0.01")))
    with pytest.raises(ReconciliationRequired):
        account.ingest_fill(replace(original, fill=replace(original.fill, position_id="unknown")))


def test_mark_is_causal_fresh_and_never_substituted_by_last():
    account = ledger()
    account.ingest_fill(record())
    v = account.view(NOW + timedelta(seconds=1))
    assert v.equity([mark()], max_mark_age=timedelta(seconds=1)) == D("1009.9")
    future = mark("1000", NOW + timedelta(seconds=2))
    late = mark("200", NOW, NOW + timedelta(seconds=2))
    assert v.equity([mark(), future, late], max_mark_age=timedelta(seconds=1)) == D("1009.9")
    for marks in ([], [future]):
        with pytest.raises(ReconciliationRequired):
            v.equity(marks, max_mark_age=timedelta(seconds=1))
    with pytest.raises(ReconciliationRequired, match="Stale"):
        v.equity([mark()], max_mark_age=timedelta(milliseconds=999))


def test_future_append_owners_fills_and_funding_do_not_change_past():
    account = ledger()
    account.ingest_fill(record())
    before = account.view(NOW + timedelta(seconds=1))
    account.register(OwnedPosition("future", "ETHUSDT", Side.LONG, NOW + timedelta(days=1)))
    account.ingest_funding(payment())
    account.ingest_fill(record("exit", "2", "105", side=Side.SHORT, reduce=True, seconds=20))
    assert account.view(NOW + timedelta(seconds=1)) == before


def test_ledger_checkpoint_and_transaction_restart_dedup(tmp_path):
    path = tmp_path / "ledger.sqlite"
    db = Journal(path)
    store = LedgerStore(db, "paper")
    store.initialize(ledger())
    r = record()
    assert store.apply("fill1", r, lambda account: account.ingest_fill(r))
    db.close()
    db = Journal(path)
    store = LedgerStore(db, "paper")
    assert not store.apply("fill1", r, lambda account: account.ingest_fill(r))
    _, account = store.read()
    restored = Ledger.restore(json.loads(canonical(account.checkpoint())))
    assert restored.view(NOW + timedelta(seconds=1)) == account.view(NOW + timedelta(seconds=1))
    before = store.read()[0]

    def fail(account):
        account.ingest_funding(payment())
        raise RuntimeError("injected persistence failure")

    with pytest.raises(RuntimeError):
        store.apply("funding1", payment(), fail)
    assert store.read()[0] == before and not store.read()[1].funding
    db.close()


def test_daily_four_percent_pause_latches_until_next_utc_day():
    c = EquityControl(NOW, D(1000))
    assert c.sample(NOW, D(1000)).entries_allowed
    s = c.sample(NOW + timedelta(minutes=1), D(960))
    assert s.daily_paused and not s.entries_allowed and not s.hard_paused
    assert c.sample(NOW + timedelta(minutes=2), D(1001)).daily_paused
    s = c.sample(NOW + timedelta(days=1), D(1001))
    assert not s.daily_paused and s.entries_allowed


def test_ten_percent_reduction_recovers_only_original_peak():
    c = EquityControl(NOW, D(1000))
    c.sample(NOW, D(1000))
    assert c.sample(NOW + timedelta(minutes=1), D(900)).risk_fraction == D("0.005")
    assert c.sample(NOW + timedelta(minutes=2), D(990)).risk_fraction == D("0.005")
    assert c.sample(NOW + timedelta(minutes=3), D(1000)).risk_fraction == D("0.01")


def test_fifteen_percent_hard_pause_survives_recovery_midnight_and_restart():
    c = EquityControl(NOW, D(1000))
    c.sample(NOW, D(1000))
    assert c.sample(NOW + timedelta(minutes=1), D(850)).hard_paused
    c = EquityControl.restore(json.loads(canonical(c.checkpoint())))
    s = c.sample(NOW + timedelta(days=1), D(1100))
    assert s.hard_paused and not s.entries_allowed
    assert not s.daily_paused and s.risk_fraction == D("0.01")


def test_safety_pause_applies_immediately_to_duplicate_sample_and_next_day():
    c = EquityControl(NOW, D(1000))
    c.sample(NOW, D(1000))
    c.pause_safety()
    assert not c.sample(NOW, D(1000)).entries_allowed
    assert not c.sample(NOW + timedelta(days=1), D(1000)).entries_allowed


def test_missing_midnight_cannot_be_replaced_by_later_baseline():
    c = EquityControl(NOW, D(1000))
    c.sample(NOW, D(1000))
    assert c.sample(NOW + timedelta(days=1), None).data_paused
    s = c.sample(NOW + timedelta(days=1, minutes=1), D(1000))
    assert s.data_paused and s.daily_return is None and not s.entries_allowed
    assert c.sample(NOW + timedelta(days=2), D(1000)).entries_allowed


def test_minute_grid_missing_sample_count_and_no_revised_history():
    c = EquityControl(NOW, D(1000))
    c.sample(NOW, D(1000))
    assert c.sample(NOW + timedelta(minutes=3), None).missing_samples == 3
    with pytest.raises(ValueError, match="revise"):
        c.sample(NOW + timedelta(minutes=3), D(1000))
    with pytest.raises(ValueError, match="minute"):
        c.sample(NOW + timedelta(minutes=4, seconds=1), D(1000))


def test_accounting_uses_precision_34_independent_of_ambient_context():
    account = ledger()
    account.ingest_fill(record())
    account.ingest_funding(payment())
    expected = account.view(NOW + timedelta(seconds=11))
    with localcontext() as ctx:
        ctx.prec = 4
        assert account.view(NOW + timedelta(seconds=11)) == expected
