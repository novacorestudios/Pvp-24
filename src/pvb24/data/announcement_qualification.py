"""Replay-bound semantic qualification of pre-Final announcement candidates.

Catalog titles remain discovery hints. A candidate becomes a qualification record only after the
official article detail response is identity/timing checked and its retained rich-text body passes
the existing strict lifecycle fact extractor. Results remain PRELIMINARY and never establish a
complete security master, complete lifecycle coverage, or production readiness.
"""

import hashlib
import json
import re
import urllib.error
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pvb24.data.acquisition import object_write
from pvb24.data.announcement_catalog import catalog_time
from pvb24.data.announcement_inventory import SCHEMA as INVENTORY_SCHEMA
from pvb24.data.announcement_inventory import (
    CatalogSlice,
    build_candidate_inventory,
)
from pvb24.data.announcements import (
    ARTICLE_CODE,
    MAX_BYTES,
    POLICY,
    extract_facts,
    public_announcement,
    strict_json,
)
from pvb24.data.archive import FINAL_START, milliseconds
from pvb24.ids import canonical, digest

SCHEMA = "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_V1"
QUALIFIED = "QUALIFIED_PRELIMINARY"
SEMANTIC_UNQUALIFIED = "SEMANTIC_UNQUALIFIED"
POST_FINAL_REVISION_BLOCKED = "POST_FINAL_REVISION_BLOCKED"
IDENTITY_REJECTED = "IDENTITY_REJECTED"
SOURCE_ERROR = "SOURCE_ERROR"


def _report_path(report_path, expected_sha256):
    path = Path(report_path)
    if (
        path.is_absolute()
        or len(path.parts) != 2
        or path.parts[0] != "reports"
        or not isinstance(expected_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        or path.name != expected_sha256 + ".json"
    ):
        raise ValueError("Explicit pinned candidate inventory report required")
    return path


def load_inventory(root, report_path, *, expected_sha256):
    """Revalidate the inventory report and both retained catalog page chains."""

    root = Path(root)
    path = _report_path(report_path, expected_sha256)
    raw = (root / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Pinned candidate inventory report changed")
    report = strict_json(raw)
    if (
        report.get("schema") != INVENTORY_SCHEMA
        or report.get("quality") != "PRELIMINARY"
        or report.get("final_test_access") != "LOCKED"
        or report.get("source_page_chain_revalidated") is not True
        or report.get("operational_ready") is not False
        or report.get("live_enabled") is not False
        or any(
            report.get(key) is not False
            for key in (
                "historical_universe_complete",
                "security_master_complete",
                "lifecycle_complete",
                "performance_run",
            )
        )
    ):
        raise ValueError("Locked PRELIMINARY source-revalidated candidate inventory required")
    start = catalog_time(report.get("window_start"))
    end = catalog_time(report.get("window_end"))
    if not start < end <= FINAL_START:
        raise ValueError("Strict pre-Final candidate inventory window required")
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or digest(candidates) != report.get("candidate_hash"):
        raise ValueError("Candidate inventory hash mismatch")
    if len({row.get("code") for row in candidates}) != len(candidates):
        raise ValueError("Unique candidate article identities required")
    unhashed = dict(report)
    inventory_hash = unhashed.pop("inventory_hash", None)
    if inventory_hash != digest(unhashed):
        raise ValueError("Candidate inventory content hash mismatch")

    source_reports = report.get("source_reports")
    if not isinstance(source_reports, list) or [
        row.get("catalog_id") for row in source_reports
    ] != [
        48,
        161,
    ]:
        raise ValueError("Pinned catalog 48/161 source reports required")
    sources = [
        CatalogSlice(
            root / "source" / f"catalog-{row['catalog_id']}",
            row["report"],
            row["report_sha256"],
        )
        for row in source_reports
    ]
    rebuilt = build_candidate_inventory(*sources)
    if canonical(rebuilt) != canonical(report):
        raise ValueError("Candidate inventory differs from retained catalog page chains")
    return report


def _kind(candidate):
    catalog_id = candidate.get("catalog_id")
    if catalog_id == 48:
        return "LISTING"
    if catalog_id == 161:
        return "DELISTING"
    raise ValueError("Reviewed listing/delisting catalog candidate required")


def _base(candidate):
    code = candidate.get("code")
    if not isinstance(code, str) or not re.fullmatch(ARTICLE_CODE, code):
        raise ValueError("Explicit candidate article code required")
    released = catalog_time(candidate.get("released_at"))
    if released >= FINAL_START:
        raise ValueError("Candidate catalog row crosses locked Final Test")
    url = candidate.get("article_url")
    expected = (
        "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode="
        + code
    )
    if url != expected:
        raise ValueError("Candidate official article URL changed")
    return code, released, url, _kind(candidate)


def qualify_candidate(candidate, raw):
    """Qualify one source response without turning unsupported text into a lifecycle fact."""

    code, released, url, kind = _base(candidate)
    source_sha256 = hashlib.sha256(raw).hexdigest()
    base = {
        "catalog_id": candidate["catalog_id"],
        "catalog_scope": candidate["catalog_scope"],
        "code": code,
        "title": candidate["title"],
        "catalog_released_at": released,
        "article_url": url,
        "kind": kind,
        "source_sha256": source_sha256,
        "source_retained": False,
        "historical_verified": False,
        "original_revision_as_published_verified": False,
        "lifecycle_fact": False,
    }
    if not raw or len(raw) > MAX_BYTES:
        return {**base, "status": IDENTITY_REJECTED, "reason": "BOUNDED_SOURCE_REQUIRED"}
    try:
        response = strict_json(raw)
        if not isinstance(response, dict) or response.get("success") is not True:
            raise ValueError("Successful CMS response required")
        data = response.get("data")
        if not isinstance(data, dict) or data.get("code") != code:
            raise ValueError("Announcement identity differs from candidate catalog row")
        publish_ms = data.get("publishDate")
        update_ms = data.get("lastUpdateTime")
        if (
            type(publish_ms) is not int
            or publish_ms < 0
            or type(update_ms) is not int
            or update_ms < 0
        ):
            raise ValueError("Explicit integer publication/update clocks required")
        published = milliseconds(str(publish_ms))
        updated = milliseconds(str(update_ms)) if update_ms else None
        if published >= FINAL_START:
            raise ValueError("Source publication crosses locked Final Test")
        if published.date() != released.date():
            raise ValueError("Catalog/detail publication day mismatch")
        if updated is not None and updated < published:
            raise ValueError("Source update precedes publication")
        version = data.get("version")
        if not isinstance(version, str) or not version:
            raise ValueError("Explicit CMS version label required")
    except (ValueError, TypeError, KeyError) as exc:
        return {**base, "status": IDENTITY_REJECTED, "reason": str(exc)}

    chronology = {
        **base,
        "published_at": published,
        "known_updated_at": updated,
        "cms_version": version,
    }
    if updated is not None and updated >= FINAL_START:
        return {
            **chronology,
            "status": POST_FINAL_REVISION_BLOCKED,
            "reason": "Current CMS revision is not causally usable before Final Test",
        }

    body = data.get("body")
    if not isinstance(body, str):
        return {
            **chronology,
            "status": IDENTITY_REJECTED,
            "reason": "Rich-text body string required",
        }
    body_sha256 = hashlib.sha256(body.encode()).hexdigest()
    try:
        facts = extract_facts(kind, strict_json(body))
        effective_key = "launch_at" if kind == "LISTING" else "scheduled_settlement_at"
        if any(fact[effective_key] <= published for fact in facts):
            raise ValueError("Announcement must precede its scheduled lifecycle change")
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        return {
            **chronology,
            "status": SEMANTIC_UNQUALIFIED,
            "reason": str(exc),
            "body_sha256": body_sha256,
            "source_retained": True,
        }

    facts_hash = digest(facts)
    request = {
        "code": code,
        "published_day": published.date().isoformat(),
        "kind": kind,
        "body_sha256": body_sha256,
        "facts_hash": facts_hash,
    }
    return {
        **chronology,
        "status": QUALIFIED,
        "body_sha256": body_sha256,
        "facts": facts,
        "facts_hash": facts_hash,
        "review_request": request,
        "available_at": (updated or published) + timedelta(seconds=2),
        "availability_policy": POLICY,
        "source_retained": True,
    }


def qualify_inventory(
    inventory_root,
    inventory_report,
    output,
    *,
    expected_inventory_sha256,
    fetch=public_announcement,
):
    """Acquire and semantically qualify every title-selected candidate exactly once."""

    started = datetime.now(UTC)
    inventory = load_inventory(
        inventory_root,
        inventory_report,
        expected_sha256=expected_inventory_sha256,
    )
    output = Path(output)
    results = []
    for candidate in inventory["candidates"]:
        try:
            raw = fetch(candidate["article_url"])
            retrieved = datetime.now(UTC)
            qualified = qualify_candidate(candidate, raw)
            qualified["retrieved_at"] = retrieved
        except (OSError, urllib.error.URLError) as exc:
            code, released, url, kind = _base(candidate)
            qualified = {
                "catalog_id": candidate["catalog_id"],
                "catalog_scope": candidate["catalog_scope"],
                "code": code,
                "title": candidate["title"],
                "catalog_released_at": released,
                "article_url": url,
                "kind": kind,
                "status": SOURCE_ERROR,
                "reason": f"{type(exc).__name__}: {exc}",
                "source_retained": False,
                "historical_verified": False,
                "original_revision_as_published_verified": False,
                "lifecycle_fact": False,
                "retrieved_at": datetime.now(UTC),
            }
        else:
            if qualified["source_retained"]:
                name = object_write(output / "objects", raw, ".json")
                if name != qualified["source_sha256"] + ".json":
                    raise ValueError("Content-addressed announcement object mismatch")
                qualified["source_object"] = "objects/" + name
        results.append(qualified)

    if len(results) != len(inventory["candidates"]):
        raise ValueError("Every candidate must produce exactly one qualification outcome")
    counts = Counter(row["status"] for row in results)
    requests = [row["review_request"] for row in results if row["status"] == QUALIFIED]
    report = {
        "schema": SCHEMA,
        "quality": "PRELIMINARY",
        "started_at": started,
        "completed_at": datetime.now(UTC),
        "inventory_report": str(inventory_report),
        "inventory_report_sha256": expected_inventory_sha256,
        "inventory_hash": inventory["inventory_hash"],
        "window_start": inventory["window_start"],
        "window_end": inventory["window_end"],
        "final_test_access": "LOCKED",
        "requested_window_complete": False,
        "upper_boundary_coverage_proven": False,
        "candidate_count": len(results),
        "status_counts": dict(sorted(counts.items())),
        "source_fetch_complete": counts[SOURCE_ERROR] == 0,
        "results": results,
        "results_hash": digest(results),
        "review_requests": requests,
        "review_requests_hash": digest(requests),
        "historical_publication_times_verified": False,
        "historical_universe_complete": False,
        "security_master_complete": False,
        "lifecycle_complete": False,
        "performance_run": False,
        "operational_ready": False,
        "live_enabled": False,
    }
    encoded = canonical(report).encode()
    name = object_write(output / "reports", encoded, ".json")
    return json.loads(encoded), output / "reports" / name
