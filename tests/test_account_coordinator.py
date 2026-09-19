from dataclasses import replace
from datetime import timedelta

import pytest
from test_accounting import payment, record
from test_data import NOW
from test_sizing import rules, solve

from pvb24.accounting.coordinator import AccountCoordinator
from pvb24.accounting.ledger import Ledger, LedgerStore, ReconciliationRequired
from pvb24.decimal_math import D
from pvb24.execution.protection import Protection
from pvb24.risk.portfolio import Portfolio
from pvb24.risk.reservations import Reservations
from pvb24.state import Conflict, Journal
from pvb24.types import Side


def setup(tmp_path):
    db = Journal(tmp_path / "account.sqlite")
    reservations = Reservations(db, "paper")
    reservations.initialize(Portfolio(D(1000), D(1000)))
    reservations.reserve(1, "signal", "BTCUSDT", Side.LONG, solve())
    LedgerStore(db, "paper").initialize(Ledger(D(1000)))
    coordinator = AccountCoordinator(db, "paper")
    coordinator.register_pending(
        Protection("signal", "BTCUSDT", Side.LONG, D("4.5"), D(1), D("0.1")), NOW
    )
    return db, reservations, coordinator


def terminal(coordinator):
    return coordinator.protection_event(
        "signal",
        "terminal",
        "synthetic-confirmed-terminal",
        lambda p: p.entry_terminal(),
        NOW + timedelta(seconds=1),
    )


def test_confirmed_fill_atomically_updates_ledger_protection_intent_and_gate(tmp_path):
    db, reservations, c = setup(tmp_path)
    original_risk = reservations.read()[1].reserved_risk
    ids = c.confirmed_fill(record())
    assert len(ids) == 1 and db.claim_dispatch(ids[0])
    assert c.confirmed_fill(record()) == ()
    _, account = LedgerStore(db, "paper").read()
    assert account.view(NOW + timedelta(seconds=1)).cash == D("999.9")
    _, state = db.snapshot("protection:paper:signal")
    assert Protection.restore(state).remaining == 2
    assert reservations.read()[1].reserved_risk == original_risk  # locked until reconciliation
    version, portfolio = reservations.read()
    another = solve(symbol="ETHUSDT", rules=replace(rules(), symbol="ETHUSDT"), portfolio=portfolio)
    with pytest.raises(Conflict, match="reconciliation"):
        reservations.reserve(version, "other", "ETHUSDT", Side.LONG, another)
    db.close()


def test_failure_cannot_commit_cash_without_protection_or_entry_pause(tmp_path, monkeypatch):
    db, reservations, c = setup(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("injected failure after fill ingestion")

    monkeypatch.setattr(Journal, "prepare_intent_tx", staticmethod(fail))
    with pytest.raises(RuntimeError):
        c.confirmed_fill(record())
    assert not LedgerStore(db, "paper").read()[1].fills
    assert Protection.restore(db.snapshot("protection:paper:signal")[1]).remaining == 0
    assert db.snapshot("account-gate:paper")[1]["ready"]
    assert (
        db.db.execute(
            "SELECT COUNT(*) FROM events WHERE event_id LIKE 'account-fill:%'"
        ).fetchone()[0]
        == 0
    )
    db.close()


def test_zero_fill_releases_reservation_only_after_terminal_and_cash_proof(tmp_path):
    db, reservations, c = setup(tmp_path)
    with pytest.raises(ReconciliationRequired, match="unresolved"):
        c.reconcile_flat(NOW, D(1000), "too-early")
    terminal(c)
    with pytest.raises(ReconciliationRequired, match="Cash mismatch"):
        c.reconcile_flat(NOW + timedelta(seconds=2), D(999), "wrong-cash")
    assert c.reconcile_flat(NOW + timedelta(seconds=2), D(1000), "proven-flat")
    portfolio = reservations.read()[1]
    assert (
        portfolio.slots == 0 and portfolio.reserved_risk == 0 and portfolio.free_collateral == 1000
    )
    assert db.snapshot("account-gate:paper")[1]["ready"]
    db.close()


def test_late_fill_after_zero_fill_release_is_preserved_and_reblocks_entries(tmp_path):
    db, _, c = setup(tmp_path)
    terminal(c)
    c.reconcile_flat(NOW + timedelta(seconds=2), D(1000), "flat")
    late = record()
    late = replace(late, fill=replace(late.fill, received_at=NOW + timedelta(seconds=3)))
    assert len(c.confirmed_fill(late)) == 1
    assert not db.snapshot("account-gate:paper")[1]["ready"]
    assert (
        LedgerStore(db, "paper").read()[1].view(NOW + timedelta(seconds=4)).positions[0].quantity
        == 2
    )
    db.close()


def test_reconciliation_cannot_backdate_terminal_evidence(tmp_path):
    db, _, c = setup(tmp_path)
    terminal(c)
    with pytest.raises(ReconciliationRequired, match="backdate"):
        c.reconcile_flat(NOW, D(1000), "backdated")
    db.close()


def test_full_exit_releases_risk_after_proof_but_cannot_clear_safety_pause(tmp_path):
    db, reservations, c = setup(tmp_path)
    c.confirmed_fill(record())
    terminal(c)
    c.protection_event(
        "signal",
        "failed",
        "synthetic-protection-timeout",
        lambda p: p.protection_failed(),
        NOW + timedelta(seconds=2),
    )
    c.confirmed_fill(record("exit", "2", "105", side=Side.SHORT, reduce=True, seconds=3))
    assert c.reconcile_flat(NOW + timedelta(seconds=4), D("1009.8"), "flat-after-emergency")
    assert reservations.read()[1].reserved_risk == 0
    gate = db.snapshot("account-gate:paper")[1]
    assert gate["safety_paused"] and not gate["ready"]
    db.close()


def test_open_account_cannot_use_flat_reconciliation_to_release_its_risk(tmp_path):
    db, _, c = setup(tmp_path)
    c.confirmed_fill(record())
    terminal(c)
    with pytest.raises(ReconciliationRequired, match="non-flat"):
        c.reconcile_flat(NOW + timedelta(seconds=2), D("999.9"), "not-flat")
    db.close()


def test_funding_also_invalidates_prior_risk_reconciliation_and_deduplicates(tmp_path):
    db, _, c = setup(tmp_path)
    c.confirmed_fill(record())
    assert c.confirmed_funding(payment())
    assert not c.confirmed_funding(payment())
    gate = db.snapshot("account-gate:paper")[1]
    assert gate["reason"] == "POST_FUNDING_RECONCILIATION_REQUIRED" and not gate["ready"]
    account = LedgerStore(db, "paper").read()[1]
    assert account.view(NOW + timedelta(seconds=11)).cash == D("999.7")
    db.close()
