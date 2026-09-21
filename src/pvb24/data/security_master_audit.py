"""Compile a fail-closed historical Security Master evidence/obligation audit.

M11V archive-reconciled lifecycle facts are stronger than M11X retained-announcement recovery.
Recovered announcements can add PRELIMINARY start/delisting evidence, but they cannot resolve an
UNKNOWN archive boundary, prove classification, or establish a complete change stream.
"""

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pvb24.data.archive import FINAL_START
from pvb24.ids import canonical, digest
from pvb24.types import utc

INPUT_SCHEMA = "PVB24_PARTIAL_HISTORICAL_METADATA_EVIDENCE_V1"
RECOVERY_SCHEMA = "PVB24_RETAINED_ANNOUNCEMENT_RECOVERY_V2"
CONFLICT_RESOLUTION_SCHEMA = "PVB24_LISTING_CONFLICT_RESOLUTION_V1"
CONFLICT_ACTIVITY_SCHEMA = "PVB24_LISTING_CONFLICT_ACTIVITY_V1"
OUTPUT_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V3"
CONSISTENT = "CONSISTENT_EVENT_BOUNDARY_ONLY"
UNKNOWN = "UNKNOWN"


def _time(value):
    if not isinstance(value, str):
        raise TypeError("Canonical timestamp string required")
    result = utc(datetime.fromisoformat(value))
    if result >= FINAL_START:
        raise ValueError("Final Test security-master evidence is LOCKED")
    return result


def _load_m11v(path, expected_sha256):
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


def _load_recovery(path, expected_sha256):
    path = Path(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned M11X recovery report hash changed")
    report = json.loads(raw)
    if (
        report.get("schema") != RECOVERY_SCHEMA
        or report.get("final_test_access") != "LOCKED"
        or report.get("quality") != "PRELIMINARY"
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
        or report.get("historical_universe_complete") is not False
        or report.get("security_history_complete") is not False
        or report.get("full_security_rows_emitted") != 0
    ):
        raise ValueError("Locked PRELIMINARY M11X recovery evidence required")
    source_pin = report.get("source_qualification_report_sha256")
    if not isinstance(source_pin, str) or not re.fullmatch(r"[0-9a-f]{64}", source_pin):
        raise ValueError("Pinned source qualification identity required")
    recorded_hash = report.get("recovery_hash")
    unhashed = dict(report)
    unhashed.pop("recovery_hash", None)
    if recorded_hash != digest(unhashed):
        raise ValueError("M11X recovery content hash mismatch")
    recovered = report.get("recovered")
    if not isinstance(recovered, list) or len(recovered) != report.get("recovered_article_count"):
        raise ValueError("M11X recovered article count changed")
    if report.get("retrospective_count") != len(report.get("retrospective", [])):
        raise ValueError("M11X retrospective count changed")
    if report.get("remaining_semantic_unqualified_count") != len(report.get("remaining", [])):
        raise ValueError("M11X remaining semantic count changed")
    return report


def _load_conflict_resolution(path, expected_sha256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned listing-conflict resolution hash changed")
    report = json.loads(raw)
    if (
        report.get("schema") != CONFLICT_RESOLUTION_SCHEMA
        or report.get("final_test_access") != "LOCKED"
        or report.get("quality") != "PRELIMINARY"
        or report.get("historical_universe_complete") is not False
        or report.get("security_history_complete") is not False
        or report.get("full_security_rows_emitted") != 0
    ):
        raise ValueError("Locked PRELIMINARY listing-conflict resolution required")
    recorded = report.get("resolution_hash")
    unhashed = dict(report)
    unhashed.pop("resolution_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("Listing-conflict resolution content hash changed")
    return report


def _load_conflict_activity(path, expected_sha256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned listing-conflict activity hash changed")
    report = json.loads(raw)
    if (
        report.get("schema") != CONFLICT_ACTIVITY_SCHEMA
        or report.get("final_test_access") != "LOCKED"
        or report.get("quality") != "PRELIMINARY"
        or report.get("historical_universe_complete") is not False
        or report.get("archive_absence_proves_inactivity") is not False
        or report.get("source_failures") != []
    ):
        raise ValueError("Source-clean PRELIMINARY listing-conflict activity required")
    recorded = report.get("activity_hash")
    unhashed = dict(report)
    unhashed.pop("activity_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("Listing-conflict activity content hash changed")
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != report.get("candidate_count"):
        raise ValueError("Listing-conflict activity candidate count changed")
    return report


def _revision(code, source_sha256, fact):
    return digest(["M11X_RETAINED_LIFECYCLE_RECOVERY_V2", code, source_sha256, fact])


def _append_listing(evidence, *, symbol, effective, available, source, revision, reconciled):
    if not isinstance(symbol, str) or not symbol.endswith("USDT"):
        raise ValueError("Explicit USDT listing symbol required")
    effective, available = _time(effective), _time(available)
    if available > effective:
        raise ValueError("Listing evidence became available after its effective time")
    evidence[symbol].append(
        {
            "symbol": symbol,
            "effective_from": effective,
            "available_at": available,
            "source": source,
            "revision_id": revision,
            "boundary_reconciled": reconciled,
        }
    )


def _append_delisting(evidence, *, symbol, effective, available, source, revision, reconciled):
    if not isinstance(symbol, str) or not symbol.endswith("USDT"):
        raise ValueError("Explicit USDT delisting symbol required")
    effective, available = _time(effective), _time(available)
    if available > effective:
        raise ValueError("Delisting evidence became available after its effective time")
    evidence[symbol].append(
        {
            "symbol": symbol,
            "effective_from": effective,
            "available_at": available,
            "source": source,
            "revision_id": revision,
            "boundary_reconciled": reconciled,
        }
    )


def _dedupe(events):
    by_identity = {}
    for event in events:
        key = (
            event["symbol"],
            event["effective_from"],
            event["source"],
            event["revision_id"],
            event["boundary_reconciled"],
        )
        prior = by_identity.get(key)
        if prior is not None and canonical(prior) != canonical(event):
            raise ValueError("Conflicting lifecycle evidence identity")
        by_identity[key] = event
    return sorted(
        by_identity.values(),
        key=lambda row: (
            row["symbol"],
            row["effective_from"],
            not row["boundary_reconciled"],
            row["revision_id"],
        ),
    )


def compile_security_master_obligations(
    path,
    expected_sha256,
    recovery_path=None,
    recovery_sha256=None,
    conflict_resolution_path=None,
    conflict_resolution_sha256=None,
    conflict_activity_path=None,
    conflict_activity_sha256=None,
):
    """Compile only source-backed partial transitions and explicit completion obligations."""
    source = _load_m11v(path, expected_sha256)
    if (recovery_path is None) != (recovery_sha256 is None):
        raise ValueError("Recovery path and SHA-256 must be supplied together")
    recovery = _load_recovery(recovery_path, recovery_sha256) if recovery_path is not None else None
    conflict_args = (
        conflict_resolution_path,
        conflict_resolution_sha256,
        conflict_activity_path,
        conflict_activity_sha256,
    )
    if any(value is not None for value in conflict_args) and not all(
        value is not None for value in conflict_args
    ):
        raise ValueError("Conflict resolution/activity paths and SHA-256 pins must be supplied together")
    resolution = (
        _load_conflict_resolution(conflict_resolution_path, conflict_resolution_sha256)
        if conflict_resolution_path is not None
        else None
    )
    activity = (
        _load_conflict_activity(conflict_activity_path, conflict_activity_sha256)
        if conflict_activity_path is not None
        else None
    )
    if resolution is not None:
        if recovery is None:
            raise ValueError("Conflict resolution requires the pinned recovery report")
        if resolution["inputs"].get("recovery_sha256") != recovery_sha256:
            raise ValueError("Conflict resolution/recovery SHA-256 pins disagree")
        if resolution["inputs"].get("recovery_hash") != recovery["recovery_hash"]:
            raise ValueError("Conflict resolution/recovery content identities disagree")

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

    listing_evidence = defaultdict(list)
    delisting_evidence = defaultdict(list)

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
        _append_listing(
            listing_evidence,
            symbol=symbol,
            effective=row["event_at"],
            available=row["available_at"],
            source=row["source"],
            revision=row["revision_id"],
            reconciled=True,
        )

    unresolved_rows = []
    unresolved_symbols = set()
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
        unresolved_symbols.add(symbol)
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

    for row in delistings:
        symbol = row.get("symbol")
        if (
            not isinstance(symbol, str)
            or not symbol.endswith("USDT")
            or row.get("boundary_status") != CONSISTENT
            or row.get("security_transition_emitted") is not False
        ):
            raise ValueError("Unsupported delisting evidence")
        _append_delisting(
            delisting_evidence,
            symbol=symbol,
            effective=row["event_at"],
            available=row["available_at"],
            source=row["source"],
            revision=row["revision_id"],
            reconciled=True,
        )

    if recovery is not None:
        for article in recovery["recovered"]:
            kind = article.get("kind")
            if kind not in ("LISTING", "DELISTING"):
                raise ValueError("Recovered lifecycle kind unsupported")
            if (
                article.get("historical_verified") is not False
                or article.get("source_retained") is not True
            ):
                raise ValueError("Recovered source qualification flags changed")
            available = article.get("available_at")
            source_url = article.get("article_url")
            source_sha = article.get("source_sha256")
            code = article.get("code")
            facts = article.get("facts")
            if (
                not isinstance(source_url, str)
                or not isinstance(source_sha, str)
                or not re.fullmatch(r"[0-9a-f]{64}", source_sha)
                or not isinstance(code, str)
                or not isinstance(facts, list)
                or not facts
            ):
                raise ValueError("Recovered source provenance required")
            for fact in facts:
                symbol = fact.get("symbol")
                revision = _revision(code, source_sha, fact)
                if kind == "LISTING":
                    if (
                        fact.get("contract_type") != "PERPETUAL"
                        or fact.get("quote_asset") != "USDT"
                    ):
                        raise ValueError("Recovered listing must be explicit USDT perpetual")
                    _append_listing(
                        listing_evidence,
                        symbol=symbol,
                        effective=fact["launch_at"],
                        available=available,
                        source=source_url,
                        revision=revision,
                        reconciled=False,
                    )
                else:
                    _append_delisting(
                        delisting_evidence,
                        symbol=symbol,
                        effective=fact["scheduled_settlement_at"],
                        available=available,
                        source=source_url,
                        revision=revision,
                        reconciled=False,
                    )

    applied_cancellations = []
    if resolution is not None:
        for item in resolution.get("cancellations", []):
            symbol = item.get("symbol")
            effective = _time(item.get("canceled_effective_from"))
            revision = item.get("canceled_revision_id")
            matches = [
                row
                for row in listing_evidence.get(symbol, [])
                if row["effective_from"] == effective and row["revision_id"] == revision
            ]
            if len(matches) != 1:
                raise ValueError("Conflict cancellation must match exactly one listing evidence row")
            listing_evidence[symbol].remove(matches[0])
            applied_cancellations.append(
                {
                    "symbol": symbol,
                    "effective_from": effective,
                    "revision_id": revision,
                    "reason": item.get("reason"),
                    "cancellation_source": item.get("cancellation_source"),
                    "cancellation_source_sha256": item.get("cancellation_source_sha256"),
                }
            )
        supplemental = resolution.get("supplemental_listings")
        if (
            not isinstance(supplemental, list)
            or len(supplemental) != resolution.get("supplemental_listing_count")
        ):
            raise ValueError("Conflict supplemental listing count changed")
        for item in supplemental:
            if (
                item.get("contract_type") != "PERPETUAL"
                or item.get("quote_asset") != "USDT"
                or item.get("historical_verified") is not False
                or item.get("universe_eligible") is not False
            ):
                raise ValueError("Supplemental listing evidence flags changed")
            _append_listing(
                listing_evidence,
                symbol=item["symbol"],
                effective=item["effective_from"],
                available=item["available_at"],
                source=item["source"],
                revision=item["revision_id"],
                reconciled=False,
            )

    activity_exact = []
    activity_unknown = []
    activity_contradicted = []
    if activity is not None:
        activity_by_key = {}
        for item in activity["candidates"]:
            symbol = item.get("symbol")
            effective = _time(item.get("effective_from"))
            key = (symbol, effective)
            if key in activity_by_key:
                raise ValueError("Duplicate listing-conflict activity candidate")
            status = item.get("archive_boundary_status")
            if status not in (
                "CONSISTENT_EVENT_BOUNDARY_ONLY",
                "UNKNOWN",
                "CONTRADICTED_BY_ARCHIVE_ACTIVITY",
            ):
                raise ValueError("Unsupported listing-conflict activity state")
            activity_by_key[key] = item

        for symbol, rows in list(listing_evidence.items()):
            retained = []
            for row in rows:
                item = activity_by_key.get((symbol, row["effective_from"]))
                if item is None:
                    retained.append(row)
                    continue
                status = item["archive_boundary_status"]
                if status == "CONSISTENT_EVENT_BOUNDARY_ONLY":
                    row = {**row, "boundary_reconciled": True}
                    activity_exact.append(
                        {"symbol": symbol, "effective_from": row["effective_from"]}
                    )
                    retained.append(row)
                elif status == "UNKNOWN":
                    activity_unknown.append(
                        {"symbol": symbol, "effective_from": row["effective_from"]}
                    )
                    retained.append(row)
                else:
                    activity_contradicted.append(
                        {
                            "symbol": symbol,
                            "effective_from": row["effective_from"],
                            "blocking_obligation": "REJECT_CONTRADICTED_LISTING_START",
                        }
                    )
            listing_evidence[symbol] = retained

    listing_evidence = {symbol: _dedupe(rows) for symbol, rows in listing_evidence.items()}
    delisting_evidence = {symbol: _dedupe(rows) for symbol, rows in delisting_evidence.items()}

    active_transitions = []
    listing_conflicts = []
    selected_starts = {}
    for symbol, rows in sorted(listing_evidence.items()):
        by_time = defaultdict(list)
        for row in rows:
            by_time[row["effective_from"]].append(row)
        times = sorted(by_time)
        reconciled_times = sorted(
            {row["effective_from"] for row in rows if row["boundary_reconciled"]}
        )
        if len(times) == 1:
            selected = by_time[times[0]]
        elif len(reconciled_times) == 1:
            selected = by_time[reconciled_times[0]]
            listing_conflicts.append(
                {
                    "symbol": symbol,
                    "selected_reconciled_start": reconciled_times[0],
                    "other_announced_starts": [
                        time for time in times if time != reconciled_times[0]
                    ],
                    "blocking_obligation": "RESOLVE_RELISTING_OR_DUPLICATE_START_SEMANTICS",
                }
            )
        else:
            listing_conflicts.append(
                {
                    "symbol": symbol,
                    "selected_reconciled_start": None,
                    "other_announced_starts": times,
                    "blocking_obligation": "RESOLVE_RELISTING_OR_DUPLICATE_START_SEMANTICS",
                }
            )
            continue
        effective = selected[0]["effective_from"]
        selected_starts[symbol] = effective
        active_transitions.append(
            {
                "symbol": symbol,
                "transition": "ACTIVE_LISTING",
                "effective_from": effective,
                "available_at": min(row["available_at"] for row in selected),
                "trading_start": effective,
                "classification": "UNKNOWN",
                "evidence_count": len(selected),
                "boundary_reconciled": any(row["boundary_reconciled"] for row in selected),
                "sources": [
                    {
                        "source": row["source"],
                        "revision_id": row["revision_id"],
                        "boundary_reconciled": row["boundary_reconciled"],
                    }
                    for row in selected
                ],
                "historical_verified": False,
                "universe_eligible": False,
            }
        )

    inactive_transitions = []
    unpaired_delistings = []
    ambiguous_delistings = []
    for symbol, rows in sorted(delisting_evidence.items()):
        for row in rows:
            start = selected_starts.get(symbol)
            conflict = any(item["symbol"] == symbol for item in listing_conflicts)
            if start is None or start >= row["effective_from"] or conflict:
                target = ambiguous_delistings if conflict else unpaired_delistings
                target.append(
                    {
                        **row,
                        "blocking_obligation": (
                            "RESOLVE_RELISTING_BEFORE_DELISTING"
                            if conflict
                            else "ACQUIRE_UNAMBIGUOUS_TRADING_START_BEFORE_DELISTING"
                        ),
                    }
                )
                continue
            inactive_transitions.append(
                {
                    "symbol": symbol,
                    "transition": "INACTIVE_DELISTED",
                    "effective_from": row["effective_from"],
                    "available_at": row["available_at"],
                    "trading_start": start,
                    "classification": "UNKNOWN",
                    "boundary_reconciled": row["boundary_reconciled"],
                    "source": row["source"],
                    "revision_id": row["revision_id"],
                    "historical_verified": False,
                    "universe_eligible": False,
                }
            )

    active_transitions.sort(key=lambda row: (row["symbol"], row["effective_from"]))
    inactive_transitions.sort(key=lambda row: (row["symbol"], row["effective_from"]))
    unresolved_rows.sort(key=lambda row: (row["symbol"], row["event_at"]))
    listing_conflicts.sort(key=lambda row: row["symbol"])
    unpaired_delistings.sort(key=lambda row: (row["symbol"], row["effective_from"]))
    ambiguous_delistings.sort(key=lambda row: (row["symbol"], row["effective_from"]))

    symbols = sorted(
        {
            *listing_evidence,
            *delisting_evidence,
            *(row["symbol"] for row in unresolved_rows),
        }
    )
    active_symbols = {row["symbol"] for row in active_transitions}
    delisted_symbols = {row["symbol"] for row in inactive_transitions}
    conflict_symbols = {row["symbol"] for row in listing_conflicts}
    by_symbol = []
    for symbol in symbols:
        obligations = ["ACQUIRE_CAUSAL_CLASSIFICATION_HISTORY", "PROVE_COMPLETE_CHANGE_STREAM"]
        if symbol in unresolved_symbols:
            obligations.append("RESOLVE_LISTING_BOUNDARY")
        if symbol in conflict_symbols:
            obligations.append("RESOLVE_RELISTING_OR_DUPLICATE_START_SEMANTICS")
        if symbol in delisting_evidence and symbol not in delisted_symbols:
            obligations.append("PAIR_DELISTING_WITH_UNAMBIGUOUS_TRADING_START")
        by_symbol.append(
            {
                "symbol": symbol,
                "has_listing_evidence": symbol in listing_evidence,
                "has_selected_trading_start": symbol in active_symbols,
                "has_unresolved_listing_boundary": symbol in unresolved_symbols,
                "has_delisting_evidence": symbol in delisting_evidence,
                "has_paired_inactive_transition": symbol in delisted_symbols,
                "obligations": sorted(set(obligations)),
                "full_security_history_complete": False,
            }
        )

    report = {
        "schema": OUTPUT_SCHEMA,
        "inputs": {
            "m11v_sha256": expected_sha256,
            "m11v_evidence_hash": source["evidence_hash"],
            "recovery_sha256": recovery_sha256,
            "recovery_hash": recovery["recovery_hash"] if recovery is not None else None,
            "source_qualification_report_sha256": (
                recovery["source_qualification_report_sha256"] if recovery is not None else None
            ),
            "conflict_resolution_sha256": conflict_resolution_sha256,
            "conflict_resolution_hash": (
                resolution["resolution_hash"] if resolution is not None else None
            ),
            "conflict_activity_sha256": conflict_activity_sha256,
            "conflict_activity_hash": activity["activity_hash"] if activity is not None else None,
        },
        "applied_cancellation_count": len(applied_cancellations),
        "applied_cancellations": sorted(
            applied_cancellations, key=lambda row: (row["symbol"], row["effective_from"])
        ),
        "activity_exact_boundary_count": len(activity_exact),
        "activity_exact_boundaries": sorted(
            activity_exact, key=lambda row: (row["symbol"], row["effective_from"])
        ),
        "activity_unknown_boundary_count": len(activity_unknown),
        "activity_unknown_boundaries": sorted(
            activity_unknown, key=lambda row: (row["symbol"], row["effective_from"])
        ),
        "activity_contradicted_boundary_count": len(activity_contradicted),
        "activity_contradicted_boundaries": sorted(
            activity_contradicted, key=lambda row: (row["symbol"], row["effective_from"])
        ),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "selected_active_transition_count": len(active_transitions),
        "selected_active_transitions": active_transitions,
        "archive_reconciled_active_transition_count": sum(
            row["boundary_reconciled"] for row in active_transitions
        ),
        "announcement_only_active_transition_count": sum(
            not row["boundary_reconciled"] for row in active_transitions
        ),
        "selected_inactive_transition_count": len(inactive_transitions),
        "selected_inactive_transitions": inactive_transitions,
        "archive_reconciled_inactive_transition_count": sum(
            row["boundary_reconciled"] for row in inactive_transitions
        ),
        "announcement_only_inactive_transition_count": sum(
            not row["boundary_reconciled"] for row in inactive_transitions
        ),
        "unresolved_listing_count": len(unresolved_rows),
        "unresolved_listings": unresolved_rows,
        "listing_start_conflict_count": len(listing_conflicts),
        "listing_start_conflicts": listing_conflicts,
        "unpaired_delisting_count": len(unpaired_delistings),
        "unpaired_delistings": unpaired_delistings,
        "ambiguous_delisting_count": len(ambiguous_delistings),
        "ambiguous_delistings": ambiguous_delistings,
        "recovery_remaining_semantic_unqualified_count": (
            recovery["remaining_semantic_unqualified_count"] if recovery is not None else None
        ),
        "recovery_retrospective_count": (
            recovery["retrospective_count"] if recovery is not None else None
        ),
        "symbol_obligations": by_symbol,
        "classification_history_complete": False,
        "rename_relisting_history_complete": False,
        "source_window_coverage_complete": False,
        "title_filter_recall_verified": False,
        "historical_publication_times_verified": False,
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
