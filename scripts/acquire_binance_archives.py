"""Acquire explicit pre-Final monthly archives; never run a backtest or submit orders."""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.acquisition import acquire, object_write  # noqa: E402
from pvb24.data.archive import FINAL_START, ArchiveRequest  # noqa: E402
from pvb24.ids import canonical, digest  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", action="append", required=True)
    parser.add_argument("--month", action="append", required=True)
    parser.add_argument(
        "--kind", action="append", choices=("klines", "markPriceKlines", "fundingRate")
    )
    parser.add_argument("--interval", action="append", choices=("1m", "1h"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    verify(ROOT)
    config = json.loads((ROOT / "config/pvb24_v1.json").read_text())
    if datetime.fromisoformat(config["research"]["final"][0]) != FINAL_START:
        raise ValueError("Acquisition holdout boundary differs from frozen baseline")
    requests = sorted(
        {
            ArchiveRequest(symbol, kind, month, interval)
            for symbol in args.symbol
            for month in args.month
            for kind in (args.kind or ("klines", "markPriceKlines", "fundingRate"))
            for interval in ([None] if kind == "fundingRate" else args.interval or ["1m", "1h"])
        },
        key=lambda r: (r.symbol, r.month, r.kind, r.interval or ""),
    )
    # Validate the entire batch above before downloading anything, including a
    # mixed request that accidentally crosses into the locked Final Test period.
    manifest = json.loads((ROOT / "config/manifest.json").read_text())
    report = {
        "schema": "PVB24_ARCHIVE_ACQUISITION_V1",
        "started_at": datetime.now(UTC),
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "worktree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "config_hash": manifest["config_hash"],
        "source_sha256": manifest["source_sha256"],
        "freqtrade": manifest["freqtrade"],
        "final_test_access": "LOCKED",
        "historical_universe": "NOT_RECONSTRUCTED",
        "historical_rules": "NOT_ACQUIRED",
        "l2_depth": "NOT_ACQUIRED",
        "performance_run": False,
        "operational_paper_ready": False,
        "archives": [],
    }
    for request in requests:
        result, attempt = acquire(request, args.output)
        report["archives"].append({"attempt": attempt, **result})
        print(
            canonical(
                {
                    "symbol": request.symbol,
                    "kind": request.kind,
                    "interval": request.interval,
                    "month": request.month,
                    "status": result["status"],
                }
            ),
            flush=True,
        )
    report["completed_at"] = datetime.now(UTC)
    report["requested_archives"] = len(requests)
    report["acquired_archives"] = sum(a["status"] == "ACQUIRED" for a in report["archives"])
    report["dataset_hash"] = digest(
        [
            {
                key: a.get(key)
                for key in (
                    "request",
                    "url",
                    "status",
                    "actual_sha256",
                    "decoder_sha256",
                    "coverage",
                )
            }
            for a in report["archives"]
        ]
    )
    report["report_hash"] = digest(report)
    name = object_write(args.output / "reports", canonical(report).encode(), ".json")
    print(
        canonical(
            {
                "report": str(args.output / "reports" / name),
                "report_hash": report["report_hash"],
                "acquired": report["acquired_archives"],
                "requested": len(requests),
            }
        )
    )
    if report["acquired_archives"] != len(requests):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
