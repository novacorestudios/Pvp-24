from dataclasses import replace
from datetime import timedelta

import pytest
from test_signals import next_frame, universe, warmed
from test_sizing import quote, rules

from pvb24.accounting.coordinator import AccountCoordinator, save_tx
from pvb24.accounting.ledger import Ledger, LedgerStore
from pvb24.accounting.risk_service import AccountRiskService
from pvb24.decimal_math import D
from pvb24.execution.planner import EntryInputs, EntryPlanner
from pvb24.execution.protection import Protection
from pvb24.ids import canonical
from pvb24.replay.account import AccountReplay
from pvb24.replay.events import Delivery, Event, Kind
from pvb24.risk.portfolio import Portfolio
from pvb24.risk.reservations import Reservations
from pvb24.state import Conflict, Journal
from pvb24.strategy.service import SignalService
from pvb24.types import Quality


def setup(tmp_path, symbols=("BTCUSDT",)):
    db = Journal(tmp_path / "planning.sqlite")
    sources, frames = {}, {}
    for index, symbol in enumerate(symbols):
        indicator = warmed(symbol)
        price = "101.21" if index % 2 == 0 else "98.79"
        frame = next_frame(indicator, close=price, volume=str(200 - index))
        frames[symbol] = frame
        with db.transaction() as tx:
            save_tx(tx, "indicators:reference:" + symbol, indicator.checkpoint())

        def model(quantity, price=price, available=frame.evaluated_at):
            return replace(
                quote(quantity),
                expected_entry=D(price),
                arrival_side_price=D(price),
                available_at=available,
            )

        sources[symbol] = EntryInputs(
            replace(rules(), symbol=symbol),
            model,
            D(1000000),
            frame.evaluated_at,
            "synthetic-snapshot:" + symbol,
        )
    time = next(iter(frames.values())).evaluated_at
    reservations = Reservations(db, "reference")
    reservations.initialize(Portfolio(D(1000), D(1000)))
    LedgerStore(db, "reference").initialize(Ledger(D(1000)))
    AccountReplay(db, "reference", Quality.PRELIMINARY)
    risk = AccountRiskService(db, "reference")
    risk.initialize(
        time.replace(second=0), max_mark_age=timedelta(seconds=1), policy_id="SYNTHETIC"
    )
    risk.sample(time.replace(second=0), [])
    service = SignalService(db, "reference", Quality.PRELIMINARY)
    u = universe(time, symbols)
    batch = service.evaluate(u, next(iter(frames.values())).candle.timing.interval_end, time)
    return db, reservations, service, u, batch, sources


def test_shared_batch_ranked_entries_reserve_capacity_sequentially_and_persist_ownership(tmp_path):
    db, reservations, _, _, batch, sources = setup(
        tmp_path, ("BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT")
    )
    assert [s.symbol for s in batch.ranked] == ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT"]
    result = EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(
        batch, sources, batch.decision_time
    )
    assert [r["symbol"] for r in result] == [s.symbol for s in batch.ranked]
    assert all(r["reason"] == "ACCEPTED" for r in result[:3])
    assert result[3]["reason"] == "SLOT_OR_SYMBOL_RESERVED"
    portfolio = reservations.read()[1]
    assert portfolio.slots == 3 and portfolio.reserved_risk <= 30
    for accepted in result[:3]:
        signal_id = accepted["signal_id"]
        p = Protection.restore(db.snapshot("protection:reference:" + signal_id)[1])
        metadata = db.snapshot("entry-metadata:reference:" + signal_id)[1]
        assert p.remaining == 0 and not p.terminal
        assert metadata["order_deadline"]
        assert accepted["client_id"]
    db.close()


def test_identical_plan_after_restart_returns_receipt_without_new_solver_or_intents(tmp_path):
    db, _, _, _, batch, sources = setup(tmp_path)
    planner = EntryPlanner(db, "reference", Quality.PRELIMINARY)
    result = planner.plan(batch, sources, batch.decision_time)
    sources = {
        s: replace(i, quote_model=lambda q: pytest.fail("must reuse receipt"))
        for s, i in sources.items()
    }
    db.close()
    db = Journal(tmp_path / "planning.sqlite")
    assert (
        EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(batch, sources, batch.decision_time)
        == result
    )
    assert db.db.execute("SELECT COUNT(*) FROM intents WHERE purpose='ENTRY'").fetchone()[0] == 1
    with pytest.raises(Conflict, match="already consumed"):
        EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(
            batch, sources, batch.decision_time + timedelta(seconds=1)
        )
    db.close()


def test_ownership_failure_rolls_back_entire_reservation_batch(tmp_path, monkeypatch):
    db, reservations, _, _, batch, sources = setup(tmp_path)

    def fail(*args):
        raise RuntimeError("ownership failed")

    monkeypatch.setattr(AccountCoordinator, "register_pending", fail)
    with pytest.raises(RuntimeError, match="ownership"):
        EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(batch, sources, batch.decision_time)
    assert reservations.read()[1].slots == 0
    assert db.db.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 0
    db.close()


@pytest.mark.parametrize(
    "case,reason",
    [
        ("deadline", "ORDER_DEADLINE"),
        ("risk", "ACCOUNT_OR_RISK_GATE"),
        ("future", "EXECUTION_INPUTS_UNAVAILABLE"),
    ],
)
def test_deadline_risk_and_future_inputs_reject_before_sizing(tmp_path, case, reason):
    db, reservations, _, _, batch, sources = setup(tmp_path)
    time = batch.decision_time
    if case == "deadline":
        time += timedelta(seconds=91)
    elif case == "risk":
        time += timedelta(minutes=1)
    else:
        sources = {
            s: replace(v, available_at=time + timedelta(seconds=1)) for s, v in sources.items()
        }
    result = EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(batch, sources, time)
    assert result[0]["reason"] == reason and reservations.read()[1].slots == 0
    db.close()


def test_price_bounds_and_participation_remain_active_in_preliminary_mode(tmp_path):
    db, reservations, _, _, batch, sources = setup(tmp_path)
    source = sources["BTCUSDT"]
    sources["BTCUSDT"] = replace(
        source, quote_model=lambda q: replace(source.quote_model(q), expected_entry=D(110))
    )
    result = EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(
        batch, sources, batch.decision_time
    )
    assert result[0]["reason"] != "ACCEPTED" and reservations.read()[1].slots == 0
    db.close()


def test_signal_service_blocks_pending_owned_symbol_and_uses_identical_core_decisions(tmp_path):
    db, _, service, u, batch, sources = setup(tmp_path)
    runtime = AccountReplay(db, "reference", Quality.PRELIMINARY)
    event = Event(
        "batch",
        Kind.ENTRY_DECISION,
        batch.decisions[0].signal_time,
        batch.decision_time,
        "synthetic",
        Quality.PRELIMINARY,
        canonical({"universe": u}),
    )
    output = runtime(Delivery(event, "CONSERVATIVE_PRIORITY", 0))
    assert canonical(output["batch"]) == canonical(batch)
    EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(batch, sources, batch.decision_time)
    another = service.evaluate(u, batch.decisions[0].signal_time, batch.decision_time)
    assert not another.ranked
    assert all("POSITION_EXISTS" in s.rejection_codes for s in another.decisions)
    db.close()


def test_signal_service_waits_for_missing_batch_then_reports_gap_at_deadline(tmp_path):
    db, _, service, u, batch, _ = setup(tmp_path)
    u = replace(u, symbols=u.symbols + ("MISSINGUSDT",))
    signal_time = batch.decisions[0].signal_time
    assert service.evaluate(u, signal_time, batch.decision_time) is None
    final = service.evaluate(u, signal_time, signal_time + timedelta(seconds=30))
    assert final.missing_symbols == ("MISSINGUSDT",)
    db.close()


def test_planner_cannot_change_account_quality(tmp_path):
    db, _, _, _, batch, sources = setup(tmp_path)
    with pytest.raises(Conflict, match="quality"):
        EntryPlanner(db, "reference", Quality.VERIFIED).plan(batch, sources, batch.decision_time)
    db.close()
