"""Audit exact retained funding settlement spacing without creating a calendar."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.funding_schedule import audit_funding_schedule  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--summary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    result = audit_funding_schedule(
        args.root,
        args.summary,
        expected_summary_sha256=args.summary_sha256,
    )
    encoded = (json.dumps(result, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace a different funding schedule audit")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "archive_settlement_rows",
                    "adjacent_archive_pairs",
                    "archive_unavailable_months",
                    "maximum_absolute_difference_microseconds",
                    "funding_schedule_complete",
                    "audit_hash",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
