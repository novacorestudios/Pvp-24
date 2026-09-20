from dataclasses import replace
from datetime import timedelta

import pytest
from test_archive_acquisition import START, archive, bar
from test_data import NOW, candle

from pvb24.data.acquisition import acquire
from pvb24.data.archive import ArchiveRequest
from pvb24.data.dataset import ArchiveDataset, daily_last, dataset_hash
from pvb24.ids import canonical, digest
from pvb24.types import Quality


def fixture_dataset(tmp_path):
    entries = []
    for kind in ("klines", "markPriceKlines"):
        req = ArchiveRequest("BTCUSDT", kind, "2024-01", "1h")
        rows = [
            bar(START + i * 3600000, **{"6": str(START + (i + 1) * 3600000 - 1)}) for i in range(24)
        ]
        raw, checksum = archive(req, rows)
        result, attempt = acquire(
            req,
            tmp_path,
            fetch=lambda url, checksum=checksum, raw=raw, **kw: (
                checksum if url.endswith("CHECKSUM") else raw
            ),
        )
        entries.append({"attempt": attempt, **result})
    report = {
        "schema": "PVB24_ARCHIVE_ACQUISITION_V1",
        "config_hash": "fixture-config",
        "final_test_access": "LOCKED",
        "archives": entries,
        "requested_archives": 2,
        "acquired_archives": 2,
        "dataset_hash": dataset_hash(entries),
    }
    return save(tmp_path, report), report


def save(tmp_path, report):
    report["report_hash"] = digest({k: v for k, v in report.items() if k != "report_hash"})
    path = tmp_path / "report.json"
    path.write_text(canonical(report))
    return path


def load(tmp_path, path, report):
    return ArchiveDataset(
        tmp_path,
        path,
        expected_dataset_hash=report["dataset_hash"],
        expected_config_hash="fixture-config",
    )


def test_pinned_archive_window_separates_mark_preserves_gaps_and_rechecks_objects(tmp_path):
    path, report = fixture_dataset(tmp_path)
    data = load(tmp_path, path, report)
    args = dict(
        start=NOW, end=NOW + timedelta(days=1), decision=NOW + timedelta(hours=2, seconds=1)
    )
    result = data.candles("BTCUSDT", "1h", **args)
    assert len(result.candles) == 1 and len(result.missing) == 23
    assert result.quality is Quality.PRELIMINARY
    marks = data.candles("BTCUSDT", "1h", price_type="MARK", **args)
    assert marks.candles[0].price_type == "MARK" and marks.candles[0].quote_volume == 0
    assert result.candles[0].price_type == "LAST" and result.candles[0].quote_volume > 0
    entry = report["archives"][0]
    (tmp_path / "objects" / entry["archive_object"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="content hash"):
        data.candles("BTCUSDT", "1h", **args)


def test_manifest_edit_and_explicit_pin_mismatch_are_rejected(tmp_path):
    path, report = fixture_dataset(tmp_path)
    with pytest.raises(ValueError, match="identity"):
        ArchiveDataset(
            tmp_path, path, expected_dataset_hash="foreign", expected_config_hash="fixture-config"
        )
    with pytest.raises(ValueError, match="identity"):
        ArchiveDataset(
            tmp_path,
            path,
            expected_dataset_hash=report["dataset_hash"],
            expected_config_hash="other-config",
        )
    path.write_text(path.read_text().replace("LOCKED", "OPEN"))
    with pytest.raises(ValueError, match="report hash"):
        load(tmp_path, path, report)


@pytest.mark.parametrize("case", ["duplicate", "attempt", "count", "quality", "failed", "final"])
def test_rehashed_manifest_still_requires_real_owned_unique_successful_pre_final_attempts(
    tmp_path, case
):
    path, report = fixture_dataset(tmp_path)
    if case == "duplicate":
        report["archives"].append(report["archives"][0])
    elif case == "attempt":
        report["archives"][0]["attempt"] = "../outside.json"
    elif case == "count":
        report["acquired_archives"] = 1
    elif case == "quality":
        report["archives"][0]["quality"] = "VERIFIED"
    elif case == "failed":
        report["archives"][0]["status"] = "UNAVAILABLE"
    elif case == "final":
        report["archives"][0]["request"]["month"] = "2025-07"
    report["dataset_hash"] = dataset_hash(report["archives"])
    save(tmp_path, report)
    with pytest.raises(ValueError):
        load(tmp_path, path, report)


def test_window_refuses_unselected_months_and_final_without_silent_truncation(tmp_path):
    path, report = fixture_dataset(tmp_path)
    data = load(tmp_path, path, report)
    with pytest.raises(ValueError, match="month not selected"):
        data.candles("BTCUSDT", "1h", start=NOW, end=NOW + timedelta(days=32), decision=NOW)
    with pytest.raises(ValueError, match="LOCKED"):
        data.candles("BTCUSDT", "1h", start=NOW, end=NOW.replace(year=2026), decision=NOW)
    with pytest.raises(ValueError, match="aligned"):
        data.candles(
            "BTCUSDT",
            "1h",
            start=NOW + timedelta(seconds=1),
            end=NOW + timedelta(hours=2),
            decision=NOW,
        )


def hours():
    return [candle(NOW + timedelta(hours=i), volume=str(i + 1)) for i in range(48)]


def aggregate(rows, *, decision=None):
    return daily_last(
        rows,
        "BTCUSDT",
        start=NOW,
        end=NOW + timedelta(days=2),
        decision=decision or NOW + timedelta(days=2, seconds=2),
    )


def test_daily_volume_requires_all_24_last_hours_and_never_uses_mark_or_partial_day():
    rows = hours()
    result = aggregate(rows)
    assert [x.quote_volume for x in result.candles] == [sum(range(1, 25)), sum(range(25, 49))]
    assert not result.missing and result.quality is Quality.PRELIMINARY
    assert result.candles[0].timing.available_at == NOW + timedelta(days=1, seconds=2)
    assert not aggregate(rows, decision=NOW + timedelta(days=1, seconds=1)).candles
    missing = aggregate(rows[:5] + rows[6:])
    assert len(missing.candles) == 1 and missing.missing == ((NOW, NOW + timedelta(days=1)),)
    marked = [replace(row, price_type="MARK") for row in rows]
    assert not aggregate(marked).candles
    assert aggregate(rows + marked) == result


def test_future_append_and_late_revision_do_not_rewrite_prior_daily_values_or_identity():
    rows = hours()
    decision = NOW + timedelta(days=1, seconds=2)
    before = aggregate(rows[:24], decision=decision)
    late = replace(
        rows[0],
        high=rows[0].high * 2,
        timing=replace(
            rows[0].timing, available_at=NOW + timedelta(days=2), revision_id="corrected"
        ),
    )
    assert aggregate(rows + [late], decision=decision) == before
    after = aggregate(rows + [late])
    assert after.candles[0].high == late.high
    assert after.candles[0].timing.available_at == late.timing.available_at
    assert after.candles[0].timing.revision_id != before.candles[0].timing.revision_id
    assert aggregate(list(reversed(rows))) == aggregate(rows)


def test_daily_input_rejects_conflicting_revision_and_off_grid_hour():
    rows = hours()
    with pytest.raises(ValueError, match="Ambiguous"):
        aggregate(rows + [replace(rows[0], high=rows[0].high * 2)])
    bad = candle(NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="UTC-grid"):
        aggregate(rows + [bad])
