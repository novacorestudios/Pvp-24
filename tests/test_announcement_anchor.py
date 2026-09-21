import hashlib
import json
import urllib.error
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from pvb24.data.announcement_anchor import (
    REVIEWED_ANCHORS,
    CatalogAnchor,
    load_anchor_review,
    review_anchor_start,
)


def ms(value):
    return int(value.timestamp() * 1000)


def article(code, when, *, article_id):
    return {
        "id": article_id,
        "code": code,
        "title": "Reviewed announcement",
        "type": 1,
        "releaseDate": ms(when),
    }


def payload(catalog_id, rows, total):
    return json.dumps(
        {
            "code": "000000",
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
            "success": True,
        }
    ).encode()


def anchor(code, when, start_page=4):
    return CatalogAnchor(
        48,
        code,
        when,
        "https://www.binance.com/en/support/announcement/detail/" + code,
        start_page,
        "https://www.binance.com/en/support/announcement/list/48",
        8,
    )


def http_400(url):
    return urllib.error.HTTPError(url, 400, "Bad Request", None, None)


def test_anchor_review_backs_off_hint_then_walks_old_to_new_without_final(tmp_path):
    code = "a" * 32
    when = datetime(2025, 6, 30, 7, 0, tzinfo=UTC)
    page3 = [
        article("3" * 32, datetime(2024, 1, 2, tzinfo=UTC), article_id=6),
        article("4" * 32, datetime(2024, 1, 1, tzinfo=UTC), article_id=5),
    ]
    page2 = [
        article(code, when, article_id=4),
        article("5" * 32, datetime(2025, 6, 1, tzinfo=UTC), article_id=3),
    ]
    calls = []

    def fetch(url):
        query = parse_qs(urlsplit(url).query)
        page = int(query["pageNo"][0])
        calls.append(page)
        if page == 4:
            raise http_400(url)
        if page == 3:
            return payload(48, page3, 6)
        if page == 2:
            return payload(48, page2, 6)
        raise AssertionError(page)

    report, path = review_anchor_start(
        anchor(code, when),
        tmp_path,
        fetch=fetch,
        page_size=2,
    )
    assert calls == [4, 3, 2]
    assert report["hint"]["backoff_pages"] == 1
    assert report["safe_start_page"] == 2
    assert report["anchor"]["code"] == code
    assert report["final_test_access"] == "LOCKED"
    assert not report["historical_universe_complete"]
    assert path.exists()


def test_anchor_timestamp_or_total_drift_fails_closed(tmp_path):
    code = "a" * 32
    reviewed = datetime(2025, 6, 30, 7, 0, tzinfo=UTC)
    old_rows = [
        article("b" * 32, datetime(2024, 1, 2, tzinfo=UTC), article_id=4),
        article("c" * 32, datetime(2024, 1, 1, tzinfo=UTC), article_id=3),
    ]

    def changed_time(url):
        page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
        if page == 2:
            return payload(48, old_rows, 4)
        return payload(
            48,
            [
                article(
                    code,
                    datetime(2025, 6, 30, 8, 0, tzinfo=UTC),
                    article_id=2,
                ),
                article("d" * 32, datetime(2025, 6, 1, tzinfo=UTC), article_id=1),
            ],
            4,
        )

    with pytest.raises(ValueError, match="release time differs"):
        review_anchor_start(
            anchor(code, reviewed, start_page=2),
            tmp_path,
            fetch=changed_time,
            page_size=2,
        )

    def changed_total(url):
        page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
        if page == 2:
            return payload(48, old_rows, 4)
        return payload(
            48,
            [
                article(code, reviewed, article_id=2),
                article("d" * 32, datetime(2025, 6, 1, tzinfo=UTC), article_id=1),
            ],
            5,
        )

    with pytest.raises(ValueError, match="total changed"):
        review_anchor_start(
            anchor(code, reviewed, start_page=2),
            tmp_path,
            fetch=changed_total,
            page_size=2,
        )


def test_review_rejects_bad_source_pin_before_network(tmp_path):
    calls = []
    bad = CatalogAnchor(
        48,
        "a" * 32,
        datetime(2025, 6, 30, tzinfo=UTC),
        "https://example.com/not-binance",
        2,
        "https://www.binance.com/en/support/announcement/list/48",
        4,
    )
    with pytest.raises(ValueError, match="exact official Binance detail URL"):
        review_anchor_start(bad, tmp_path, fetch=lambda url: calls.append(url))
    assert not calls


def test_review_fails_closed_on_final_page_and_does_not_retain_it(tmp_path):
    code = "a" * 32
    reviewed = datetime(2025, 6, 30, 7, 0, tzinfo=UTC)
    final = article("c" * 32, datetime(2025, 7, 1, tzinfo=UTC), article_id=2)
    older = article("d" * 32, datetime(2025, 6, 1, tzinfo=UTC), article_id=1)

    with pytest.raises(ValueError, match="locked Final Test"):
        review_anchor_start(
            anchor(code, reviewed, start_page=1),
            tmp_path,
            fetch=lambda url: payload(48, [final, older], 2),
            page_size=2,
        )
    assert not list((tmp_path / "objects").glob("*.json"))


def test_review_rejects_cross_page_order_drift(tmp_path):
    code = "a" * 32
    reviewed = datetime(2025, 6, 30, 7, 0, tzinfo=UTC)

    def fetch(url):
        page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
        if page == 2:
            return payload(
                48,
                [
                    article("b" * 32, datetime(2025, 1, 2, tzinfo=UTC), article_id=4),
                    article("c" * 32, datetime(2025, 1, 1, tzinfo=UTC), article_id=3),
                ],
                4,
            )
        return payload(
            48,
            [
                article(code, reviewed, article_id=2),
                article("d" * 32, datetime(2024, 12, 1, tzinfo=UTC), article_id=1),
            ],
            4,
        )

    with pytest.raises(ValueError, match="ordering changed"):
        review_anchor_start(
            anchor(code, reviewed, start_page=2),
            tmp_path,
            fetch=fetch,
            page_size=2,
        )


def test_anchor_review_loader_replays_and_binds_source_chain(tmp_path):
    code = "a" * 32
    when = datetime(2025, 6, 30, 7, 0, tzinfo=UTC)
    page3 = [
        article("3" * 32, datetime(2024, 1, 2, tzinfo=UTC), article_id=6),
        article("4" * 32, datetime(2024, 1, 1, tzinfo=UTC), article_id=5),
    ]
    page2 = [
        article(code, when, article_id=4),
        article("5" * 32, datetime(2025, 6, 1, tzinfo=UTC), article_id=3),
    ]

    def fetch(url):
        page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
        if page == 4:
            raise http_400(url)
        if page == 3:
            return payload(48, page3, 6)
        if page == 2:
            return payload(48, page2, 6)
        raise AssertionError(page)

    custom = anchor(code, when)
    report, path = review_anchor_start(custom, tmp_path, fetch=fetch, page_size=2)

    # Loader binds to the repository-reviewed anchor registry, so temporarily use its exact identity.
    from pvb24.data import announcement_anchor as module

    original = module.REVIEWED_ANCHORS[48]
    module.REVIEWED_ANCHORS[48] = custom
    try:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        checked = load_anchor_review(
            tmp_path,
            path.relative_to(tmp_path),
            expected_report_sha256=sha,
        )
        assert checked["safe_start_page"] == report["safe_start_page"]
        source = tmp_path / "objects" / checked["pages"][0]["object"]
        source.write_bytes(b"corrupt")
        with pytest.raises(ValueError, match="source page changed"):
            load_anchor_review(
                tmp_path,
                path.relative_to(tmp_path),
                expected_report_sha256=sha,
            )
    finally:
        module.REVIEWED_ANCHORS[48] = original


def test_anchor_review_loader_rejects_wrong_report_pin(tmp_path):
    reviewed = REVIEWED_ANCHORS[48]

    def fetch(url):
        page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
        rows = [
            article(
                reviewed.code,
                reviewed.released_at,
                article_id=page,
            )
        ]
        return payload(48, rows, page)

    report, path = review_anchor_start(
        CatalogAnchor(
            reviewed.catalog_id,
            reviewed.code,
            reviewed.released_at,
            reviewed.source_url,
            1,
            reviewed.hint_source_url,
            reviewed.hint_ui_pages,
        ),
        tmp_path,
        fetch=fetch,
        page_size=1,
    )
    assert report["safe_start_page"] == 1
    with pytest.raises(ValueError, match="report changed"):
        load_anchor_review(
            tmp_path,
            path.relative_to(tmp_path),
            expected_report_sha256="0" * 64,
        )
