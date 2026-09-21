"""Audit complete market-data coverage against a frozen historical-universe obligation set."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pvb24.evaluation.market_data import complete_attestations, qualify_market_data  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--archive-report", type=Path, required=True)
    parser.add_argument("--dataset-hash", required=True)
    parser.add_argument("--config-hash", required=True)
    parser.add_argument("--obligations", type=Path, required=True)
    parser.add_argument("--obligations-sha256", required=True)
    parser.add_argument("--universe-attestation", type=Path, required=True)
    parser.add_argument("--universe-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = qualify_market_data(
        args.archive_root,
        args.archive_report,
        expected_dataset_hash=args.dataset_hash,
        expected_config_hash=args.config_hash,
        obligations_path=args.obligations,
        obligations_sha256=args.obligations_sha256,
        universe_attestation_path=args.universe_attestation,
        universe_sha256=args.universe_sha256,
    )
    attestations = complete_attestations(report)
    output = {
        "report": report,
        "attestations": attestations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(json.loads(canonical(output)), indent=2) + "\n")
    print(canonical({"output": str(args.output), "complete": sorted(attestations)}))
    return 0 if len(attestations) == 3 else 2


if __name__ == "__main__":
    raise SystemExit(main())
