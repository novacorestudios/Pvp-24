"""Compile pinned M11X listing-conflict semantic resolution."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from verify_provenance import verify  # noqa: E402

from pvb24.data.listing_conflict_resolution import (  # noqa: E402
    compile_listing_conflict_resolution,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--recovery-sha256", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(ROOT)
    report = compile_listing_conflict_resolution(
        args.recovery, args.recovery_sha256, args.source_root
    )
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "cancellation_count": report["cancellation_count"],
                "supplemental_listing_count": report["supplemental_listing_count"],
                "remaining_conflict_symbols": report["remaining_conflict_symbols"],
                "resolution_hash": report["resolution_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
