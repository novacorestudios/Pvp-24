"""Acquire a catalog slice only from a replay-verified reviewed pre-Final anchor."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcement_anchor import (  # noqa: E402
    REVIEWED_ANCHORS,
    load_anchor_review,
    report_sha256,
    review_anchor_start,
)
from pvb24.data.announcement_catalog import acquire_slice  # noqa: E402
from pvb24.data.archive import FINAL_START  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed.astimezone(UTC)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-id", type=int, choices=(48, 161), required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", default=FINAL_START.isoformat())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-anchor-pages", type=int, default=200)
    parser.add_argument("--max-hint-backoff", type=int, default=20)
    parser.add_argument("--max-slice-pages", type=int, default=100)
    args = parser.parse_args()

    verify(ROOT)
    start, end = time(args.window_start), time(args.window_end)
    anchor = REVIEWED_ANCHORS[args.catalog_id]
    if not start < anchor.released_at < end <= FINAL_START:
        raise ValueError("Reviewed anchor must lie strictly inside the requested pre-Final window")

    anchor_root = args.output / "anchor"
    anchor_report, anchor_path = review_anchor_start(
        anchor,
        anchor_root,
        max_pages=args.max_anchor_pages,
        max_hint_backoff=args.max_hint_backoff,
    )
    anchor_sha = report_sha256(anchor_path)
    checked_anchor = load_anchor_review(
        anchor_root,
        anchor_path.relative_to(anchor_root),
        expected_report_sha256=anchor_sha,
    )

    slice_root = args.output / "slice"
    slice_report, slice_path = acquire_slice(
        args.catalog_id,
        slice_root,
        start_page=checked_anchor["safe_start_page"],
        start=start,
        end=end,
        max_pages=args.max_slice_pages,
    )
    slice_sha = hashlib.sha256(slice_path.read_bytes()).hexdigest()
    articles = slice_report["articles"]
    newest = max((row["released_at"] for row in articles), default=None)
    oldest = min((row["released_at"] for row in articles), default=None)

    summary = {
        "schema": "PVB24_REVIEWED_ANNOUNCEMENT_SLICE_BINDING_V1",
        "catalog_id": args.catalog_id,
        "quality": "PRELIMINARY",
        "window_start": start,
        "window_end": end,
        "anchor_report": str(anchor_path.relative_to(args.output)),
        "anchor_report_sha256": anchor_sha,
        "safe_start_page": checked_anchor["safe_start_page"],
        "safe_start_url": checked_anchor["safe_start_url"],
        "slice_report": str(slice_path.relative_to(args.output)),
        "slice_report_sha256": slice_sha,
        "selected_page_chain_complete": slice_report["catalog_slice_complete"],
        "requested_window_complete": False,
        "upper_boundary_coverage_proven": False,
        "coverage_newest_at": newest,
        "coverage_oldest_at": oldest,
        "historical_universe_complete": False,
        "security_master_complete": False,
        "lifecycle_complete": False,
        "performance_run": False,
        "final_test_access": "LOCKED",
        "operational_ready": False,
        "live_enabled": False,
    }
    print(json.dumps(json.loads(canonical(summary)), indent=2))
    return 0 if slice_report["catalog_slice_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
