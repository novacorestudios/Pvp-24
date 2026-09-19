from datetime import timedelta

import pytest
from test_account_coordinator import setup
from test_accounting import mark, record
from test_data import NOW

from pvb24.accounting.risk_service import AccountRiskService
from pvb24.decimal_math import D
from pvb24.state import Conflict


def service(db):
    result = AccountRiskService(db, "paper")
    result.initialize(NOW, max_mark_age=timedelta(seconds=1), policy_id="SYNTHETIC-TEST-POLICY")
    return result


def entry_id(db):
    return db.db.execute("SELECT client_id FROM intents WHERE purpose='ENTRY'").fetchone()[0]


def test_policy_frozen_before_cashflows_and_cannot_be_reconfigured(tmp_path):
    db, _, coordinator = setup(tmp_path)
    risk = service(db)
    with pytest.raises(Conflict, match="already frozen"):
        risk.initialize(NOW, max_mark_age=timedelta(seconds=2), policy_id="changed")
    assert risk.status() is None
    assert not db.claim_dispatch(entry_id(db))  # no risk sample yet
    status, _ = risk.sample(NOW, [])
    assert status.entries_allowed and db.claim_dispatch(entry_id(db))
    db.close()


def test_missing_mark_blocks_entry_dispatch_but_not_protection(tmp_path):
    db, _, c = setup(tmp_path)
    risk = service(db)
    risk.sample(NOW, [])
    assert db.claim_dispatch(entry_id(db))
    (protect,) = c.confirmed_fill(record(quantity="4.5"))
    status, actions = risk.sample(NOW + timedelta(minutes=1), [])
    assert status.data_paused and not status.entries_allowed and actions == ()
    assert db.claim_dispatch(protect)
    db.close()


def test_hard_drawdown_atomically_emits_full_reduce_only_close_and_cancels_entry(tmp_path):
    db, _, c = setup(tmp_path)
    risk = service(db)
    risk.sample(NOW, [])
    db.claim_dispatch(entry_id(db))
    c.confirmed_fill(record(quantity="4.5"))
    time = NOW + timedelta(minutes=1)
    status, ids = risk.sample(time, [mark("60", time)])
    assert status.hard_paused and not status.entries_allowed
    purposes = [
        db.db.execute("SELECT purpose FROM intents WHERE client_id=?", (cid,)).fetchone()[0]
        for cid in ids
    ]
    assert sorted(purposes) == ["CANCEL_ENTRY", "EXIT_MARKET"]
    assert risk.sample(time, [mark("60", time)])[1] == ()
    next_time = time + timedelta(minutes=1)
    assert risk.sample(next_time, [mark("60", next_time)])[1] == ()  # unknown close is not retried
    with pytest.raises(ValueError, match="old sample"):
        risk.sample(time, [mark("60", time)])
    db.close()


def test_hard_pause_closes_only_newly_confirmed_uncovered_quantity(tmp_path):
    db, _, c = setup(tmp_path)
    risk = service(db)
    risk.sample(NOW, [])
    db.claim_dispatch(entry_id(db))
    c.confirmed_fill(record(quantity="2"))
    time = NOW + timedelta(minutes=1)
    risk.sample(time, [mark("20", time)])  # 160 loss -> hard pause, close request covers 2
    c.confirmed_fill(record("late", "2.5", seconds=61))
    status, ids = risk.sample(
        time + timedelta(minutes=1), [mark("20", time + timedelta(minutes=1))]
    )
    assert status.hard_paused and len(ids) == 1
    import json

    payload = json.loads(
        db.db.execute("SELECT payload FROM intents WHERE client_id=?", (ids[0],)).fetchone()[0]
    )
    assert D(payload["quantity"]) == D("2.5") and payload["reduce_only"] is True
    db.close()


def test_daily_pause_cancels_an_unsent_entry_without_ever_claiming_it(tmp_path):
    db, _, c = setup(tmp_path)
    risk = service(db)
    risk.sample(NOW, [])
    # A dedicated account expense in this test comes from an owned fee-only
    # synthetic fill; prove its own entry was already dispatched first.
    db.claim_dispatch(entry_id(db))
    c.confirmed_fill(record(quantity="2", fee="50"))
    extra, _ = db.prepare_intent("paper", "other-signal", "ENTRY", {"fixture": "unsent"})
    time = NOW + timedelta(minutes=1)
    status, _ = risk.sample(time, [mark("100", time)])
    assert status.daily_paused and not status.hard_paused
    assert not db.claim_dispatch(extra)
    assert (
        db.db.execute("SELECT state FROM intents WHERE client_id=?", (extra,)).fetchone()[0]
        == "CANCELED"
    )
    db.close()


def test_risk_state_and_policy_survive_restart(tmp_path):
    db, _, _ = setup(tmp_path)
    risk = service(db)
    original, _ = risk.sample(NOW, [])
    path = tmp_path / "account.sqlite"
    db.close()
    from pvb24.state import Journal

    db = Journal(path)
    assert AccountRiskService(db, "paper").status() == original
    db.close()
