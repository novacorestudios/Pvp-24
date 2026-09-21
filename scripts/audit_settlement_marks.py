"""Offline diagnostics over pinned funding reports and selected official Mark bars."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.settlement_audit import audit_settlement_marks  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--coverage-sha256", required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument(
        "--sample", nargs=2, action="append", default=[], metavar=("ROOT", "ATTEMPT")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(ROOT)
    result = audit_settlement_marks(
        args.coverage, args.coverage_sha256, args.history_root, args.sample
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(result, indent=2) + "\n").encode()
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace a different settlement audit")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "source_mark_present",
                    "source_mark_missing",
                    "archive_derived_settlement_prices",
                    "audit_hash",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
