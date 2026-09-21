"""Compile retained lifecycle and rule-field evidence without inventing full history.

The compiler joins announcement qualification availability with lifecycle reconciliation
boundaries and independently reviewed tick-change facts.  It can emit PRELIMINARY listing
Security candidates only when an announced listing boundary was separately reconciled as
consistent.  UNKNOWN boundaries stay UNKNOWN.  Field-level rule evidence never becomes a
ContractRules snapshot unless every mandatory rule field is independently sourced elsewhere.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pvb24.data.archive import FINAL_START
from pvb24.data.universe import Security
from pvb24.decimal_math import D, require_decimal
from pvb24.ids import canonical, digest
from pvb24.types import utc

QUALIFICATION_SCHEMA = "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_V3"
LIFECYCLE_SCHEMA = "PVB24_LIFECYCLE_ARCHIVE_ACTIVITY_V3"
TICK_SCHEMA = "PVB24_ANNOUNCEMENT_SOURCE_COVERAGE_V1"
OUTPUT_SCHEMA = "PVB24_PARTIAL_HISTORICAL_METADATA_EVIDENCE_V1"
CONSISTENT = "CONSISTENT_EVENT_BOUNDARY_ONLY"
UNKNOWN = "UNKNOWN"


def _load_pinned(path, expected_hash, *, schema):
    path = Path(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("Pinned historical metadata evidence hash changed")
    payload = json.loads(raw)
    if payload.get("schema") != schema or payload.get("final_test_access") != "LOCKED":
        raise ValueError("Historical metadata evidence schema/holdout policy not qualified")
    return payload


def _time(value):
    parsed = utc(datetime.fromisoformat(value))
    if parsed >= FINAL_START:
        raise ValueError("Final Test metadata evidence is LOCKED")
    return parsed


def _qualified_articles(report):
    rows = {}
    for item in report.get("results", []):
        if item.get("status") != "QUALIFIED_PRELIMINARY":
            continue
        code = item.get("code")
        if not isinstance(code, str) or not code or code in rows:
            raise ValueError("Qualified announcement code must be unique")
        if not item.get("source_retained") or not item.get("source_sha256"):
            raise ValueError("Qualified announcement retained-source provenance required")
        _time(item["available_at"])
        rows[code] = item
    return rows


def _event_time(kind, fact):
    if kind == "LISTING":
        return _time(fact["launch_at"])
    if kind == "DELISTING":
        return _time(fact["scheduled_settlement_at"])
    raise ValueError("Unsupported lifecycle evidence kind")


def _matching_fact(article, reconciliation):
    facts = article.get("facts")
    if not isinstance(facts, list) or not facts:
        raise ValueError("Qualified announcement facts required")
    target = reconciliation.get("fact")
    matches = [fact for fact in facts if canonical(fact) == canonical(target)]
    if len(matches) != 1:
        raise ValueError("Lifecycle fact must match exactly one qualified announcement fact")
    return matches[0]


def compile_partial_historical_metadata(
    qualification_path,
    qualification_sha256,
    lifecycle_path,
    lifecycle_sha256,
    tick_path,
    tick_sha256,
):
    qualification = _load_pinned(
        qualification_path,
        qualification_sha256,
        schema=QUALIFICATION_SCHEMA,
    )
    lifecycle = _load_pinned(lifecycle_path, lifecycle_sha256, schema=LIFECYCLE_SCHEMA)
    ticks = _load_pinned(tick_path, tick_sha256, schema=TICK_SCHEMA)

    if qualification.get("source_fetch_complete") is not True:
        raise ValueError("Complete selected announcement source fetch required")
    source_failures = lifecycle.get("source_failures")
    if not isinstance(source_failures, list) or source_failures:
        raise ValueError("Lifecycle source failures must be an empty explicit list")
    if lifecycle.get("qualification_results_hash") != qualification.get("results_hash"):
        raise ValueError("Lifecycle/qualification result identities disagree")
    if lifecycle.get("qualification_review_requests_hash") != qualification.get(
        "review_requests_hash"
    ):
        raise ValueError("Lifecycle/qualification review identities disagree")

    articles = _qualified_articles(qualification)
    listing_candidates = []
    unresolved_listings = []
    delisting_events = []

    reconciliations = lifecycle.get("reconciliations")
    if not isinstance(reconciliations, list) or len(reconciliations) != lifecycle.get(
        "reconciliation_count"
    ):
        raise ValueError("Lifecycle reconciliation count changed")

    for row in reconciliations:
        kind = row.get("kind")
        status = row.get("status")
        if kind not in ("LISTING", "DELISTING") or status not in (CONSISTENT, UNKNOWN):
            raise ValueError("Unsupported lifecycle reconciliation state")
        symbol = row.get("symbol")
        code = row.get("article_code")
        if not isinstance(symbol, str) or not symbol.endswith("USDT"):
            raise ValueError("Explicit USDT lifecycle symbol required")
        article = articles.get(code)
        if article is None or article.get("kind") != kind:
            raise ValueError("Lifecycle event lacks matching qualified announcement")
        if article.get("source_sha256") != row.get("article_source_sha256"):
            raise ValueError("Lifecycle source revision differs from qualification evidence")
        fact = _matching_fact(article, row)
        event_at = _event_time(kind, fact)
        if event_at != _time(row["event_at"]):
            raise ValueError("Lifecycle event time differs from qualified fact")
        available_at = _time(article["available_at"])
        if available_at > event_at and not (
            fact.get("revision_type") == "POSTPONEMENT"
            and kind == "LISTING"
            and fact.get("previous_launch_at")
        ):
            raise ValueError("Lifecycle fact became available after its own event")

        provenance = {
            "article_code": code,
            "source": article["article_url"],
            "revision_id": article["source_sha256"],
            "available_at": available_at,
            "event_at": event_at,
            "boundary_status": status,
        }

        if kind == "LISTING":
            if fact.get("contract_type") != "PERPETUAL" or fact.get("quote_asset") != "USDT":
                raise ValueError("Only explicit USDT perpetual listing evidence is supported")
            item = {
                **provenance,
                "symbol": symbol,
                "contract_type": fact["contract_type"],
                "quote_asset": fact["quote_asset"],
                "classification": "UNKNOWN",
                "historical_verified": False,
            }
            if status == CONSISTENT:
                listing_candidates.append(item)
            else:
                unresolved_listings.append(item)
        else:
            delisting_events.append(
                {
                    **provenance,
                    "symbol": symbol,
                    "entry_cutoff_at": (
                        _time(fact["entry_cutoff_at"]) if fact.get("entry_cutoff_at") else None
                    ),
                    "scheduled_settlement_at": event_at,
                    "security_transition_emitted": False,
                }
            )

    tick_events = []
    excluded_non_usdt = []
    coverage = ticks.get("coverage")
    if not isinstance(coverage, list):
        raise ValueError("Tick evidence coverage rows required")
    for row in coverage:
        if row.get("kind") != "TICK_CHANGE":
            continue
        fact = row.get("facts")
        if not isinstance(fact, dict):
            raise ValueError("Tick-change fact required")
        symbol = fact.get("symbol")
        if not isinstance(symbol, str):
            raise ValueError("Tick-change symbol required")
        if not symbol.endswith("USDT"):
            excluded_non_usdt.append(symbol)
            continue
        effective_at = _time(fact["effective_at"])
        available_at = _time(row["available_at"])
        if available_at > effective_at:
            raise ValueError("Tick change was not causally available before effective time")
        before, after = D(fact["tick_before"]), D(fact["tick_after"])
        require_decimal(before, positive=True)
        require_decimal(after, positive=True)
        tick_events.append(
            {
                "symbol": symbol,
                "effective_at": effective_at,
                "available_at": available_at,
                "tick_before": before,
                "tick_after": after,
                "source": row["source"],
                "revision_id": row["source_sha256"],
                "historical_verified": False,
                "full_contract_rules_emitted": False,
            }
        )

    listing_candidates.sort(key=lambda x: (x["symbol"], x["event_at"], x["revision_id"]))
    unresolved_listings.sort(key=lambda x: (x["symbol"], x["event_at"], x["revision_id"]))
    delisting_events.sort(key=lambda x: (x["symbol"], x["event_at"], x["revision_id"]))
    tick_events.sort(key=lambda x: (x["symbol"], x["effective_at"], x["revision_id"]))

    report = {
        "schema": OUTPUT_SCHEMA,
        "inputs": {
            "qualification_sha256": qualification_sha256,
            "lifecycle_sha256": lifecycle_sha256,
            "tick_evidence_sha256": tick_sha256,
            "qualification_results_hash": qualification["results_hash"],
            "lifecycle_reconciliation_hash": lifecycle["reconciliation_hash"],
            "tick_data_hash": ticks["data_hash"],
        },
        "listing_candidate_count": len(listing_candidates),
        "listing_candidates": listing_candidates,
        "unresolved_listing_count": len(unresolved_listings),
        "unresolved_listings": unresolved_listings,
        "delisting_event_count": len(delisting_events),
        "delisting_events": delisting_events,
        "tick_field_event_count": len(tick_events),
        "tick_field_events": tick_events,
        "excluded_non_usdt_tick_symbols": sorted(set(excluded_non_usdt)),
        "preliminary_security_rows_emittable": len(listing_candidates),
        "full_security_rows_emitted": 0,
        "full_contract_rule_rows_emitted": 0,
        "classification_complete": False,
        "security_change_stream_complete": False,
        "security_history_complete": False,
        "contract_rule_history_complete": False,
        "historical_universe_complete": False,
        "liquidation_tiers_complete": False,
        "mandatory_rule_gaps": [
            "QUANTITY_STEP",
            "MIN_QUANTITY",
            "MAX_QUANTITY",
            "MIN_NOTIONAL",
            "CONTRACT_SIZE",
            "MAINTENANCE_TIERS",
            "ORDER_CAPABILITIES",
            "LAST_STOP_CAPABILITY",
        ],
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    report["evidence_hash"] = digest(report)
    return json.loads(canonical(report))


def preliminary_listing_securities(report):
    """Materialize only the explicitly safe PRELIMINARY listing candidates.

    UNKNOWN classification intentionally makes these rows ineligible for the PVB-24
    universe until independent classification evidence exists.
    """
    if report.get("schema") != OUTPUT_SCHEMA or report.get("final_test_access") != "LOCKED":
        raise ValueError("Compiled historical metadata evidence required")
    rows = []
    for item in report.get("listing_candidates", []):
        if item.get("boundary_status") != CONSISTENT or item.get("classification") != "UNKNOWN":
            raise ValueError("Only consistent UNKNOWN-classification candidates are permitted")
        rows.append(
            Security(
                symbol=item["symbol"],
                trading_start=_time(item["event_at"]),
                effective_from=_time(item["event_at"]),
                available_at=_time(item["available_at"]),
                classification="UNKNOWN",
                active=True,
                source=item["source"],
                revision_id=item["revision_id"],
                historical_verified=False,
                contract_type=item["contract_type"],
                quote_asset=item["quote_asset"],
            )
        )
    return tuple(rows)
