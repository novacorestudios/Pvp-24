"""Official Binance announcement catalog discovery for historical source qualification.

This is source discovery only. Catalog membership, titles, or current pagination never become
historical trading eligibility. The adapter retains exact source pages and fails closed on
identity, ordering, pagination, or holdout violations.
"""

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from pvb24.data.acquisition import NoRedirect, object_write
from pvb24.data.announcements import ARTICLE_CODE
from pvb24.data.archive import EPOCH, FINAL_START, milliseconds
from pvb24.ids import canonical, digest
from pvb24.types import utc

BASE = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
MAX_PAGE = 2 * 1024 * 1024
DEFAULT_PAGE_SIZE = 20
CATALOGS = {
    48: "NEW_CRYPTOCURRENCY_LISTING",
    161: "DELISTING",
}
DECODER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def epoch_ms(value):
    value = utc(value)
    delta = value - EPOCH
    if delta.microseconds % 1000:
        raise ValueError("Catalog boundary must be an exact millisecond")
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


def page_url(catalog_id, page_no, page_size=DEFAULT_PAGE_SIZE):
    if type(catalog_id) is not int or catalog_id not in CATALOGS:
        raise ValueError("Reviewed official announcement catalog required")
    if type(page_no) is not int or page_no < 1:
        raise ValueError("Positive catalog page number required")
    if type(page_size) is not int or not 1 <= page_size <= 20:
        raise ValueError("Bounded catalog page size 1..20 required")
    return (
        BASE
        + "?"
        + urlencode(
            {
                "type": 1,
                "catalogId": catalog_id,
                "pageNo": page_no,
                "pageSize": page_size,
            }
        )
    )


def public_page(url):
    if not url.startswith(BASE + "?"):
        raise ValueError("Official Binance announcement catalog endpoint required")
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=30) as response:
        raw = response.read(MAX_PAGE + 1)
    if len(raw) > MAX_PAGE:
        raise ValueError("Announcement catalog page exceeds resource limit")
    return raw


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate announcement catalog JSON key")
            result[key] = value
        return result

    def reject(value):
        raise ValueError("Exact announcement catalog values required")

    return json.loads(raw, object_pairs_hook=pairs, parse_float=reject, parse_constant=reject)


def decode_page(raw, catalog_id, page_no, page_size=DEFAULT_PAGE_SIZE):
    page_url(catalog_id, page_no, page_size)
    if not raw or len(raw) > MAX_PAGE:
        raise ValueError("Nonempty bounded announcement catalog page required")
    payload = _strict_json(raw)
    if (
        not isinstance(payload, dict)
        or payload.get("success") is not True
        or payload.get("code") != "000000"
    ):
        raise ValueError("Successful official announcement catalog response required")
    data = payload.get("data")
    catalogs = data.get("catalogs") if isinstance(data, dict) else None
    if not isinstance(catalogs, list) or len(catalogs) != 1:
        raise ValueError("Exactly one requested announcement catalog required")
    catalog = catalogs[0]
    if not isinstance(catalog, dict) or catalog.get("catalogId") != catalog_id:
        raise ValueError("Announcement catalog identity differs from request")
    total = catalog.get("total")
    articles = catalog.get("articles")
    if type(total) is not int or total < 0 or not isinstance(articles, list):
        raise ValueError("Explicit catalog total and article list required")
    if len(articles) > page_size:
        raise ValueError("Catalog page exceeds requested page size")

    rows = []
    seen = set()
    previous = None
    for item in articles:
        if not isinstance(item, dict):
            raise ValueError("Announcement catalog article object required")
        code = item.get("code")
        title = item.get("title")
        release = item.get("releaseDate")
        article_id = item.get("id")
        article_type = item.get("type")
        if (
            not isinstance(code, str)
            or not re.fullmatch(ARTICLE_CODE, code)
            or not isinstance(title, str)
            or not title.strip()
            or type(release) is not int
            or release < 0
            or type(article_id) is not int
            or article_id < 0
            or type(article_type) is not int
            or article_type != 1
        ):
            raise ValueError("Malformed announcement catalog article identity")
        if code in seen:
            raise ValueError("Duplicate article code within catalog page")
        seen.add(code)
        if previous is not None and release > previous:
            raise ValueError("Announcement catalog page is not newest-first")
        previous = release
        rows.append(
            {
                "catalog_id": catalog_id,
                "catalog_scope": CATALOGS[catalog_id],
                "article_id": article_id,
                "code": code,
                "title": title.strip(),
                "released_at": milliseconds(str(release)),
            }
        )
    return total, tuple(rows)


def catalog_time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return utc(value)


def _accept_rows(selected, rows, start, end, page_size, page_no, total):
    # Validate before retaining any bytes. Never filter out a Final-period row.
    if any(row["released_at"] >= end for row in rows):
        raise ValueError("Fetched catalog page crosses the locked/upper boundary")
    expected_count = max(0, min(page_size, total - (page_no - 1) * page_size))
    if len(rows) != expected_count:
        raise ValueError("Catalog page length conflicts with declared total/position")
    if (
        selected
        and rows
        and rows[0]["released_at"] > min(row["released_at"] for row in selected.values())
    ):
        raise ValueError("Catalog ordering changed across pages")
    for row in rows:
        if row["code"] in selected:
            raise ValueError("Duplicate/revised article across catalog pages")
    selected.update((row["code"], row) for row in rows)
    return not rows or len(rows) < page_size or min(row["released_at"] for row in rows) < start


def _ordered(selected):
    return sorted(
        selected.values(), key=lambda row: (row["released_at"], row["code"]), reverse=True
    )


def acquire_slice(
    catalog_id,
    output,
    *,
    start_page,
    start,
    end=FINAL_START,
    fetch=public_page,
    page_size=DEFAULT_PAGE_SIZE,
    max_pages=100,
):
    """Acquire an explicit reviewed pre-Final catalog slice.

    start_page is intentionally caller supplied. Current catalog pagination can shift and can
    expose holdout rows on newer pages. Every fetched row must be inside the caller's pre-Final
    slice; a mixed/future page is rejected rather than filtered.
    """

    page_url(catalog_id, start_page, page_size)
    start, end = utc(start), utc(end)
    epoch_ms(start)
    epoch_ms(end)
    if not start < end <= FINAL_START:
        raise ValueError("Nonempty pre-Final announcement discovery window required")
    if type(max_pages) is not int or not 1 <= max_pages <= 200:
        raise ValueError("Explicit bounded announcement page budget required")

    root = Path(output)
    report = {
        "schema": "PVB24_ANNOUNCEMENT_CATALOG_SLICE_V1",
        "catalog_id": catalog_id,
        "catalog_scope": CATALOGS[catalog_id],
        "start_page": start_page,
        "page_size": page_size,
        "window_start": start,
        "window_end": end,
        "started_at": datetime.now(UTC),
        "status": "INCOMPLETE",
        "quality": "PRELIMINARY",
        "decoder_sha256": DECODER_SHA256,
        "final_test_access": "LOCKED",
        "pages": [],
        "articles": [],
        "historical_universe_complete": False,
        "security_master_complete": False,
        "lifecycle_complete": False,
        "performance_run": False,
    }
    selected = {}
    expected_total = None
    try:
        for offset in range(max_pages):
            page_no = start_page + offset
            url = page_url(catalog_id, page_no, page_size)
            raw = fetch(url)
            total, rows = decode_page(raw, catalog_id, page_no, page_size)
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise ValueError("Catalog total changed during one acquisition slice")
            terminal = _accept_rows(selected, rows, start, end, page_size, page_no, total)
            name = object_write(root / "objects", raw, ".json")
            report["pages"].append(
                {
                    "page_no": page_no,
                    "url": url,
                    "object": name,
                    "received_at": datetime.now(UTC),
                }
            )
            report["articles"] = _ordered(selected)
            if terminal:
                report["status"] = "ACQUIRED"
                break
        else:
            raise ValueError("Announcement catalog page budget exhausted before lower boundary")
    except (OSError, ValueError, TypeError, urllib.error.URLError) as exc:
        report.update(error_type=type(exc).__name__, error=str(exc))

    report["completed_at"] = datetime.now(UTC)
    report["catalog_total_observed"] = expected_total
    report["in_window_articles"] = [
        row for row in report["articles"] if start <= row["released_at"] < end
    ]
    report["article_hash"] = digest(report["in_window_articles"])
    report["catalog_slice_complete"] = report["status"] == "ACQUIRED"
    encoded = canonical(report).encode()
    name = object_write(root / "reports", encoded, ".json")
    return json.loads(encoded), root / "reports" / name


def load_slice(root, report_path, *, expected_report_sha256):
    """Replay the pinned page chain; a self-consistent report hash is insufficient."""
    root, path = Path(root), Path(report_path)
    if (
        not isinstance(expected_report_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_report_sha256)
        or path.as_posix() != "reports/" + expected_report_sha256 + ".json"
    ):
        raise ValueError("Owned pinned announcement catalog report changed/path invalid")
    raw = (root / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_report_sha256:
        raise ValueError("Pinned announcement catalog report changed")
    report = _strict_json(raw)
    if (
        report.get("schema") != "PVB24_ANNOUNCEMENT_CATALOG_SLICE_V1"
        or report.get("status") != "ACQUIRED"
        or report.get("final_test_access") != "LOCKED"
        or report.get("decoder_sha256") != DECODER_SHA256
        or report.get("catalog_slice_complete") is not True
        or report.get("quality") != "PRELIMINARY"
        or any(
            report.get(k) is not False
            for k in (
                "historical_universe_complete",
                "security_master_complete",
                "lifecycle_complete",
                "performance_run",
            )
        )
    ):
        raise ValueError("Acquired locked preliminary announcement catalog slice required")
    catalog, size, first = (report[k] for k in ("catalog_id", "page_size", "start_page"))
    page_url(catalog, first, size)
    if report.get("catalog_scope") != CATALOGS[catalog]:
        raise ValueError("Catalog source scope changed")
    start, end = (catalog_time(report[k]) for k in ("window_start", "window_end"))
    if not start < end <= FINAL_START:
        raise ValueError("Strict pre-Final catalog window required")
    epoch_ms(start)
    epoch_ms(end)
    begun, completed = (catalog_time(report[k]) for k in ("started_at", "completed_at"))
    pages = report.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 200:
        raise ValueError("Nonempty bounded catalog source page chain required")
    selected, terminal, previous_receipt = {}, False, begun
    for offset, page in enumerate(pages):
        if terminal:
            raise ValueError("Catalog pages continue after terminal source page")
        if page.get("page_no") != first + offset or page.get("url") != page_url(
            catalog, first + offset, size
        ):
            raise ValueError("Catalog page sequence/URL changed")
        received = catalog_time(page["received_at"])
        if not previous_receipt <= received <= completed:
            raise ValueError("Catalog receipt outside ordered acquisition interval")
        previous_receipt = received
        name = page.get("object")
        if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}\.json", name):
            raise ValueError("Content-addressed catalog source page required")
        source = (root / "objects" / name).read_bytes()
        if hashlib.sha256(source).hexdigest() + ".json" != name:
            raise ValueError("Announcement catalog source page changed")
        total, rows = decode_page(source, catalog, page["page_no"], size)
        if (
            type(report.get("catalog_total_observed")) is not int
            or total != report["catalog_total_observed"]
        ):
            raise ValueError("Retained catalog page total differs from report")
        terminal = _accept_rows(selected, rows, start, end, size, page["page_no"], total)
    if not terminal:
        raise ValueError("Catalog source page chain truncated before lower boundary")
    articles = _ordered(selected)
    in_window = [row for row in articles if start <= row["released_at"] < end]
    if (
        canonical(articles) != canonical(report.get("articles"))
        or canonical(in_window) != canonical(report.get("in_window_articles"))
        or digest(in_window) != report.get("article_hash")
    ):
        raise ValueError("Catalog article selection differs from retained source pages")
    return report
