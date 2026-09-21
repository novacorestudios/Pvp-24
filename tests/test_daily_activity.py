import hashlib
import io
import urllib.error
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from pvb24.data.daily_activity import (
    DailyKlineRequest,
    acquire_daily_activity,
    decode_daily_activity,
    load_daily_activity,
    reconcile_qualification_activity,
)


def ms(value):
    return int(value.timestamp() * 1000)


def source(request, starts):
    rows = []
    for start in starts:
        rows.append(
            ",".join(
                [
                    str(ms(start)),
                    "1",
                    "1",
                    "1",
                    "1",
                    "1",
                    str(ms(start + timedelta(minutes=1)) - 1),
                    "1",
                    "1",
                    "0.5",
                    "0.5",
                    "0",
                ]
            )
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr(request.filename[:-4] + ".csv", "\n".join(rows) + "\n")
    archive = buffer.getvalue()
    checksum = f"{hashlib.sha256(archive).hexdigest()}  {request.filename}\n".encode()
    return archive, checksum


def fetcher(objects):
    def fetch(url, *, max_bytes):
        value = objects.get(url)
        if value is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        assert len(value) <= max_bytes
        return value

    return fetch


def qualification(kind, event):
    key = "launch_at" if kind == "LISTING" else "scheduled_settlement_at"
    return {
        "schema": "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_V1",
        "final_test_access": "LOCKED",
        "results_hash": "r" * 64,
        "review_requests_hash": "q" * 64,
        "results": [
            {
                "status": "QUALIFIED_PRELIMINARY",
                "code": "a" * 32,
                "source_sha256": "b" * 64,
                "kind": kind,
                "facts": [{"symbol": "TESTUSDT", key: event.isoformat()}],
            }
        ],
    }


def add_source(objects, request, starts):
    archive, checksum = source(request, starts)
    objects[request.url] = archive
    objects[request.checksum_url] = checksum



def test_contiguous_minute_rows_are_valid_and_gap_free():
    request = DailyKlineRequest("TESTUSDT", "2024-01-01")
    first = datetime(2024, 1, 1, tzinfo=UTC)
    archive, checksum = source(request, [first, first + timedelta(minutes=1)])
    activity = decode_daily_activity(request, archive, checksum)
    assert activity["rows"] == 2
    assert activity["first_interval_start"] == first.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    assert activity["last_interval_end"] == (first + timedelta(minutes=2)).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    assert activity["internal_gaps"] == []



def test_listing_exact_event_start_is_consistent_but_missing_prior_day_is_unknown(tmp_path):
    event = datetime(2020, 8, 12, 7, tzinfo=UTC)
    request = DailyKlineRequest("TESTUSDT", "2020-08-12")
    objects = {}
    add_source(objects, request, [event, event + timedelta(minutes=1)])

    report, path = reconcile_qualification_activity(
        qualification("LISTING", event), tmp_path, fetch=fetcher(objects)
    )
    row = report["reconciliations"][0]
    assert row["status"] == "CONSISTENT_EVENT_BOUNDARY_ONLY"
    assert row["boundary_day"]["status"] == "UNAVAILABLE"
    assert "BOUNDARY_ARCHIVE_OBJECT_MISSING_IS_UNKNOWN" in row["notes"]
    assert not row["archive_absence_proves_inactivity"]
    assert report["probe_count"] == 2 and not report["source_failures"]
    assert path.exists()


def test_listing_prior_day_activity_is_a_contradiction(tmp_path):
    event = datetime(2020, 8, 12, 7, tzinfo=UTC)
    event_request = DailyKlineRequest("TESTUSDT", "2020-08-12")
    prior_request = DailyKlineRequest("TESTUSDT", "2020-08-11")
    objects = {}
    add_source(objects, event_request, [event])
    add_source(objects, prior_request, [datetime(2020, 8, 11, 23, 59, tzinfo=UTC)])

    report, _ = reconcile_qualification_activity(
        qualification("LISTING", event), tmp_path, fetch=fetcher(objects)
    )
    row = report["reconciliations"][0]
    assert row["status"] == "CONTRADICTED_BY_ARCHIVE_ACTIVITY"
    assert "PRIOR_DAY_ACTIVITY_PRESENT" in row["contradictions"]


def test_delisting_exact_end_is_consistent_but_next_day_absence_is_not_proof(tmp_path):
    event = datetime(2024, 3, 26, 9, tzinfo=UTC)
    request = DailyKlineRequest("TESTUSDT", "2024-03-26")
    objects = {}
    add_source(
        objects,
        request,
        [event - timedelta(minutes=2), event - timedelta(minutes=1)],
    )

    report, _ = reconcile_qualification_activity(
        qualification("DELISTING", event), tmp_path, fetch=fetcher(objects)
    )
    row = report["reconciliations"][0]
    assert row["status"] == "CONSISTENT_EVENT_BOUNDARY_ONLY"
    expected_end = event.isoformat(timespec="microseconds").replace("+00:00", "Z")
    assert row["event_day"]["last_interval_end"] == expected_end
    assert row["boundary_day"]["status"] == "UNAVAILABLE"
    assert not report["historical_lifecycle_verified"]


def test_delisting_next_day_activity_is_a_contradiction(tmp_path):
    event = datetime(2024, 3, 26, 9, tzinfo=UTC)
    event_request = DailyKlineRequest("TESTUSDT", "2024-03-26")
    next_request = DailyKlineRequest("TESTUSDT", "2024-03-27")
    objects = {}
    add_source(objects, event_request, [event - timedelta(minutes=1)])
    add_source(objects, next_request, [datetime(2024, 3, 27, tzinfo=UTC)])

    report, _ = reconcile_qualification_activity(
        qualification("DELISTING", event), tmp_path, fetch=fetcher(objects)
    )
    row = report["reconciliations"][0]
    assert row["status"] == "CONTRADICTED_BY_ARCHIVE_ACTIVITY"
    assert "NEXT_DAY_ACTIVITY_PRESENT" in row["contradictions"]


def test_daily_activity_checksum_tamper_fails_closed_and_cannot_be_loaded(tmp_path):
    request = DailyKlineRequest("TESTUSDT", "2024-01-01")
    archive, checksum = source(request, [datetime(2024, 1, 1, tzinfo=UTC)])
    first = b"0" if checksum[:1] != b"0" else b"1"
    objects = {request.url: archive, request.checksum_url: first + checksum[1:]}
    result, attempt = acquire_daily_activity(request, tmp_path, fetch=fetcher(objects))
    assert result["status"] == "INVALID_OR_FAILED"
    with pytest.raises(ValueError, match="validated acquired"):
        load_daily_activity(tmp_path, attempt)


def test_daily_request_rejects_final_or_non_usdt_without_network():
    with pytest.raises(ValueError, match="pre-Final"):
        DailyKlineRequest("BTCUSDT", "2025-07-01")
    with pytest.raises(ValueError, match="USD-M USDT"):
        DailyKlineRequest("BTCUSD", "2024-01-01")
