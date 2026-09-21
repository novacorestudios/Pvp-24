"""Audit Security Master obligations from pinned M11V historical metadata evidence.

This module deliberately emits only evidence-backed partial transitions. It never invents
classification, trading start, rename/relisting history, or current activity from later state.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pvb24.data.archive import FINAL_START
from pvb24.ids import canonical, digest
from pvb24.types import utc

INPUT_SCHEMA = "PVB24_PARTIAL_HISTORICAL_METADATA_EVIDENCE_V1"
OUTPUT_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V1"
CONSISTENT = "CONSISTENT_EVENT_BOUNDARY_ONLY"
UNKNOWN = "UNKNOWN"


def _time(value):
    if not isinstance(value, str):
        raise TypeError("Canonical timestamp string required")
    result = utc(datetime.fromisoformat(value))
    if result >= FINAL_START:
        raise ValueError("Final Test security-master evidence is LOCKED")
    return result


def _load_pinned(path, expected_sha256):
    path = Path(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned M11V historical metadata report hash changed")
    report = json.loads(raw)
    if (
        report.get("schema") != INPUT_SCHEMA
        or report.get("final_test_access") != "LOCKED"
        or report.get("quality") != "PRELIMINARY"
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
        or report.get("historical_universe_complete") is not False
        or report.get("security_history_complete") is not False
    ):
        raise ValueError("Locked PRELIMINARY M11V evidence required")
    recorded_hash = report.get("evidence_hash")
    unhashed = dict(report)
    unhashed.pop("evidence_hash", None)
    if recorded_hash != digest(unhashed):
        raise ValueError("M11V evidence hash mismatch")
    return report


def compile_security_master_obligations(path, expected_sha256):
    """Compile only proven partial transitions and explicit completion obligations."""
    source = _load_pinned(path, expected_sha256)

    listings = source.get("listing_candidates")
    unresolved = source.get("unresolved_listings")
    delistings = source.get("delisting_events")
    if (
        not isinstance(listings, list)
        or len(listings) != source.get("listing_candidate_count")
        or not isinstance(unresolved, list)
        or len(unresolved) != source.get("unresolved_listing_count")
        or not isinstance(delistings, list)
        or len(delistings) != source.get("delisting_event_count")
    ):
        raise ValueError("M11V lifecycle evidence counts changed")

    confirmed = {}
    active_transitions = []
    for row in listings:
        symbol = row.get("symbol")
        if (
            not isinstance(symbol, str)
            or not symbol.endswith("USDT")
            or row.get("boundary_status") != CONSISTENT
            or row.get("classification") != "UNKNOWN"
            or row.get("historical_verified") is not False
            or row.get("contract_type") != "PERPETUAL"
            or row.get("quote_asset") != "USDT"
        ):
            raise ValueError("Unsupported confirmed listing evidence")
        event_at = _time(row["event_at"])
        available_at = _time(row["available_at"])
        if available_at > event_at:
            raise ValueError("Confirmed listing must be available no later than its event")
        prior = confirmed.get(symbol)
        identity = (event_at, row.get("revision_id"))
        if prior is not None and prior != identity:
            raise ValueError("Multiple confirmed listing starts require relisting semantics")
        confirmed[symbol] = identity
        active_transitions.append(
            {
                "symbol": symbol,
                "transition": "ACTIVE_LISTING",
                "effective_from": event_at,
                "available_at": available_at,
                "trading_start": event_at,
                "classification": "UNKNOWN",
                "source": row["source"],
                "revision_id": row["revision_id"],
                "historical_verified": False,
                "universe_eligible": False,
            }
        )

    unresolved_rows = []
    for row in unresolved:
        symbol = row.get("symbol")
        if (
            not isinstance(symbol, str)
            or not symbol.endswith("USDT")
            or row.get("boundary_status") != UNKNOWN
            or row.get("classification") != "UNKNOWN"
            or row.get("historical_verified") is not False
        ):
            raise ValueError("Unsupported unresolved listing evidence")
        unresolved_rows.append(
            {
                "symbol": symbol,
                "event_at": _time(row["event_at"]),
                "available_at": _time(row["available_at"]),
                "source": row["source"],
                "revision_id": row["revision_id"],
                "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
            }
        )

    inactive_transitions = []
    unpaired_delistings = []
    for row in delistings:
        symbol = row.get("symbol")
        if (
            not isinstance(symbol, str)
            or not symbol.endswith("USDT")
            or row.get("boundary_status") != CONSISTENT
            or row.get("security_transition_emitted") is not False
        ):
            raise ValueError("Unsupported delisting evidence")
        event_at = _time(row["event_at"])
        available_at = _time(row["available_at"])
        if available_at > event_at:
            raise ValueError("Delisting evidence must be available no later than settlement")
        prior = confirmed.get(symbol)
        if prior is None:
            unpaired_delistings.append(
                {
                    "symbol": symbol,
                    "event_at": event_at,
                    "available_at": available_at,
                    "source": row["source"],
                    "revision_id": row["revision_id"],
                    "blocking_obligation": "ACQUIRE_TRADING_START_BEFORE_DELISTING",
                }
            )
            continue
        trading_start, _ = prior
        if trading_start >= event_at:
            raise ValueError("Delisting cannot precede confirmed trading start")
        inactive_transitions.append(
            {
                "symbol": symbol,
                "transition": "INACTIVE_DELISTED",
                "effective_from": event_at,
                "available_at": available_at,
                "trading_start": trading_start,
                "classification": "UNKNOWN",
                "source": row["source"],
                "revision_id": row["revision_id"],
                "historical_verified": False,
                "universe_eligible": False,
            }
        )

    symbols = sorted(
        {
            *(row["symbol"] for row in active_transitions),
            *(row["symbol"] for row in unresolved_rows),
            *(row["symbol"] for row in unpaired_delistings),
            *(row["symbol"] for row in inactive_transitions),
        }
    )
    by_symbol = []
    active_symbols = {row["symbol"] for row in active_transitions}
    unresolved_symbols = {row["symbol"] for row in unresolved_rows}
    delisted_symbols = {
        row["symbol"] for row in unpaired_delistings + inactive_transitions
    }
    for symbol in symbols:
        obligations = ["ACQUIRE_CAUSAL_CLASSIFICATION_HISTORY", "PROVE_COMPLETE_CHANGE_STREAM"]
        if symbol in unresolved_symbols:
            obligations.append("RESOLVE_LISTING_BOUNDARY")
        if symbol in delisted_symbols and symbol not in active_symbols:
            obligations.append("ACQUIRE_TRADING_START_BEFORE_DELISTING")
        by_symbol.append(
            {
                "symbol": symbol,
                "has_confirmed_listing_start": symbol in active_symbols,
                "has_unresolved_listing_boundary": symbol in unresolved_symbols,
                "has_delisting_evidence": symbol in delisted_symbols,
                "obligations": sorted(set(obligations)),
                "full_security_history_complete": False,
            }
        )

    report = {
        "schema": OUTPUT_SCHEMA,
        "input_sha256": expected_sha256,
        "input_evidence_hash": source["evidence_hash"],
        "symbol_count": len(symbols),
        "symbols": symbols,
        "confirmed_active_transition_count": len(active_transitions),
        "confirmed_active_transitions": sorted(
            active_transitions, key=lambda row: (row["symbol"], row["effective_from"])
        ),
        "confirmed_inactive_transition_count": len(inactive_transitions),
        "confirmed_inactive_transitions": sorted(
            inactive_transitions, key=lambda row: (row["symbol"], row["effective_from"])
        ),
        "unresolved_listing_count": len(unresolved_rows),
        "unresolved_listings": sorted(
            unresolved_rows, key=lambda row: (row["symbol"], row["event_at"])
        ),
        "unpaired_delisting_count": len(unpaired_delistings),
        "unpaired_delistings": sorted(
            unpaired_delistings, key=lambda row: (row["symbol"], row["event_at"])
        ),
        "symbol_obligations": by_symbol,
        "classification_history_complete": False,
        "rename_relisting_history_complete": False,
        "source_window_coverage_complete": False,
        "title_filter_recall_verified": False,
        "security_change_stream_complete": False,
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "complete_attestation_emitted": False,
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    report["audit_hash"] = digest(report)
    return json.loads(canonical(report))
