"""Fail-closed review of pre-Final Binance announcement catalog start positions."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pvb24.data.acquisition import object_write
from pvb24.data.announcement_catalog import (
    CATALOGS,
    DEFAULT_PAGE_SIZE,
    decode_page,
    page_url,
    public_page,
)
from pvb24.data.announcements import ARTICLE_CODE
from pvb24.data.archive import FINAL_START
from pvb24.ids import canonical
from pvb24.types import utc

PROBE_PAGE = 1_000_000


@dataclass(frozen=True)
class CatalogAnchor:
    catalog_id: int
    code: str
    released_at: datetime
    source_url: str


REVIEWED_ANCHORS = {
    48: CatalogAnchor(
        48,
        "fb8600ebb2ae4e80a0db1945e683993c",
        datetime(2025, 6, 30, 7, 0, tzinfo=UTC),
        "https://www.binance.com/en/support/announcement/detail/"
        "fb8600ebb2ae4e80a0db1945e683993c",
    ),
    161: CatalogAnchor(
        161,
        "173b2a63c03141009029407ecfebd14a",
        datetime(2025, 6, 26, 7, 0, tzinfo=UTC),
        "https://www.binance.com/en/support/announcement/detail/"
        "173b2a63c03141009029407ecfebd14a",
    ),
}


def _validated(anchor: CatalogAnchor) -> CatalogAnchor:
    if type(anchor.catalog_id) is not int or anchor.catalog_id not in CATALOGS:
        raise ValueError("Reviewed Binance announcement catalog required")
    if not isinstance(anchor.code, str) or not re.fullmatch(ARTICLE_CODE, anchor.code):
        raise ValueError("Exact reviewed announcement article code required")
    released = utc(anchor.released_at)
    if released != anchor.released_at or released >= FINAL_START:
        raise ValueError("Anchor must be an exact pre-Final UTC observation")
    expected = "https://www.binance.com/en/support/announcement/detail/" + anchor.code
    if anchor.source_url != expected:
        raise ValueError("Anchor must pin its exact official Binance detail URL")
    return anchor


def _expected_count(total: int, page_no: int, page_size: int) -> int:
    return max(0, min(page_size, total - (page_no - 1) * page_size))


def review_anchor_start(
    anchor: CatalogAnchor,
    output: Path,
    *,
    fetch=public_page,
    target_page_size: int = DEFAULT_PAGE_SIZE,
    probe_page: int = PROBE_PAGE,
    max_requests: int = 5000,
):
    """Locate a safe catalog page by walking from the oldest row toward a reviewed anchor.

    The scan uses singleton pages and stops on the reviewed pre-Final anchor. It never
    intentionally traverses newer rows to discover the anchor. The returned target page is the
    first page at target_page_size whose first ordinal is not newer than the anchor ordinal.
    """

    anchor = _validated(anchor)
    page_url(anchor.catalog_id, 1, target_page_size)
    if type(probe_page) is not int or probe_page < 2:
        raise ValueError("Out-of-range catalog probe page required")
    if type(max_requests) is not int or not 1 <= max_requests <= 10000:
        raise ValueError("Explicit bounded anchor-review request budget required")

    started = datetime.now(UTC)
    probe_url = page_url(anchor.catalog_id, probe_page, 1)
    probe_raw = fetch(probe_url)
    total, probe_rows = decode_page(probe_raw, anchor.catalog_id, probe_page, 1)
    if probe_rows or not 0 < total < probe_page:
        raise ValueError("Empty out-of-range catalog probe with exact total required")

    previous_time = None
    anchor_position = None
    anchor_raw = None
    anchor_row = None
    requests = 1
    lower = max(1, total - max_requests + 2)
    for position in range(total, lower - 1, -1):
        url = page_url(anchor.catalog_id, position, 1)
        raw = fetch(url)
        requests += 1
        observed_total, rows = decode_page(raw, anchor.catalog_id, position, 1)
        if observed_total != total or len(rows) != 1:
            raise ValueError("Stable singleton catalog source required during anchor review")
        row = rows[0]
        released = row["released_at"]
        if released >= FINAL_START:
            raise ValueError("Anchor review reached the locked Final Test before the anchor")
        if previous_time is not None and released < previous_time:
            raise ValueError("Catalog ordering changed while approaching reviewed anchor")
        previous_time = released
        if row["code"] == anchor.code:
            if released != anchor.released_at:
                raise ValueError("Reviewed anchor release time differs from catalog source")
            anchor_position = position
            anchor_raw = raw
            anchor_row = row
            break
        if released > anchor.released_at:
            raise ValueError("Reviewed anchor absent before source advanced past anchor time")
    if anchor_position is None or anchor_raw is None or anchor_row is None:
        raise ValueError("Reviewed anchor not found within bounded source review")

    safe_page = 1 + (anchor_position - 1 + target_page_size - 1) // target_page_size
    safe_url = page_url(anchor.catalog_id, safe_page, target_page_size)
    safe_raw = fetch(safe_url)
    requests += 1
    safe_total, safe_rows = decode_page(
        safe_raw, anchor.catalog_id, safe_page, target_page_size
    )
    expected = _expected_count(total, safe_page, target_page_size)
    if safe_total != total or expected <= 0 or len(safe_rows) != expected:
        raise ValueError("Safe start page position conflicts with stable catalog total")
    if any(row["released_at"] > anchor.released_at for row in safe_rows):
        raise ValueError("Safe start page contains a row newer than reviewed anchor")
    if any(row["released_at"] >= FINAL_START for row in safe_rows):
        raise ValueError("Safe start page crosses the locked Final Test")

    root = Path(output)
    probe_object = object_write(root / "objects", probe_raw, ".json")
    anchor_object = object_write(root / "objects", anchor_raw, ".json")
    safe_object = object_write(root / "objects", safe_raw, ".json")
    report = {
        "schema": "PVB24_ANNOUNCEMENT_CATALOG_ANCHOR_REVIEW_V1",
        "catalog_id": anchor.catalog_id,
        "catalog_scope": CATALOGS[anchor.catalog_id],
        "quality": "PRELIMINARY",
        "started_at": started,
        "completed_at": datetime.now(UTC),
        "final_test_access": "LOCKED",
        "anchor": {
            "code": anchor.code,
            "released_at": anchor.released_at,
            "source_url": anchor.source_url,
            "singleton_page": anchor_position,
            "object": anchor_object,
            "row": anchor_row,
        },
        "probe": {
            "page_no": probe_page,
            "url": probe_url,
            "object": probe_object,
            "catalog_total_observed": total,
        },
        "target_page_size": target_page_size,
        "safe_start_page": safe_page,
        "safe_start_url": safe_url,
        "safe_start_object": safe_object,
        "safe_start_rows": safe_rows,
        "safe_start_newest_at": safe_rows[0]["released_at"],
        "safe_start_oldest_at": safe_rows[-1]["released_at"],
        "requests": requests,
        "historical_universe_complete": False,
        "security_master_complete": False,
        "lifecycle_complete": False,
        "performance_run": False,
        "operational_ready": False,
        "live_enabled": False,
    }
    encoded = canonical(report).encode()
    name = object_write(root / "reports", encoded, ".json")
    return json.loads(encoded), root / "reports" / name


def report_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
