"""Review a source-pinned pre-Final start page for Binance announcement catalogs."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcement_anchor import (  # noqa: E402
    REVIEWED_ANCHORS,
    report_sha256,
    review_anchor_start,
)
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-id", type=int, choices=(48, 161), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-requests", type=int, default=5000)
    args = parser.parse_args()

    verify(ROOT)
    report, path = review_anchor_start(
        REVIEWED_ANCHORS[args.catalog_id],
        args.output,
        max_requests=args.max_requests,
    )
    summary = {
        "schema": "PVB24_ANNOUNCEMENT_CATALOG_ANCHOR_SUMMARY_V1",
        "catalog_id": args.catalog_id,
        "report": str(path),
        "report_sha256": report_sha256(path),
        "anchor_code": report["anchor"]["code"],
        "anchor_released_at": report["anchor"]["released_at"],
        "catalog_total_observed": report["probe"]["catalog_total_observed"],
        "safe_start_page": report["safe_start_page"],
        "safe_start_newest_at": report["safe_start_newest_at"],
        "safe_start_oldest_at": report["safe_start_oldest_at"],
        "final_test_access": "LOCKED",
        "historical_universe_complete": False,
        "operational_ready": False,
    }
    print(json.dumps(json.loads(canonical(summary)), indent=2))


if __name__ == "__main__":
    main()
