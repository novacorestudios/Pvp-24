"""Compile the V6 Security Master obligation audit from the requalified delta."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.security_master_successor import (  # noqa: E402
    compile_security_master_successor,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--delta", type=Path, required=True)
    parser.add_argument("--delta-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    report = compile_security_master_successor(
        args.base,
        args.base_sha256,
        args.delta,
        args.delta_sha256,
    )
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace different V6 Security Master audit")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "selected_active_transition_count": report[
                    "selected_active_transition_count"
                ],
                "archive_reconciled_active_transition_count": report[
                    "archive_reconciled_active_transition_count"
                ],
                "announcement_only_active_transition_count": report[
                    "announcement_only_active_transition_count"
                ],
                "unresolved_listing_count": report["unresolved_listing_count"],
                "rejected_active_transition_count": report[
                    "rejected_active_transition_count"
                ],
                "requalified_exact_delisting_unpaired_count": report[
                    "requalified_exact_delisting_unpaired_count"
                ],
                "security_history_complete": report["security_history_complete"],
                "historical_universe_complete": report["historical_universe_complete"],
                "audit_hash": report["audit_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
