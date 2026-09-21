import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_archive_acquisition import START, archive, bar

from pvb24.data.acquisition import acquire
from pvb24.data.archive import ArchiveRequest
from pvb24.data.dataset import dataset_hash
from pvb24.evaluation.market_data import (
    CAPABILITIES,
    SCHEMA,
    complete_attestations,
    load_obligations,
    qualify_market_data,
)
from pvb24.evaluation.readiness import ATTESTATION_SCHEMA
from pvb24.ids import canonical, digest

START_2024 = datetime(2024, 1, 1, tzinfo=UTC)
END_2024 = datetime(2024, 2, 1, tzinfo=UTC)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def universe(tmp_path, **changes):
    payload = {
        "schema": ATTESTATION_SCHEMA,
        "capability": "HISTORICAL_UNIVERSE",
        "complete": True,
        "coverage_start": "2020-01-01T00:00:00.000000Z",
        "coverage_end": "2025-07-01T00:00:00.000000Z",
        "quality": "PRELIMINARY",
        "gaps": [],
        "final_test_access": "LOCKED",
    }
    payload.update(changes)
    path = tmp_path / "universe.json"
    path.write_text(canonical(payload))
    return path, sha(path)


def obligations(tmp_path, universe_hash, rows=None):
    rows = rows or [
        {
            "symbol": "BTCUSDT",
            "start": START_2024.isoformat(),
            "end": END_2024.isoformat(),
        }
    ]
    payload = {
        "schema": SCHEMA,
        "window_start": "2020-01-01T00:00:00.000000Z",
        "window_end": "2025-07-01T00:00:00.000000Z",
        "final_test_access": "LOCKED",
        "universe_attestation_sha256": universe_hash,
        "obligations": rows,
    }
    path = tmp_path / "obligations.json"
    path.write_text(canonical(payload))
    return path, sha(path)


def one_month_rows(interval):
    step = 60_000 if interval == "1m" else 3_600_000
    count = 44_640 if interval == "1m" else 744
    rows = []
    for index in range(count):
        when = START + index * step
        rows.append(bar(when, **{"6": str(when + step - 1)}))
    return rows


def acquisition(tmp_path, *, omit=None, gap=None):
    entries = []
    for capability, (kind, interval) in CAPABILITIES.items():
        if capability == omit:
            continue
        request = ArchiveRequest("BTCUSDT", kind, "2024-01", interval)
        rows = one_month_rows(interval)
        if capability == gap:
            rows = rows[:-1]
        raw, checksum = archive(request, rows)
        result, attempt = acquire(
            request,
            tmp_path,
            fetch=lambda url, raw=raw, checksum=checksum, **kw: (
                checksum if url.endswith("CHECKSUM") else raw
            ),
        )
        entries.append({"attempt": attempt, **result})
    report = {
        "schema": "PVB24_ARCHIVE_ACQUISITION_V1",
        "config_hash": "fixture-config",
        "final_test_access": "LOCKED",
        "archives": entries,
        "requested_archives": len(entries),
        "acquired_archives": len(entries),
        "dataset_hash": dataset_hash(entries),
    }
    report["report_hash"] = digest(report)
    path = tmp_path / "acquisition.json"
    path.write_text(canonical(report))
    return path, report


def qualify(tmp_path, **kwargs):
    upath, uhash = universe(tmp_path)
    opath, ohash = obligations(tmp_path, uhash)
    apath, report = acquisition(tmp_path, **kwargs)
    return qualify_market_data(
        tmp_path,
        apath,
        expected_dataset_hash=report["dataset_hash"],
        expected_config_hash="fixture-config",
        obligations_path=opath,
        obligations_sha256=ohash,
        universe_attestation_path=upath,
        universe_sha256=uhash,
    )


def test_full_required_month_is_verified_from_retained_objects_before_attestation(tmp_path):
    report = qualify(tmp_path)
    assert all(report["capabilities"][name]["complete"] for name in CAPABILITIES)
    attestations = complete_attestations(report)
    assert set(attestations) == set(CAPABILITIES)
    for name, row in attestations.items():
        assert row["schema"] == ATTESTATION_SCHEMA and row["capability"] == name
        assert row["complete"] and row["gaps"] == []
        assert row["final_test_access"] == "LOCKED"


@pytest.mark.parametrize("case", ["missing", "gap"])
def test_missing_or_incomplete_month_never_becomes_complete(case, tmp_path):
    report = qualify(tmp_path, **{case if case == "missing" else "gap": "MARK_1M"})
    row = report["capabilities"]["MARK_1M"]
    assert not row["complete"] and row["gaps"]
    assert "MARK_1M" not in complete_attestations(report)


def test_corrupt_retained_archive_blocks_attestation_even_if_manifest_claims_complete(tmp_path):
    upath, uhash = universe(tmp_path)
    opath, ohash = obligations(tmp_path, uhash)
    apath, report = acquisition(tmp_path)
    mark = next(row for row in report["archives"] if row["request"]["kind"] == "markPriceKlines")
    (tmp_path / "objects" / mark["archive_object"]).write_bytes(b"corrupt")
    result = qualify_market_data(
        tmp_path,
        apath,
        expected_dataset_hash=report["dataset_hash"],
        expected_config_hash="fixture-config",
        obligations_path=opath,
        obligations_sha256=ohash,
        universe_attestation_path=upath,
        universe_sha256=uhash,
    )
    assert not result["capabilities"]["MARK_1M"]["complete"]
    assert result["capabilities"]["MARK_1M"]["invalid_archives"]


@pytest.mark.parametrize(
    "change,match",
    [
        ({"complete": False}, "COMPLETE locked"),
        ({"gaps": ["x"]}, "COMPLETE locked"),
        ({"final_test_access": "OPEN"}, "COMPLETE locked"),
        ({"coverage_end": "2024-12-01T00:00:00Z"}, "ends before"),
    ],
)
def test_obligations_require_real_complete_universe_attestation(tmp_path, change, match):
    upath, uhash = universe(tmp_path, **change)
    opath, ohash = obligations(tmp_path, uhash)
    with pytest.raises(ValueError, match=match):
        load_obligations(
            opath,
            expected_sha256=ohash,
            universe_attestation_path=upath,
            universe_sha256=uhash,
        )


def test_obligation_pin_and_universe_binding_cannot_be_changed(tmp_path):
    upath, uhash = universe(tmp_path)
    opath, ohash = obligations(tmp_path, uhash)
    opath.write_text(opath.read_text() + " ")
    with pytest.raises(ValueError, match="SHA-256 changed"):
        load_obligations(
            opath,
            expected_sha256=ohash,
            universe_attestation_path=upath,
            universe_sha256=uhash,
        )


@pytest.mark.parametrize(
    "row",
    [
        {"symbol": "../BTCUSDT", "start": START_2024.isoformat(), "end": END_2024.isoformat()},
        {"symbol": "BTCUSDT", "start": "2019-12-01T00:00:00Z", "end": END_2024.isoformat()},
        {"symbol": "BTCUSDT", "start": START_2024.isoformat(), "end": "2025-08-01T00:00:00Z"},
        {"symbol": "BTCUSDT", "start": "2024-01-02T00:00:00Z", "end": END_2024.isoformat()},
    ],
)
def test_obligations_fail_closed_on_symbol_holdout_or_non_month_boundaries(tmp_path, row):
    upath, uhash = universe(tmp_path)
    opath, ohash = obligations(tmp_path, uhash, [row])
    with pytest.raises(ValueError):
        load_obligations(
            opath,
            expected_sha256=ohash,
            universe_attestation_path=upath,
            universe_sha256=uhash,
        )


def test_attestation_report_does_not_open_performance_or_operations(tmp_path):
    report = qualify(tmp_path)
    assert report["performance_run"] is False
    assert report["operational_ready"] is False
    assert report["final_test_access"] == "LOCKED"
    assert report["quality"] == "PRELIMINARY"
