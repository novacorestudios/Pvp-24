"""Pinned pre-Final listing/delisting candidate inventory.

Catalog titles are discovery hints only. They never become lifecycle facts or trading eligibility.
Only complete, locked M11O slices may enter this inventory; article bodies must be independently
acquired and semantically qualified by the announcement decoder before any attestation.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from pvb24.data.announcement_catalog import CATALOGS, catalog_time, load_slice
from pvb24.data.announcements import BASE as ARTICLE_BASE
from pvb24.data.archive import FINAL_START
from pvb24.ids import canonical, digest

SCHEMA = "PVB24_ANNOUNCEMENT_CANDIDATE_INVENTORY_V1"

_LISTING_HINTS = (
    re.compile(r"\b(?:launch|launches|launching)\b.*\bperpetual\b", re.I),
    re.compile(r"\b(?:list|lists|listing)\b.*\b(?:futures|perpetual)\b", re.I),
    re.compile(
        r"\b(?:futures|perpetual)\b.*\b(?:listing|launch)\b.*"
        r"\b(?:delay|delayed|postpone|postponed|reschedule|rescheduled)\b",
        re.I,
    ),
)
_DELISTING_HINTS = (
    re.compile(r"\b(?:delist|delists|delisting)\b.*\b(?:futures|perpetual|contract)\b", re.I),
    re.compile(r"\b(?:futures|perpetual|contract)\b.*\b(?:delist|delisting)\b", re.I),
)


def _candidate_kind(catalog_id, title):
    patterns = _LISTING_HINTS if catalog_id == 48 else _DELISTING_HINTS
    return CATALOGS[catalog_id] if any(pattern.search(title) for pattern in patterns) else None


def _build_candidate_inventory(*reports):
    """Transform already revalidated report payloads; use the public pinned loader.

    The function deliberately does not fetch article bodies and does not infer symbols from titles.
    Unmatched titles remain counted as reviewed catalog rows but are not promoted to candidates.
    """

    if not reports:
        raise ValueError("At least one pinned announcement catalog slice required")
    windows = set()
    seen_catalogs = set()
    candidates = {}
    reviewed_rows = 0
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("Announcement catalog report object required")
        catalog_id = report.get("catalog_id")
        if catalog_id not in CATALOGS or catalog_id in seen_catalogs:
            raise ValueError("Exactly one report per reviewed announcement catalog required")
        seen_catalogs.add(catalog_id)
        if (
            report.get("schema") != "PVB24_ANNOUNCEMENT_CATALOG_SLICE_V1"
            or report.get("status") != "ACQUIRED"
            or report.get("catalog_slice_complete") is not True
            or report.get("final_test_access") != "LOCKED"
        ):
            raise ValueError("Complete locked announcement catalog slice required")
        start = catalog_time(report.get("window_start"))
        end = catalog_time(report.get("window_end"))
        if not start < end <= FINAL_START:
            raise ValueError("Strict pre-Final inventory window required")
        windows.add((start, end))
        rows = report.get("in_window_articles")
        if not isinstance(rows, list) or digest(rows) != report.get("article_hash"):
            raise ValueError("Pinned in-window article selection required")
        for row in rows:
            reviewed_rows += 1
            if (
                row.get("catalog_id") != catalog_id
                or row.get("catalog_scope") != CATALOGS[catalog_id]
            ):
                raise ValueError("Catalog row identity mismatch")
            released = catalog_time(row.get("released_at"))
            if not start <= released < end:
                raise ValueError("Catalog row escapes pinned pre-Final window")
            code, title = row.get("code"), row.get("title")
            if not isinstance(code, str) or not isinstance(title, str) or not title.strip():
                raise ValueError("Explicit article identity and title required")
            kind = _candidate_kind(catalog_id, title)
            if kind is None:
                continue
            candidate = {
                "catalog_id": catalog_id,
                "catalog_scope": CATALOGS[catalog_id],
                "article_id": row.get("article_id"),
                "code": code,
                "title": title.strip(),
                "released_at": released,
                "article_url": ARTICLE_BASE + code,
                "qualification": "BODY_REVIEW_REQUIRED",
                "lifecycle_fact": False,
            }
            prior = candidates.get(code)
            if prior is not None and canonical(prior) != canonical(candidate):
                raise ValueError("Candidate article identity conflicts across pinned catalogs")
            candidates[code] = candidate
    if len(windows) != 1:
        raise ValueError("Candidate catalogs must share one exact pre-Final window")
    start, end = windows.pop()
    ordered = sorted(candidates.values(), key=lambda row: (row["released_at"], row["code"]))
    result = {
        "schema": SCHEMA,
        "quality": "PRELIMINARY",
        "window_start": start,
        "window_end": end,
        "final_test_access": "LOCKED",
        "catalogs": sorted(seen_catalogs),
        "reviewed_catalog_rows": reviewed_rows,
        "unmatched_catalog_rows": reviewed_rows - len(ordered),
        "title_filter_recall_verified": False,
        "historical_publication_times_verified": False,
        "operational_ready": False,
        "live_enabled": False,
        "candidates": ordered,
        "candidate_hash": digest(ordered),
        "historical_universe_complete": False,
        "security_master_complete": False,
        "lifecycle_complete": False,
        "performance_run": False,
    }
    return result


@dataclass(frozen=True)
class CatalogSlice:
    root: Path
    report: str
    sha256: str


def build_candidate_inventory(*sources):
    """Build only from externally pinned reports and revalidated retained pages.

    No fetch, implicit latest revision, or title-derived lifecycle/availability.
    """
    if not sources or any(not isinstance(source, CatalogSlice) for source in sources):
        raise ValueError("Pinned CatalogSlice source selections required")
    reports = [
        load_slice(source.root, source.report, expected_report_sha256=source.sha256)
        for source in sources
    ]
    result = _build_candidate_inventory(*reports)
    pins = {
        report["catalog_id"]: source.sha256 for report, source in zip(reports, sources, strict=True)
    }
    result["source_reports"] = sorted(
        [
            {
                "catalog_id": report["catalog_id"],
                "report_sha256": source.sha256,
                "report": source.report,
                "start_page": report["start_page"],
                "page_size": report["page_size"],
                "article_hash": report["article_hash"],
                "pages": report["pages"],
            }
            for report, source in zip(reports, sources, strict=True)
        ],
        key=lambda row: row["catalog_id"],
    )
    for candidate in result["candidates"]:
        candidate["source_report_sha256"] = pins[candidate["catalog_id"]]
    result["candidate_hash"] = digest(result["candidates"])
    result["source_page_chain_revalidated"] = True
    result["implementation_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["inventory_hash"] = digest(result)
    return result
