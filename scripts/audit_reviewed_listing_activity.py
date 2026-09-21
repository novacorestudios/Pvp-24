"""Acquire Binance Vision activity for pinned M11X reviewed listing facts."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.reviewed_listing_activity import acquire_reviewed_listing_activity  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(ROOT)
    facts = json.loads(args.facts.read_bytes())
    report = acquire_reviewed_listing_activity(args.root, facts)
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "candidate_count": report["candidate_count"],
                "source_failures": report["source_failures"],
                "statuses": {
                    row["symbol"]: row["archive_boundary_status"]
                    for row in report["candidates"]
                },
                "activity_hash": report["activity_hash"],
            }
        )
    )
    return 2 if report["source_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
