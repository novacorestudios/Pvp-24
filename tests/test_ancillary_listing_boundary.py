import csv
import hashlib
import io
import json
import urllib.error
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from pvb24.data.ancillary_listing_boundary import (
    compile_ancillary_listing_boundary_evidence,
)
from pvb24.data.archive import FUNDING_HEADER, KLINE_HEADER, ArchiveRequest
from pvb24.ids import digest


def millis(value):
    return int(value.timestamp() * 1000)


def kline_archive(request, times):
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(KLINE_HEADER)
    for value in times:
        start = millis(value)
        writer.writerow(
            [
                str(start),
                "1",
                "1",
                "1",
                "1",
                "0",
                str(start + 59999),
                "0",
                "0",
                "0",
                "0",
                "0",
            ]
        )
    return zipped(request, text.getvalue())


def funding_archive(request, times):
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(FUNDING_HEADER)
    for value in times:
        writer.writerow([str(millis(value)), "8", "0.0001"])
    return zipped(request, text.getvalue())


def zipped(request, text):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(request.filename[:-4] + ".csv", text)
    raw = data.getvalue()
    checksum = (hashlib.sha256(raw).hexdigest() + "  " + request.filename + "\n").encode()
    return raw, checksum


def write_v8(tmp_path):
    unresolved = [
        {
            "symbol": symbol,
            "event_at": event,
            "available_at": "2020-12-01T00:00:00.000000Z",
            "source": f"https://example.test/{symbol}",
            "revision_id": symbol[0].lower() * 64,
            "article_code": symbol.lower(),
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        }
        for symbol, event in (
            ("AAAUSDT", "2020-12-22T07:00:00.000000Z"),
            ("BBBUSDT", "2020-12-23T07:00:00.000000Z"),
            ("CCCUSDT", "2020-12-24T07:00:00.000000Z"),
        )
    ]
    report = {
        "schema": "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V8",
        "unresolved_listing_count": len(unresolved),
        "unresolved_listings": unresolved,
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
    path = Path(tmp_path) / "v8.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def test_ancillary_sources_corroborate_without_claiming_first_trade(tmp_path):
    v8, v8_sha = write_v8(tmp_path)
    mark_a = ArchiveRequest("AAAUSDT", "markPriceKlines", "2020-12", "1m")
    fund_b = ArchiveRequest("BBBUSDT", "fundingRate", "2020-12")
    sources = {
        mark_a.url: kline_archive(
            mark_a,
            [
                datetime(2020, 12, 22, 6, 59, tzinfo=UTC),
                datetime(2020, 12, 22, 7, 1, tzinfo=UTC),
            ],
        ),
        fund_b.url: funding_archive(
            fund_b,
            [datetime(2020, 12, 23, 8, tzinfo=UTC)],
        ),
    }

    def fetch(url, **kwargs):
        for base, (raw, checksum) in sources.items():
            if url == base:
                return raw
            if url == base + ".CHECKSUM":
                return checksum
        raise urllib.error.HTTPError(url, 404, "fixture", None, None)

    report = compile_ancillary_listing_boundary_evidence(
        v8,
        v8_sha,
        tmp_path / "ancillary",
        fetch=fetch,
    )

    assert report["source_failure_count"] == 0
    assert report["status_counts"] == {
        "ANNOUNCED_EXACT_ANCILLARY_POST_LAUNCH_CORROBORATED": 2,
        "UNKNOWN": 1,
    }
    by_symbol = {row["symbol"]: row for row in report["results"]}
    assert by_symbol["AAAUSDT"]["supporting_source_kinds"] == ["markPriceKlines"]
    assert by_symbol["AAAUSDT"]["ancillary_sources"][0]["pre_event_row_count"] == 1
    assert by_symbol["AAAUSDT"]["ancillary_proves_first_executable_trade"] is False
    assert by_symbol["BBBUSDT"]["supporting_source_kinds"] == ["fundingRate"]
    assert by_symbol["CCCUSDT"]["status"] == "UNKNOWN"
    assert report["pre_event_ancillary_used_as_inactivity_proof"] is False


def test_ancillary_invalid_checksum_is_explicit_source_failure(tmp_path):
    v8, v8_sha = write_v8(tmp_path)
    request = ArchiveRequest("AAAUSDT", "markPriceKlines", "2020-12", "1m")
    raw, _ = kline_archive(
        request,
        [datetime(2020, 12, 22, 7, 1, tzinfo=UTC)],
    )
    bad = ("0" * 64 + "  " + request.filename + "\n").encode()

    def fetch(url, **kwargs):
        if url == request.url:
            return raw
        if url == request.url + ".CHECKSUM":
            return bad
        raise urllib.error.HTTPError(url, 404, "fixture", None, None)

    report = compile_ancillary_listing_boundary_evidence(
        v8,
        v8_sha,
        tmp_path / "ancillary",
        fetch=fetch,
    )
    assert report["source_failure_count"] == 1
    aaa = next(row for row in report["results"] if row["symbol"] == "AAAUSDT")
    assert aaa["status"] == "SOURCE_FAILURE"
