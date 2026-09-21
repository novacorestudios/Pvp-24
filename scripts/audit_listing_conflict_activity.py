"""Acquire checksum-verified M11X activity evidence for conflicting listing starts."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from verify_provenance import verify  # noqa: E402

from pvb24.data.listing_conflict_activity import acquire_listing_conflict_activity  # noqa: E402
from pvb24.types import utc  # noqa: E402


def candidate(symbol, value, source):
    return {
        "symbol": symbol,
        "effective_from": utc(datetime.fromisoformat(value)),
        "candidate_source": source,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(ROOT)
    candidates = [
        candidate("BNTUSDT", "2020-12-28T07:00:00+00:00", "RECOVERED_ANNOUNCEMENT"),
        candidate("BNTUSDT", "2023-08-10T12:00:00+00:00", "PINNED_CONFLICT_SOURCE"),
        candidate("CHZUSDT", "2020-12-29T07:00:00+00:00", "RECOVERED_ANNOUNCEMENT"),
        candidate("CHZUSDT", "2021-01-21T07:00:00+00:00", "RECOVERED_ANNOUNCEMENT"),
        candidate("UNFIUSDT", "2020-12-28T07:00:00+00:00", "RECOVERED_ANNOUNCEMENT"),
        candidate("UNFIUSDT", "2021-02-19T07:00:00+00:00", "RECOVERED_ANNOUNCEMENT"),
    ]
    report = acquire_listing_conflict_activity(args.root, candidates)
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "candidate_count": report["candidate_count"],
                "source_failures": report["source_failures"],
                "statuses": {
                    row["symbol"] + "@" + row["effective_from"]: row["archive_boundary_status"]
                    for row in report["candidates"]
                },
                "activity_hash": report["activity_hash"],
            }
        )
    )
    return 2 if report["source_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
