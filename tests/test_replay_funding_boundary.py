from dataclasses import replace
from datetime import timedelta

import pytest
from test_account_replay import deliver, envelope, open_owned, record, runtime_setup
from test_data import NOW

from pvb24.accounting.ledger import (
    FillRecord,
    Ledger,
    LedgerStore,
    OwnedPosition,
    ReconciliationRequired,
)
from pvb24.decimal_math import D
from pvb24.ids import canonical
from pvb24.replay.account import AccountReplay
from pvb24.replay.events import Event, Kind
from pvb24.replay.funding import replay_funding_payments
from pvb24.state import Journal
from pvb24.types import Quality, Side

SETTLEMENT = NOW + timedelta(seconds=10)


def source_entry(**changes):
    row = {
        "symbol": "BTCUSDT",
        "funding_time": SETTLEMENT.isoformat(),
        "rate": "0.001",
        "mark_price": "100",
        "rate_type": "Regular",
        "available_at": (SETTLEMENT + timedelta(seconds=2)).isoformat(),
    }
    row.update(changes)
    return {
        "record": row,
        "source": "https://fapi.binance.com/fapi/v1/fundingRate?m11l=1",
        "revision_id": "d" * 64,
    }


def funding_event(name="funding", entry=None, available=None, source=None):
    entry = entry or source_entry()
    available = available or SETTLEMENT + timedelta(seconds=2)
    return Event(
        name,
        Kind.FUNDING,
        SETTLEMENT,
        available,
        source or entry["source"],
        Quality.PRELIMINARY,
        canonical({"type": "EXACT_SOURCE_FUNDING", "entry": entry}),
    )


def test_exact_source_funding_uses_owned_replay_boundary_quantity(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    result = deliver(runtime, funding_event())
    assert result["eligible_positions"] == 1 and result["ingested"] == 1
    assert len(result["payment_ids"]) == 1
    view = LedgerStore(db, "paper").read()[1].view(SETTLEMENT + timedelta(seconds=2))
    assert view.funding == D("-0.45")
    payment = next(iter(LedgerStore(db, "paper").read()[1].funding.values()))
    assert payment.eligible_quantity == D("4.5")
    assert payment.settlement_time == SETTLEMENT
    db.close()


def test_reduction_before_boundary_reduces_eligible_quantity(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    reduced = record(
        "reduce",
        "1.5",
        "100",
        side=Side.SHORT,
        reduce=True,
        seconds=5,
    )
    deliver(
        runtime,
        envelope(
            "reduce",
            Kind.REDUCE_FILL,
            reduced,
            reduced.fill.event_time,
            reduced.fill.received_at,
        ),
    )
    deliver(runtime, funding_event())
    payment = next(iter(LedgerStore(db, "paper").read()[1].funding.values()))
    assert payment.eligible_quantity == D("3")
    assert payment.cashflow == D("-0.3")
    db.close()


def test_fill_after_settlement_is_known_but_excluded_from_boundary_quantity(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    after = record(
        "after",
        "1",
        "100",
        side=Side.SHORT,
        reduce=True,
        seconds=11,
    )
    deliver(
        runtime,
        envelope(
            "after",
            Kind.REDUCE_FILL,
            after,
            after.fill.event_time,
            after.fill.received_at,
        ),
    )
    deliver(runtime, funding_event())
    payment = next(iter(LedgerStore(db, "paper").read()[1].funding.values()))
    assert payment.eligible_quantity == D("4.5")
    view = LedgerStore(db, "paper").read()[1].view(SETTLEMENT + timedelta(seconds=2))
    assert view.positions[0].quantity == D("3.5")
    db.close()


def test_late_fill_that_revises_frozen_funding_boundary_fails_closed(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    deliver(runtime, funding_event())
    late = record(
        "late",
        "1",
        "100",
        side=Side.SHORT,
        reduce=True,
        seconds=9,
    )
    late = replace(
        late,
        fill=replace(
            late.fill,
            received_at=SETTLEMENT + timedelta(seconds=3),
        ),
    )
    with pytest.raises(ReconciliationRequired, match="funding boundary"):
        deliver(
            runtime,
            envelope(
                "late",
                Kind.REDUCE_FILL,
                late,
                late.fill.event_time,
                late.fill.received_at,
            ),
        )
    ledger = LedgerStore(db, "paper").read()[1]
    assert "late" not in ledger.fills
    assert ledger.view(SETTLEMENT + timedelta(seconds=4)).funding == D("-0.45")
    assert not db.snapshot("account-gate:paper")[1]["ready"]
    db.close()


@pytest.mark.parametrize(
    "event_change,entry_change,match",
    [
        ({"available": SETTLEMENT + timedelta(seconds=1)}, {}, "source availability"),
        (
            {},
            {"funding_time": (SETTLEMENT + timedelta(milliseconds=1)).isoformat()},
            "timing",
        ),
        ({}, {"mark_price": None}, "settlement Mark"),
        ({}, {"rate_type": "UNKNOWN"}, "Regular"),
        ({"source": "different"}, {}, "source differs"),
    ],
)
def test_exact_source_event_timing_economics_and_provenance_fail_closed(
    tmp_path,
    event_change,
    entry_change,
    match,
):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    event = funding_event(entry=source_entry(**entry_change), **event_change)
    with pytest.raises(ValueError, match=match):
        deliver(runtime, event)
    assert not LedgerStore(db, "paper").read()[1].funding
    db.close()


def test_exact_source_path_cannot_be_promoted_to_verified(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    event = replace(funding_event(), quality=Quality.VERIFIED)
    with pytest.raises(ValueError, match="PRELIMINARY"):
        deliver(runtime, event)
    db.close()


def test_flat_boundary_emits_no_payment(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    result = deliver(runtime, funding_event())
    assert result["eligible_positions"] == 0
    assert result["ingested"] == 0 and result["payment_ids"] == []
    assert not LedgerStore(db, "paper").read()[1].funding
    db.close()


def test_exact_source_replay_receipt_is_restart_idempotent(tmp_path):
    db, _, runtime = runtime_setup(tmp_path)
    open_owned(runtime, db)
    event = funding_event()
    first = deliver(runtime, event)
    count = len(LedgerStore(db, "paper").read()[1].funding)
    db.close()

    reopened = Journal(tmp_path / "account.sqlite")
    resumed = AccountReplay(reopened, "paper", Quality.PRELIMINARY)
    assert deliver(resumed, event) == first
    assert len(LedgerStore(reopened, "paper").read()[1].funding) == count == 1
    reopened.close()


def test_ambiguous_same_boundary_fill_order_is_not_eligibility_evidence():
    ledger = Ledger(D(1000))
    ledger.register(OwnedPosition("p", "BTCUSDT", Side.LONG, NOW))
    entered = record("e", "2", "100", side=Side.LONG, seconds=10)
    reduced = record(
        "x",
        "1",
        "100",
        side=Side.SHORT,
        reduce=True,
        seconds=10,
    )
    ledger.ingest_fill(FillRecord(entered.fill))
    ledger.ingest_fill(FillRecord(reduced.fill))
    with pytest.raises(ReconciliationRequired, match="Ambiguous fill ordering"):
        replay_funding_payments(
            ledger,
            source_entry(),
            SETTLEMENT + timedelta(seconds=2),
        )
