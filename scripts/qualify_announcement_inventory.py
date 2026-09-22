"""Acquire and semantically qualify replay-pinned announcement candidates."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcement_qualification import (  # noqa: E402
    SOURCE_ERROR,
    qualify_inventory,
    retained_source_fetch,
)
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-root", type=Path, required=True)
    parser.add_argument("--inventory-report", required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retained-source-root", type=Path)
    parser.add_argument("--retained-report-sha256")
    args = parser.parse_args()

    if (args.retained_source_root is None) != (args.retained_report_sha256 is None):
        raise SystemExit("Both retained source arguments are required together")

    verify(ROOT)
    fetch = (
        retained_source_fetch(args.retained_source_root, args.retained_report_sha256)
        if args.retained_source_root is not None
        else None
    )
    kwargs = {"fetch": fetch} if fetch is not None else {}
    report, path = qualify_inventory(
        args.inventory_root,
        args.inventory_report,
        args.output,
        expected_inventory_sha256=args.inventory_sha256,
        **kwargs,
    )
    summary = {
        "schema": "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_SUMMARY_V3",
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
