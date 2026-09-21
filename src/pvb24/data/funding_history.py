"""Bounded public funding history and exact-time archive comparison, no fills."""

import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from pvb24.data.acquisition import NoRedirect, object_write
from pvb24.data.archive import EPOCH, ArchiveRequest, milliseconds
from pvb24.decimal_math import D, require_decimal
from pvb24.ids import canonical, digest

BASE = "https://fapi.binance.com/fapi/v1/fundingRate"
MAX_PAGE = 2 * 1024 * 1024
DECODER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def epoch_ms(time):
    delta = time - EPOCH
    if delta.microseconds % 1000:
        raise ValueError("Exact millisecond boundary required")
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


def request_url(request, cursor=None, limit=1000):
    request.__post_init__()
    if request.kind != "fundingRate":
        raise ValueError("Explicit monthly funding request required")
    start, end = epoch_ms(request.start), epoch_ms(request.end) - 1
    if cursor is None:
        cursor = start
    if type(cursor) is not int or not start <= cursor <= end:
        raise ValueError("Funding cursor outside the pre-Final month")
    if type(limit) is not int or not 2 <= limit <= 1000:
        raise ValueError("Bounded funding page limit 2..1000 required")
    return (
        BASE
        + "?"
        + urlencode({"symbol": request.symbol, "startTime": cursor, "endTime": end, "limit": limit})
    )


def public_history(url):
    if not url.startswith(BASE + "?"):
        raise ValueError("Official public funding-history endpoint required")
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=30) as response:
        raw = response.read(MAX_PAGE + 1)
    if len(raw) > MAX_PAGE:
        raise ValueError("Funding history page exceeds resource limit")
    return raw


def decode_page(request, raw, cursor, limit):
    request_url(request, cursor, limit)
    if len(raw) > MAX_PAGE:
        raise ValueError("Funding history page exceeds resource limit")

    def reject_float(value):
        raise ValueError("Financial source fields must use exact decimal text")

    source = json.loads(raw, parse_float=reject_float, parse_constant=reject_float)
    if not isinstance(source, list) or len(source) > limit:
        raise ValueError("Bounded funding-history array required")
    rows, seen, previous = [], set(), None
    for item in source:
        if not isinstance(item, dict) or item.get("symbol") != request.symbol:
            raise ValueError("Funding history symbol differs from requested contract")
        stamp = item.get("fundingTime")
        if type(stamp) is not int or not cursor <= stamp < epoch_ms(request.end):
            raise ValueError("Funding timestamp outside the explicit requested interval")
        if previous is not None and stamp < previous:
            raise ValueError("Funding history is not ascending")
        previous = stamp
        rate = item.get("fundingRate")
        mark = item.get("markPrice")
        rate_type = item.get("rateType", "UNKNOWN")
        if not isinstance(rate, str) or rate_type not in ("Regular", "Special", "UNKNOWN"):
            raise ValueError("Explicit funding-rate text and supported source rate type required")
        rate = D(rate)
        if mark not in (None, ""):
            if not isinstance(mark, str):
                raise ValueError("Settlement Mark must be exact decimal text")
            mark = D(mark)
            require_decimal(mark, positive=True)
        else:
            mark = None
        key = (stamp, rate_type)
        if key in seen:
            raise ValueError("Duplicate funding time/type in one source page")
        seen.add(key)
        rows.append(
            {
                "symbol": request.symbol,
                "funding_time": milliseconds(str(stamp)),
                "rate": rate,
                "mark_price": mark,
                "rate_type": rate_type,
                "available_at": milliseconds(str(stamp)) + timedelta(seconds=2),
            }
        )
    return rows


def acquire_history(
    request: ArchiveRequest, output, *, fetch=public_history, limit=1000, max_pages=20
):
    request_url(request, limit=limit)  # Final/month guard before any network or write
    if type(max_pages) is not int or not 1 <= max_pages <= 100:
        raise ValueError("Explicit bounded funding page budget required")
    root = Path(output)
    report = {
        "schema": "PVB24_FUNDING_HISTORY_ACQUISITION_V1",
        "symbol": request.symbol,
        "month": request.month,
        "started_at": datetime.now(UTC),
        "status": "INCOMPLETE",
        "quality": "PRELIMINARY",
        "decoder_sha256": DECODER_SHA256,
        "final_test_access": "LOCKED",
        "pages": [],
        "rows": [],
        "historical_publication_times_verified": False,
        "funding_schedule_complete": False,
        "position_eligibility_verified": False,
        "timing_policy": "FUNDING_TIME_PLUS_2S_MODELLED",
    }
    cursor = epoch_ms(request.start)
    selected = {}
    try:
        for _ in range(max_pages):
            url = request_url(request, cursor, limit)
            raw = fetch(url)
            if len(raw) > MAX_PAGE:
                raise ValueError("Funding history page exceeds resource limit")
            name = object_write(root / "objects", raw, ".json")
            report["pages"].append({"url": url, "object": name, "received_at": datetime.now(UTC)})
            rows = decode_page(request, raw, cursor, limit)
            for row in rows:
                key = (row["funding_time"], row["rate_type"])
                prior = selected.get(key)
                if prior is not None and canonical(prior["record"]) != canonical(row):
                    raise ValueError("Funding revision changed across overlapping pages")
                if prior is None:
                    selected[key] = {"record": row, "source": url, "revision_id": name[:-5]}
            report["rows"] = [selected[k] for k in sorted(selected)]
            if len(rows) < limit:
                report["status"] = "ACQUIRED"
                break
            last = epoch_ms(rows[-1]["funding_time"])
            if last <= cursor:
                raise ValueError("Funding pagination cannot progress through a same-time boundary")
            # Inclusive overlap retains all rate types at the page boundary.
            # Advancing by one millisecond would silently skip a second type.
            cursor = last
        else:
            raise ValueError("Funding page budget exhausted before completion")
    except (OSError, ValueError, ArithmeticError, urllib.error.URLError) as exc:
        report.update(error_type=type(exc).__name__, error=str(exc))
    report["completed_at"] = datetime.now(UTC)
    report["settlement_mark_complete"] = (
        report["status"] == "ACQUIRED"
        and bool(report["rows"])
        and all(r["record"]["mark_price"] is not None for r in report["rows"])
    )
    report["regular_type_complete"] = (
        report["status"] == "ACQUIRED"
        and bool(report["rows"])
        and all(r["record"]["rate_type"] == "Regular" for r in report["rows"])
    )
    report["data_hash"] = digest(report["rows"])
    name = object_write(root / "reports", canonical(report).encode(), ".json")
    return json.loads(canonical(report)), root / "reports" / name


def compare_archive(archive_rows, history_report):
    if history_report["status"] != "ACQUIRED":
        raise ValueError("Incomplete funding source cannot establish a comparison")
    if digest(history_report["rows"]) != history_report["data_hash"]:
        raise ValueError("Funding source records changed")
    archive = {}
    for row in archive_rows:
        key = (row.symbol, row.calculated_at)
        if key in archive:
            raise ValueError("Duplicate archive funding identity")
        archive[key] = row.rate
    history = {}
    unsupported = []
    for entry in history_report["rows"]:
        row = entry["record"]
        if row["rate_type"] != "Regular":
            unsupported.append(row)
            continue
        key = (row["symbol"], datetime.fromisoformat(row["funding_time"]))
        if key in history:
            raise ValueError("Duplicate regular funding identity")
        history[key] = row
    common = set(archive) & set(history)
    mismatch = [key for key in sorted(common) if archive[key] != D(history[key]["rate"])]

    def identity(keys):
        return [{"symbol": s, "time": t} for s, t in sorted(keys)]

    return {
        "archive_rows": len(archive),
        "regular_history_rows": len(history),
        "matched_time_and_rate": len(common) - len(mismatch),
        "rate_mismatches": identity(mismatch),
        "archive_only": identity(set(archive) - set(history)),
        "history_only": identity(set(history) - set(archive)),
        "unsupported_rate_rows": unsupported,
        "timestamp_rounding_applied": False,
        "funding_schedule_complete": False,
        "historical_publication_times_verified": False,
    }
