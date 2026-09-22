"""Offline recovery of retained announcement sources for M11X.

Previously qualified facts must replay identically. Only content-addressed retained semantic
failures may be promoted into PRELIMINARY lifecycle facts. Recovery uses bounded body patterns
observed in the retained source set, never titles alone and never network access.
"""

import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pvb24.data.announcement_qualification import (
    QUALIFIED,
    SEMANTIC_UNQUALIFIED,
    qualify_candidate,
)
from pvb24.data.announcement_qualification import (
    SCHEMA as QUALIFICATION_SCHEMA,
)
from pvb24.data.announcements import POLICY, legacy_html_text, strict_json, text
from pvb24.data.archive import FINAL_START
from pvb24.ids import canonical, digest
from pvb24.types import utc

SCHEMA = "PVB24_RETAINED_ANNOUNCEMENT_RECOVERY_V2"
_LISTING_TIME = re.compile(
    r"(\d{4}[/-]\d{2}[/-]\d{2}\s+\d{1,2}:\d{2}(?:\s*(?:AM|PM))?)",
    re.IGNORECASE,
)
_DELISTING_TIME = re.compile(
    r"(\d{4}-\d{2}-\d{2}(?:\s+at)?\s+\d{1,2}:\d{2}(?:\s*(?:AM|PM))?)",
    re.IGNORECASE,
)


def _load_old_report(root, expected_sha256):
    root = Path(root)
    path = root / "reports" / f"{expected_sha256}.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned qualification report hash changed")
    report = json.loads(raw)
    if (
        report.get("schema") != QUALIFICATION_SCHEMA
        or report.get("final_test_access") != "LOCKED"
        or report.get("quality") != "PRELIMINARY"
        or report.get("source_fetch_complete") is not True
        or report.get("historical_universe_complete") is not False
        or report.get("security_master_complete") is not False
        or report.get("lifecycle_complete") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
    ):
        raise ValueError("Locked PRELIMINARY qualification report required")
    results = report.get("results")
    if (
        not isinstance(results, list)
        or len(results) != report.get("candidate_count")
        or digest(results) != report.get("results_hash")
    ):
        raise ValueError("Qualification result set changed")
    return report


def _candidate(row):
    return {
        "catalog_id": row["catalog_id"],
        "catalog_scope": row["catalog_scope"],
        "code": row["code"],
        "title": row["title"],
        "released_at": row["catalog_released_at"],
        "article_url": row["article_url"],
    }


def _raw_source(root, row):
    source_hash = row.get("source_sha256")
    source_object = row.get("source_object")
    if (
        row.get("source_retained") is not True
        or not isinstance(source_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", source_hash)
        or source_object != f"objects/{source_hash}.json"
    ):
        raise ValueError("Content-addressed retained source required for offline recovery")
    raw = (Path(root) / source_object).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source_hash:
        raise ValueError("Retained announcement source bytes changed")
    return raw


def _body_text(raw):
    response = strict_json(raw)
    if not isinstance(response, dict) or response.get("success") is not True:
        raise ValueError("Successful retained CMS response required")
    data = response.get("data")
    if not isinstance(data, dict):
        raise ValueError("Retained CMS data object required")
    body = data.get("body")
    if not isinstance(body, str) or not body:
        raise ValueError("Nonempty retained body required")
    stripped = body.lstrip()
    if stripped.startswith("{"):
        return text(strict_json(body))
    if stripped.startswith("<"):
        return legacy_html_text(body)
    raise ValueError("Unsupported retained body encoding")


def _parse_recovery_time(value, *, timezone="UTC"):
    if timezone.upper() != "UTC":
        raise ValueError("Explicit UTC retained lifecycle timestamp required")
    value = value.replace(" at ", " ").replace("/", "-").strip()
    parsed = None
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(value, fmt).replace(tzinfo=UTC)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValueError("Unsupported retained lifecycle timestamp")
    if parsed >= FINAL_START:
        raise ValueError("Final-period metadata facts remain LOCKED")
    return parsed


def _listing_variant_facts(body_text):
    if "binance futures will launch" not in body_text.lower():
        raise ValueError("Explicit Binance Futures launch statement required")
    leverages = re.findall(
        r"(?:select between 1-|up to )(\d+)x leverage",
        body_text,
        flags=re.IGNORECASE,
    )
    if len(set(leverages)) != 1:
        raise ValueError("One explicit announced maximum leverage required")
    maximum = int(leverages[0])
    if not 1 <= maximum <= 125:
        raise ValueError("Unsupported announced maximum leverage")

    facts = []
    grouped = re.compile(
        r"(?:launch\s+|,\s*|\band\s+)(?:a\s+)?"
        r"(?P<names>(?:[A-Z0-9]+/USDT(?:\s*(?:,|and)\s*)?)+)\s+"
        r"perpetual contracts?\s+with trading opening at\s+"
        + _LISTING_TIME.pattern
        + r"\s*\((?P<timezone>UTC(?:[+-]\d{1,2})?)\)",
        flags=re.IGNORECASE,
    )
    for match in grouped.finditer(body_text):
        names = re.findall(r"\b([A-Z0-9]+)/USDT\b", match.group("names"), flags=re.IGNORECASE)
        if not names or len(names) != len(set(name.upper() for name in names)):
            raise ValueError("Unique explicit USDT listing symbols required")
        launch_at = _parse_recovery_time(match.group(2), timezone=match.group("timezone"))
        for name in names:
            facts.append(
                {
                    "symbol": name.upper() + "USDT",
                    "launch_at": launch_at,
                    "max_leverage": maximum,
                    "contract_type": "PERPETUAL",
                    "quote_asset": "USDT",
                }
            )
    if facts:
        if len({fact["symbol"] for fact in facts}) != len(facts):
            raise ValueError("Duplicate recovered listing symbol")
        return sorted(facts, key=lambda fact: fact["symbol"])

    single = re.search(
        r"Binance Futures will launch\s+(?P<symbol>[A-Z0-9]+USDT)\s+"
        r"perpetual contracts?,?\s+with trading open at\s+"
        + _LISTING_TIME.pattern
        + r"\s*\((?P<timezone>UTC(?:[+-]\d{1,2})?)\)",
        body_text,
        flags=re.IGNORECASE,
    )
    if single:
        return [
            {
                "symbol": single.group("symbol").upper(),
                "launch_at": _parse_recovery_time(
                    single.group(2), timezone=single.group("timezone")
                ),
                "max_leverage": maximum,
                "contract_type": "PERPETUAL",
                "quote_asset": "USDT",
            }
        ]

    direct = re.search(
        r"Binance Futures will launch USDT-margined\s+(?P<base>[A-Z0-9]+)\s+"
        r"perpetual contracts?\s+with up to\s+(?P<maximum>\d+)x leverage at\s+"
        + _LISTING_TIME.pattern
        + r"\s*\((?P<timezone>UTC(?:[+-]\d{1,2})?)\)",
        body_text,
        flags=re.IGNORECASE,
    )
    if direct:
        direct_maximum = int(direct.group("maximum"))
        if direct_maximum != maximum or not 1 <= direct_maximum <= 125:
            raise ValueError("Conflicting announced maximum leverage")
        return [
            {
                "symbol": direct.group("base").upper() + "USDT",
                "launch_at": _parse_recovery_time(
                    direct.group(3), timezone=direct.group("timezone")
                ),
                "max_leverage": direct_maximum,
                "contract_type": "PERPETUAL",
                "quote_asset": "USDT",
            }
        ]
    raise ValueError("No additional causal USDT perpetual listing variant qualified")


def _time_matches(value):
    result = []
    for match in _DELISTING_TIME.finditer(value):
        suffix = value[match.end() : match.end() + 16]
        timezone_match = re.match(r"\s*\((UTC(?:[+-]\d{1,2})?)\)", suffix, flags=re.IGNORECASE)
        if timezone_match is None:
            raise ValueError("Explicit UTC retained lifecycle timestamp required")
        when = _parse_recovery_time(match.group(1), timezone=timezone_match.group(1))
        result.append((match.start(), match.end() + timezone_match.end(), when))
    return result


def _append_base_symbol(result, base):
    base = base.upper()
    if base.endswith("USDT"):
        symbol = base
    elif base.endswith(("BUSD", "USD")):
        return
    else:
        symbol = base + "USDT"
    if symbol not in result:
        result.append(symbol)


def _segment_usdt_symbols(segment):
    result = []
    for symbol in re.findall(r"\b[A-Z0-9]+USDT\b", segment):
        if symbol not in result:
            result.append(symbol)

    for base in re.findall(
        r"USDT-Margined\s+([A-Z0-9]+)\s+(?:Perpetual\s+)?Contracts?",
        segment,
        flags=re.IGNORECASE,
    ):
        _append_base_symbol(result, base)

    for match in re.finditer(
        r"([A-Z0-9]+(?:\s*(?:,|and)\s*[A-Z0-9]+)*)\s+"
        r"USDT-Margined\s+Contracts?",
        segment,
        flags=re.IGNORECASE,
    ):
        for base in re.findall(r"\b[A-Z0-9]+\b", match.group(1)):
            if base.upper() != "AND":
                _append_base_symbol(result, base)
    return result


def _apply_cutoffs(facts, body_text):
    cutoff_matches = list(
        re.finditer(
            r"Users are not allowed to open new positions[^.]{0,5000}\.",
            body_text,
            flags=re.IGNORECASE,
        )
    )
    if not cutoff_matches:
        if re.search(
            r"Users are not allowed to open new positions",
            body_text,
            flags=re.IGNORECASE,
        ):
            raise ValueError("Malformed retained new-position cutoff statement")
        return facts
    if len(cutoff_matches) != 1:
        raise ValueError("One explicit retained new-position cutoff statement required")
    sentence = cutoff_matches[0].group(0)
    times = _time_matches(sentence)
    if not times:
        raise ValueError("Explicit retained new-position cutoff time required")

    cutoffs = {}
    if len(times) == 1:
        symbols = re.findall(r"\b[A-Z0-9]+USDT\b", sentence)
        targets = symbols or [fact["symbol"] for fact in facts]
        for symbol in targets:
            cutoffs[symbol] = times[0][2]
    else:
        for index, (_, end, when) in enumerate(times):
            segment_end = times[index + 1][0] if index + 1 < len(times) else len(sentence)
            symbols = re.findall(r"\b[A-Z0-9]+USDT\b", sentence[end:segment_end])
            for symbol in symbols:
                cutoffs[symbol] = when

    result = []
    for fact in facts:
        symbol = fact["symbol"]
        if symbol not in cutoffs:
            raise ValueError("Retained cutoff schedule does not cover every recovered symbol")
        cutoff = cutoffs[symbol]
        if cutoff > fact["scheduled_settlement_at"]:
            raise ValueError("Recovered position cutoff follows settlement")
        result.append({**fact, "entry_cutoff_at": cutoff})
    return result


def _delisting_variant_facts(body_text):
    settlement_matches = list(
        re.finditer(
            r"Binance Futures will [^.]{0,3000}?automatic settlements?[^.]{0,3000}?\.",
            body_text,
            flags=re.IGNORECASE,
        )
    )
    if len(settlement_matches) != 1:
        raise ValueError("One explicit Binance Futures settlement statement required")
    sentence = settlement_matches[0].group(0)
    if "(UTC)" not in sentence:
        raise ValueError("Explicit UTC settlement schedule required")
    times = _time_matches(sentence)
    if not times:
        raise ValueError("Explicit retained settlement time required")

    facts = []
    if "respectively" in sentence.lower() and len(times) > 1:
        quote_symbols = re.findall(
            r"\b[A-Z0-9]+(?:USDT|BUSD)\b",
            sentence[: times[0][0]],
        )
        if len(quote_symbols) == len(times):
            for symbol, (_, _, when) in zip(quote_symbols, times, strict=True):
                if symbol.endswith("USDT"):
                    facts.append({"symbol": symbol, "scheduled_settlement_at": when})
        else:
            base_match = re.search(
                r"([A-Z0-9]+(?:\s*(?:,|and)\s*[A-Z0-9]+)+)\s+"
                r"USDT-Margined\s+Contracts?",
                sentence[: times[0][0]],
                flags=re.IGNORECASE,
            )
            if base_match:
                bases = [
                    token
                    for token in re.findall(r"\b[A-Z0-9]+\b", base_match.group(1))
                    if token.upper() != "AND"
                ]
                if len(bases) == len(times):
                    for base, (_, _, when) in zip(bases, times, strict=True):
                        symbols = []
                        _append_base_symbol(symbols, base)
                        if symbols:
                            facts.append(
                                {
                                    "symbol": symbols[0],
                                    "scheduled_settlement_at": when,
                                }
                            )

    if not facts:
        start = 0
        for position, end, when in times:
            segment = sentence[start:position]
            for symbol in _segment_usdt_symbols(segment):
                facts.append({"symbol": symbol, "scheduled_settlement_at": when})
            start = end

    by_symbol = {}
    for fact in facts:
        symbol = fact["symbol"]
        prior = by_symbol.get(symbol)
        if prior is not None and prior != fact["scheduled_settlement_at"]:
            raise ValueError("Conflicting retained delisting times for one symbol")
        by_symbol[symbol] = fact["scheduled_settlement_at"]
    if not by_symbol:
        raise ValueError("No explicit USDT perpetual delisting facts in retained source")

    normalized = [
        {"symbol": symbol, "scheduled_settlement_at": when}
        for symbol, when in sorted(by_symbol.items())
    ]
    return _apply_cutoffs(normalized, body_text)


def _effective_time(kind, fact):
    return fact["launch_at"] if kind == "LISTING" else fact["scheduled_settlement_at"]


def _specialized_recovery(kind, raw):
    body = _body_text(raw)
    if kind == "LISTING":
        return _listing_variant_facts(body)
    if kind == "DELISTING":
        return _delisting_variant_facts(body)
    raise ValueError("M11X recovery supports listing/delisting facts only")


def _recovered_row(row, replayed, facts, method):
    available_at = (replayed.get("known_updated_at") or replayed["published_at"]) + timedelta(
        seconds=2
    )
    if available_at >= FINAL_START:
        raise ValueError("Recovered source availability crosses locked Final Test")
    if any(utc(_effective_time(row["kind"], fact)) < available_at for fact in facts):
        raise ValueError(
            "Recovered lifecycle fact was not causally available before effective time"
        )
    return {
        "kind": row["kind"],
        "code": row["code"],
        "title": row["title"],
        "old_reason": row["reason"],
        "recovery_method": method,
        "catalog_released_at": row["catalog_released_at"],
        "published_at": replayed["published_at"],
        "known_updated_at": replayed["known_updated_at"],
        "available_at": available_at,
        "availability_policy": POLICY,
        "article_url": row["article_url"],
        "source_sha256": row["source_sha256"],
        "body_sha256": replayed["body_sha256"],
        "facts": facts,
        "facts_hash": digest(facts),
        "historical_verified": False,
        "source_retained": True,
    }


def recover_retained_lifecycle_facts(root, expected_report_sha256):
    report = _load_old_report(root, expected_report_sha256)
    recovered = []
    retrospective = []
    remaining = []
    prior_qualified_count = 0

    for row in report["results"]:
        status = row.get("status")
        if status not in (QUALIFIED, SEMANTIC_UNQUALIFIED):
            raise ValueError("Offline recovery expects retained qualified/semantic rows only")
        raw = _raw_source(root, row)
        replayed = qualify_candidate(_candidate(row), raw)
        if status == QUALIFIED:
            recorded = {
                key: value
                for key, value in row.items()
                if key not in ("retrieved_at", "source_object")
            }
            if canonical(replayed) != canonical(recorded):
                raise ValueError("Previously qualified announcement semantics changed")
            prior_qualified_count += 1
            continue

        facts = None
        method = None
        try:
            specialized_facts = _specialized_recovery(row["kind"], raw)
        except (ValueError, TypeError, KeyError, ArithmeticError) as specialized_exc:
            specialized_facts = None
        if replayed.get("status") == QUALIFIED and specialized_facts is not None:
            if canonical(replayed["facts"]) != canonical(specialized_facts):
                remaining.append(
                    {
                        "code": row["code"],
                        "kind": row["kind"],
                        "title": row["title"],
                        "old_reason": row["reason"],
                        "new_status": SEMANTIC_UNQUALIFIED,
                        "new_reason": "Shared/specialized lifecycle semantics disagree",
                        "source_sha256": row["source_sha256"],
                    }
                )
                continue
            facts = specialized_facts
            method = "VALIDATED_SHARED_DECODER"
        elif replayed.get("status") == QUALIFIED:
            remaining.append(
                {
                    "code": row["code"],
                    "kind": row["kind"],
                    "title": row["title"],
                    "old_reason": row["reason"],
                    "new_status": SEMANTIC_UNQUALIFIED,
                    "new_reason": str(specialized_exc),
                    "source_sha256": row["source_sha256"],
                }
            )
            continue
        elif replayed.get("status") == SEMANTIC_UNQUALIFIED:
            try:
                facts = _specialized_recovery(row["kind"], raw)
                method = "PINNED_RETAINED_BODY_VARIANT_V2"
            except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                remaining.append(
                    {
                        "code": row["code"],
                        "kind": row["kind"],
                        "title": row["title"],
                        "old_reason": row["reason"],
                        "new_status": replayed["status"],
                        "new_reason": str(exc),
                        "source_sha256": row["source_sha256"],
                    }
                )
                continue

        if facts is None:
            remaining.append(
                {
                    "code": row["code"],
                    "kind": row["kind"],
                    "title": row["title"],
                    "old_reason": row["reason"],
                    "new_status": replayed.get("status"),
                    "new_reason": replayed.get("reason"),
                    "source_sha256": row["source_sha256"],
                }
            )
            continue

        try:
            recovered_row = _recovered_row(row, replayed, facts, method)
        except ValueError as exc:
            retrospective.append(
                {
                    "code": row["code"],
                    "kind": row["kind"],
                    "title": row["title"],
                    "reason": str(exc),
                    "source_sha256": row["source_sha256"],
                    "facts": facts,
                    "facts_hash": digest(facts),
                }
            )
            continue
        recovered.append(recovered_row)

    recovered.sort(key=lambda row: (row["available_at"], row["kind"], row["code"]))
    retrospective.sort(key=lambda row: (row["kind"], row["code"]))
    remaining.sort(key=lambda row: (row["kind"], row["code"]))
    listing_facts = [fact for row in recovered if row["kind"] == "LISTING" for fact in row["facts"]]
    delisting_facts = [
        fact for row in recovered if row["kind"] == "DELISTING" for fact in row["facts"]
    ]
    all_symbols = sorted({fact["symbol"] for row in recovered for fact in row["facts"]})
    listing_symbols = sorted({fact["symbol"] for fact in listing_facts})
    delisting_symbols = sorted({fact["symbol"] for fact in delisting_facts})
    remaining_reasons = Counter(row["new_reason"] for row in remaining)

    result = {
        "schema": SCHEMA,
        "source_qualification_report_sha256": expected_report_sha256,
        "source_results_hash": report["results_hash"],
        "source_candidate_count": report["candidate_count"],
        "prior_qualified_count_replayed_identically": prior_qualified_count,
        "recovered_article_count": len(recovered),
        "recovered_fact_count": sum(len(row["facts"]) for row in recovered),
        "recovered_symbol_count": len(all_symbols),
        "recovered_symbols": all_symbols,
        "recovered_listing_article_count": sum(row["kind"] == "LISTING" for row in recovered),
        "recovered_listing_fact_count": len(listing_facts),
        "recovered_listing_symbol_count": len(listing_symbols),
        "recovered_listing_symbols": listing_symbols,
        "recovered_delisting_article_count": sum(row["kind"] == "DELISTING" for row in recovered),
        "recovered_delisting_fact_count": len(delisting_facts),
        "recovered_delisting_symbol_count": len(delisting_symbols),
        "recovered_delisting_symbols": delisting_symbols,
        "recovered": recovered,
        "retrospective_count": len(retrospective),
        "retrospective": retrospective,
        "remaining_semantic_unqualified_count": len(remaining),
        "remaining_status_counts": dict(
            sorted(Counter(row["new_status"] for row in remaining).items())
        ),
        "remaining_reason_counts": dict(sorted(remaining_reasons.items())),
        "remaining": remaining,
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
    result["recovery_hash"] = digest(result)
    return json.loads(canonical(result))


def recover_retained_listing_facts(root, expected_report_sha256):
    """Backward-compatible entrypoint; M11X V2 now recovers listing and delisting facts."""
    return recover_retained_lifecycle_facts(root, expected_report_sha256)
