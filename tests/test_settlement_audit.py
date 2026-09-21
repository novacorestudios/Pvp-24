import hashlib
import json

import pytest
from test_archive_acquisition import START, archive, bar
from test_funding_coverage import pair

from pvb24.data.acquisition import acquire
from pvb24.data.archive import ArchiveRequest
from pvb24.data.settlement_audit import audit_settlement_marks
from pvb24.ids import canonical


def setup(tmp_path):
    monthly, _ = pair(tmp_path / "funding", missing_mark=True)
    selection = {"final_test_access": "LOCKED", "coverage": [monthly]}
    path = tmp_path / "selection.json"
    path.write_text(canonical(selection))
    req = ArchiveRequest("BTCUSDT", "markPriceKlines", "2024-01", "1m")
    raw, checksum = archive(req, [bar(), bar(START + 8 * 3600000)])
    _, attempt = acquire(
        req,
        tmp_path / "marks",
        fetch=lambda url, **kw: checksum if url.endswith("CHECKSUM") else raw,
    )
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), attempt


def test_exact_join_keeps_missing_and_never_promotes_open_close_or_jitter(tmp_path):
    path, pin, attempt = setup(tmp_path)
    result = audit_settlement_marks(
        path, pin, tmp_path / "funding/history", [(tmp_path / "marks", attempt)]
    )
    assert result["source_mark_missing"] == 1
    assert result["source_mark_present"] == 1
    assert result["months"][0]["missing_settlement_times_ms"] == [START]
    sample = result["archive_samples"][0]
    assert sample["exact_open_time_matches"] == 1  # second funding time is +1ms
    assert sample["matched_bars_unavailable_at_funding_availability"] == 1
    assert sample["exact_previous_close_time_matches"] == 0
    assert sample["qualified_settlement_prices"] == 0
    assert not result["settlement_pricing_complete"]
    assert not result["operational_ready"] and result["final_test_access"] == "LOCKED"


def test_later_archive_information_cannot_fill_settlement_gaps(tmp_path):
    path, pin, attempt = setup(tmp_path)
    before = audit_settlement_marks(path, pin, tmp_path / "funding/history")
    after = audit_settlement_marks(
        path, pin, tmp_path / "funding/history", [(tmp_path / "marks", attempt)]
    )
    for key in (
        "months",
        "source_mark_missing",
        "source_mark_present",
        "settlement_pricing_complete",
    ):
        assert before[key] == after[key]


def test_previous_close_is_diagnostic_only_even_when_exactly_available(tmp_path):
    from test_funding_history import payload, row

    from pvb24.data.funding_coverage import audit_month

    funding_root = tmp_path / "funding"
    mark_root = tmp_path / "marks"
    funding_time = START + 60_000
    funding_request = ArchiveRequest("BTCUSDT", "fundingRate", "2024-01")
    funding_raw, funding_checksum = archive(
        funding_request,
        [[str(funding_time), "8", "0.0001"]],
    )
    monthly, _ = audit_month(
        funding_request,
        funding_root,
        archive_fetch=lambda url, **kw: (
            funding_checksum if url.endswith(".CHECKSUM") else funding_raw
        ),
        history_fetch=lambda url: payload([row(funding_time, markPrice="100.25")]),
    )
    selection = {"final_test_access": "LOCKED", "coverage": [monthly]}
    selection_path = tmp_path / "selection-previous-close.json"
    selection_path.write_text(canonical(selection))

    mark_request = ArchiveRequest("BTCUSDT", "markPriceKlines", "2024-01", "1m")
    mark_raw, mark_checksum = archive(
        mark_request,
        [
            bar(START, **{"4": "100.20"}),
            bar(funding_time, **{"1": "100.30"}),
        ],
    )
    _, attempt = acquire(
        mark_request,
        mark_root,
        fetch=lambda url, **kw: mark_checksum if url.endswith("CHECKSUM") else mark_raw,
    )

    result = audit_settlement_marks(
        selection_path,
        hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        funding_root / "history",
        [(mark_root, attempt)],
    )
    sample = result["archive_samples"][0]
    assert sample["exact_previous_close_time_matches"] == 1
    assert sample["previous_close_unavailable_at_funding_availability"] == 0
    assert sample["known_mark_unequal_previous_close_times"] == ["2024-01-01T00:01:00.000000Z"]
    assert sample["qualified_settlement_prices"] == 0
    assert result["archive_derived_settlement_prices"] == 0


@pytest.mark.parametrize("change", ["hash", "request", "report", "duplicate", "final", "empty"])
def test_selection_tampering_and_holdout_fail_closed(tmp_path, change):
    path, pin, _ = setup(tmp_path)
    value = json.loads(path.read_text())
    if change == "request":
        value["coverage"][0]["request"]["symbol"] = "ETHUSDT"
    elif change == "report":
        value["coverage"][0]["history"]["report"] = "../foreign.json"
    elif change == "duplicate":
        value["coverage"].append(value["coverage"][0])
    elif change == "final":
        value["coverage"][0]["request"]["month"] = "2025-07"
    elif change == "empty":
        value["coverage"] = []
    path.write_text(canonical(value) + "\n")
    if change != "hash":
        pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        audit_settlement_marks(path, pin, tmp_path / "funding/history")


def test_underlying_source_is_reverified_not_trusted_from_report_counts(tmp_path):
    path, pin, _ = setup(tmp_path)
    page = next((tmp_path / "funding/history/objects").glob("*.json"))
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(ValueError, match="page bytes changed"):
        audit_settlement_marks(path, pin, tmp_path / "funding/history")


def test_duplicate_samples_do_not_inflate_coverage(tmp_path):
    path, pin, attempt = setup(tmp_path)
    sample = (tmp_path / "marks", attempt)
    with pytest.raises(ValueError, match="Unique"):
        audit_settlement_marks(path, pin, tmp_path / "funding/history", [sample, sample])


def test_price_agreement_and_disagreement_are_diagnostics_not_qualification(tmp_path):
    path, _, attempt = setup(tmp_path)
    monthly, _ = pair(tmp_path / "funding", missing_mark=False)
    path.write_text(canonical({"final_test_access": "LOCKED", "coverage": [monthly]}))
    result = audit_settlement_marks(
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        tmp_path / "funding/history",
        [(tmp_path / "marks", attempt)],
    )
    sample = result["archive_samples"][0]
    assert len(sample["known_mark_unequal_open_times"]) == 1
    assert not sample["known_mark_equal_open_times"]
    assert sample["exact_previous_close_time_matches"] == 0
    assert sample["qualified_settlement_prices"] == 0
    assert result["settlement_pricing_complete"]  # Both REST rows have associated prices.
    assert not result["funding_schedule_complete"]
