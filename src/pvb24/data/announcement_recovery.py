"""Offline recovery of retained announcement sources under a widened listing decoder.

Previously qualified facts must replay identically. Only retained semantic failures may
be promoted into recovered PRELIMINARY facts, and no network access occurs here.
"""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from pvb24.data.announcement_qualification import (
    QUALIFIED,
    SCHEMA as QUALIFICATION_SCHEMA,
    SEMANTIC_UNQUALIFIED,
    qualify_candidate,
)
from pvb24.ids import canonical, digest

SCHEMA = "PVB24_RETAINED_ANNOUNCEMENT_RECOVERY_V1"


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


def recover_retained_listing_facts(root, expected_report_sha256):
    report = _load_old_report(root, expected_report_sha256)
    recovered = []
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

        if replayed.get("status") == QUALIFIED:
            if row.get("kind") != "LISTING":
                raise ValueError("M11X recovery may promote listing facts only")
            recovered.append(
                {
                    "code": row["code"],
                    "title": row["title"],
                    "old_reason": row["reason"],
                    "catalog_released_at": row["catalog_released_at"],
                    "published_at": replayed["published_at"],
                    "known_updated_at": replayed["known_updated_at"],
                    "available_at": replayed["available_at"],
                    "article_url": row["article_url"],
                    "source_sha256": row["source_sha256"],
                    "body_sha256": replayed["body_sha256"],
                    "facts": replayed["facts"],
                    "facts_hash": replayed["facts_hash"],
                    "historical_verified": False,
                    "source_retained": True,
                }
            )
        else:
            remaining.append(
                {
                    "code": row["code"],
                    "kind": row["kind"],
                    "title": row["title"],
                    "old_reason": row["reason"],
                    "new_status": replayed["status"],
                    "new_reason": replayed.get("reason"),
                    "source_sha256": row["source_sha256"],
                }
            )

    recovered.sort(key=lambda row: (row["published_at"], row["code"]))
    remaining.sort(key=lambda row: (row["kind"], row["code"]))
    symbols = sorted({fact["symbol"] for row in recovered for fact in row["facts"]})
    remaining_reasons = Counter(row["new_reason"] for row in remaining)

    result = {
        "schema": SCHEMA,
        "source_qualification_report_sha256": expected_report_sha256,
        "source_results_hash": report["results_hash"],
        "source_candidate_count": report["candidate_count"],
        "prior_qualified_count_replayed_identically": prior_qualified_count,
        "recovered_article_count": len(recovered),
        "recovered_fact_count": sum(len(row["facts"]) for row in recovered),
        "recovered_symbol_count": len(symbols),
        "recovered_symbols": symbols,
        "recovered": recovered,
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
