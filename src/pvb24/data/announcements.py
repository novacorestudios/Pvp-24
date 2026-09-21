"""Pinned official announcement facts; retrospective revisions stay PRELIMINARY.

Only explicitly reviewed pre-Final articles are fetched. The complete response
is retained locally, but only factual extracts/hashes belong in public reports.
No listing age, full rule snapshot, settlement fill or coverage is inferred.
"""

import hashlib
import html
import json
import re
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pvb24.data.acquisition import NoRedirect, object_write
from pvb24.data.archive import FINAL_START, milliseconds
from pvb24.data.lifecycle import DelistingNotice
from pvb24.decimal_math import D, require_decimal
from pvb24.ids import canonical, digest
from pvb24.replay.events import Event, Kind
from pvb24.types import Quality, utc

BASE = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode="
MAX_BYTES = 2 * 1024 * 1024
POLICY = "PRELIMINARY_CMS_REVIEWED_REVISION_PUBLICATION_OR_KNOWN_UPDATE_PLUS_2S_V1"
DECODER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
UTC_TEXT = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \(UTC\)"
ARTICLE_CODE = r"(?:[0-9]{12}|[0-9a-f]{32})"


@dataclass(frozen=True)
class AnnouncementRequest:
    code: str
    published_day: str
    kind: str
    body_sha256: str
    facts_hash: str

    def __post_init__(self):
        if not re.fullmatch(ARTICLE_CODE, self.code):
            raise ValueError("Explicit official article code required")
        day = date.fromisoformat(self.published_day)
        if day.isoformat() != self.published_day or day >= FINAL_START.date():
            raise ValueError("Reviewed pre-Final publication date required; Final remains LOCKED")
        if self.kind not in ("DELISTING", "TICK_CHANGE", "LISTING"):
            raise ValueError("Unsupported reviewed announcement kind")
        if any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in (self.body_sha256, self.facts_hash)):
            raise ValueError("Reviewed body and facts hashes required")

    @property
    def url(self):
        self.__post_init__()
        return BASE + self.code


def public_announcement(url):
    if not re.fullmatch(re.escape(BASE) + ARTICLE_CODE, url):
        raise ValueError("Official read-only announcement URL required")
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=30) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Announcement exceeds resource limit")
    return raw


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate announcement JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Exact JSON values required")

    return json.loads(raw, object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)


def nodes(root, depth=0):
    if not isinstance(root, dict) or depth > 64:
        raise ValueError("Invalid or too deeply nested announcement body")
    kind = root.get("node")
    if kind == "text":
        if not isinstance(root.get("text"), str) or root.get("child"):
            raise ValueError("Invalid text node")
    elif kind not in ("root", "element") or not isinstance(root.get("child", []), list):
        raise ValueError("Unsupported announcement tree")
    yield root
    for child in root.get("child", []):
        yield from nodes(child, depth + 1)


def text(node):
    return html.unescape("".join(n["text"] for n in nodes(node) if n["node"] == "text")).strip()


def explicit_time(value):
    result = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    if result >= FINAL_START:
        raise ValueError("Final-period metadata facts remain LOCKED")
    return result


def legacy_listing_time(value):
    result = datetime.strptime(value, "%Y/%m/%d %I:%M %p").replace(tzinfo=UTC)
    if result >= FINAL_START:
        raise ValueError("Final-period metadata facts remain LOCKED")
    return result


def extract_facts(kind, body):
    all_nodes = list(nodes(body))
    if len(all_nodes) > 20000 or body.get("node") != "root":
        raise ValueError("Bounded rich-text root required")
    if kind == "DELISTING":
        # Match the contract announcement, never the separate arbitrage-bot paragraph.
        matches = []
        for block in body.get("child", []):
            matches.extend(
                re.findall(
                    r"Binance Futures will close all positions and conduct an automatic "
                    r"settlement on the (.+?) perpetual contracts at " + UTC_TEXT,
                    text(block),
                )
            )
        if len(matches) != 1 or "contracts will be delisted" not in text(body):
            raise ValueError("One unambiguous perpetual-contract delisting required")
        names, when = matches[0]
        symbols = re.findall(r"\b[A-Z0-9]+USDT\b", names)
        residual = re.sub(r"\b[A-Z0-9]+USDT\b|USDⓈ-M|\band\b|[\s,]", "", names)
        if residual or not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("Explicit unique USDT perpetual delisting symbols required")
        cutoff = re.findall(
            r"not allowed to open new positions for the aforementioned contracts starting from "
            + UTC_TEXT,
            text(body),
        )
        if len(cutoff) != 1:
            raise ValueError("One explicit new-position cutoff required")
        settlement, cutoff_time = explicit_time(when), explicit_time(cutoff[0])
        if cutoff_time > settlement:
            raise ValueError("Position cutoff after scheduled settlement")
        return [
            {
                "symbol": symbol,
                "scheduled_settlement_at": settlement,
                "entry_cutoff_at": cutoff_time,
            }
            for symbol in sorted(symbols)
        ]
    if kind == "LISTING":
        body_text = text(body)
        if "Binance Futures will launch" not in body_text or "perpetual contract" not in body_text:
            raise ValueError("Explicit Binance Futures perpetual launch statement required")
        symbols = sorted(set(re.findall(r"\\b([A-Z0-9]+)/USDT\\b", body_text)))
        launches = re.findall(
            r"(?:trading opening at|trading opens on|open trading at)\\s*"
            r"(\\d{4}/\\d{2}/\\d{2}\\s+\\d{1,2}:\\d{2}\\s+(?:AM|PM))\\s*\\(UTC\\)",
            body_text,
        )
        leverages = re.findall(
            r"(?:select between 1-|up to )(\\d+)x leverage",
            body_text,
            flags=re.IGNORECASE,
        )
        if len(symbols) != 1 or len(launches) != 1 or len(leverages) != 1:
            raise ValueError("One unambiguous legacy USDT perpetual listing required")
        maximum = int(leverages[0])
        if not 1 <= maximum <= 125:
            raise ValueError("Unsupported announced maximum leverage")
        return [
            {
                "symbol": symbols[0] + "USDT",
                "launch_at": legacy_listing_time(launches[0]),
                "max_leverage": maximum,
                "contract_type": "PERPETUAL",
                "quote_asset": "USDT",
            }
        ]
    if kind != "TICK_CHANGE":
        raise ValueError("Unsupported announcement kind")
    effective = re.findall(r"perpetual futures contracts at " + UTC_TEXT, text(body))
    tables = [node for node in all_nodes if node.get("tag") == "table"]
    if len(effective) != 1 or len(tables) != 1 or "adjust the tick size" not in text(body):
        raise ValueError("One explicit tick-change table and effective time required")
    rows = [node for node in nodes(tables[0]) if node.get("tag") == "tr"]
    cells = [[text(c) for c in row.get("child", [])] for row in rows]
    if not cells or cells[0] != ["Contract Type", "Trading Pair", "Before", "After"]:
        raise ValueError("Unsupported tick-change table columns")
    facts = []
    for index, row in enumerate(cells[1:]):
        if index == 0:
            if len(row) != 4 or row[0] != "USDⓈ-M Futures":
                raise ValueError("Explicit USD-M contract table required")
            row = row[1:]
        if len(row) != 3 or not re.fullmatch(r"[A-Z0-9]+USD[TC]", row[0]):
            raise ValueError("Unexpected contract row")
        before, after = D(row[1]), D(row[2])
        require_decimal(before, positive=True)
        require_decimal(after, positive=True)
        facts.append(
            {
                "symbol": row[0],
                "effective_at": explicit_time(effective[0]),
                "tick_before": before,
                "tick_after": after,
            }
        )
    if not facts or len({f["symbol"] for f in facts}) != len(facts):
        raise ValueError("Unique nonempty tick-change rows required")
    return sorted(facts, key=lambda f: f["symbol"])


def decode(request, raw):
    request.__post_init__()
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Nonempty bounded announcement response required")
    response = strict_json(raw)
    if not isinstance(response, dict) or response.get("success") is not True:
        raise ValueError("Successful CMS response required")
    data = response.get("data")
    if not isinstance(data, dict) or data.get("code") != request.code:
        raise ValueError("Announcement identity differs from reviewed source")
    for field in ("publishDate", "lastUpdateTime"):
        if type(data.get(field)) is not int or data[field] < 0:
            raise ValueError("Explicit integer source publication/update clocks required")
    published = milliseconds(str(data["publishDate"]))
    if published.date().isoformat() != request.published_day:
        raise ValueError("Source publication differs from reviewed pre-Final date")
    updated = milliseconds(str(data["lastUpdateTime"])) if data["lastUpdateTime"] else None
    if updated is not None and (updated < published or updated >= FINAL_START):
        raise ValueError("Source update outside reviewed pre-Final chronology")
    body = data.get("body")
    if (
        not isinstance(body, str)
        or hashlib.sha256(body.encode()).hexdigest() != request.body_sha256
    ):
        raise ValueError("Announcement body changed; explicit review required")
    facts = extract_facts(request.kind, strict_json(body))
    if digest(facts) != request.facts_hash:
        raise ValueError("Extracted facts differ from independently reviewed facts")
    effective_key = {
        "DELISTING": "scheduled_settlement_at",
        "TICK_CHANGE": "effective_at",
        "LISTING": "launch_at",
    }[request.kind]
    if any(f[effective_key] <= published for f in facts):
        raise ValueError("Announcement must precede its scheduled change")
    if not isinstance(data.get("version"), str) or not data["version"]:
        raise ValueError("Source version label required (not proof of original revision)")
    return {
        "code": request.code,
        "kind": request.kind,
        "source": request.url,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "body_sha256": request.body_sha256,
        "published_at": published,
        "known_updated_at": updated,
        "cms_version": data["version"],
        "revision_id": digest(
            [request.code, published, updated, data["version"], request.body_sha256]
        ),
        "available_at": (updated or published) + timedelta(seconds=2),
        "availability_policy": POLICY,
        "historical_verified": False,
        "original_revision_as_published_verified": False,
        "actual_received_at_historical": None,
        "quality": Quality.PRELIMINARY,
        "facts": facts,
        "facts_hash": digest(facts),
        "security_master_complete": False,
        "contract_rules_complete": False,
        "settlement_execution_proven": False,
    }


def acquire(request, root, *, fetch=public_announcement):
    request.__post_init__()
    raw = fetch(request.url)
    received = datetime.now(UTC)
    if len(raw) > MAX_BYTES:
        raise ValueError("Announcement exceeds resource limit")
    raw_name = object_write(Path(root) / "objects", raw, ".json")
    result = {
        "schema": "PVB24_ANNOUNCEMENT_ACQUISITION_V1",
        "request": asdict(request),
        "source_object": "objects/" + raw_name,
        "received_at": received,
        "decoder_sha256": DECODER_SHA256,
        "final_test_access": "LOCKED",
        **decode(request, raw),
    }
    encoded = canonical(result).encode()
    name = object_write(Path(root) / "reports", encoded, ".json")
    return json.loads(encoded), "reports/" + name


def load_acquired(root, report_path, *, expected_report_hash):
    path = Path(report_path)
    if (
        path.is_absolute()
        or len(path.parts) != 2
        or path.parts[0] != "reports"
        or path.name != expected_report_hash + ".json"
    ):
        raise ValueError("Explicit pinned announcement report required")
    payload = (Path(root) / path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_report_hash:
        raise ValueError("Announcement report hash changed")
    report = strict_json(payload)
    request = AnnouncementRequest(**report["request"])
    if (
        report["schema"] != "PVB24_ANNOUNCEMENT_ACQUISITION_V1"
        or report["decoder_sha256"] != DECODER_SHA256
        or report["final_test_access"] != "LOCKED"
    ):
        raise ValueError("Announcement schema/decoder/holdout identity changed")
    raw_name = report["source_sha256"] + ".json"
    if report["source_object"] != "objects/" + raw_name or not re.fullmatch(
        r"[0-9a-f]{64}\.json", raw_name
    ):
        raise ValueError("Owned announcement source object required")
    decoded = decode(request, (Path(root) / "objects" / raw_name).read_bytes())
    if canonical(decoded) != canonical({k: report[k] for k in decoded}):
        raise ValueError("Announcement facts differ from retained source bytes")
    return report


def delisting_events(root, report_path, *, expected_report_hash, through):
    """Recheck source bytes; future articles never enter a prior event batch."""
    through = utc(through)
    if through >= FINAL_START:
        raise ValueError("Pre-Final replay boundary required")
    report = load_acquired(root, report_path, expected_report_hash=expected_report_hash)
    if report["kind"] != "DELISTING":
        return ()  # A tick delta is deliberately not an executable full rule snapshot.
    available = datetime.fromisoformat(report["available_at"])
    if available > through:
        return ()
    result = []
    for fact in report["facts"]:
        notice = DelistingNotice(
            fact["symbol"],
            datetime.fromisoformat(report["published_at"]),
            datetime.fromisoformat(fact["scheduled_settlement_at"]),
            available,
            report["source"],
            report["revision_id"],
            False,
        )
        result.append(
            Event(
                digest([POLICY, notice]),
                Kind.OBSERVATION,
                notice.announced_at,
                available,
                notice.source,
                Quality.PRELIMINARY,
                canonical({"type": "DELISTING_NOTICE", "record": notice}),
            )
        )
    return tuple(result)
