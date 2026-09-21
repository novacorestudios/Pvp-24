"""Qualify selected target listings from pinned reviewed Binance CMS sources.

The parser is deliberately narrow and validates the article lead against the rendered contract
table. It emits PRELIMINARY listing facts only; Binance Vision activity remains a separate gate.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from pvb24.data.archive import FINAL_START
from pvb24.data.reviewed_listing_source import SCHEMA as SOURCE_SCHEMA
from pvb24.data.reviewed_listing_source import inspect_reviewed_listing_source
from pvb24.ids import canonical, digest
from pvb24.types import utc

SCHEMA = "PVB24_REVIEWED_LISTING_FACTS_V1"
REVISION_DOMAIN = "M11X_REVIEWED_LISTING_FACT_V1"

SOURCES = {
    "6971c0a0c4fe43ef9969c1d6252dea74": {
        "target": "BLUEBIRDUSDT",
        "report_sha256": "9a672c004bd0437143e8cf29334855cd0e8bc68d130fa8f5cf7719602f5b10ae",
        "source_sha256": "da6e7e3d52c311e652383fb096540384570860fc997c46020052d2d16de2d6bb",
    },
    "d6c6c06ddb074c829d90155b0aba661b": {
        "target": "CVXUSDT",
        "report_sha256": "c3cfc9bcb7ed009374fe1f46c5f24894379f05a11e470c0d0b6e5946f141595a",
        "source_sha256": "6f3200edae2e1b69346fb468ebe0b5be79c40de12a62fe7d37f985927d88b54c",
    },
    "521a6a71b21046f2b07b021edfd41b9f": {
        "target": "MAVIAUSDT",
        "report_sha256": "e84adf7acfe697b70e0b37b250da695e2ef04ee44a318180124417f13baaf5a6",
        "source_sha256": "d275dc36bdeb359730e8b59171203e30f5d75987358e0d787e4180cfade0e9fd",
    },
    "155dd1d3b26d48918d75d263833a5d1d": {
        "target": "GLMRUSDT",
        "report_sha256": "2afbbc54ea2dd8e503d3f0acee8ccbb2c3b0e25e66f1674bb9ce224482bbd870",
        "source_sha256": "08db5bd65758d890bad3ee52cbf3098e4eb03f42c76222af857169fe0a3cce0c",
    },
    "d7e84d0cbade4525bd55e61e7ee0f83a": {
        "target": "MBLUSDT",
        "report_sha256": "8f379975a6b8aef5a7a313dd2a0cc120c088e9f72a3c375fdc2f4ce46ca2f4f1",
        "source_sha256": "e7feaf207c7574f2af9895f6e8d3f00c7b041985843fec6cafdd4c8b4c402d6f",
    },
    "93710257326b4f33aed7d8b7b73746d1": {
        "target": "ORBSUSDT",
        "report_sha256": "50d7913f6dc15ae2be5e3ee913da393d524772b6703de453482b0afb2fdc3ab9",
        "source_sha256": "f24821c5d0ce3a5ed2980de92fd8ebd146303ad97d84a82dc6cc3949ae78e351",
    },
    "81c80244a5fb4bfab3cea51cd2ed325b": {
        "target": "RADUSDT",
        "report_sha256": "ddc71caf84f568840b73fd8c23df358ddb0b789664e17402aa5a57c6eac7c898",
        "source_sha256": "aedd38431f1f762672b27317815f40b87a82c81f89776861895e655a3e901b13",
    },
    "adabdfbc53344094808a7bea464f101b": {
        "target": "ICPUSDT",
        "report_sha256": "5cd880c24b35b126004449300ab40211e3eaf59569fcd012e957ca73accf64bc",
        "source_sha256": "bc34b2bba343c7c030bdd0a0eb29b412eed57f9f0637c88f9783be4f2c95d34e",
    },
    "2e53db8e7af34d7dae7310e4a4336cdd": {
        "target": "SNTUSDT",
        "report_sha256": "6c446139fbd168b47614eae21df3d1502d64079c894b714c459e6efa28115505",
        "source_sha256": "ef4b6baa7bfd927a073419558a6e04627dba5e7facebba60feb0c26f845e9d73",
    },
    "bd18df283ead40d09fd60c8eab984e41": {
        "target": "TLMUSDT",
        "report_sha256": "7bf69c681994cda1f64615ba7ebad9c5e05909a3b570ed843f6d5d6bce500c90",
        "source_sha256": "cd7168db7ab9cb32e47ba21f5d4975acc8e5570a42020c579ec036edb27a2058",
    },
    "5d8c7476197344d087b5af436bfc74ae": {
        "target": "SLPUSDT",
        "report_sha256": "f62529faef5f07c164206bb9bbb06b53e82c95cf58dcd958199f72b75b871ab3",
        "source_sha256": "82f0cb7a595b78b9a9d9951303addba342db89a92598118891b399f0871528e7",
    },
}


def _time(value):
    if not isinstance(value, str):
        raise TypeError("Canonical timestamp string required")
    result = utc(datetime.fromisoformat(value))
    if result >= FINAL_START:
        raise ValueError("Final Test listing evidence remains LOCKED")
    return result


def _parse_datetime(day, clock):
    result = datetime.strptime(day + " " + clock, "%Y-%m-%d %H:%M").replace(
        tzinfo=FINAL_START.tzinfo
    )
    if result >= FINAL_START:
        raise ValueError("Final Test listing event remains LOCKED")
    return result


def _load(root, code, pin):
    root = Path(root) / code
    report_path = root / "reports" / f"{pin['report_sha256']}.json"
    report_raw = report_path.read_bytes()
    if hashlib.sha256(report_raw).hexdigest() != pin["report_sha256"]:
        raise ValueError("Reviewed listing report hash changed")
    report = json.loads(report_raw)
    if (
        report.get("schema") != SOURCE_SCHEMA
        or report.get("code") != code
        or report.get("source_sha256") != pin["source_sha256"]
        or report.get("source_object") != f"objects/{pin['source_sha256']}.json"
        or report.get("semantic_listing_facts_emitted") is not False
        or report.get("security_rows_emitted") != 0
        or report.get("final_test_access") != "LOCKED"
    ):
        raise ValueError("Pinned reviewed listing source required")
    raw = (root / report["source_object"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin["source_sha256"]:
        raise ValueError("Reviewed listing source bytes changed")
    replayed = inspect_reviewed_listing_source(code, raw)
    comparable = dict(report)
    comparable.pop("source_object", None)
    if canonical(replayed) != canonical(comparable):
        raise ValueError("Reviewed listing report differs from retained source")
    return report


def _modern_single(body):
    match = re.search(
        r"Binance Futures will launch the USDⓈ-M (?P<base>[A-Z0-9]+) "
        r"perpetual contract at (?P<day>\d{4}-\d{2}-\d{2}) "
        r"(?P<clock>\d{2}:\d{2})\s+\(UTC\), with up to (?P<lev>\d+)x leverage\.",
        body,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return [
        (
            match.group("base").upper() + "USDT",
            _parse_datetime(match.group("day"), match.group("clock")),
            int(match.group("lev")),
        )
    ]


def _legacy_single(body):
    match = re.search(
        r"Binance Futures will launch USDⓈ-M (?P<base>[A-Z0-9]+) perpetual contracts "
        r"with up to (?P<lev>\d+)x leverage on (?P<day>\d{4}-\d{2}-\d{2}) "
        r"at (?P<clock>\d{2}:\d{2})\s+\(UTC\)\.",
        body,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return [
        (
            match.group("base").upper() + "USDT",
            _parse_datetime(match.group("day"), match.group("clock")),
            int(match.group("lev")),
        )
    ]


def _bluebird(body):
    match = re.search(
        r"Binance Futures will launch USDⓈ-M Binance Bluebird Index perpetual contracts "
        r"\([“\"](?P<symbol>[A-Z0-9]+USDT) Perpetual Contracts[”\"]\) "
        r"with up to (?P<lev>\d+)x leverage on (?P<day>\d{4}-\d{2}-\d{2}) "
        r"at (?P<clock>\d{2}:\d{2})\s+\(UTC\)\.",
        body,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return [
        (
            match.group("symbol").upper(),
            _parse_datetime(match.group("day"), match.group("clock")),
            int(match.group("lev")),
        )
    ]


def _paired(body):
    match = re.search(
        r"Binance Futures will launch USDⓈ-M (?P<names>[A-Z0-9, ]+?\band\s+[A-Z0-9]+) "
        r"perpetual contracts with up to (?P<lev>\d+)x leverage on "
        r"(?P<schedule>[^.]+?) respectively\.",
        body,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    names = [
        token.upper()
        for token in re.findall(r"\b[A-Z0-9]+\b", match.group("names"))
        if token.upper() != "AND"
    ]
    times = re.findall(
        r"(\d{4}-\d{2}-\d{2}) at (\d{2}:\d{2})\s+\(UTC\)",
        match.group("schedule"),
    )
    if len(names) != len(times) or len(names) < 2 or len(names) != len(set(names)):
        raise ValueError("Ambiguous paired reviewed listing schedule")
    leverage = int(match.group("lev"))
    return [
        (name + "USDT", _parse_datetime(day, clock), leverage)
        for name, (day, clock) in zip(names, times, strict=True)
    ]


def _multi_after(body):
    match = re.search(
        r"Binance Futures will launch USDT-margined "
        r"(?P<names>[A-Z0-9, ]+?\band\s+[A-Z0-9]+) perpetual contracts on "
        r"(?P<schedule>[^.]+?) respectively, with up to (?P<lev>\d+)x leverage\.",
        body,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    names = [
        token.upper()
        for token in re.findall(r"\b[A-Z0-9]+\b", match.group("names"))
        if token.upper() != "AND"
    ]
    times = re.findall(
        r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\s+\(UTC\)",
        match.group("schedule"),
    )
    if len(names) != len(times) or len(names) < 2 or len(names) != len(set(names)):
        raise ValueError("Ambiguous multi-symbol reviewed listing schedule")
    leverage = int(match.group("lev"))
    return [
        (name + "USDT", _parse_datetime(day, clock), leverage)
        for name, (day, clock) in zip(names, times, strict=True)
    ]


def extract_target_listing_fact(body, target):
    parsers = (_modern_single, _legacy_single, _bluebird, _paired, _multi_after)
    matches = [facts for parser in parsers if (facts := parser(body)) is not None]
    if len(matches) != 1:
        raise ValueError("Exactly one supported reviewed listing lead required")
    facts = matches[0]
    selected = [item for item in facts if item[0] == target]
    if len(selected) != 1:
        raise ValueError("Reviewed target symbol must appear exactly once in launch lead")
    symbol, launch_at, leverage = selected[0]
    if not 1 <= leverage <= 125:
        raise ValueError("Reviewed maximum leverage is out of range")

    if len(facts) == 1:
        stamp = launch_at.strftime("%Y-%m-%d %H:%M")
        table_pattern = re.escape(symbol) + r"\s*Launch Time\s*" + re.escape(stamp) + r"\s*\(UTC\)"
    else:
        symbol_sequence = r"\s*".join(re.escape(item[0]) for item in facts)
        time_sequence = r"\s*".join(
            re.escape(item[1].strftime("%Y-%m-%d %H:%M")) + r"\s*\(UTC\)" for item in facts
        )
        table_pattern = symbol_sequence + r"\s*Launch Time\s*" + time_sequence
    if re.search(table_pattern, body, flags=re.IGNORECASE) is None:
        raise ValueError("Rendered contract table does not corroborate reviewed launch order")

    prior = re.search(
        r"old\s+" + re.escape(symbol) + r"\s+contract, which was previously delisted at "
        r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\s+\(UTC\)",
        body,
        flags=re.IGNORECASE,
    )
    prior_delisted_at = _parse_datetime(*prior.groups()) if prior is not None else None
    return {
        "symbol": symbol,
        "launch_at": launch_at,
        "max_leverage": leverage,
        "contract_type": "PERPETUAL",
        "quote_asset": "USDT",
        "prior_epoch_disclosed": prior_delisted_at is not None,
        "prior_epoch_delisted_at": prior_delisted_at,
        "classification_hint": "NON_CRYPTO_INDEX" if symbol == "BLUEBIRDUSDT" else None,
    }


def compile_reviewed_listing_facts(root):
    rows = []
    for code, pin in sorted(SOURCES.items()):
        report = _load(root, code, pin)
        fact = extract_target_listing_fact(report["body_text"], pin["target"])
        available_at = _time(report["available_at"])
        if available_at > utc(fact["launch_at"]):
            raise ValueError("Reviewed listing source became available after launch")
        rows.append(
            {
                "code": code,
                "target": pin["target"],
                "source": report["source"],
                "source_sha256": report["source_sha256"],
                "body_sha256": report["body_sha256"],
                "report_sha256": pin["report_sha256"],
                "published_at": _time(report["published_at"]),
                "available_at": available_at,
                "fact": fact,
                "revision_id": digest([REVISION_DOMAIN, code, report["source_sha256"], fact]),
                "boundary_reconciled": False,
                "historical_verified": False,
                "universe_eligible": False,
            }
        )

    result = {
        "schema": SCHEMA,
        "source_count": len(rows),
        "fact_count": len(rows),
        "target_symbols": sorted(row["target"] for row in rows),
        "results": rows,
        "prior_epoch_disclosure_count": sum(row["fact"]["prior_epoch_disclosed"] for row in rows),
        "classification_hint_count": sum(
            row["fact"]["classification_hint"] is not None for row in rows
        ),
        "security_rows_emitted": 0,
        "security_history_complete": False,
        "historical_universe_complete": False,
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    result["facts_hash"] = digest(result)
    return json.loads(canonical(result))
