"""Resolve only source-proven M11X listing-schedule revisions.

This module binds two explicitly reviewed official Binance CMS revisions to the pinned retained
lifecycle recovery. It may cancel an earlier announced schedule only when the postponement text
identifies the exact symbol/leverage and became available before that schedule. It does not infer
market activity, relisting, classification, or complete Security history.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from pvb24.data.announcements import explicit_time
from pvb24.data.archive import FINAL_START
from pvb24.data.listing_conflict_source import (
    SCHEMA as SOURCE_SCHEMA,
    inspect_listing_conflict_source,
)
from pvb24.ids import canonical, digest
from pvb24.types import utc

RECOVERY_SCHEMA = "PVB24_RETAINED_ANNOUNCEMENT_RECOVERY_V2"
OUTPUT_SCHEMA = "PVB24_LISTING_CONFLICT_RESOLUTION_V1"
RECOVERY_REVISION_DOMAIN = "M11X_RETAINED_LIFECYCLE_RECOVERY_V2"
SOURCE_REVISION_DOMAIN = "M11X_LISTING_CONFLICT_SOURCE_V1"

POSTPONEMENT_CODE = "02d2b629c7b04786b9a76c132a3ed541"
POSTPONEMENT_REPORT = "96665982bcbea73f154aee4f6de42ef18663a79347dfffc771a629c4087f21ef"
POSTPONEMENT_SOURCE = "cc300492f07c157cb414f9c1a0f622ece892e933c677d9526c1839b6261a5459"
BNT_2023_CODE = "e59b61e52ad24b43bd1032052ea3a025"
BNT_2023_REPORT = "dd1de65cf83967d1bab2a93cfc6142fcaa9b4cd77e0aef2aadd392d317783010"
BNT_2023_SOURCE = "fcd9f8bd95590428bfa597fdd943dd6cf934a7b034691cbe72d798554869b898"


def _time(value):
    if not isinstance(value, str):
        raise TypeError("Canonical timestamp string required")
    result = utc(datetime.fromisoformat(value))
    if result >= FINAL_START:
        raise ValueError("Final Test listing-conflict evidence remains LOCKED")
    return result


def _load_source(root, code, report_sha, source_sha):
    root = Path(root) / code
    report_path = root / "reports" / f"{report_sha}.json"
    report_raw = report_path.read_bytes()
    if hashlib.sha256(report_raw).hexdigest() != report_sha:
        raise ValueError("Pinned listing-conflict source report hash changed")
    report = json.loads(report_raw)
    if (
        report.get("schema") != SOURCE_SCHEMA
        or report.get("code") != code
        or report.get("source_sha256") != source_sha
        or report.get("source_object") != f"objects/{source_sha}.json"
        or report.get("final_test_access") != "LOCKED"
        or report.get("semantic_resolution_emitted") is not False
        or report.get("security_rows_emitted") != 0
    ):
        raise ValueError("Pinned PRELIMINARY listing-conflict source required")
    raw = (root / report["source_object"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source_sha:
        raise ValueError("Listing-conflict source bytes changed")
    replayed = inspect_listing_conflict_source(code, raw)
    comparable = dict(report)
    comparable.pop("source_object", None)
    if canonical(replayed) != canonical(comparable):
        raise ValueError("Listing-conflict source report differs from retained bytes")
    return report


def _load_recovery(path, expected_sha):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("Pinned retained lifecycle recovery hash changed")
    report = json.loads(raw)
    if (
        report.get("schema") != RECOVERY_SCHEMA
        or report.get("final_test_access") != "LOCKED"
        or report.get("quality") != "PRELIMINARY"
        or report.get("retrospective_count") != 0
        or report.get("historical_universe_complete") is not False
        or report.get("security_history_complete") is not False
    ):
        raise ValueError("Locked PRELIMINARY retained lifecycle recovery required")
    recorded = report.get("recovery_hash")
    unhashed = dict(report)
    unhashed.pop("recovery_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("Retained lifecycle recovery content hash changed")
    return report


def _recovery_revision(article, fact):
    return digest(
        [
            RECOVERY_REVISION_DOMAIN,
            article["code"],
            article["source_sha256"],
            fact,
        ]
    )


def _parse_postponement(report):
    body = report["body_text"]
    match = re.search(
        r"Trading open for the USDT-Margined "
        r"(?P<names>[A-Z0-9]+(?:\s+and\s+[A-Z0-9]+)+) "
        r"(?P<leverage>\d+)X Perpetual Contracts[^.]*will be postponed\. "
        r"A new date and time will be announced soon\.",
        body,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise ValueError("Exact BNT/UNFI postponement statement required")
    bases = [token.upper() for token in re.findall(r"[A-Z0-9]+", match.group("names"))]
    bases = [token for token in bases if token != "AND"]
    if len(bases) != len(set(bases)) or not bases:
        raise ValueError("Unique postponed contract bases required")
    leverage = int(match.group("leverage"))
    if not 1 <= leverage <= 125:
        raise ValueError("Valid postponed maximum leverage required")
    return tuple(base + "USDT" for base in bases), leverage


def _parse_bnt_2023(report):
    body = report["body_text"]
    match = re.search(
        r"Binance Futures will launch the USDⓈ-M "
        r"(?P<base>[A-Z0-9]+) perpetual contract at "
        r"(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \(UTC\), "
        r"with up to (?P<leverage>\d+)x leverage\.",
        body,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise ValueError("Exact modern BNT launch statement required")
    symbol = match.group("base").upper() + "USDT"
    launch = explicit_time(match.group("time"))
    leverage = int(match.group("leverage"))
    if symbol != "BNTUSDT" or not 1 <= leverage <= 125:
        raise ValueError("Explicit BNTUSDT launch evidence required")
    if f"{symbol}Launch Time" not in body or match.group("time") not in body:
        raise ValueError("BNT launch table must corroborate symbol and time")
    return {
        "symbol": symbol,
        "launch_at": launch,
        "max_leverage": leverage,
        "contract_type": "PERPETUAL",
        "quote_asset": "USDT",
    }


def compile_listing_conflict_resolution(
    recovery_path,
    recovery_sha256,
    source_root,
):
    recovery = _load_recovery(recovery_path, recovery_sha256)
    postponement = _load_source(
        source_root,
        POSTPONEMENT_CODE,
        POSTPONEMENT_REPORT,
        POSTPONEMENT_SOURCE,
    )
    bnt_source = _load_source(
        source_root,
        BNT_2023_CODE,
        BNT_2023_REPORT,
        BNT_2023_SOURCE,
    )

    postponed_symbols, postponed_leverage = _parse_postponement(postponement)
    if postponed_symbols != ("BNTUSDT", "UNFIUSDT") or postponed_leverage != 50:
        raise ValueError("Reviewed postponement scope changed")
    cancellation_available = _time(postponement["available_at"])

    cancellations = []
    for symbol in postponed_symbols:
        matches = []
        for article in recovery["recovered"]:
            if article.get("kind") != "LISTING":
                continue
            for fact in article.get("facts", []):
                if fact.get("symbol") == symbol and fact.get("max_leverage") == postponed_leverage:
                    matches.append((article, fact))
        if len(matches) != 1:
            raise ValueError("Postponement must identify exactly one recovered 50X schedule")
        article, fact = matches[0]
        effective = _time(fact["launch_at"])
        if cancellation_available > effective:
            raise ValueError("Postponement became available after canceled schedule")
        cancellations.append(
            {
                "symbol": symbol,
                "canceled_effective_from": effective,
                "canceled_revision_id": _recovery_revision(article, fact),
                "canceled_source": article["article_url"],
                "canceled_source_sha256": article["source_sha256"],
                "cancellation_available_at": cancellation_available,
                "cancellation_source": postponement["source"],
                "cancellation_source_sha256": postponement["source_sha256"],
                "reason": "OFFICIAL_PRE_EFFECTIVE_POSTPONEMENT",
            }
        )

    bnt_fact = _parse_bnt_2023(bnt_source)
    bnt_available = _time(bnt_source["available_at"])
    bnt_effective = utc(bnt_fact["launch_at"])
    if bnt_available > bnt_effective:
        raise ValueError("BNT 2023 launch source became available after launch")
    supplemental = {
        "symbol": bnt_fact["symbol"],
        "effective_from": bnt_effective,
        "available_at": bnt_available,
        "max_leverage": bnt_fact["max_leverage"],
        "contract_type": bnt_fact["contract_type"],
        "quote_asset": bnt_fact["quote_asset"],
        "source": bnt_source["source"],
        "source_sha256": bnt_source["source_sha256"],
        "revision_id": digest(
            [
                SOURCE_REVISION_DOMAIN,
                bnt_source["code"],
                bnt_source["source_sha256"],
                bnt_fact,
            ]
        ),
        "boundary_reconciled": False,
        "historical_verified": False,
        "universe_eligible": False,
    }

    result = {
        "schema": OUTPUT_SCHEMA,
        "inputs": {
            "recovery_sha256": recovery_sha256,
            "recovery_hash": recovery["recovery_hash"],
            "postponement_report_sha256": POSTPONEMENT_REPORT,
            "postponement_source_sha256": POSTPONEMENT_SOURCE,
            "bnt_2023_report_sha256": BNT_2023_REPORT,
            "bnt_2023_source_sha256": BNT_2023_SOURCE,
        },
        "cancellation_count": len(cancellations),
        "cancellations": sorted(cancellations, key=lambda row: row["symbol"]),
        "supplemental_listing_count": 1,
        "supplemental_listings": [supplemental],
        "resolved_conflict_count": 0,
        "remaining_conflict_symbols": ["BNTUSDT", "CHZUSDT", "UNFIUSDT"],
        "market_activity_proven": False,
        "classification_history_complete": False,
        "security_change_stream_complete": False,
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    result["resolution_hash"] = digest(result)
    return json.loads(canonical(result))
