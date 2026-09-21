"""Fail-closed review of pre-Final Binance announcement catalog start pages."""

import hashlib
import json
import re
import urllib.error
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


@dataclass(frozen=True)
class CatalogAnchor:
    catalog_id: int
    code: str
    released_at: datetime
    source_url: str
    start_page_hint: int
    hint_source_url: str
    hint_ui_pages: int


REVIEWED_ANCHORS = {
    48: CatalogAnchor(
        48,
        "fb8600ebb2ae4e80a0db1945e683993c",
        datetime(2025, 6, 30, 7, 0, tzinfo=UTC),
        "https://www.binance.com/en/support/announcement/detail/fb8600ebb2ae4e80a0db1945e683993c",
        114,
        "https://www.binance.com/en/support/announcement/list/48",
        227,
    ),
    161: CatalogAnchor(
        161,
        "173b2a63c03141009029407ecfebd14a",
        datetime(2025, 6, 26, 7, 0, tzinfo=UTC),
        "https://www.binance.com/en/support/announcement/detail/173b2a63c03141009029407ecfebd14a",
        22,
        "https://www.binance.com/en/support/announcement/list/161",
        44,
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
    expected_list = f"https://www.binance.com/en/support/announcement/list/{anchor.catalog_id}"
    if anchor.hint_source_url != expected_list:
        raise ValueError("Start-page hint must cite the exact official Binance catalog URL")
    if (
        type(anchor.hint_ui_pages) is not int
        or anchor.hint_ui_pages < 1
        or type(anchor.start_page_hint) is not int
        or anchor.start_page_hint < 1
    ):
        raise ValueError("Positive reviewed catalog page hints required")
    return anchor


def _expected_count(total: int, page_no: int, page_size: int) -> int:
    return max(0, min(page_size, total - (page_no - 1) * page_size))


def _page(fetch, anchor, page_no, page_size):
    url = page_url(anchor.catalog_id, page_no, page_size)
    raw = fetch(url)
    total, rows = decode_page(raw, anchor.catalog_id, page_no, page_size)
    return url, raw, total, rows


def review_anchor_start(
    anchor: CatalogAnchor,
    output: Path,
    *,
    fetch=public_page,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = 200,
    max_hint_backoff: int = 20,
):
    """Walk a reviewed old-page hint toward a pre-Final anchor.

    The human-reviewed hint comes from the official catalog UI pagination and is only a bounded
    search hint, never a completeness claim. Out-of-range HTTP 400 responses may be backed off
    before the first valid source page. Once a valid page is found, every decoded row must remain
    strictly pre-Final. The exact reviewed anchor code/time must be encountered before source time
    advances past it.
    """

    anchor = _validated(anchor)
    page_url(anchor.catalog_id, 1, page_size)
    if type(max_pages) is not int or not 1 <= max_pages <= 500:
        raise ValueError("Explicit bounded catalog review page budget required")
    if type(max_hint_backoff) is not int or not 0 <= max_hint_backoff <= 100:
        raise ValueError("Bounded reviewed-hint backoff required")

    started = datetime.now(UTC)
    root = Path(output)
    pages = []
    expected_total = None
    previous_newest = None
    first_valid_page = None
    page_no = anchor.start_page_hint
    backoff = 0

    while page_no >= 1 and len(pages) < max_pages:
        try:
            url, raw, total, rows = _page(fetch, anchor, page_no, page_size)
        except urllib.error.HTTPError as exc:
            if first_valid_page is not None or exc.code != 400 or backoff >= max_hint_backoff:
                raise
            backoff += 1
            page_no -= 1
            continue

        if not rows:
            if first_valid_page is None and backoff < max_hint_backoff:
                backoff += 1
                page_no -= 1
                continue
            raise ValueError("Nonempty reviewed announcement catalog page required")

        if first_valid_page is None:
            first_valid_page = page_no
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise ValueError("Catalog total changed during reviewed anchor walk")
        if len(rows) != _expected_count(total, page_no, page_size):
            raise ValueError("Catalog page length conflicts with declared total/position")
        if any(row["released_at"] >= FINAL_START for row in rows):
            raise ValueError("Reviewed catalog walk reached the locked Final Test")

        oldest = min(row["released_at"] for row in rows)
        newest = max(row["released_at"] for row in rows)
        if previous_newest is not None and oldest < previous_newest:
            raise ValueError("Catalog ordering changed while walking toward reviewed anchor")
        previous_newest = newest

        source_name = object_write(root / "objects", raw, ".json")
        pages.append(
            {
                "page_no": page_no,
                "url": url,
                "object": source_name,
                "oldest_at": oldest,
                "newest_at": newest,
            }
        )

        matches = [row for row in rows if row["code"] == anchor.code]
        if len(matches) > 1:
            raise ValueError("Reviewed anchor appears more than once on one catalog page")
        if matches:
            if matches[0]["released_at"] != anchor.released_at:
                raise ValueError("Reviewed anchor release time differs from catalog source")
            report = {
                "schema": "PVB24_ANNOUNCEMENT_CATALOG_ANCHOR_REVIEW_V2",
                "catalog_id": anchor.catalog_id,
                "catalog_scope": CATALOGS[anchor.catalog_id],
                "quality": "PRELIMINARY",
                "started_at": started,
                "completed_at": datetime.now(UTC),
                "final_test_access": "LOCKED",
                "hint": {
                    "source_url": anchor.hint_source_url,
                    "ui_pages_observed": anchor.hint_ui_pages,
                    "cms_start_page_hint": anchor.start_page_hint,
                    "backoff_pages": backoff,
                    "first_valid_page": first_valid_page,
                },
                "anchor": {
                    "code": anchor.code,
                    "released_at": anchor.released_at,
                    "source_url": anchor.source_url,
                    "catalog_page": page_no,
                    "row": matches[0],
                },
                "catalog_total_observed": expected_total,
                "page_size": page_size,
                "safe_start_page": page_no,
                "safe_start_url": url,
                "pages": pages,
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

        if newest > anchor.released_at:
            raise ValueError("Reviewed anchor absent before catalog advanced past anchor time")
        page_no -= 1

    raise ValueError("Reviewed anchor not found within bounded pre-Final catalog walk")


def report_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
