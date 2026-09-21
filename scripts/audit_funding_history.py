"""Acquire pre-Final public funding history and compare exact archive identities."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.acquisition import load_acquired, object_write  # noqa: E402
from pvb24.data.archive import ArchiveRequest, records  # noqa: E402
from pvb24.data.dataset import ArchiveDataset  # noqa: E402
from pvb24.data.funding_history import acquire_history, compare_archive  # noqa: E402
from pvb24.ids import canonical, digest  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset-hash", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    verify(ROOT)
    baseline = json.loads((ROOT / "config/manifest.json").read_text())
    request = ArchiveRequest(args.symbol, "fundingRate", args.month)
    ArchiveDataset(
        args.archive_root,
        args.manifest,
        expected_dataset_hash=args.dataset_hash,
        expected_config_hash=baseline["config_hash"],
    )
    manifest = json.loads(args.manifest.read_text())
    selected = [a for a in manifest["archives"] if ArchiveRequest(**a["request"]) == request]
    if len(selected) != 1:
        raise ValueError("Exactly one pinned funding archive required")
    source, raw, checksum = load_acquired(args.archive_root, selected[0]["attempt"])
    archive_rows = list(records(source, raw, checksum))
    history, path = acquire_history(request, args.output)
    report = {
        "schema": "PVB24_FUNDING_SOURCE_COMPARISON_V1",
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "worktree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "config_hash": baseline["config_hash"],
        "source_sha256": baseline["source_sha256"],
        "archive_dataset_hash": args.dataset_hash,
        "archive_attempt": selected[0]["attempt"],
        "history_report": str(path),
        "history": history,
        "final_test_access": "LOCKED",
        "performance_run": False,
        "operational_paper_ready": False,
    }
    if history["status"] == "ACQUIRED":
        report["comparison"] = compare_archive(archive_rows, history)
    report["report_hash"] = digest(report)
    name = object_write(args.output / "comparisons", canonical(report).encode(), ".json")
    print(
        canonical(
            {
                "report": str(args.output / "comparisons" / name),
                "status": history["status"],
                "funding_rows": len(history["rows"]),
                "comparison": report.get("comparison"),
            }
        ),
        flush=True,
    )
    if history["status"] != "ACQUIRED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
