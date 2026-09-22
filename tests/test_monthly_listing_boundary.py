import csv
import hashlib
import io
import json
import urllib.error
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from pvb24.data.archive import KLINE_HEADER, ArchiveRequest
from pvb24.data.monthly_listing_boundary import (
    compile_monthly_listing_boundary_evidence,
)
from pvb24.ids import digest


def millis(value):
    return int(value.timestamp() * 1000)


def bar(value):
    start = millis(value)
    return [
        str(start),
        "1",
        "1",
        "1",
        "1",
        "10",
        str(start + 59999),
        "100",
        "1",
        "5",
        "50",
        "0",
    ]


def archive(request, rows):
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(KLINE_HEADER)
    writer.writerows(rows)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr(request.filename[:-4] + ".csv", text.getvalue())
    raw = data.getvalue()
    checksum = (
        hashlib.sha256(raw).hexdigest() + "  " + request.filename + "\n"
    ).encode()
    return raw, checksum


def write_v7(tmp_path):
    rows = [
        {
            "symbol": symbol,
            "event_at": event,
            "available_at": "2020-12-01T00:00:00.000000Z",
            "source": f"https://example.test/{symbol}",
            "revision_id": symbol[0].lower() * 64,
            "article_code": symbol.lower() + event[8:10],
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        }
        for symbol, event in (
            ("AAAUSDT", "2020-12-22T07:00:00.000000Z"),
            ("AAAUSDT", "2020-12-28T07:00:00.000000Z"),
            ("BBBUSDT", "2020-12-29T07:00:00.000000Z"),
            ("CCCUSDT", "2020-12-30T07:00:00.000000Z"),
        )
    ]
    report = {
        "schema": "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V7",
        "unresolved_listing_count": len(rows),
        "unresolved_listings": rows,
        "quality": "PRELIMINARY",
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "complete_attestation_emitted": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    report["audit_hash"] = digest(report)
    raw = (json.dumps(report, indent=2) + "\n").encode()
    path = Path(tmp_path) / "v7.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def test_monthly_fallback_partitions_exact_contradicted_post_and_unknown(tmp_path):
    v7, v7_sha = write_v7(tmp_path)
    requests = {
        symbol: ArchiveRequest(symbol, "klines", "2020-12", "1m")
        for symbol in ("AAAUSDT", "BBBUSDT")
    }
    sources = {
        requests["AAAUSDT"].url: archive(
            requests["AAAUSDT"],
            [bar(datetime(2020, 12, 22, 7, tzinfo=UTC))],
        ),
        requests["BBBUSDT"].url: archive(
            requests["BBBUSDT"],
            [bar(datetime(2020, 12, 29, 7, 5, tzinfo=UTC))],
        ),
    }

    def fetch(url, **kwargs):
        for base, (raw, checksum) in sources.items():
            if url == base:
                return raw
            if url == base + ".CHECKSUM":
                return checksum
        raise urllib.error.HTTPError(url, 404, "fixture", None, None)

    report = compile_monthly_listing_boundary_evidence(
        v7,
        v7_sha,
        tmp_path / "monthly",
        fetch=fetch,
    )

    assert report["monthly_source_count"] == 3
    assert report["source_failure_count"] == 0
    assert report["status_counts"] == {
        "ANNOUNCED_EXACT_POST_LAUNCH_MONTHLY_ACTIVITY_CORROBORATED": 1,
        "CONSISTENT_FIRST_MONTHLY_ACTIVITY_AT_ANNOUNCED_LAUNCH": 1,
        "CONTRADICTED_BY_PRE_EVENT_MONTHLY_ACTIVITY": 1,
        "UNKNOWN": 1,
    }
    by_identity = {
        (row["symbol"], row["event_at"]): row for row in report["results"]
    }
    assert by_identity[
        ("AAAUSDT", "2020-12-22T07:00:00.000000Z")
    ]["status"] == "CONSISTENT_FIRST_MONTHLY_ACTIVITY_AT_ANNOUNCED_LAUNCH"
    assert by_identity[
        ("AAAUSDT", "2020-12-28T07:00:00.000000Z")
    ]["status"] == "CONTRADICTED_BY_PRE_EVENT_MONTHLY_ACTIVITY"
    assert by_identity[
        ("BBBUSDT", "2020-12-29T07:00:00.000000Z")
    ]["archive_proves_exact_launch"] is False
    assert by_identity[
        ("CCCUSDT", "2020-12-30T07:00:00.000000Z")
    ]["status"] == "UNKNOWN"
    assert report["historical_universe_complete"] is False


def test_monthly_checksum_failure_is_explicit_source_failure(tmp_path):
    v7, v7_sha = write_v7(tmp_path)
    request = ArchiveRequest("AAAUSDT", "klines", "2020-12", "1m")
    raw, checksum = archive(
        request,
        [bar(datetime(2020, 12, 22, 7, tzinfo=UTC))],
    )
    bad_checksum = ("0" * 64 + "  " + request.filename + "\n").encode()

    def fetch(url, **kwargs):
        if url == request.url:
            return raw
        if url == request.url + ".CHECKSUM":
            return bad_checksum
        raise urllib.error.HTTPError(url, 404, "fixture", None, None)

    report = compile_monthly_listing_boundary_evidence(
        v7,
        v7_sha,
        tmp_path / "monthly",
        fetch=fetch,
    )
    assert report["source_failure_count"] == 1
    assert report["source_failures"][0]["status"] == "INVALID_OR_FAILED"
