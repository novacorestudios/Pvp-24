"""Qualify historical Binance USD-M leverage/maintenance-tier announcement evidence.

Official announcements can prove notional boundaries, maintenance-margin rates,
maximum leverage bands, update timing and position-cohort policy. They do not
contain the maintenance amount/cum field required to validate exact liquidation
prices, so this module never emits ContractRules or marks liquidation validated.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from pvb24.data.announcements import nodes, strict_json, text
from pvb24.data.margin_tier_source import SCHEMA as PROBE_SCHEMA
from pvb24.data.margin_tier_source import inspect_margin_tier_response
from pvb24.decimal_math import D, require_decimal
from pvb24.ids import canonical, digest
from pvb24.types import utc

SCHEMA = "PVB24_HISTORICAL_LIQUIDATION_EVIDENCE_V1"
HEADER = [
    "Leverage Before Change",
    "Position Before Change (Notional Value in USDT)",
    "Maintenance Margin Rate Before Change",
    "Leverage After Change",
    "Position After Change (Notional Value in USDT)",
    "Maintenance Margin Rate After Change",
]
SUPER_HEADER = ["Previous Leverage and Margin Tiers", "New Leverage and Margin Tiers"]
POSITION_RE = re.compile(r"(?P<floor>[0-9][0-9,.]*) < Position ≤ (?P<cap>[0-9][0-9,.]*)")
LEVERAGE_RANGE_RE = re.compile(r"(?P<low>\d+)\s*-\s*(?P<high>\d+)x")
LEVERAGE_SINGLE_RE = re.compile(r"(?P<value>\d+)x")
EFFECTIVE_RE = re.compile(
    r"Binance Futures (?:has updated|will update) the leverage and margin tiers "
    r"of (?:the following )?.+? at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \(UTC\)"
)
NOT_AFFECTED = "existing positions opened before the update will not be affected"
AFFECTED = "existing positions opened before the update will be affected"


def _load_probe(root, code, report_hash):
    root = Path(root) / code
    report_path = root / "reports" / f"{report_hash}.json"
    raw_report = report_path.read_bytes()
    if hashlib.sha256(raw_report).hexdigest() != report_hash:
        raise ValueError("Margin-tier probe report hash changed")
    report = strict_json(raw_report)
    if (
        report.get("schema") != PROBE_SCHEMA
        or report.get("code") != code
        or report.get("status") != "PRE_FINAL_REVISION_REVIEWABLE"
        or report.get("final_test_access") != "LOCKED"
    ):
        raise ValueError("Qualified pre-Final margin-tier probe required")
    source_hash = report.get("source_sha256")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ValueError("Pinned margin-tier source hash required")
    raw = (root / "objects" / f"{source_hash}.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != source_hash:
        raise ValueError("Margin-tier source bytes changed")
    rechecked = inspect_margin_tier_response(code, raw)
    if canonical(rechecked) != canonical(report):
        raise ValueError("Margin-tier probe differs from retained source bytes")
    return report, raw


def _time(value):
    if not isinstance(value, str):
        raise TypeError("Canonical timestamp string required")
    return utc(datetime.fromisoformat(value))


def _number(value):
    result = D(value.replace(",", ""))
    require_decimal(result, nonnegative=True)
    return result


def _leverage(value):
    match = LEVERAGE_RANGE_RE.fullmatch(value)
    if match:
        low, high = int(match.group("low")), int(match.group("high"))
        if not 1 <= low <= high <= 125:
            raise ValueError("Invalid leverage range")
        return high
    match = LEVERAGE_SINGLE_RE.fullmatch(value)
    if not match:
        raise ValueError("Unsupported leverage band")
    result = int(match.group("value"))
    if not 1 <= result <= 125:
        raise ValueError("Invalid leverage value")
    return result


def _tier(triple):
    leverage_text, position_text, rate_text = triple
    position = POSITION_RE.fullmatch(position_text)
    if position is None:
        raise ValueError("Unsupported USD-M notional tier")
    floor = _number(position.group("floor"))
    cap = _number(position.group("cap"))
    if cap <= floor:
        raise ValueError("Invalid notional tier bounds")
    if not rate_text.endswith("%"):
        raise ValueError("Explicit maintenance-margin percent required")
    rate = D(rate_text[:-1]) / D(100)
    require_decimal(rate, positive=True)
    if rate >= 1:
        raise ValueError("Invalid maintenance-margin rate")
    return {
        "notional_floor": floor,
        "notional_cap": cap,
        "maintenance_margin_rate": rate,
        "max_leverage": _leverage(leverage_text),
        "leverage_text": leverage_text,
    }


def _validate_schedule(rows):
    if not rows or rows[0]["notional_floor"] != 0:
        raise ValueError("Complete zero-based tier schedule required")
    previous = None
    for row in rows:
        if previous is not None:
            if previous["notional_cap"] != row["notional_floor"]:
                raise ValueError("Non-contiguous maintenance tiers")
            if row["maintenance_margin_rate"] < previous["maintenance_margin_rate"]:
                raise ValueError("Maintenance-margin rate cannot decrease by tier")
            if row["max_leverage"] > previous["max_leverage"]:
                raise ValueError("Maximum leverage cannot increase by tier")
        previous = row
    return rows


def _parse_table(table):
    rows = [node for node in nodes(table) if node.get("tag") == "tr"]
    cells = [[text(cell) for cell in row.get("child", [])] for row in rows]
    if cells and cells[0] == SUPER_HEADER:
        cells = cells[1:]
    if not cells or cells[0] != HEADER:
        raise ValueError("Unsupported USD-M leverage/margin table header")
    previous, new = [], []
    continuation_side = None
    for row in cells[1:]:
        if len(row) == 6:
            continuation_side = None
            previous.append(_tier(row[:3]))
            new.append(_tier(row[3:]))
        elif len(row) == 4 and row[0] in ("NA", "N/A"):
            continuation_side = "NEW"
            new.append(_tier(row[1:]))
        elif len(row) == 4 and row[-1] in ("NA", "N/A"):
            continuation_side = "PREVIOUS"
            previous.append(_tier(row[:3]))
        elif len(row) == 3 and continuation_side == "NEW":
            new.append(_tier(row))
        elif len(row) == 3 and continuation_side == "PREVIOUS":
            previous.append(_tier(row))
        else:
            raise ValueError("Ambiguous leverage/margin table row")
    return _validate_schedule(previous), _validate_schedule(new)


def _article_facts(report, raw):
    response = strict_json(raw)
    body = strict_json(response["data"]["body"])
    body_text = text(body)
    effective_matches = EFFECTIVE_RE.findall(body_text)
    if len(effective_matches) != 1:
        raise ValueError("One explicit leverage-tier effective time required")
    from pvb24.data.announcements import explicit_time

    effective_at = explicit_time(effective_matches[0])
    published_at = _time(report["published_at"])
    updated_at = _time(report["known_updated_at"]) if report["known_updated_at"] else None
    available_at = (updated_at or published_at) + timedelta(seconds=2)

    has_not_affected = NOT_AFFECTED in body_text
    has_affected = AFFECTED in body_text
    if has_not_affected == has_affected:
        raise ValueError("One explicit existing-position update policy required")
    existing_positions_affected = has_affected

    children = body.get("child", [])
    symbol_rows = []
    coin_m_tables = 0
    seen_symbols = set()
    for index, child in enumerate(children):
        if child.get("tag") != "table":
            continue
        if index == 0:
            raise ValueError("Margin-tier table missing contract heading")
        heading = text(children[index - 1])
        if "COIN-M Perpetual Contract" in heading:
            coin_m_tables += 1
            continue
        if "USDⓈ-M Perpetual Contract" not in heading:
            raise ValueError("Margin-tier table contract type is ambiguous")
        symbols = re.findall(r"\b[A-Z0-9]+USDT\b", heading)
        if not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("Unique explicit USD-M symbols required")
        previous, new = _parse_table(child)
        for symbol in symbols:
            if symbol in seen_symbols:
                raise ValueError("Duplicate symbol schedule in announcement")
            seen_symbols.add(symbol)
            symbol_rows.append(
                {
                    "symbol": symbol,
                    "previous_tiers": previous,
                    "new_tiers": new,
                    "maintenance_amounts_present": False,
                    "maintenance_deductions_present": False,
                    "contract_rules_emitted": False,
                    "liquidation_validated": False,
                }
            )
    if not symbol_rows:
        raise ValueError("At least one USD-M tier schedule required")

    causal_notice = available_at <= effective_at
    return {
        "code": report["code"],
        "source": report["source"],
        "source_sha256": report["source_sha256"],
        "body_sha256": report["body_sha256"],
        "published_at": published_at,
        "available_at": available_at,
        "effective_at": effective_at,
        "timing_relation": (
            "ANNOUNCED_BEFORE_EFFECTIVE" if causal_notice else "PUBLISHED_AFTER_EFFECTIVE"
        ),
        "new_schedule_causally_announced_before_effective": causal_notice,
        "existing_positions_opened_before_update_affected": existing_positions_affected,
        "position_cohort_selection_required": not existing_positions_affected,
        "usd_m_symbols": sorted(symbol_rows, key=lambda row: row["symbol"]),
        "coin_m_tables_skipped": coin_m_tables,
        "maintenance_amount_source": "MISSING_FROM_ANNOUNCEMENT",
        "quality": "PRELIMINARY",
        "historical_rule_history_complete": False,
        "liquidation_validated": False,
    }


def compile_historical_liquidation_evidence(root, sources):
    """Compile pinned article evidence; no historical rule gaps are filled."""
    articles = []
    identities = set()
    for code, report_hash in sources:
        identity = (code, report_hash)
        if identity in identities:
            raise ValueError("Duplicate margin-tier source selection")
        identities.add(identity)
        report, raw = _load_probe(root, code, report_hash)
        articles.append(_article_facts(report, raw))
    articles.sort(key=lambda row: (row["effective_at"], row["code"]))

    all_symbols = sorted(
        {schedule["symbol"] for article in articles for schedule in article["usd_m_symbols"]}
    )
    report = {
        "schema": SCHEMA,
        "articles": articles,
        "source_count": len(articles),
        "symbols": all_symbols,
        "causally_announced_change_count": sum(
            article["new_schedule_causally_announced_before_effective"] for article in articles
        ),
        "retrospective_change_count": sum(
            not article["new_schedule_causally_announced_before_effective"] for article in articles
        ),
        "position_cohort_policy_observed": any(
            article["position_cohort_selection_required"] for article in articles
        ),
        "maintenance_amounts_complete": False,
        "maintenance_deductions_complete": False,
        "exchange_liquidation_value_validation_complete": False,
        "historical_liquidation_rules_complete": False,
        "contract_rules_emitted": 0,
        "liquidation_validated": False,
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    report["evidence_hash"] = digest(report)
    return json.loads(canonical(report))
