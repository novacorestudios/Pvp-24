import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from pvb24.data.announcement_anchor import CatalogAnchor, review_anchor_start


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


def anchor(code, when):
    return CatalogAnchor(
        48,
        code,
        when,
        "https://www.binance.com/en/support/announcement/detail/" + code,
    )


def test_anchor_review_walks_oldest_to_anchor_and_never_requests_newer_singleton(tmp_path):
    code = "a" * 32
    when = datetime(2025, 6, 30, 7, 0, tzinfo=UTC)
    rows = {
        5: article("5" * 32, datetime(2024, 1, 1, tzinfo=UTC), article_id=5),
        4: article("4" * 32, datetime(2025, 1, 1, tzinfo=UTC), article_id=4),
        3: article(code, when, article_id=3),
        2: article("2" * 32, datetime(2025, 7, 2, tzinfo=UTC), article_id=2),
        1: article("1" * 32, datetime(2025, 8, 1, tzinfo=UTC), article_id=1),
    }
    calls = []

    def fetch(url):
        query = parse_qs(urlsplit(url).query)
        page, size = int(query["pageNo"][0]), int(query["pageSize"][0])
        calls.append((page, size))
        if page == 999:
            return payload(48, [], 5)
        if size == 1:
            return payload(48, [rows[page]], 5)
        assert (page, size) == (2, 2)
        return payload(48, [rows[3], rows[4]], 5)

    report, path = review_anchor_start(
        anchor(code, when),
        tmp_path,
        fetch=fetch,
        target_page_size=2,
        probe_page=999,
        max_requests=10,
    )
    assert report["safe_start_page"] == 2
    assert report["anchor"]["singleton_page"] == 3
    assert (2, 1) not in calls and (1, 1) not in calls
    assert report["final_test_access"] == "LOCKED"
    assert not report["historical_universe_complete"]
    assert path.exists()


def test_alignment_moves_to_next_target_page_when_anchor_is_not_first_row(tmp_path):
    code = "a" * 32
    when = datetime(2025, 6, 1, tzinfo=UTC)
    rows = {
        5: article("5" * 32, datetime(2024, 1, 1, tzinfo=UTC), article_id=5),
        4: article(code, when, article_id=4),
    }

    def fetch(url):
        query = parse_qs(urlsplit(url).query)
        page, size = int(query["pageNo"][0]), int(query["pageSize"][0])
        if page == 999:
            return payload(48, [], 5)
        if size == 1:
            return payload(48, [rows[page]], 5)
        assert (page, size) == (3, 2)
        return payload(48, [rows[5]], 5)

    report, _ = review_anchor_start(
        anchor(code, when),
        tmp_path,
        fetch=fetch,
        target_page_size=2,
        probe_page=999,
    )
    assert report["safe_start_page"] == 3
    assert report["safe_start_rows"][0]["code"] == "5" * 32


def test_anchor_timestamp_or_total_drift_fails_closed(tmp_path):
    code = "a" * 32
    reviewed = datetime(2025, 6, 30, 7, 0, tzinfo=UTC)

    def changed_time(url):
        query = parse_qs(urlsplit(url).query)
        page = int(query["pageNo"][0])
        if page == 999:
            return payload(48, [], 1)
        return payload(
            48,
            [article(code, datetime(2025, 6, 30, 8, 0, tzinfo=UTC), article_id=1)],
            1,
        )

    with pytest.raises(ValueError, match="release time differs"):
        review_anchor_start(anchor(code, reviewed), tmp_path, fetch=changed_time, probe_page=999)

    def changed_total(url):
        query = parse_qs(urlsplit(url).query)
        page = int(query["pageNo"][0])
        if page == 999:
            return payload(48, [], 2)
        return payload(
            48,
            [article(code, reviewed, article_id=1)],
            3,
        )

    with pytest.raises(ValueError, match="Stable singleton"):
        review_anchor_start(anchor(code, reviewed), tmp_path, fetch=changed_total, probe_page=999)


def test_review_rejects_bad_source_pin_before_network(tmp_path):
    calls = []
    bad = CatalogAnchor(
        48,
        "a" * 32,
        datetime(2025, 6, 30, tzinfo=UTC),
        "https://example.com/not-binance",
    )
    with pytest.raises(ValueError, match="exact official Binance detail URL"):
        review_anchor_start(bad, tmp_path, fetch=lambda url: calls.append(url))
    assert not calls


def test_review_fails_if_source_reaches_final_before_anchor(tmp_path):
    code = "a" * 32
    reviewed = datetime(2025, 6, 30, 7, 0, tzinfo=UTC)
    old = article("b" * 32, datetime(2025, 6, 1, tzinfo=UTC), article_id=2)
    final = article("c" * 32, datetime(2025, 7, 1, tzinfo=UTC), article_id=1)

    def fetch(url):
        query = parse_qs(urlsplit(url).query)
        page = int(query["pageNo"][0])
        if page == 999:
            return payload(48, [], 2)
        return payload(48, [old if page == 2 else final], 2)

    with pytest.raises(ValueError, match="locked Final Test"):
        review_anchor_start(anchor(code, reviewed), tmp_path, fetch=fetch, probe_page=999)
