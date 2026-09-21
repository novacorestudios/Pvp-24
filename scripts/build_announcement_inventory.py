"""Offline source-pinned candidate inventory. Does not acquire bodies or grant readiness."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.acquisition import object_write  # noqa: E402
from pvb24.data.announcement_inventory import CatalogSlice, build_candidate_inventory  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--slice", nargs=3, action="append", required=True, metavar=("ROOT", "REPORT", "SHA256")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(ROOT)
    sources = [CatalogSlice(Path(root), report, sha) for root, report, sha in args.slice]
    inventory = build_candidate_inventory(*sources)
    name = object_write(args.output / "reports", canonical(inventory).encode(), ".json")
    print(
        canonical(
            {
                "report": str(args.output / "reports" / name),
                "report_sha256": name[:-5],
                "candidates": len(inventory["candidates"]),
                "reviewed_catalog_rows": inventory["reviewed_catalog_rows"],
                "historical_universe_complete": False,
                "operational_ready": False,
                "final_test_access": "LOCKED",
            }
        )
    )


if __name__ == "__main__":
    main()
