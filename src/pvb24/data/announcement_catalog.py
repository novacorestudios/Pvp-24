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

BASE = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
MAX_PAGE = 2 * 1024 * 1024
DEFAULT_PAGE_SIZE = 20
CATALOGS = {
    48: "NEW_CRYPTOCURRENCY_LISTING",
    161: "DELISTING",
}
DECODER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def epoch_ms(value):
    value = value.astimezone(UTC)
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
    return BASE + "?" + urlencode(
        {
            "type": 1,
            "catalogId": catalog_id,
            "pageNo": page_no,
            "pageSize": page_size,
        }
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
    start, end = start.astimezone(UTC), end.astimezone(UTC)
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
            name = object_write(root / "objects", raw, ".json")
            total, rows = decode_page(raw, catalog_id, page_no, page_size)
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise ValueError("Catalog total changed during one acquisition slice")
            report["pages"].append(
                {
                    "page_no": page_no,
                    "url": url,
                    "object": name,
                    "received_at": datetime.now(UTC),
                }
            )
            if not rows:
                report["status"] = "ACQUIRED"
                break
            for row in rows:
                released = row["released_at"]
                if released >= end:
                    raise ValueError("Fetched catalog page crosses the locked/upper boundary")
                prior = selected.get(row["code"])
                if prior is not None and canonical(prior) != canonical(row):
                    raise ValueError("Announcement catalog revision changed across pages")
                selected[row["code"]] = row
            report["articles"] = [
                selected[key]
                for key in sorted(
                    selected,
                    key=lambda code: (
                        selected[code]["released_at"],
                        code,
                    ),
                    reverse=True,
                )
            ]
            if min(row["released_at"] for row in rows) < start:
                report["status"] = "ACQUIRED"
                break
            if len(rows) < page_size:
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
    root = Path(root)
    path = Path(report_path)
    if path.is_absolute() or len(path.parts) != 2 or path.parts[0] != "reports":
        raise ValueError("Owned announcement catalog report path required")
    raw = (root / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_report_sha256:
        raise ValueError("Pinned announcement catalog report changed")
    report = _strict_json(raw)
    if (
        report.get("schema") != "PVB24_ANNOUNCEMENT_CATALOG_SLICE_V1"
        or report.get("status") != "ACQUIRED"
        or report.get("final_test_access") != "LOCKED"
        or report.get("decoder_sha256") != DECODER_SHA256
    ):
        raise ValueError("Acquired locked announcement catalog slice required")
    if digest(report.get("in_window_articles")) != report.get("article_hash"):
        raise ValueError("Announcement catalog article selection changed")
    for page in report.get("pages", []):
        name = page.get("object")
        if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}\.json", name):
            raise ValueError("Content-addressed catalog source page required")
        source = (root / "objects" / name).read_bytes()
        if hashlib.sha256(source).hexdigest() + ".json" != name:
            raise ValueError("Announcement catalog source page changed")
        total, _ = decode_page(
            source,
            report["catalog_id"],
            page["page_no"],
            report["page_size"],
        )
        if total != report["catalog_total_observed"]:
            raise ValueError("Retained catalog page total differs from report")
    return report
