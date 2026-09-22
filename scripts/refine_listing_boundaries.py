"""Compile conservative post-launch corroboration for unresolved listing boundaries."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.listing_boundary_refinement import (  # noqa: E402
    compile_listing_boundary_refinement,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--security-master", type=Path, required=True)
    parser.add_argument("--security-master-sha256", required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--lifecycle-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    report = compile_listing_boundary_refinement(
        args.security_master,
        args.security_master_sha256,
        args.lifecycle,
        args.lifecycle_sha256,
    )
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace different listing-boundary refinement")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "input_unresolved_listing_count": report["input_unresolved_listing_count"],
                "resolved_announcement_boundary_count": report[
                    "resolved_announcement_boundary_count"
                ],
                "remaining_unresolved_listing_count": report[
                    "remaining_unresolved_listing_count"
                ],
                "historical_universe_complete": report["historical_universe_complete"],
                "refinement_hash": report["refinement_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
