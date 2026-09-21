"""Checksum-verified daily LAST 1m activity probes for lifecycle reconciliation.

Daily archive presence is activity evidence only. A missing object is UNKNOWN and never proves
inactivity, delisting, listing age, historical eligibility, or a complete security master.
"""

import csv
import hashlib
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
import zlib
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pvb24.data.acquisition import NoRedirect, object_write
from pvb24.data.archive import FINAL_START, KLINE_HEADER, checksum_digest, milliseconds
from pvb24.decimal_math import D, require_decimal
from pvb24.ids import canonical, digest
from pvb24.types import utc

BASE = "https://data.binance.vision/data/futures/um/daily/klines/"
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_CHECKSUM = 4096
SCHEMA = "PVB24_LIFECYCLE_ARCHIVE_ACTIVITY_V1"


@dataclass(frozen=True)
class DailyKlineRequest:
    symbol: str
    day: str

    def __post_init__(self):
        if not re.fullmatch(r"[A-Z0-9]+USDT", self.symbol):
            raise ValueError("Explicit USD-M USDT activity symbol required")
        parsed = date.fromisoformat(self.day)
        if parsed.isoformat() != self.day or parsed >= FINAL_START.date():
            raise ValueError("Explicit pre-Final UTC archive day required")

    @property
    def start(self):
        return datetime.combine(date.fromisoformat(self.day), datetime.min.time(), tzinfo=UTC)

    @property
    def end(self):
        return self.start + timedelta(days=1)

    @property
    def filename(self):
        return f"{self.symbol}-1m-{self.day}.zip"

    @property
    def url(self):
        self.__post_init__()
        return BASE + f"{self.symbol}/1m/{self.filename}"

    @property
    def checksum_url(self):
        return self.url + ".CHECKSUM"


def public_daily_bytes(url, *, max_bytes):
    suffix = r"([A-Z0-9]+USDT)/1m/\1-1m-\d{4}-\d{2}-\d{2}\.zip(?:\.CHECKSUM)?"
    pattern = re.escape(BASE) + suffix
    if not re.fullmatch(pattern, url):
        raise ValueError("Official daily USD-M LAST 1m archive URL required")
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=30) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Daily archive response exceeds its resource limit")
    return raw


def _validate_row(row, request, index):
    if len(row) != len(KLINE_HEADER):
        raise ValueError(f"Unexpected daily kline CSV schema at row {index}")
    event = milliseconds(row[0])
    if not request.start <= event < request.end or int(row[0]) % 60000:
        raise ValueError("Daily kline row escapes its UTC day/minute grid")
    end = event + timedelta(minutes=1)
    if milliseconds(row[6]) != end - timedelta(milliseconds=1):
        raise ValueError("Daily kline close timestamp differs from minute boundary")
    for offset in (1, 2, 3, 4):
        require_decimal(D(row[offset]), positive=True)
    for offset in (5, 7, 9, 10):
        require_decimal(D(row[offset]), nonnegative=True)
    if not row[8].isdigit():
        raise ValueError("Nonnegative integer trade count required")
    if D(row[9]) > D(row[5]) or D(row[10]) > D(row[7]):
        raise ValueError("Taker volume exceeds total source volume")
    if (D(row[5]) == 0) != (D(row[7]) == 0):
        raise ValueError("Base and quote zero-volume fields disagree")
    return event, end, D(row[7]) == 0


def decode_daily_activity(request, archive, checksum):
    request.__post_init__()
    revision = hashlib.sha256(archive).hexdigest()
    if checksum_digest(checksum, request.filename) != revision:
        raise ValueError("Daily archive SHA-256 does not match official checksum")
    expected = request.filename[:-4] + ".csv"
    first = last = previous = None
    rows = zero_volume = 0
    gaps = []
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        members = zipped.infolist()
        if len(members) != 1 or members[0].filename != expected or members[0].is_dir():
            raise ValueError("Daily archive must contain only its exact named CSV member")
        if members[0].file_size > 128 * 1024 * 1024 or members[0].flag_bits & 1:
            raise ValueError("Unsupported daily archive member")
        with (
            zipped.open(members[0]) as binary,
            io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as stream,
        ):
            reader = csv.reader(stream, strict=True)
            for index, row in enumerate(reader, start=1):
                if index == 1 and tuple(row) == KLINE_HEADER:
                    continue
                start, end, is_zero = _validate_row(row, request, index)
                if previous is not None:
                    if start <= previous:
                        raise ValueError("Duplicate/backwards daily kline timestamp")
                    if start > previous:
                        gaps.append({"start": previous, "end": start})
                first = start if first is None else first
                last = previous = end
                rows += 1
                zero_volume += int(is_zero)
    return {
        "rows": rows,
        "first_interval_start": first,
        "last_interval_end": last,
        "internal_gaps": gaps,
        "zero_volume_last_bars": zero_volume,
        "source_day": request.day,
        "source_revision_sha256": revision,
        "quality": "PRELIMINARY",
        "historical_eligibility_verified": False,
        "missing_object_means_inactive": False,
    }


def acquire_daily_activity(request, root, *, fetch=public_daily_bytes):
    request.__post_init__()
    root = Path(root)
    result = {
        "schema": "PVB24_DAILY_ACTIVITY_ACQUISITION_V1",
        "request": asdict(request),
        "url": request.url,
        "checksum_url": request.checksum_url,
        "started_at": datetime.now(UTC),
        "status": "IN_PROGRESS",
        "quality": "PRELIMINARY",
        "final_test_access": "LOCKED",
        "historical_eligibility_verified": False,
        "missing_object_means_inactive": False,
    }
    try:
        checksum = fetch(request.checksum_url, max_bytes=MAX_CHECKSUM)
        expected = checksum_digest(checksum, request.filename)
        result["checksum_object"] = object_write(root / "objects", checksum, ".checksum")
        result["expected_sha256"] = expected
        cached = root / "objects" / (expected + ".zip")
        if cached.exists():
            archive = cached.read_bytes()
        else:
            archive = fetch(request.url, max_bytes=MAX_ARCHIVE)
        if len(archive) > MAX_ARCHIVE:
            raise ValueError("Daily archive exceeds its resource limit")
        result["actual_sha256"] = hashlib.sha256(archive).hexdigest()
        if result["actual_sha256"] != expected:
            raise ValueError("Downloaded daily archive failed official SHA-256 verification")
        result["archive_object"] = object_write(root / "objects", archive, ".zip")
        result["bytes"] = len(archive)
        result["activity"] = decode_daily_activity(request, archive, checksum)
        result["status"] = "ACQUIRED" if result["activity"]["rows"] else "EMPTY"
    except urllib.error.HTTPError as exc:
        result.update(
            status="UNAVAILABLE" if exc.code == 404 else "HTTP_ERROR",
            http_status=exc.code,
        )
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        ArithmeticError,
        zipfile.BadZipFile,
        csv.Error,
        EOFError,
        zlib.error,
    ) as exc:
        result.update(status="INVALID_OR_FAILED", error_type=type(exc).__name__, error=str(exc))
    result["completed_at"] = datetime.now(UTC)
    encoded = canonical(result).encode()
    name = object_write(root / "attempts", encoded, ".json")
    return json.loads(encoded), "attempts/" + name


def load_daily_activity(root, attempt_path):
    root, path = Path(root), Path(attempt_path)
    if path.is_absolute() or len(path.parts) != 2 or path.parts[0] != "attempts":
        raise ValueError("Owned daily activity attempt path required")
    payload = (root / path).read_bytes()
    if hashlib.sha256(payload).hexdigest() + ".json" != path.name:
        raise ValueError("Daily activity attempt content hash changed")
    result = json.loads(payload)
    request = DailyKlineRequest(**result["request"])
    if result.get("status") != "ACQUIRED" or result.get("url") != request.url:
        raise ValueError("A validated acquired daily activity is required")
    objects = []
    for field, suffix in (("archive_object", ".zip"), ("checksum_object", ".checksum")):
        name = result.get(field)
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("Invalid daily activity object path")
        raw = (root / "objects" / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() + suffix != name:
            raise ValueError("Daily activity source object changed")
        objects.append(raw)
    decoded = decode_daily_activity(request, *objects)
    if canonical(decoded) != canonical(result.get("activity")):
        raise ValueError("Daily activity decode differs from acquisition record")
    return result


def _event(kind, fact):
    key = "launch_at" if kind == "LISTING" else "scheduled_settlement_at"
    value = utc(datetime.fromisoformat(fact[key]))
    if value.second or value.microsecond or value >= FINAL_START:
        raise ValueError("Minute-aligned pre-Final lifecycle event required")
    return value


def probe_plan(qualification):
    probes = set()
    for article in qualification.get("results", []):
        if article.get("status") != "QUALIFIED_PRELIMINARY":
            continue
        kind = article.get("kind")
        if kind not in ("LISTING", "DELISTING"):
            raise ValueError("Only listing/delisting lifecycle facts may be reconciled")
        for fact in article.get("facts", []):
            event = _event(kind, fact)
            boundary = (
                event.date() - timedelta(days=1)
                if kind == "LISTING"
                else event.date() + timedelta(days=1)
            )
            for day in (event.date(), boundary):
                probes.add(DailyKlineRequest(fact["symbol"], day.isoformat()))
    return tuple(sorted(probes, key=lambda item: (item.symbol, item.day)))


def _observation(result, attempt):
    activity = result.get("activity") or {}
    return {
        "status": result["status"],
        "url": result["url"],
        "attempt": attempt,
        "rows": activity.get("rows"),
        "first_interval_start": activity.get("first_interval_start"),
        "last_interval_end": activity.get("last_interval_end"),
        "internal_gaps": activity.get("internal_gaps"),
        "missing_object_means_inactive": False,
    }


def _reconcile(kind, fact, event_observation, boundary_observation):
    event = _event(kind, fact)
    contradictions = []
    notes = []
    exact = False
    if event_observation["status"] == "ACQUIRED":
        if kind == "LISTING":
            first = utc(datetime.fromisoformat(event_observation["first_interval_start"]))
            if first < event:
                contradictions.append("EVENT_DAY_ACTIVITY_PRECEDES_ANNOUNCED_LAUNCH")
            elif first == event:
                exact = True
            else:
                notes.append("EVENT_DAY_ARCHIVE_STARTS_AFTER_ANNOUNCED_LAUNCH")
        else:
            last = utc(datetime.fromisoformat(event_observation["last_interval_end"]))
            if last > event:
                contradictions.append("EVENT_DAY_ACTIVITY_CONTINUES_AFTER_SCHEDULED_SETTLEMENT")
            elif last == event:
                exact = True
            else:
                notes.append("EVENT_DAY_ARCHIVE_ENDS_BEFORE_SCHEDULED_SETTLEMENT")
        if event_observation.get("internal_gaps"):
            notes.append("EVENT_DAY_ARCHIVE_HAS_INTERNAL_GAPS")
    else:
        notes.append("EVENT_DAY_ARCHIVE_NOT_ACQUIRED")

    if boundary_observation["status"] == "ACQUIRED" and boundary_observation.get("rows"):
        contradictions.append(
            "PRIOR_DAY_ACTIVITY_PRESENT" if kind == "LISTING" else "NEXT_DAY_ACTIVITY_PRESENT"
        )
    elif boundary_observation["status"] == "UNAVAILABLE":
        notes.append("BOUNDARY_ARCHIVE_OBJECT_MISSING_IS_UNKNOWN")
    elif boundary_observation["status"] != "ACQUIRED":
        notes.append("BOUNDARY_ARCHIVE_NOT_ACQUIRED")

    if contradictions:
        status = "CONTRADICTED_BY_ARCHIVE_ACTIVITY"
    elif exact:
        status = "CONSISTENT_EVENT_BOUNDARY_ONLY"
    else:
        status = "UNKNOWN"
    return {
        "status": status,
        "contradictions": contradictions,
        "notes": notes,
        "archive_absence_proves_inactivity": False,
        "historical_lifecycle_verified": False,
    }


def reconcile_qualification_activity(qualification, output, *, fetch=public_daily_bytes):
    if qualification.get("schema") != "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_V1":
        raise ValueError("Pinned body qualification report required")
    if qualification.get("final_test_access") != "LOCKED":
        raise ValueError("Final Test must remain locked")
    output = Path(output)
    attempts = {}
    failures = []
    for request in probe_plan(qualification):
        result, attempt = acquire_daily_activity(request, output / "archive", fetch=fetch)
        attempts[(request.symbol, request.day)] = (result, attempt)
        if result["status"] in ("HTTP_ERROR", "INVALID_OR_FAILED"):
            failures.append(
                {"symbol": request.symbol, "day": request.day, "status": result["status"]}
            )

    reconciliations = []
    for article in qualification["results"]:
        if article.get("status") != "QUALIFIED_PRELIMINARY":
            continue
        kind = article["kind"]
        for fact in article["facts"]:
            event = _event(kind, fact)
            boundary = (
                event.date() - timedelta(days=1)
                if kind == "LISTING"
                else event.date() + timedelta(days=1)
            )
            event_result, event_attempt = attempts[(fact["symbol"], event.date().isoformat())]
            boundary_result, boundary_attempt = attempts[(fact["symbol"], boundary.isoformat())]
            event_obs = _observation(event_result, event_attempt)
            boundary_obs = _observation(boundary_result, boundary_attempt)
            reconciliations.append(
                {
                    "article_code": article["code"],
                    "article_source_sha256": article["source_sha256"],
                    "kind": kind,
                    "symbol": fact["symbol"],
                    "event_at": event,
                    "fact": fact,
                    "event_day": event_obs,
                    "boundary_day": boundary_obs,
                    **_reconcile(kind, fact, event_obs, boundary_obs),
                }
            )
    reconciliations.sort(key=lambda row: (row["event_at"], row["symbol"], row["article_code"]))
    counts = {}
    for row in reconciliations:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    report = {
        "schema": SCHEMA,
        "quality": "PRELIMINARY",
        "created_at": datetime.now(UTC),
        "qualification_results_hash": qualification["results_hash"],
        "qualification_review_requests_hash": qualification["review_requests_hash"],
        "final_test_access": "LOCKED",
        "probe_count": len(attempts),
        "source_failures": failures,
        "reconciliation_count": len(reconciliations),
        "status_counts": dict(sorted(counts.items())),
        "reconciliations": reconciliations,
        "reconciliation_hash": digest(reconciliations),
        "archive_absence_proves_inactivity": False,
        "historical_lifecycle_verified": False,
        "historical_universe_complete": False,
        "security_master_complete": False,
        "performance_run": False,
        "operational_ready": False,
        "live_enabled": False,
    }
    encoded = canonical(report).encode()
    name = object_write(output / "reports", encoded, ".json")
    return json.loads(encoded), output / "reports" / name
