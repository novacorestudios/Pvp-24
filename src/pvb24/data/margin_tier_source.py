"""Pre-Final official Binance margin-tier announcement source probe.

This module is evidence discovery only. It never creates ContractRules, never derives
maintenance deductions, and never marks liquidation validation complete.
"""

import hashlib
import json
import re
from pathlib import Path

from pvb24.data.announcements import ARTICLE_CODE, BASE, nodes, strict_json, text
from pvb24.data.archive import FINAL_START, milliseconds
from pvb24.ids import canonical

SCHEMA = "PVB24_MARGIN_TIER_SOURCE_PROBE_V1"
MAX_TABLES = 64
MAX_ROWS_PER_TABLE = 128
MAX_CELLS_PER_ROW = 16


def _source_url(code):
    if not re.fullmatch(ARTICLE_CODE, code):
        raise ValueError("Explicit official article code required")
    return BASE + code


def _table_cells(body):
    tables = [node for node in nodes(body) if node.get("tag") == "table"]
    if len(tables) > MAX_TABLES:
        raise ValueError("Too many announcement tables")
    result = []
    for table in tables:
        rows = [node for node in nodes(table) if node.get("tag") == "tr"]
        if len(rows) > MAX_ROWS_PER_TABLE:
            raise ValueError("Announcement table exceeds row bound")
        rendered = []
        for row in rows:
            cells = [text(cell) for cell in row.get("child", [])]
            if len(cells) > MAX_CELLS_PER_ROW:
                raise ValueError("Announcement row exceeds cell bound")
            rendered.append(cells)
        result.append(rendered)
    return result


def inspect_margin_tier_response(code, raw):
    """Inspect one retained CMS response without promoting any trading rule."""
    if not raw:
        raise ValueError("Nonempty announcement response required")
    response = strict_json(raw)
    if not isinstance(response, dict) or response.get("success") is not True:
        raise ValueError("Successful CMS response required")
    data = response.get("data")
    if not isinstance(data, dict) or data.get("code") != code:
        raise ValueError("Announcement identity differs from requested source")
    for field in ("publishDate", "lastUpdateTime"):
        if type(data.get(field)) is not int or data[field] < 0:
            raise ValueError("Explicit integer publication/update clocks required")

    published = milliseconds(str(data["publishDate"]))
    updated = milliseconds(str(data["lastUpdateTime"])) if data["lastUpdateTime"] else None
    if published >= FINAL_START:
        raise ValueError("Final-period announcement access is LOCKED")
    if updated is not None and updated < published:
        raise ValueError("Announcement update predates publication")

    result = {
        "schema": SCHEMA,
        "code": code,
        "source": _source_url(code),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "published_at": published,
        "known_updated_at": updated,
        "final_test_access": "LOCKED",
        "contract_rules_emitted": False,
        "liquidation_validated": False,
    }
    if updated is not None and updated >= FINAL_START:
        result.update(
            {
                "status": "POST_FINAL_REVISION_BLOCKED",
                "body_sha256": None,
                "table_count": None,
                "tables": None,
            }
        )
        return json.loads(canonical(result))

    body_raw = data.get("body")
    if not isinstance(body_raw, str) or not body_raw:
        raise ValueError("Nonempty rich-text body required")
    body = strict_json(body_raw)
    tables = _table_cells(body)
    result.update(
        {
            "status": "PRE_FINAL_REVISION_REVIEWABLE",
            "body_sha256": hashlib.sha256(body_raw.encode()).hexdigest(),
            "table_count": len(tables),
            "tables": tables,
        }
    )
    return json.loads(canonical(result))


def retain_probe(root, code, raw):
    """Retain raw bytes only when the source revision itself is pre-Final."""
    root = Path(root)
    report = inspect_margin_tier_response(code, raw)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    report_bytes = (json.dumps(report, indent=2) + "\n").encode()
    report_hash = hashlib.sha256(report_bytes).hexdigest()
    (root / "reports" / f"{report_hash}.json").write_bytes(report_bytes)

    if report["status"] == "PRE_FINAL_REVISION_REVIEWABLE":
        (root / "objects").mkdir(parents=True, exist_ok=True)
        (root / "objects" / f"{report['source_sha256']}.json").write_bytes(raw)
        report["source_object"] = f"objects/{report['source_sha256']}.json"
    else:
        report["source_object"] = None
    return report, report_hash
