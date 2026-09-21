"""Offline M11X replay of retained announcement sources with the widened listing decoder."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcement_recovery import recover_retained_listing_facts  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    report = recover_retained_listing_facts(args.root, args.report_sha256)
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace different M11X recovery report")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "prior_qualified_count_replayed_identically": report[
                    "prior_qualified_count_replayed_identically"
                ],
                "recovered_article_count": report["recovered_article_count"],
                "recovered_fact_count": report["recovered_fact_count"],
                "recovered_symbol_count": report["recovered_symbol_count"],
                "remaining_semantic_unqualified_count": report[
                    "remaining_semantic_unqualified_count"
                ],
                "recovery_hash": report["recovery_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
