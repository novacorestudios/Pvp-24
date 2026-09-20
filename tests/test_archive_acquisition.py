import csv
import hashlib
import io
import json
import subprocess
import sys
import urllib.error
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest

from pvb24.data.acquisition import acquire, load_acquired
from pvb24.data.archive import FUNDING_HEADER, KLINE_HEADER, ArchiveRequest, coverage, records
from pvb24.decimal_math import D

ROOT = Path(__file__).resolve().parents[1]
START = 1704067200000


def archive(request, rows, *, header=True, member=None):
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    if header:
        writer.writerow(FUNDING_HEADER if request.kind == "fundingRate" else KLINE_HEADER)
    writer.writerows(rows)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member or request.filename[:-4] + ".csv", text.getvalue())
    raw = data.getvalue()
    checksum = (hashlib.sha256(raw).hexdigest() + "  " + request.filename + "\n").encode()
    return raw, checksum


def bar(time=START, **changed):
    row = [
        str(time),
        "100.10",
        "101.20",
        "99.00",
        "100.20",
        "10",
        str(time + 59999),
        "1000",
        "12",
        "4",
        "400",
        "0",
    ]
    for key, value in changed.items():
        row[int(key)] = value
    return row


@pytest.mark.parametrize("header", [True, False])
def test_real_layout_keeps_decimal_ohlc_and_exclusive_close_plus_two_second_availability(header):
    req = ArchiveRequest("BTCUSDT", "klines", "2024-01", "1m")
    raw, check = archive(req, [bar()], header=header)
    candle = list(records(req, raw, check))[0]
    assert candle.close == D("100.20") and candle.quote_volume == D(1000)
    assert candle.timing.interval_start == req.start
    assert candle.timing.interval_end == req.start + timedelta(minutes=1)
    assert candle.timing.available_at == candle.timing.interval_end + timedelta(seconds=2)
    assert candle.timing.received_at is None
    assert candle.timing.revision_id == hashlib.sha256(raw).hexdigest()
    assert candle.price_type == "LAST"


def test_mark_archive_ignores_nontrading_volume_fields_and_never_promotes_to_verified():
    req = ArchiveRequest("BTCUSDT", "markPriceKlines", "2024-01", "1m")
    raw, check = archive(req, [bar(**{"5": "0", "7": "0", "9": "0", "10": "0"})])
    candle = list(records(req, raw, check))[0]
    assert candle.price_type == "MARK" and candle.quote_volume == 0
    report = coverage(req, raw, check)
    assert report["quality"] == "PRELIMINARY" and not report["execution_depth_verified"]
    assert not report["historical_publication_times_verified"]


def test_funding_uses_each_declared_interval_without_assuming_eight_hours_or_coverage():
    req = ArchiveRequest("BTCUSDT", "fundingRate", "2024-01")
    raw, check = archive(req, [[START, "8", "-0.0001"], [START + 4 * 3600000, "4", "0.0002"]])
    first, second = list(records(req, raw, check))
    assert first.calculated_at - first.declared_duration == req.start - timedelta(hours=8)
    assert second.calculated_at - second.declared_duration == first.calculated_at
    assert first.rate == D("-0.0001") and second.available_at == second.calculated_at + timedelta(
        seconds=2
    )
    report = coverage(req, raw, check)
    assert not report["gaps"] and not report["funding_schedule_complete"]
    assert report["last_interval_end"] < req.end


def test_missing_rows_remain_explicit_gaps_and_source_zero_volume_is_retained():
    req = ArchiveRequest("BTCUSDT", "klines", "2024-01", "1m")
    rows = [
        bar(START + 60000),
        bar(START + 180000, **{"5": "0", "7": "0", "8": "0", "9": "0", "10": "0"}),
    ]
    raw, check = archive(req, rows)
    result = coverage(req, raw, check)
    assert result["rows"] == 2 and result["zero_volume_last_bars"] == 1
    assert len(result["gaps"]) == 3 and not result["monthly_bar_grid_complete"]
    assert len(list(records(req, raw, check))) == 2  # no synthetic filling


def test_funding_calc_time_jitter_is_preserved_and_reported_without_silent_rounding():
    req = ArchiveRequest("BTCUSDT", "fundingRate", "2024-01")
    raw, check = archive(
        req,
        [
            [START, "8", "0.0001"],
            [START + 8 * 3600000 + 1, "8", "0.0001"],
            [START + 16 * 3600000, "8", "0.0001"],
        ],
    )
    decoded = list(records(req, raw, check))
    assert decoded[1].calculated_at.microsecond == 1000
    report = coverage(req, raw, check)
    assert [r["difference_microseconds"] for r in report["funding_interval_discontinuities"]] == [
        1000,
        -1000,
    ]
    assert not report["funding_schedule_complete"]


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "backwards",
        "close",
        "off_grid",
        "outside",
        "nan",
        "ohlc",
        "negative_volume",
        "taker",
        "microseconds",
        "changed_header",
    ],
)
def test_invalid_source_rows_are_rejected(case):
    req = ArchiveRequest("BTCUSDT", "klines", "2024-01", "1m")
    cases = {
        "duplicate": [bar(), bar()],
        "backwards": [bar(START + 60000), bar()],
        "close": [bar(**{"6": str(START + 60000)})],
        "off_grid": [bar(START + 1)],
        "outside": [bar(START - 60000)],
        "nan": [bar(**{"4": "NaN"})],
        "ohlc": [bar(**{"2": "90"})],
        "negative_volume": [bar(**{"7": "-1"})],
        "taker": [bar(**{"10": "1001"})],
        "microseconds": [bar(START * 1000)],
        "changed_header": [list(reversed(KLINE_HEADER)), bar()],
    }
    raw, check = archive(req, cases[case])
    with pytest.raises((ValueError, OverflowError)):
        coverage(req, raw, check)


@pytest.mark.parametrize("case", ["checksum", "filename", "member", "invalid_zip"])
def test_integrity_errors_are_audited_and_never_consumable(tmp_path, case):
    req = ArchiveRequest("BTCUSDT", "klines", "2024-01", "1m")
    raw, check = archive(req, [bar()], member="../foreign.csv" if case == "member" else None)
    if case == "checksum":
        raw += b"changed"
    elif case == "filename":
        check = check.replace(req.filename.encode(), b"OTHER.zip")
    elif case == "invalid_zip":
        raw = b"not a ZIP"
        check = (hashlib.sha256(raw).hexdigest() + "  " + req.filename).encode()
    result, attempt = acquire(
        req, tmp_path, fetch=lambda url, **kw: check if url.endswith("CHECKSUM") else raw
    )
    assert result["status"] == "INVALID_OR_FAILED"
    assert (tmp_path / attempt).exists()
    with pytest.raises(ValueError, match="validated acquired"):
        load_acquired(tmp_path, attempt)


def test_download_records_hashes_and_reuse_retains_prior_revisions_and_detects_corrupt_objects(
    tmp_path,
):
    req = ArchiveRequest("BTCUSDT", "klines", "2024-01", "1m")
    raw, check = archive(req, [bar()])
    fetch = lambda url, **kw: check if url.endswith("CHECKSUM") else raw  # noqa: E731
    result, attempt = acquire(req, tmp_path, fetch=fetch)
    assert result["status"] == "ACQUIRED"
    assert load_acquired(tmp_path, attempt) == (req, raw, check)
    again, _ = acquire(req, tmp_path, fetch=fetch)
    assert again["archive_object"] == result["archive_object"]
    old_object = result["archive_object"]
    raw, check = archive(req, [bar(**{"4": "100.30"})])
    new, newer = acquire(req, tmp_path, fetch=fetch)
    assert new["archive_object"] != old_object and (tmp_path / "objects" / old_object).exists()
    assert load_acquired(tmp_path, attempt)[1] != load_acquired(tmp_path, newer)[1]
    (tmp_path / "objects" / new["archive_object"]).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="content hash changed"):
        load_acquired(tmp_path, newer)


def test_missing_archive_and_http_failure_are_separate_from_zero_volume(tmp_path):
    req = ArchiveRequest("BTCUSDT", "klines", "2024-01", "1m")
    for code in (404, 429):

        def missing(url, code=code, **kw):
            raise urllib.error.HTTPError(url, code, "fixture", None, None)

        result, _ = acquire(req, tmp_path, fetch=missing)
        assert result["status"] == ("UNAVAILABLE" if code == 404 else "HTTP_ERROR")
        assert "coverage" not in result


def test_final_lock_and_entire_batch_validation_precede_all_downloads(tmp_path):
    with pytest.raises(ValueError, match="LOCKED"):
        ArchiveRequest("BTCUSDT", "klines", "2025-07", "1m")
    output = tmp_path / "must-not-exist"
    run = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/acquire_binance_archives.py"),
            "--symbol",
            "BTCUSDT",
            "--month",
            "2024-01",
            "--month",
            "2025-07",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0 and "LOCKED" in run.stderr and not output.exists()


def test_request_and_attempt_paths_cannot_escape_owned_archive_directories(tmp_path):
    with pytest.raises(ValueError):
        ArchiveRequest("../BTCUSDT", "klines", "2024-01", "1m")
    with pytest.raises(ValueError):
        load_acquired(tmp_path, "../private.json")
    req = ArchiveRequest("BTCUSDT", "klines", "2024-01", "1m")
    raw, check = archive(req, [bar()])
    _, attempt = acquire(
        req, tmp_path, fetch=lambda url, **kw: check if url.endswith("CHECKSUM") else raw
    )
    path = tmp_path / attempt
    changed = json.loads(path.read_text())
    changed["quality"] = "VERIFIED"
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="attempt content hash"):
        load_acquired(tmp_path, attempt)
