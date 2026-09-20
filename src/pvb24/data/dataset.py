"""Explicit frozen archive selection and causal, gap-visible candle windows."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import localcontext
from pathlib import Path

from pvb24.data.acquisition import load_acquired
from pvb24.data.archive import FINAL_START, ArchiveRequest, records
from pvb24.data.candles import causal_candles
from pvb24.data.schemas import Candle, Timing
from pvb24.decimal_math import CONTEXT, D
from pvb24.ids import canonical, digest
from pvb24.types import Quality, utc


@dataclass(frozen=True)
class CandleWindow:
    candles: tuple[Candle, ...]
    missing: tuple[tuple[datetime, datetime], ...]
    quality: Quality = Quality.PRELIMINARY


def dataset_hash(archives):
    """Same ordered identity used by the 11A manifest; excludes retrieval clocks."""
    return digest(
        [
            {
                key: a.get(key)
                for key in (
                    "request",
                    "url",
                    "status",
                    "actual_sha256",
                    "decoder_sha256",
                    "coverage",
                )
            }
            for a in archives
        ]
    )


def bounds(start, end, duration):
    start, end = utc(start), utc(end)
    if not start < end <= FINAL_START:
        raise ValueError("Nonempty pre-Final window required; Final Test remains LOCKED")
    for value in (start, end):
        midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
        if (value - midnight) % duration:
            raise ValueError("UTC interval-aligned window required")
    return start, end


class ArchiveDataset:
    """Pin a caller-reviewed dataset hash; never choose a latest source revision.

    This class supplies PRELIMINARY candles, not a security master, trading rules
    or funding eligibility. No network or trading operations are performed.
    """

    quality = Quality.PRELIMINARY

    def __init__(self, root, report_path, *, expected_dataset_hash, expected_config_hash):
        self.root = Path(root)
        report = json.loads(Path(report_path).read_text())
        if report.get("schema") != "PVB24_ARCHIVE_ACQUISITION_V1":
            raise ValueError("Unsupported acquisition manifest")
        if digest({k: v for k, v in report.items() if k != "report_hash"}) != report["report_hash"]:
            raise ValueError("Acquisition report hash changed")
        if (
            not expected_dataset_hash
            or report["dataset_hash"] != expected_dataset_hash
            or dataset_hash(report["archives"]) != expected_dataset_hash
            or report["config_hash"] != expected_config_hash
            or report["final_test_access"] != "LOCKED"
        ):
            raise ValueError("Dataset/config identity differs from the explicit frozen selection")
        entries = []
        for entry in report["archives"]:
            request = ArchiveRequest(**entry["request"])  # holdout guard before object reads
            attempt = entry["attempt"]
            path = Path(attempt)
            if path.is_absolute() or path.parts[:1] != ("attempts",) or len(path.parts) != 2:
                raise ValueError("Owned acquisition attempt path required")
            if entry["status"] != "ACQUIRED" or entry["quality"] != "PRELIMINARY":
                raise ValueError("Every selected archive must be acquired and PRELIMINARY")
            payload = (self.root / path).read_bytes()
            embedded = {k: v for k, v in entry.items() if k != "attempt"}
            if payload != canonical(embedded).encode() or digest(embedded) + ".json" != path.name:
                raise ValueError("Manifest attempt differs from pinned acquisition evidence")
            entries.append((request, attempt))
        if not entries or len({req for req, _ in entries}) != len(entries):
            raise ValueError("Exactly one explicit revision per archive is required")
        if report["requested_archives"] != len(entries) or report["acquired_archives"] != len(
            entries
        ):
            raise ValueError("Acquisition manifest includes incomplete or inconsistent selection")
        self._entries = tuple(entries)
        self.data_hash = expected_dataset_hash

    def candles(self, symbol, interval, *, start, end, decision, price_type="LAST"):
        if interval not in ("1m", "1h") or price_type not in ("LAST", "MARK"):
            raise ValueError("Explicit LAST/MARK 1m/1h selection required")
        duration = timedelta(minutes=1) if interval == "1m" else timedelta(hours=1)
        start, end = bounds(start, end, duration)
        decision = utc(decision)
        kind = "klines" if price_type == "LAST" else "markPriceKlines"
        required = []
        month = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while month < end:
            request = ArchiveRequest(symbol, kind, month.strftime("%Y-%m"), interval)
            matches = [attempt for req, attempt in self._entries if req == request]
            if len(matches) != 1:
                raise ValueError(f"Requested source month not selected: {request.filename}")
            required.append((request, matches[0]))
            month = request.end
        selected = []
        for request, attempt in required:
            verified, raw, checksum = load_acquired(self.root, attempt)
            if verified != request:
                raise ValueError("Acquired source request differs from the pinned selection")
            selected.extend(
                row
                for row in records(request, raw, checksum)
                if start <= row.timing.interval_start < end and row.timing.available_at <= decision
            )
        known = {row.timing.interval_start for row in selected}
        missing = []
        step = start
        while step < end:
            if step not in known:
                missing.append((step, step + duration))
            step += duration
        return CandleWindow(tuple(selected), tuple(missing))


def daily_last(hourly, symbol, *, start, end, decision):
    """Only 24 completed available LAST hours can form a UTC daily observation.

    Missing/not-yet-available days remain explicit. Revisions use only selected
    causal constituents, so appending future inputs cannot change earlier days.
    """
    day = timedelta(days=1)
    hour = timedelta(hours=1)
    start, end = bounds(start, end, day)
    selected = causal_candles(hourly, symbol, hour, utc(decision), end_at=end)
    selected = [row for row in selected if row.timing.interval_start >= start]
    for row in selected:
        if (
            row.timing.interval_start.minute
            or row.timing.interval_start.second
            or row.timing.interval_start.microsecond
        ):
            raise ValueError("Daily volume requires UTC-grid hourly input")
    by_start = {row.timing.interval_start: row for row in selected}
    result, missing = [], []
    current = start
    while current < end:
        keys = [current + i * hour for i in range(24)]
        if not all(key in by_start for key in keys):
            missing.append((current, current + day))
            current += day
            continue
        members = [by_start[key] for key in keys]
        policy = "derived:LAST_1H_TO_UTC_1D_V1"
        timing = Timing(
            current + day,
            current,
            current + day,
            max(row.timing.available_at for row in members),
            None,
            policy,
            digest({"policy": policy, "constituents": members}),
        )
        with localcontext(CONTEXT):
            volume = sum((row.quote_volume for row in members), D(0))
        result.append(
            Candle(
                symbol,
                timing,
                members[0].open,
                max(row.high for row in members),
                min(row.low for row in members),
                members[-1].close,
                volume,
                "LAST",
                volume == 0,
            )
        )
        current += day
    return CandleWindow(tuple(result), tuple(missing))
