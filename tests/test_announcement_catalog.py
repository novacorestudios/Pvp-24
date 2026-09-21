import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from pvb24.data.announcement_catalog import (
    acquire_slice,
    decode_page,
    load_slice,
    page_url,
)

START = datetime(2020, 1, 1, tzinfo=UTC)
END = datetime(2025, 7, 1, tzinfo=UTC)


def ms(value):
    return int(value.timestamp() * 1000)


def article(code="0123456789abcdef0123456789abcdef", when=None, **changes):
    return {
        "id": 1,
        "code": code,
        "title": "Binance Futures Will Launch TEST/USDT Perpetual Contract",
        "type": 1,
        "releaseDate": ms(when or datetime(2024, 1, 1, tzinfo=UTC)),
        **changes,
    }


def payload(catalog_id, rows, *, total=40, success=True, code="000000"):
    return json.dumps(
        {
            "code": code,
            "message": None,
            "messageDetail": None,
            "data": {
                "catalogs": [
                    {
                        "catalogId": catalog_id,
                        "catalogName": "fixture",
                        "total": total,
                        "articles": rows,
                        "catalogs": [],
                    }
                ]
            },
            "success": success,
        }
    ).encode()


def test_official_catalog_page_identity_and_newest_first_decode():
    newer = article(when=datetime(2024, 2, 1, tzinfo=UTC))
    older = article(
        code="360038585151",
        when=datetime(2024, 1, 1, tzinfo=UTC),
        id=2,
    )
    total, rows = decode_page(payload(48, [newer, older]), 48, 7)
    assert total == 40 and [row["code"] for row in rows] == [
        newer["code"],
        "360038585151",
    ]
    assert rows[1]["catalog_scope"] == "NEW_CRYPTOCURRENCY_LISTING"
    params = parse_qs(urlsplit(page_url(48, 7)).query)
    assert params == {
        "type": ["1"],
        "catalogId": ["48"],
        "pageNo": ["7"],
        "pageSize": ["20"],
    }


@pytest.mark.parametrize(
    "case",
    [
        "wrong_catalog",
        "failure",
        "wrong_code",
        "duplicate",
        "ascending",
        "bad_article_code",
        "float_release",
        "too_many",
    ],
)
def test_catalog_source_ambiguity_or_inexact_identity_is_rejected(case):
    rows = [
        article(when=datetime(2024, 2, 1, tzinfo=UTC)),
        article(
            code="360038585151",
            id=2,
            when=datetime(2024, 1, 1, tzinfo=UTC),
        ),
    ]
    catalog_id, kwargs = 48, {}
    if case == "wrong_catalog":
        catalog_id = 161
    elif case == "failure":
        kwargs["success"] = False
    elif case == "wrong_code":
        kwargs["code"] = "999999"
    elif case == "duplicate":
        rows[1]["code"] = rows[0]["code"]
    elif case == "ascending":
        rows.reverse()
    elif case == "bad_article_code":
        rows[0]["code"] = "../x"
    elif case == "float_release":
        rows[0]["releaseDate"] = 1.5
    elif case == "too_many":
        rows = [article(code=f"{i:032x}") for i in range(21)]
    with pytest.raises(ValueError):
        decode_page(payload(catalog_id, rows, **kwargs), 48, 1)


def test_explicit_pre_final_slice_retains_pages_and_stops_after_lower_boundary(tmp_path):
    pages = {
        5: [
            article(when=datetime(2020, 2, 1, tzinfo=UTC)),
            article(code="360038585151", id=2, when=datetime(2020, 1, 10, tzinfo=UTC)),
        ],
        6: [
            article(
                code="360038969011",
                id=3,
                when=datetime(2019, 12, 31, tzinfo=UTC),
            )
        ],
    }
    calls = []

    def fetch(url):
        page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
        calls.append(page)
        return payload(48, pages[page], total=123)

    report, path = acquire_slice(
        48,
        tmp_path,
        start_page=5,
        start=START,
        end=END,
        fetch=fetch,
    )
    assert report["status"] == "ACQUIRED" and report["catalog_slice_complete"]
    assert calls == [5, 6] and len(report["in_window_articles"]) == 2
    assert not report["historical_universe_complete"]
    assert not report["security_master_complete"] and not report["lifecycle_complete"]
    assert path.exists()
    checked = load_slice(
        tmp_path,
        path.relative_to(tmp_path),
        expected_report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    assert checked["article_hash"] == report["article_hash"]


def test_page_with_final_or_upper_boundary_article_fails_closed_instead_of_filtering(tmp_path):
    future = article(when=datetime(2025, 7, 1, tzinfo=UTC))
    report, path = acquire_slice(
        48,
        tmp_path,
        start_page=1,
        start=START,
        end=END,
        fetch=lambda url: payload(48, [future]),
    )
    assert report["status"] == "INCOMPLETE"
    assert "locked/upper boundary" in report["error"]
    assert not report["catalog_slice_complete"] and path.exists()


@pytest.mark.parametrize("case", ["total_change", "revision", "budget"])
def test_catalog_pagination_never_silently_accepts_drift_or_truncation(tmp_path, case):
    calls = []

    def fetch(url):
        page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
        calls.append(page)
        if page == 2:
            row = article(when=datetime(2024, 1, 1, tzinfo=UTC))
            return payload(161, [row], total=40)
        if case == "total_change":
            return payload(
                161,
                [article(code="360038585151", id=2, when=datetime(2023, 1, 1, tzinfo=UTC))],
                total=41,
            )
        if case == "revision":
            return payload(
                161,
                [
                    article(
                        when=datetime(2024, 1, 1, tzinfo=UTC),
                        title="changed",
                    )
                ],
                total=40,
            )
        return payload(
            161,
            [article(code="360038585151", id=2, when=datetime(2023, 1, 1, tzinfo=UTC))],
            total=40,
        )

    report, _ = acquire_slice(
        161,
        tmp_path,
        start_page=2,
        start=START,
        end=END,
        fetch=fetch,
        page_size=1,
        max_pages=1 if case == "budget" else 3,
    )
    assert report["status"] == "INCOMPLETE" and "error" in report
    assert not report["catalog_slice_complete"]


def test_retained_source_object_and_report_pins_are_rechecked(tmp_path):
    report, path = acquire_slice(
        161,
        tmp_path,
        start_page=3,
        start=START,
        end=END,
        fetch=lambda url: payload(
            161,
            [article(when=datetime(2019, 12, 1, tzinfo=UTC))],
            total=1,
        ),
    )
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    loaded = load_slice(tmp_path, path.relative_to(tmp_path), expected_report_sha256=expected)
    source = tmp_path / "objects" / loaded["pages"][0]["object"]
    source.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="source page changed"):
        load_slice(tmp_path, path.relative_to(tmp_path), expected_report_sha256=expected)
    with pytest.raises(ValueError, match="report changed"):
        load_slice(tmp_path, path.relative_to(tmp_path), expected_report_sha256="0" * 64)


def test_catalog_discovery_cannot_claim_history_or_unlock_final(tmp_path):
    report, _ = acquire_slice(
        48,
        tmp_path,
        start_page=1,
        start=START,
        end=END,
        fetch=lambda url: payload(
            48,
            [article(when=datetime(2019, 12, 1, tzinfo=UTC))],
            total=1,
        ),
    )
    assert report["performance_run"] is False
    assert report["final_test_access"] == "LOCKED"
    assert report["quality"] == "PRELIMINARY"
    for field in (
        "historical_universe_complete",
        "security_master_complete",
        "lifecycle_complete",
    ):
        assert report[field] is False


@pytest.mark.parametrize(
    "args",
    [
        (999, 1, 20),
        (48, 0, 20),
        (48, 1, 0),
        (48, 1, 21),
        (48, True, 20),
    ],
)
def test_catalog_requests_are_bounded_and_reviewed(args):
    with pytest.raises(ValueError):
        page_url(*args)
