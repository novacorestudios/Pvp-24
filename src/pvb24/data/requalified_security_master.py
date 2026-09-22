"""Integrate requalified lifecycle evidence with the pinned Security Master audit.

The integration is deliberately fail-closed. It does not emit eligible securities. It
records which already-selected transitions are retrospectively corroborated, which remain
UNKNOWN, and which must be rejected because official archive activity contradicts the
announced boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from pvb24.data.announcement_requalification import validate_requalification_summary
from pvb24.ids import canonical, digest

SCHEMA = "PVB24_REQUALIFIED_SECURITY_MASTER_DELTA_V1"
BASE_SCHEMA = "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V5"
LIFECYCLE_SCHEMA = "PVB24_REQUALIFIED_LIFECYCLE_ARCHIVE_ACTIVITY_V1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
CONSISTENT = "CONSISTENT_EVENT_BOUNDARY_ONLY"
UNKNOWN = "UNKNOWN"
CONTRADICTED = "CONTRADICTED_BY_ARCHIVE_ACTIVITY"


def _load(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError("Explicit SHA-256 pin required")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned Security Master integration input hash changed")
    return json.loads(raw)


def _validate_base(report):
    if (
        report.get("schema") != BASE_SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("security_history_complete") is not False
        or report.get("historical_universe_complete") is not False
        or report.get("full_security_rows_emitted") != 0
        or report.get("complete_attestation_emitted") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
    ):
        raise ValueError("Locked PRELIMINARY Security Master audit required")
    unhashed = dict(report)
    recorded = unhashed.pop("audit_hash", None)
    if recorded != digest(unhashed):
        raise ValueError("Security Master audit hash mismatch")
    if report.get("selected_active_transition_count") != len(
        report.get("selected_active_transitions", [])
    ):
        raise ValueError("Security Master active transition count mismatch")
    if report.get("selected_inactive_transition_count") != len(
        report.get("selected_inactive_transitions", [])
    ):
        raise ValueError("Security Master inactive transition count mismatch")
    return report


def _validate_lifecycle(report, requalification):
    if (
        report.get("schema") != LIFECYCLE_SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("source_failures") != []
        or report.get("historical_universe_complete") is not False
        or report.get("security_master_complete") is not False
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
        or report.get("source_requalification_hash") != requalification["requalification_hash"]
        or report.get("qualification_results_hash") != requalification["results_hash"]
        or report.get("qualification_review_requests_hash")
        != requalification["review_requests_hash"]
    ):
        raise ValueError("Source-clean locked requalified lifecycle evidence required")

    rows = report.get("reconciliations")
    if (
        not isinstance(rows, list)
        or report.get("reconciliation_count") != len(rows)
        or report.get("reconciliation_hash") != digest(rows)
    ):
        raise ValueError("Requalified lifecycle reconciliation count/hash mismatch")
    counts = Counter(row.get("status") for row in rows)
    if report.get("status_counts") != dict(sorted(counts.items())):
        raise ValueError("Requalified lifecycle status counts mismatch")
    if not set(counts).issubset({CONSISTENT, UNKNOWN, CONTRADICTED}):
        raise ValueError("Unsupported requalified lifecycle status")
    return report


def _transition_map(rows):
    result = {}
    for row in rows:
        key = (row.get("symbol"), row.get("effective_from"))
        if key in result:
            raise ValueError("Duplicate Security Master transition identity")
        result[key] = row
    return result


def compile_requalified_security_master_delta(
    base_path,
    base_sha256,
    requalification_path,
    requalification_sha256,
    lifecycle_path,
    lifecycle_sha256,
):
    base = _validate_base(_load(base_path, base_sha256))
    requalification = validate_requalification_summary(
        _load(requalification_path, requalification_sha256)
    )
    lifecycle = _validate_lifecycle(_load(lifecycle_path, lifecycle_sha256), requalification)

    articles = {row["code"]: row for row in requalification["results"]}
    if len(articles) != len(requalification["results"]):
        raise ValueError("Duplicate requalification article code")

    active = _transition_map(base["selected_active_transitions"])
    inactive = _transition_map(base["selected_inactive_transitions"])
    unpaired = {
        (row["symbol"], row["effective_from"]): row for row in base.get("unpaired_delistings", [])
    }

    exact_active = []
    unknown_active = []
    contradicted_active = []
    exact_active_missing = []
    unknown_active_missing = []
    exact_inactive = []
    exact_unpaired = []

    for row in lifecycle["reconciliations"]:
        code = row.get("article_code")
        article = articles.get(code)
        if (
            article is None
            or article.get("kind") != row.get("kind")
            or article.get("source_sha256") != row.get("article_source_sha256")
            or canonical(row.get("fact")) not in {canonical(fact) for fact in article.get("facts", [])}
        ):
            raise ValueError("Lifecycle reconciliation lacks exact requalification lineage")

        identity = (row["symbol"], row["event_at"])
        status = row["status"]
        item = {
            "symbol": row["symbol"],
            "kind": row["kind"],
            "effective_from": row["event_at"],
            "article_code": code,
            "article_source_sha256": row["article_source_sha256"],
            "source": article["article_url"],
            "available_at": article["available_at"],
            "status": status,
        }

        if row["kind"] == "LISTING":
            if status == CONSISTENT:
                if identity in active:
                    exact_active.append(
                        {
                            **item,
                            "base_boundary_reconciled": active[identity]["boundary_reconciled"],
                        }
                    )
                else:
                    exact_active_missing.append(item)
            elif status == UNKNOWN:
                if identity in active:
                    unknown_active.append(item)
                else:
                    unknown_active_missing.append(item)
            else:
                if identity in active:
                    contradicted_active.append(
                        {
                            **item,
                            "contradictions": row.get("contradictions", []),
                            "blocking_obligation": "REJECT_CONTRADICTED_LISTING_START",
                        }
                    )
        elif row["kind"] == "DELISTING":
            if status != CONSISTENT:
                raise ValueError("Non-consistent requalified delisting is unsupported")
            if identity in inactive:
                exact_inactive.append(item)
            elif identity in unpaired:
                exact_unpaired.append(
                    {
                        **item,
                        "blocking_obligation": "ACQUIRE_UNAMBIGUOUS_TRADING_START_BEFORE_DELISTING",
                    }
                )
        else:
            raise ValueError("Unsupported lifecycle kind")

    newly_reconciled_active = sum(
        row["base_boundary_reconciled"] is False for row in exact_active
    )
    recommended_active = base["selected_active_transition_count"] - len(contradicted_active)
    recommended_reconciled = (
        base["archive_reconciled_active_transition_count"] + newly_reconciled_active
    )
    recommended_announcement_only = recommended_active - recommended_reconciled
    if recommended_active < 0 or recommended_announcement_only < 0:
        raise ValueError("Invalid successor Security Master transition counts")

    report = {
        "schema": SCHEMA,
        "quality": "PRELIMINARY",
        "inputs": {
            "base_security_master_sha256": base_sha256,
            "base_security_master_audit_hash": base["audit_hash"],
            "requalification_sha256": requalification_sha256,
            "requalification_hash": requalification["requalification_hash"],
            "lifecycle_sha256": lifecycle_sha256,
            "lifecycle_reconciliation_hash": lifecycle["reconciliation_hash"],
        },
        "exact_listing_count": sum(
            row["kind"] == "LISTING" and row["status"] == CONSISTENT
            for row in lifecycle["reconciliations"]
        ),
        "unknown_listing_count": sum(
            row["kind"] == "LISTING" and row["status"] == UNKNOWN
            for row in lifecycle["reconciliations"]
        ),
        "contradicted_listing_count": sum(
            row["kind"] == "LISTING" and row["status"] == CONTRADICTED
            for row in lifecycle["reconciliations"]
        ),
        "exact_delisting_count": sum(
            row["kind"] == "DELISTING" and row["status"] == CONSISTENT
            for row in lifecycle["reconciliations"]
        ),
        "base_active_corroborated_count": len(exact_active),
        "base_active_corroborated": exact_active,
        "base_active_newly_reconciled_count": newly_reconciled_active,
        "base_active_unknown_boundary_count": len(unknown_active),
        "base_active_unknown_boundaries": unknown_active,
        "base_active_contradicted_count": len(contradicted_active),
        "base_active_contradicted": contradicted_active,
        "exact_listing_without_base_active_count": len(exact_active_missing),
        "exact_listings_without_base_active": exact_active_missing,
        "unknown_listing_without_base_active_count": len(unknown_active_missing),
        "unknown_listings_without_base_active": unknown_active_missing,
        "base_inactive_corroborated_count": len(exact_inactive),
        "base_inactive_corroborated": exact_inactive,
        "exact_delisting_unpaired_count": len(exact_unpaired),
        "exact_delistings_unpaired": exact_unpaired,
        "recommended_successor_active_transition_count": recommended_active,
        "recommended_successor_archive_reconciled_active_count": recommended_reconciled,
        "recommended_successor_announcement_only_active_count": recommended_announcement_only,
        "classification_history_complete": False,
        "rename_relisting_history_complete": False,
        "source_window_coverage_complete": False,
        "historical_publication_times_verified": False,
        "security_change_stream_complete": False,
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "complete_attestation_emitted": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    report["delta_hash"] = digest(report)
    return json.loads(canonical(report))
