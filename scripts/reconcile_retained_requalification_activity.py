"""Reconcile retained requalification facts with checksum-verified official daily archives."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcements import strict_json  # noqa: E402
from pvb24.data.daily_activity import reconcile_requalification_activity  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requalification", type=Path, required=True)
    parser.add_argument("--requalification-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    raw = args.requalification.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.requalification_sha256:
        raise ValueError("Pinned retained requalification hash changed")
    requalification = strict_json(raw)

    report, content_addressed = reconcile_requalification_activity(
        requalification,
        args.output_root,
    )
    encoded = content_addressed.read_bytes()
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    if args.output_report.exists() and args.output_report.read_bytes() != encoded:
        raise ValueError("Refusing to replace different requalified lifecycle evidence")
    args.output_report.write_bytes(encoded)

    summary = {
        "schema": report["schema"],
        "source_requalification_hash": report["source_requalification_hash"],
        "report_sha256": content_addressed.stem,
        "qualified_fact_count": report["qualified_fact_count"],
        "effective_fact_count": report["effective_fact_count"],
        "superseded_count": report["superseded_count"],
        "late_revision_count": report["late_revision_count"],
        "probe_count": report["probe_count"],
        "reconciliation_count": report["reconciliation_count"],
        "status_counts": report["status_counts"],
        "source_failures": report["source_failures"],
        "historical_universe_complete": False,
        "security_master_complete": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    print(json.dumps(json.loads(canonical(summary))))
    return 2 if report["source_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
