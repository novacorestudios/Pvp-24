"""Revalidate a frozen public funding-history report against every source page."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pvb24.data.archive import ArchiveRequest
from pvb24.data.funding_history import DECODER_SHA256, decode_page, epoch_ms, request_url
from pvb24.ids import canonical, digest
from pvb24.types import utc


def load_history(root, report_name, *, expected_report_hash):
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_report_hash)
        or report_name != expected_report_hash + ".json"
    ):
        raise ValueError("Explicit content-addressed funding report pin required")
    root = Path(root)
    payload = (root / "reports" / report_name).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_report_hash:
        raise ValueError("Funding history report hash changed")
    report = json.loads(payload)
    request = ArchiveRequest(report["symbol"], "fundingRate", report["month"])
    if (
        report["schema"] != "PVB24_FUNDING_HISTORY_ACQUISITION_V1"
        or report["status"] != "ACQUIRED"
        or report["quality"] != "PRELIMINARY"
        or report["decoder_sha256"] != DECODER_SHA256
        or report["final_test_access"] != "LOCKED"
        or report["timing_policy"] != "FUNDING_TIME_PLUS_2S_MODELLED"
    ):
        raise ValueError("Funding source status/schema/decoder/policy not qualified")
    if any(
        report[k] is not False
        for k in (
            "historical_publication_times_verified",
            "funding_schedule_complete",
            "position_eligibility_verified",
        )
    ):
        raise ValueError("Funding source cannot promote historical or settlement qualification")
    if not 1 <= len(report["pages"]) <= 100:
        raise ValueError("Bounded completed funding page chain required")
    started, completed = [
        utc(datetime.fromisoformat(report[k])) for k in ("started_at", "completed_at")
    ]
    cursor, selected, limit = epoch_ms(request.start), {}, None
    for index, page in enumerate(report["pages"]):
        query = parse_qs(urlsplit(page["url"]).query)
        values = query.get("limit", [])
        if len(values) != 1 or not values[0].isdigit():
            raise ValueError("Explicit funding page limit required")
        page_limit = int(values[0])
        limit = page_limit if limit is None else limit
        if page_limit != limit or page["url"] != request_url(request, cursor, limit):
            raise ValueError("Funding page chain cursor/request changed")
        received = utc(datetime.fromisoformat(page["received_at"]))
        if not started <= received <= completed:
            raise ValueError("Funding acquisition receipt outside its attempt")
        name = page["object"]
        if not re.fullmatch(r"[0-9a-f]{64}\.json", name):
            raise ValueError("Owned funding page object required")
        raw = (root / "objects" / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() + ".json" != name:
            raise ValueError("Retained funding page bytes changed")
        rows = decode_page(request, raw, cursor, limit)
        for row in rows:
            key = (row["funding_time"], row["rate_type"])
            previous = selected.get(key)
            if previous is not None and canonical(previous["record"]) != canonical(row):
                raise ValueError("Funding page boundary revision conflict")
            if previous is None:
                selected[key] = {"record": row, "source": page["url"], "revision_id": name[:-5]}
        last_page = index == len(report["pages"]) - 1
        if (len(rows) < limit) != last_page:
            raise ValueError("Funding chain is truncated or continues after completion")
        if not last_page:
            next_cursor = epoch_ms(rows[-1]["funding_time"])
            if next_cursor <= cursor:
                raise ValueError("Funding pagination did not advance")
            cursor = next_cursor
    rows = [selected[key] for key in sorted(selected)]
    if canonical(rows) != canonical(report["rows"]) or digest(rows) != report["data_hash"]:
        raise ValueError("Funding report rows differ from retained pages")
    marks = bool(rows) and all(r["record"]["mark_price"] is not None for r in rows)
    regular = bool(rows) and all(r["record"]["rate_type"] == "Regular" for r in rows)
    if (
        report["settlement_mark_complete"] is not marks
        or report["regular_type_complete"] is not regular
    ):
        raise ValueError("Funding report overstates source field coverage")
    return request, report
