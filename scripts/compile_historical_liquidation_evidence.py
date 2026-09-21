"""Compile pinned M11W historical leverage/maintenance-tier evidence."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.margin_tier_history import compile_historical_liquidation_evidence  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sources = []
    for item in args.source:
        code, separator, report_hash = item.partition(":")
        if not separator:
            raise ValueError("--source must be CODE:REPORT_SHA256")
        sources.append((code, report_hash))

    verify(ROOT)
    result = compile_historical_liquidation_evidence(args.root, sources)
    encoded = (json.dumps(result, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace different historical liquidation evidence")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "source_count": result["source_count"],
                "symbols": result["symbols"],
                "causally_announced_change_count": result["causally_announced_change_count"],
                "retrospective_change_count": result["retrospective_change_count"],
                "position_cohort_policy_observed": result["position_cohort_policy_observed"],
                "historical_liquidation_rules_complete": result[
                    "historical_liquidation_rules_complete"
                ],
                "evidence_hash": result["evidence_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
