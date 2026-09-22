"""Acquire official monthly archives for remaining V7 listing boundaries."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.monthly_listing_boundary import (  # noqa: E402
    compile_monthly_listing_boundary_evidence,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--security-master", type=Path, required=True)
    parser.add_argument("--security-master-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    report = compile_monthly_listing_boundary_evidence(
        args.security_master,
        args.security_master_sha256,
        args.output_root,
    )
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace different monthly boundary evidence")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "input_unresolved_listing_count": report[
                    "input_unresolved_listing_count"
                ],
                "monthly_source_count": report["monthly_source_count"],
                "status_counts": report["status_counts"],
                "source_failure_count": report["source_failure_count"],
                "historical_universe_complete": report[
                    "historical_universe_complete"
                ],
                "evidence_hash": report["evidence_hash"],
            }
        )
    )
    return 2 if report["source_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
