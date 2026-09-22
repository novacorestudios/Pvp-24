"""Requalify the exact retained M11T announcement bytes into a versioned artifact."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcement_requalification import (  # noqa: E402
    requalify_retained_qualification,
)
from pvb24.data.durable_evidence import load_locator, verify_bundle  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--locator", type=Path, required=True)
    parser.add_argument("--inventory-root", type=Path, required=True)
    parser.add_argument("--qualification-root", type=Path, required=True)
    parser.add_argument("--source-report-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    locator, bundle = load_locator(args.locator, ROOT)
    verified = verify_bundle(
        bundle,
        expected_sha256=locator["bundle_sha256"],
        expected_manifest_sha256=locator["manifest_sha256"],
    )
    report = requalify_retained_qualification(
        inventory_root=args.inventory_root,
        qualification_root=args.qualification_root,
        source_report_sha256=args.source_report_sha256,
        durable_bundle_sha256=verified["bundle_sha256"],
    )
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace different retained requalification evidence")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "candidate_count": report["candidate_count"],
                "source_bytes_reverified_count": report["source_bytes_reverified_count"],
                "status_counts": report["status_counts"],
                "changed_result_count": report["changed_result_count"],
                "status_promoted_to_qualified_count": report["status_promoted_to_qualified_count"],
                "reason_only_change_count": report["reason_only_change_count"],
                "historical_universe_complete": report["historical_universe_complete"],
                "security_master_complete": report["security_master_complete"],
                "requalification_hash": report["requalification_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
