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
    _strict_json,
    catalog_time,
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
        "cd4d635399374a68ace90874ce8b9eb2",
        datetime(2021, 3, 29, 6, 54, 2, 522000, tzinfo=UTC),
        "https://www.binance.com/en/support/announcement/detail/cd4d635399374a68ace90874ce8b9eb2",
        114,
        "https://www.binance.com/en/support/announcement/list/48",
        227,
    ),
    161: CatalogAnchor(
        161,
        "85c046a0853b43c2b791ffc3343ed7f0",
        datetime(2025, 1, 15, 7, 0, 13, 729000, tzinfo=UTC),
        "https://www.binance.com/en/support/announcement/detail/85c046a0853b43c2b791ffc3343ed7f0",
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


def load_anchor_review(root: Path, report_path: Path, *, expected_report_sha256: str):
    """Replay and verify a content-addressed reviewed anchor report and its source pages."""

    root, path = Path(root), Path(report_path)
    if (
        not isinstance(expected_report_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_report_sha256)
        or path.as_posix() != "reports/" + expected_report_sha256 + ".json"
    ):
        raise ValueError("Owned pinned announcement anchor report changed/path invalid")
    raw = (root / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_report_sha256:
        raise ValueError("Pinned announcement anchor report changed")

    report = _strict_json(raw)
    if (
        report.get("schema") != "PVB24_ANNOUNCEMENT_CATALOG_ANCHOR_REVIEW_V2"
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or any(
            report.get(key) is not False
            for key in (
                "historical_universe_complete",
                "security_master_complete",
                "lifecycle_complete",
                "performance_run",
                "operational_ready",
                "live_enabled",
            )
        )
    ):
        raise ValueError("Locked preliminary reviewed announcement anchor required")

    catalog_id = report.get("catalog_id")
    if catalog_id not in REVIEWED_ANCHORS:
        raise ValueError("Reviewed announcement anchor catalog required")
    anchor = _validated(REVIEWED_ANCHORS[catalog_id])
    if report.get("catalog_scope") != CATALOGS[catalog_id]:
        raise ValueError("Reviewed announcement anchor catalog scope changed")

    page_size = report.get("page_size")
    if type(page_size) is not int:
        raise ValueError("Exact reviewed announcement page size required")
    page_url(catalog_id, 1, page_size)

    hint = report.get("hint")
    if not isinstance(hint, dict):
        raise ValueError("Reviewed announcement anchor hint required")
    if (
        hint.get("source_url") != anchor.hint_source_url
        or hint.get("ui_pages_observed") != anchor.hint_ui_pages
        or hint.get("cms_start_page_hint") != anchor.start_page_hint
        or type(hint.get("backoff_pages")) is not int
        or type(hint.get("first_valid_page")) is not int
        or hint["backoff_pages"] < 0
        or hint["first_valid_page"] < 1
        or hint["first_valid_page"] != anchor.start_page_hint - hint["backoff_pages"]
    ):
        raise ValueError("Reviewed announcement anchor hint binding changed")

    started = catalog_time(report.get("started_at"))
    completed = catalog_time(report.get("completed_at"))
    if completed < started:
        raise ValueError("Reviewed announcement anchor completion precedes start")

    pages = report.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 500:
        raise ValueError("Nonempty bounded reviewed announcement page chain required")

    expected_total = report.get("catalog_total_observed")
    if type(expected_total) is not int or expected_total < 0:
        raise ValueError("Exact reviewed announcement catalog total required")

    previous_newest = None
    matches = []
    first_valid = hint["first_valid_page"]
    for offset, page in enumerate(pages):
        expected_page = first_valid - offset
        if expected_page < 1:
            raise ValueError("Reviewed announcement page chain escaped positive pages")
        expected_url = page_url(catalog_id, expected_page, page_size)
        if page.get("page_no") != expected_page or page.get("url") != expected_url:
            raise ValueError("Reviewed announcement page sequence/URL changed")

        name = page.get("object")
        if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}\.json", name):
            raise ValueError("Content-addressed reviewed announcement source page required")
        source = (root / "objects" / name).read_bytes()
        if hashlib.sha256(source).hexdigest() + ".json" != name:
            raise ValueError("Reviewed announcement source page changed")

        total, rows = decode_page(source, catalog_id, expected_page, page_size)
        if total != expected_total or len(rows) != _expected_count(total, expected_page, page_size):
            raise ValueError("Reviewed announcement page total/length changed")
        if any(row["released_at"] >= FINAL_START for row in rows):
            raise ValueError("Reviewed announcement replay reached the locked Final Test")
        if not rows:
            raise ValueError("Nonempty reviewed announcement source page required")

        oldest = min(row["released_at"] for row in rows)
        newest = max(row["released_at"] for row in rows)
        if previous_newest is not None and oldest < previous_newest:
            raise ValueError("Reviewed announcement ordering changed across retained pages")
        previous_newest = newest
        if (
            catalog_time(page.get("oldest_at")) != oldest
            or catalog_time(page.get("newest_at")) != newest
        ):
            raise ValueError("Reviewed announcement page time bounds changed")

        for row in rows:
            if row["code"] == anchor.code:
                matches.append((offset, row))

    if len(matches) != 1 or matches[0][0] != len(pages) - 1:
        raise ValueError("Exact reviewed announcement anchor must terminate retained page chain")
    matched = matches[0][1]
    if matched["released_at"] != anchor.released_at:
        raise ValueError("Reviewed announcement anchor release time changed")

    safe_start_page = report.get("safe_start_page")
    if (
        safe_start_page != pages[-1]["page_no"]
        or report.get("safe_start_url") != page_url(catalog_id, safe_start_page, page_size)
    ):
        raise ValueError("Reviewed announcement safe start page changed")

    recorded_anchor = report.get("anchor")
    if (
        not isinstance(recorded_anchor, dict)
        or recorded_anchor.get("code") != anchor.code
        or catalog_time(recorded_anchor.get("released_at")) != anchor.released_at
        or recorded_anchor.get("source_url") != anchor.source_url
        or recorded_anchor.get("catalog_page") != safe_start_page
        or canonical(recorded_anchor.get("row")) != canonical(matched)
    ):
        raise ValueError("Reviewed announcement anchor identity changed")
    return report


def report_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
