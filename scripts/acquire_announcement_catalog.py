"""Acquire an explicitly reviewed pre-Final Binance announcement catalog slice."""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcement_catalog import acquire_slice  # noqa: E402
from pvb24.data.archive import FINAL_START  # noqa: E402
from pvb24.ids import canonical, digest  # noqa: E402


def time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed.astimezone(UTC)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-id", type=int, choices=(48, 161), required=True)
    parser.add_argument("--start-page", type=int, required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", default=FINAL_START.isoformat())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=100)
    args = parser.parse_args()

    verify(ROOT)
    start, end = time(args.window_start), time(args.window_end)
    if end > FINAL_START:
        raise ValueError("Final Test catalog access remains LOCKED")
    report, path = acquire_slice(
        args.catalog_id,
        args.output,
        start_page=args.start_page,
        start=start,
        end=end,
        max_pages=args.max_pages,
    )
    summary = {
        "schema": "PVB24_ANNOUNCEMENT_CATALOG_DISCOVERY_SUMMARY_V1",
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "catalog_id": args.catalog_id,
        "report_path": str(path),
        "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": report["status"],
        "article_hash": report["article_hash"],
        "in_window_articles": len(report["in_window_articles"]),
        "catalog_slice_complete": report["catalog_slice_complete"],
        "historical_universe_complete": False,
        "security_master_complete": False,
        "lifecycle_complete": False,
        "final_test_access": "LOCKED",
        "performance_run": False,
        "operational_ready": False,
    }
    summary["summary_hash"] = digest(summary)
    print(json.dumps(json.loads(canonical(summary)), indent=2))
    return 0 if report["catalog_slice_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
