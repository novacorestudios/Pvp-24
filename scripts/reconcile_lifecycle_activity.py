"""Reconcile semantic lifecycle pins with checksum-verified daily LAST archive activity."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcement_qualification import load_qualification  # noqa: E402
from pvb24.data.daily_activity import reconcile_qualification_activity  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-root", type=Path, required=True)
    parser.add_argument("--qualification-root", type=Path, required=True)
    parser.add_argument("--qualification-report", required=True)
    parser.add_argument("--qualification-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    qualification = load_qualification(
        args.qualification_root,
        args.qualification_report,
        expected_sha256=args.qualification_sha256,
        inventory_root=args.inventory_root,
    )
    report, path = reconcile_qualification_activity(qualification, args.output)
    summary = {
        "schema": "PVB24_LIFECYCLE_ARCHIVE_ACTIVITY_SUMMARY_V3",
        "report": str(path),
        "report_sha256": path.stem,
        "qualified_fact_count": report["qualified_fact_count"],
        "effective_fact_count": report["effective_fact_count"],
        "superseded_count": report["superseded_count"],
        "late_revision_count": report["late_revision_count"],
        "probe_count": report["probe_count"],
        "reconciliation_count": report["reconciliation_count"],
        "status_counts": report["status_counts"],
        "source_failures": report["source_failures"],
        "archive_absence_proves_inactivity": False,
        "historical_lifecycle_verified": False,
        "historical_universe_complete": False,
        "operational_ready": False,
        "final_test_access": "LOCKED",
    }
    print(json.dumps(json.loads(canonical(summary)), indent=2))
    return 2 if report["source_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
