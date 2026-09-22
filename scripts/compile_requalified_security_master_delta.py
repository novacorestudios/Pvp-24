"""Compile the requalified lifecycle delta against the pinned Security Master audit."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.requalified_security_master import (  # noqa: E402
    compile_requalified_security_master_delta,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--requalification", type=Path, required=True)
    parser.add_argument("--requalification-sha256", required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--lifecycle-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    report = compile_requalified_security_master_delta(
        args.base,
        args.base_sha256,
        args.requalification,
        args.requalification_sha256,
        args.lifecycle,
        args.lifecycle_sha256,
    )
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace different requalified Security Master delta")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "base_active_corroborated_count": report["base_active_corroborated_count"],
                "base_active_newly_reconciled_count": report[
                    "base_active_newly_reconciled_count"
                ],
                "base_active_unknown_boundary_count": report[
                    "base_active_unknown_boundary_count"
                ],
                "base_active_contradicted_count": report["base_active_contradicted_count"],
                "base_inactive_corroborated_count": report[
                    "base_inactive_corroborated_count"
                ],
                "exact_delisting_unpaired_count": report["exact_delisting_unpaired_count"],
                "recommended_successor_active_transition_count": report[
                    "recommended_successor_active_transition_count"
                ],
                "historical_universe_complete": report["historical_universe_complete"],
                "delta_hash": report["delta_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
