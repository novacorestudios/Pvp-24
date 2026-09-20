"""Official monthly USD-M archive identities and strict PRELIMINARY decoding.

Integrity-checked archive bytes are not verified historical availability,
contract eligibility or executable liquidity. Final Test access stays locked.
"""

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import quote

from pvb24.data.availability import preliminary_timing
from pvb24.data.schemas import Candle
from pvb24.decimal_math import D, require_decimal

FINAL_START = datetime(2025, 7, 1, tzinfo=UTC)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
BASE = "https://data.binance.vision/data/futures/um/monthly/"
KLINE_HEADER = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
)
FUNDING_HEADER = ("calc_time", "funding_interval_hours", "last_funding_rate")


@dataclass(frozen=True)
class FundingArchiveRow:
    """Raw settlement evidence, not a complete causal FundingSettlement index.

    calc_time can differ from the nominal settlement boundary. Preserve it and
    the separately declared interval; never silently round or join timestamps.
    """

    symbol: str
    calculated_at: datetime
    interval_hours: Decimal
    rate: Decimal
    available_at: datetime
    source: str
    revision_id: str

    @property
    def declared_duration(self):
        numerator, denominator = self.interval_hours.as_integer_ratio()
        micros, remainder = divmod(numerator * 3600000000, denominator)
        if remainder:
            raise ValueError("Funding interval cannot be represented in microseconds")
        return timedelta(microseconds=micros)


@dataclass(frozen=True)
class ArchiveRequest:
    symbol: str
    kind: str
    month: str
    interval: str | None = None

    def __post_init__(self):
        if not self.symbol.isalnum() or not self.symbol.endswith("USDT"):
            raise ValueError("Explicit USD-M USDT archive symbol required")
        if self.kind not in ("klines", "markPriceKlines", "fundingRate"):
            raise ValueError("Unsupported archive kind")
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", self.month):
            raise ValueError("Exact YYYY-MM archive month required")
        if self.end > FINAL_START:
            raise ValueError(
                "Final Test archive access is LOCKED until a committed research freeze"
            )
        if self.kind == "fundingRate":
            if self.interval is not None:
                raise ValueError("Funding archives have no kline interval")
        elif self.interval not in ("1m", "1h"):
            raise ValueError("PVB24 ingestion supports explicit 1m or 1h bars")

    @property
    def start(self):
        return datetime.strptime(self.month, "%Y-%m").replace(tzinfo=UTC)

    @property
    def end(self):
        start = self.start
        return datetime(start.year + (start.month == 12), start.month % 12 + 1, 1, tzinfo=UTC)

    @property
    def filename(self):
        return f"{self.symbol}-{self.interval or self.kind}-{self.month}.zip"

    @property
    def url(self):
        middle = quote(self.symbol, safe="") + ("/" + self.interval if self.interval else "")
        return BASE + self.kind + "/" + middle + "/" + quote(self.filename, safe="")


def checksum_digest(raw: bytes, expected_filename: str):
    rows = raw.decode("ascii").splitlines()
    if len(rows) != 1:
        raise ValueError("A single named SHA-256 checksum is required")
    parts = rows[0].split()
    if (
        len(parts) != 2
        or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0])
        or parts[1].removeprefix("*") != expected_filename
    ):
        raise ValueError("Checksum must bind this exact archive filename")
    return parts[0].lower()


def milliseconds(value):
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("Integer millisecond timestamp required")
    return EPOCH + timedelta(milliseconds=int(value))


def records(request: ArchiveRequest, archive: bytes, checksum: bytes):
    # Revalidate even a manually restored/tampered request before reading rows.
    request.__post_init__()
    revision = hashlib.sha256(archive).hexdigest()
    if checksum_digest(checksum, request.filename) != revision:
        raise ValueError("Archive SHA-256 does not match the official checksum")
    expected = request.filename[:-4] + ".csv"
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        members = zipped.infolist()
        if len(members) != 1 or members[0].filename != expected or members[0].is_dir():
            raise ValueError("Archive must contain only its exact named CSV member")
        if members[0].file_size > 512 * 1024 * 1024:
            raise ValueError("Archive CSV exceeds the supported resource limit")
        if members[0].flag_bits & 1:
            raise ValueError("Encrypted archive members are not supported")
        with (
            zipped.open(members[0]) as binary,
            io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as stream,
        ):
            reader = csv.reader(stream, strict=True)
            header = FUNDING_HEADER if request.kind == "fundingRate" else KLINE_HEADER
            previous = None
            for index, row in enumerate(reader):
                if index == 0 and tuple(row) == header:
                    continue
                if len(row) != len(header):
                    raise ValueError(f"Unexpected CSV schema at row {index + 1}")
                event = milliseconds(row[0])
                if not request.start <= event < request.end:
                    raise ValueError("Archive row is outside its declared month")
                if previous is not None and event <= previous:
                    raise ValueError("Duplicate or backwards archive timestamp")
                previous = event
                if request.kind == "fundingRate":
                    hours = D(row[1])
                    require_decimal(hours, positive=True)
                    funding = FundingArchiveRow(
                        request.symbol,
                        event,
                        hours,
                        D(row[2]),
                        event + timedelta(seconds=2),
                        request.url,
                        revision,
                    )
                    _ = funding.declared_duration  # validate precision/range without rounding
                    yield funding
                    continue
                duration = timedelta(minutes=1) if request.interval == "1m" else timedelta(hours=1)
                millis_per_bar = 60000 if request.interval == "1m" else 3600000
                if int(row[0]) % millis_per_bar:
                    raise ValueError("Archive candle is off its UTC interval grid")
                end = event + duration
                if milliseconds(row[6]) != end - timedelta(milliseconds=1):
                    raise ValueError("Binance inclusive close timestamp differs from bar boundary")
                mark = request.kind == "markPriceKlines"
                volume = D(0) if mark else D(row[7])
                if not mark:
                    for i in (5, 7, 9, 10):
                        require_decimal(D(row[i]), nonnegative=True)
                    if not row[8].isdigit():
                        raise ValueError("Nonnegative integer trade count required")
                    if D(row[9]) > D(row[5]) or D(row[10]) > volume:
                        raise ValueError("Taker volume exceeds total source volume")
                    if (D(row[5]) == 0) != (volume == 0):
                        raise ValueError("Base and quote zero-volume fields disagree")
                yield Candle(
                    request.symbol,
                    preliminary_timing(event, end, request.url, revision),
                    D(row[1]),
                    D(row[2]),
                    D(row[3]),
                    D(row[4]),
                    volume,
                    "MARK" if mark else "LAST",
                    volume == 0,
                )


def coverage(request: ArchiveRequest, archive: bytes, checksum: bytes):
    count, zero_volume = 0, 0
    first = last = previous = None
    gaps = []
    funding_discontinuities = []
    for record in records(request, archive, checksum):
        count += 1
        if isinstance(record, Candle):
            start, end = record.timing.interval_start, record.timing.interval_end
            zero_volume += int(record.price_type == "LAST" and record.quote_volume == 0)
            expected = request.start if previous is None else previous
        else:
            end = record.calculated_at
            start = end - record.declared_duration
            expected = start if previous is None else previous
            if start != expected:
                delta = start - expected
                funding_discontinuities.append(
                    {
                        "previous_calc_time": expected,
                        "calc_time": end,
                        "declared_interval_hours": record.interval_hours,
                        "difference_microseconds": (delta.days * 86400 + delta.seconds) * 1000000
                        + delta.microseconds,
                    }
                )
        if start < expected and isinstance(record, Candle):
            raise ValueError("Overlapping declared source intervals")
        if start > expected:
            gaps.append({"start": expected, "end": start})
        first = start if first is None else first
        last = previous = end
    if request.kind != "fundingRate" and (last is None or last < request.end):
        gaps.append({"start": last or request.start, "end": request.end})
    return {
        "rows": count,
        "first_interval_start": first,
        "last_interval_end": last,
        "gaps": gaps,
        "zero_volume_last_bars": zero_volume,
        "monthly_bar_grid_complete": request.kind != "fundingRate" and count > 0 and not gaps,
        "funding_schedule_complete": False,
        "funding_interval_discontinuities": funding_discontinuities,
        "quality": "PRELIMINARY",
        "timing_policy": "INTERVAL_END_PLUS_2S_MODELLED",
        "historical_publication_times_verified": False,
        "contract_eligibility_verified": False,
        "execution_depth_verified": False,
    }
