from datetime import UTC, datetime, timedelta

import pytest

from pvb24.data.funding_usability import (
    FundingEligibilityEvidence,
    funding_payment_from_exact_source,
    qualify_history_rows,
)
from pvb24.decimal_math import D
from pvb24.types import Side

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def entry(**changes):
    record = {
        "symbol": "BTCUSDT",
        "funding_time": T0.isoformat(),
        "rate": "0.0001",
        "mark_price": "42000.25",
        "rate_type": "Regular",
        "available_at": (T0 + timedelta(seconds=2)).isoformat(),
    }
    record.update(changes)
    return {
        "record": record,
        "source": "https://fapi.binance.com/fapi/v1/fundingRate?fixture=1",
        "revision_id": "a" * 64,
    }


def eligibility(**changes):
    values = {
        "position_id": "position-1",
        "symbol": "BTCUSDT",
        "side": Side.LONG,
        "eligible_quantity": D("0.5"),
        "settlement_time": T0,
        "available_at": T0 + timedelta(seconds=3),
        "source": "synthetic-qualified-account-boundary",
        "revision_id": "b" * 64,
        "boundary_verified": True,
    }
    values.update(changes)
    return FundingEligibilityEvidence(**values)


def test_exact_source_economics_plus_boundary_evidence_build_one_accounting_payment():
    payment = funding_payment_from_exact_source(entry(), eligibility())
    assert payment.position_id == "position-1"
    assert payment.side is Side.LONG and payment.eligible_quantity == D("0.5")
    assert payment.mark_price == D("42000.25") and payment.final_rate == D("0.0001")
    assert payment.settlement_time == T0
    assert payment.available_at == T0 + timedelta(seconds=3)
    assert payment.cashflow == D("-2.1000125")
    assert payment.source.endswith("#" + "a" * 64)
    assert len(payment.event_id) == len(payment.eligibility_evidence) == 64


def test_payment_availability_waits_for_both_economics_and_eligibility():
    later_source = entry(available_at=(T0 + timedelta(seconds=9)).isoformat())
    payment = funding_payment_from_exact_source(later_source, eligibility())
    assert payment.available_at == T0 + timedelta(seconds=9)


@pytest.mark.parametrize(
    "source_change,eligibility_change,match",
    [
        ({"mark_price": None}, {}, "settlement Mark"),
        ({"rate_type": "UNKNOWN"}, {}, "Regular"),
        ({"rate_type": "Special"}, {}, "Regular"),
        ({"symbol": "ETHUSDT"}, {}, "match exactly"),
        (
            {"funding_time": (T0 + timedelta(milliseconds=1)).isoformat()},
            {},
            "match exactly",
        ),
        ({}, {"symbol": "ETHUSDT"}, "match exactly"),
        (
            {},
            {"settlement_time": T0 + timedelta(milliseconds=1)},
            "match exactly",
        ),
    ],
)
def test_missing_or_nonmatching_source_evidence_never_becomes_a_payment(
    source_change, eligibility_change, match
):
    with pytest.raises(ValueError, match=match):
        funding_payment_from_exact_source(
            entry(**source_change), eligibility(**eligibility_change)
        )


def test_boundary_evidence_is_fail_closed():
    with pytest.raises(ValueError, match="independently verified"):
        eligibility(boundary_verified=False)
    with pytest.raises(ValueError, match="cannot predate"):
        eligibility(available_at=T0 - timedelta(microseconds=1))
    with pytest.raises(TypeError):
        funding_payment_from_exact_source(entry(), object())


def test_qualification_separates_exact_economics_from_schedule_and_position_eligibility():
    rows = [
        entry(),
        entry(
            funding_time=(T0 + timedelta(hours=8)).isoformat(),
            available_at=(T0 + timedelta(hours=8, seconds=2)).isoformat(),
            mark_price=None,
        ),
        entry(
            funding_time=(T0 + timedelta(hours=16)).isoformat(),
            available_at=(T0 + timedelta(hours=16, seconds=2)).isoformat(),
            rate_type="Special",
        ),
    ]
    report = qualify_history_rows(rows)
    assert report["rows"] == 3 and report["exact_source_economics_rows"] == 1
    assert report["missing_settlement_mark_rows"] == 1
    assert report["unsupported_rate_type_rows"] == 1
    assert report["conditionally_ledger_usable_rows"] == 1
    assert report["unconditional_ledger_usable_rows"] == 0
    assert report["requires_independent_position_eligibility"]
    assert not report["funding_schedule_complete"]
    assert not report["funding_reserve_coverage_qualified"]
    assert not report["position_eligibility_verified"]
    assert report["quality"] == "PRELIMINARY" and not report["operational_ready"]


def test_irregular_exact_timestamps_are_preserved_not_rounded_into_a_schedule():
    rows = [
        entry(),
        entry(
            funding_time=(T0 + timedelta(hours=8, milliseconds=1)).isoformat(),
            available_at=(T0 + timedelta(hours=8, seconds=2, milliseconds=1)).isoformat(),
        ),
    ]
    report = qualify_history_rows(rows)
    assert report["last_settlement_time"] == "2024-01-01T08:00:00.001000Z"
    assert not report["funding_schedule_complete"]


def test_duplicate_source_identity_is_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        qualify_history_rows([entry(), entry()])


def test_source_wrapper_and_record_must_be_exact_not_best_effort():
    changed = entry()
    changed["unexpected"] = True
    with pytest.raises(ValueError, match="wrapper"):
        funding_payment_from_exact_source(changed, eligibility())
    changed = entry()
    changed["record"]["unexpected"] = "x"
    with pytest.raises(ValueError, match="schema"):
        funding_payment_from_exact_source(changed, eligibility())


def test_event_identity_changes_when_independent_eligibility_evidence_changes():
    first = funding_payment_from_exact_source(entry(), eligibility())
    second = funding_payment_from_exact_source(
        entry(), eligibility(revision_id="c" * 64)
    )
    assert first.event_id != second.event_id
