import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from pvb24.data.announcement_inventory import (
    _build_candidate_inventory as build_candidate_inventory,
)
from pvb24.ids import canonical, digest

START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2025, 1, 1, tzinfo=UTC)


def report(catalog_id, scope, rows):
    return {
        "schema": "PVB24_ANNOUNCEMENT_CATALOG_SLICE_V1",
        "catalog_id": catalog_id,
        "catalog_scope": scope,
        "status": "ACQUIRED",
        "catalog_slice_complete": True,
        "final_test_access": "LOCKED",
        "window_start": START,
        "window_end": END,
        "in_window_articles": rows,
        "article_hash": digest(rows),
    }


def row(catalog_id, scope, code, title, released):
    return {
        "catalog_id": catalog_id,
        "catalog_scope": scope,
        "article_id": int(code[-4:], 16),
        "code": code,
        "title": title,
        "released_at": released,
    }


def test_inventory_is_discovery_only_and_deterministic():
    listing = row(
        48,
        "NEW_CRYPTOCURRENCY_LISTING",
        "0" * 31 + "1",
        "Binance Futures Will Launch ABCUSDT Perpetual Contract",
        datetime(2024, 2, 1, tzinfo=UTC),
    )
    unrelated = row(
        48,
        "NEW_CRYPTOCURRENCY_LISTING",
        "0" * 31 + "2",
        "Binance Adds ABC to Convert",
        datetime(2024, 2, 2, tzinfo=UTC),
    )
    delisting = row(
        161,
        "DELISTING",
        "0" * 31 + "3",
        "Binance Futures Will Delist ABCUSDT Perpetual Contract",
        datetime(2024, 10, 1, tzinfo=UTC),
    )
    result = build_candidate_inventory(
        report(161, "DELISTING", [delisting]),
        report(48, "NEW_CRYPTOCURRENCY_LISTING", [unrelated, listing]),
    )
    assert result["final_test_access"] == "LOCKED"
    assert result["reviewed_catalog_rows"] == 3
    assert [item["code"] for item in result["candidates"]] == [listing["code"], delisting["code"]]
    assert all(item["qualification"] == "BODY_REVIEW_REQUIRED" for item in result["candidates"])
    assert all(item["lifecycle_fact"] is False for item in result["candidates"])
    assert result["historical_universe_complete"] is False
    assert result["security_master_complete"] is False
    assert result["performance_run"] is False
    assert result["candidate_hash"] == digest(result["candidates"])



def test_inventory_discovers_retained_listing_delay_revision():
    delayed = row(
        48,
        "NEW_CRYPTOCURRENCY_LISTING",
        "0" * 31 + "6",
        "DOT USDT-Margined Perpetual Contract Listing Delayed to 2020/08/22",
        datetime(2024, 2, 1, tzinfo=UTC),
    )
    result = build_candidate_inventory(
        report(48, "NEW_CRYPTOCURRENCY_LISTING", [delayed])
    )
    assert [item["code"] for item in result["candidates"]] == [delayed["code"]]
    assert result["candidates"][0]["qualification"] == "BODY_REVIEW_REQUIRED"
    assert result["candidates"][0]["lifecycle_fact"] is False



def test_inventory_fails_closed_on_unpinned_or_boundary_rows():
    listing = row(
        48,
        "NEW_CRYPTOCURRENCY_LISTING",
        "0" * 31 + "4",
        "Launch XYZUSDT Perpetual Contract",
        datetime(2024, 3, 1, tzinfo=UTC),
    )
    good = report(48, "NEW_CRYPTOCURRENCY_LISTING", [listing])
    bad_hash = deepcopy(good)
    bad_hash["article_hash"] = "0" * 64
    with pytest.raises(ValueError, match="Pinned"):
        build_candidate_inventory(bad_hash)

    boundary = deepcopy(good)
    boundary["in_window_articles"][0]["released_at"] = END
    boundary["article_hash"] = digest(boundary["in_window_articles"])
    with pytest.raises(ValueError, match="escapes"):
        build_candidate_inventory(boundary)


def test_inventory_requires_same_window_and_unique_catalog():
    empty48 = report(48, "NEW_CRYPTOCURRENCY_LISTING", [])
    duplicate = deepcopy(empty48)
    with pytest.raises(ValueError, match="Exactly one"):
        build_candidate_inventory(empty48, duplicate)

    empty161 = report(161, "DELISTING", [])
    empty161["window_start"] = datetime(2024, 2, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="one exact"):
        build_candidate_inventory(empty48, empty161)


def test_inventory_accepts_actual_iso_report_serialization_without_changing_identity():
    source = report(
        48,
        "NEW_CRYPTOCURRENCY_LISTING",
        [
            row(
                48,
                "NEW_CRYPTOCURRENCY_LISTING",
                "0" * 31 + "5",
                "Launch ABCUSDT Perpetual Contract",
                datetime(2024, 3, 1, tzinfo=UTC),
            )
        ],
    )
    assert build_candidate_inventory(source) == build_candidate_inventory(
        json.loads(canonical(source))
    )


@pytest.mark.parametrize("field", ["window_start", "window_end"])
def test_inventory_rejects_naive_times(field):
    source = report(48, "NEW_CRYPTOCURRENCY_LISTING", [])
    source[field] = "2024-01-01T00:00:00"
    with pytest.raises(ValueError, match="Timezone-aware"):
        build_candidate_inventory(source)


def test_inventory_rejects_final_window():
    source = report(48, "NEW_CRYPTOCURRENCY_LISTING", [])
    source["window_end"] = "2025-07-01T00:00:00.001Z"
    with pytest.raises(ValueError, match="pre-Final"):
        build_candidate_inventory(source)
