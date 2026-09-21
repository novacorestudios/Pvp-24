"""Compile semantic facts from the pinned M11X reviewed listing source batch."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.reviewed_listing_facts import compile_reviewed_listing_facts  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(ROOT)
    report = compile_reviewed_listing_facts(args.source_root)
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "source_count": report["source_count"],
                "target_symbols": report["target_symbols"],
                "prior_epoch_disclosure_count": report["prior_epoch_disclosure_count"],
                "classification_hint_count": report["classification_hint_count"],
                "facts_hash": report["facts_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
