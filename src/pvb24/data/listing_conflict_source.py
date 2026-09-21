"""Retain explicitly reviewed official Binance CMS sources for M11X listing conflicts.

This is source acquisition only. It does not convert article text into Security rows or resolve
listing boundaries. Semantic conflict resolution must be a separate pinned step.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from pvb24.data.announcements import ARTICLE_CODE, BASE, nodes, strict_json, text
from pvb24.data.archive import FINAL_START, milliseconds
from pvb24.ids import canonical

SCHEMA = "PVB24_LISTING_CONFLICT_SOURCE_V1"


def inspect_listing_conflict_source(code, raw):
    if not isinstance(code, str) or not re.fullmatch(ARTICLE_CODE, code):
        raise ValueError("Explicit official article code required")
    if not raw:
        raise ValueError("Nonempty official CMS response required")
    response = strict_json(raw)
    if not isinstance(response, dict) or response.get("success") is not True:
        raise ValueError("Successful CMS response required")
    data = response.get("data")
    if not isinstance(data, dict) or data.get("code") != code:
        raise ValueError("CMS source identity differs from requested article")
    published_ms = data.get("publishDate")
    updated_ms = data.get("lastUpdateTime")
    if type(published_ms) is not int or published_ms < 0:
        raise ValueError("Explicit publication clock required")
    if type(updated_ms) is not int or updated_ms < 0:
        raise ValueError("Explicit update clock required")
    published = milliseconds(str(published_ms))
    updated = milliseconds(str(updated_ms)) if updated_ms else None
    if published >= FINAL_START or (updated is not None and updated >= FINAL_START):
        raise ValueError("Final-period CMS revision remains LOCKED")
    if updated is not None and updated < published:
        raise ValueError("CMS update predates publication")

    body_raw = data.get("body")
    if not isinstance(body_raw, str) or not body_raw:
        raise ValueError("Nonempty rich-text body required")
    body = strict_json(body_raw)
    body_text = text(body)
    if not body_text:
        raise ValueError("Nonempty rendered article text required")
    if len(list(nodes(body))) > 20000:
        raise ValueError("Bounded article body required")

    result = {
        "schema": SCHEMA,
        "code": code,
        "source": BASE + code,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "body_sha256": hashlib.sha256(body_raw.encode()).hexdigest(),
        "published_at": published,
        "known_updated_at": updated,
        "available_at": (updated or published).timestamp(),
        "body_text": body_text,
        "semantic_resolution_emitted": False,
        "security_rows_emitted": 0,
        "historical_universe_complete": False,
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    return json.loads(canonical(result))


def retain_listing_conflict_source(root, code, raw):
    root = Path(root)
    report = inspect_listing_conflict_source(code, raw)
    (root / "objects").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    source_name = report["source_sha256"] + ".json"
    (root / "objects" / source_name).write_bytes(raw)
    report["source_object"] = "objects/" + source_name
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    report_sha = hashlib.sha256(encoded).hexdigest()
    (root / "reports" / f"{report_sha}.json").write_bytes(encoded)
    return report, report_sha
