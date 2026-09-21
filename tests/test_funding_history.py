import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from test_archive_acquisition import START

from pvb24.data.archive import ArchiveRequest, FundingArchiveRow
from pvb24.data.funding_history import acquire_history, compare_archive, decode_page, request_url
from pvb24.decimal_math import D

REQ = ArchiveRequest("BTCUSDT", "fundingRate", "2024-01")


def row(stamp=START, **changes):
    return {
        "symbol": "BTCUSDT",
        "fundingTime": stamp,
        "fundingRate": "0.0001",
        "markPrice": "42000.12345678",
        "rateType": "Regular",
        **changes,
    }


def payload(rows):
    return json.dumps(rows).encode()


def test_inclusive_pagination_retains_second_rate_type_at_same_time_boundary(tmp_path):
    t0, t1, t2, t3 = [START + i * 3600000 for i in range(4)]
    pages = {
        t0: [row(t0), row(t1), row(t2)],
        t2: [row(t2), row(t2, rateType="Special"), row(t3)],
        t3: [row(t3)],
    }
    urls = []

    def fetch(url):
        urls.append(url)
        return payload(pages[int(parse_qs(urlsplit(url).query)["startTime"][0])])

    report, path = acquire_history(REQ, tmp_path, fetch=fetch, limit=3)
    assert report["status"] == "ACQUIRED" and len(report["rows"]) == 5 and len(urls) == 3
    assert not report["regular_type_complete"] and report["settlement_mark_complete"]
    assert not report["funding_schedule_complete"] and not report["position_eligibility_verified"]
    assert path.exists() and all(
        (tmp_path / "objects" / p["object"]).exists() for p in report["pages"]
    )
    assert report["rows"][0]["record"]["mark_price"] == "42000.12345678"


@pytest.mark.parametrize(
    "change",
    [
        {"symbol": "ETHUSDT"},
        {"fundingTime": START - 1},
        {"fundingTime": START * 1000},
        {"fundingRate": float("nan")},
        {"fundingRate": 0.001},
        {"markPrice": "0"},
    ],
)
def test_invalid_or_inexact_source_economics_are_rejected(change):
    with pytest.raises(ValueError):
        decode_page(REQ, payload([row(**change)]), START, 1000)


def test_missing_mark_and_unspecified_rate_type_remain_unknown_not_zero_or_regular(tmp_path):
    item = row(markPrice="")
    del item["rateType"]
    report, _ = acquire_history(REQ, tmp_path, fetch=lambda url: payload([item]))
    assert report["status"] == "ACQUIRED" and not report["settlement_mark_complete"]
    assert not report["regular_type_complete"]
    assert report["rows"][0]["record"]["mark_price"] is None
    assert report["rows"][0]["record"]["rate_type"] == "UNKNOWN"
    comparison = compare_archive([], report)
    assert len(comparison["unsupported_rate_rows"]) == 1


@pytest.mark.parametrize("case", ["revision", "budget", "stuck"])
def test_failed_pagination_never_attests_complete_settlement_mark_coverage(tmp_path, case):
    calls = []

    def fetch(url):
        calls.append(url)
        if case == "stuck":
            return payload([row(), row(rateType="Special")])
        if len(calls) == 1:
            return payload([row(), row(START + 3600000)])
        return payload([row(START + 3600000, fundingRate="0.0002")])

    report, path = acquire_history(
        REQ, tmp_path, fetch=fetch, limit=2, max_pages=1 if case == "budget" else 3
    )
    assert report["status"] == "INCOMPLETE" and "error" in report and path.exists()
    assert not report["settlement_mark_complete"] and not report["regular_type_complete"]
    with pytest.raises(ValueError, match="Incomplete"):
        compare_archive([], report)


def test_exact_cross_source_comparison_never_rounds_milliseconds_or_substitutes_rates(tmp_path):
    report, _ = acquire_history(
        REQ,
        tmp_path,
        fetch=lambda url: payload([row(), row(START + 3600000, fundingRate="0.0002")]),
    )
    first = FundingArchiveRow(
        "BTCUSDT", REQ.start, D(8), D("0.0001"), REQ.start + timedelta(seconds=2), "fixture", "v1"
    )
    shifted = FundingArchiveRow(
        "BTCUSDT",
        REQ.start + timedelta(hours=1, milliseconds=1),
        D(1),
        D("0.0002"),
        REQ.start + timedelta(hours=1, seconds=2),
        "fixture",
        "v1",
    )
    compared = compare_archive([first, shifted], report)
    assert compared["matched_time_and_rate"] == 1
    assert len(compared["archive_only"]) == len(compared["history_only"]) == 1
    assert not compared["timestamp_rounding_applied"] and not compared["funding_schedule_complete"]
    from dataclasses import replace

    mismatch = compare_archive([replace(first, rate=D("0.0003"))], report)
    assert len(mismatch["rate_mismatches"]) == 1
    report["rows"][0]["record"]["rate"] = "100"
    with pytest.raises(ValueError, match="records changed"):
        compare_archive([first], report)


def test_requests_are_explicit_bounded_and_final_is_rejected_before_io(tmp_path):
    params = parse_qs(urlsplit(request_url(REQ)).query)
    assert params["startTime"] == [str(START)] and params["endTime"] == ["1706745599999"]
    for cursor in (START - 1, True, 1706745600000):
        with pytest.raises(ValueError):
            request_url(REQ, cursor)
    for limit in (1, 1001, True):
        with pytest.raises(ValueError):
            request_url(REQ, limit=limit)
    object.__setattr__(REQ, "month", "2025-07")
    try:
        with pytest.raises(ValueError, match="LOCKED"):
            acquire_history(REQ, tmp_path, fetch=lambda url: pytest.fail("Final network request"))
        assert not list(tmp_path.iterdir())
    finally:
        object.__setattr__(REQ, "month", "2024-01")
