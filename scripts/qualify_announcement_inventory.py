"""Acquire and semantically qualify replay-pinned announcement candidates."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcement_qualification import SOURCE_ERROR, qualify_inventory  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-root", type=Path, required=True)
    parser.add_argument("--inventory-report", required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    report, path = qualify_inventory(
        args.inventory_root,
        args.inventory_report,
        args.output,
        expected_inventory_sha256=args.inventory_sha256,
    )
    summary = {
        "schema": "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_SUMMARY_V2",
        "report": str(path),
        "report_sha256": path.stem,
        "candidate_count": report["candidate_count"],
        "status_counts": report["status_counts"],
        "qualified_review_requests": len(report["review_requests"]),
        "source_fetch_complete": report["source_fetch_complete"],
        "requested_window_complete": False,
        "upper_boundary_coverage_proven": False,
        "historical_universe_complete": False,
        "operational_ready": False,
        "final_test_access": "LOCKED",
    }
    print(json.dumps(json.loads(canonical(summary)), indent=2))
    return 2 if report["status_counts"].get(SOURCE_ERROR, 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
