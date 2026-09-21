"""Compile retained lifecycle and tick-rule evidence into a fail-closed partial metadata report."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.historical_metadata_evidence import (  # noqa: E402
    compile_partial_historical_metadata,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--qualification-sha256", required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--lifecycle-sha256", required=True)
    parser.add_argument("--tick-evidence", type=Path, required=True)
    parser.add_argument("--tick-evidence-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    result = compile_partial_historical_metadata(
        args.qualification,
        args.qualification_sha256,
        args.lifecycle,
        args.lifecycle_sha256,
        args.tick_evidence,
        args.tick_evidence_sha256,
    )
    encoded = (json.dumps(result, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace a different historical metadata evidence report")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "listing_candidate_count",
                    "unresolved_listing_count",
                    "delisting_event_count",
                    "tick_field_event_count",
                    "historical_universe_complete",
                    "evidence_hash",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
