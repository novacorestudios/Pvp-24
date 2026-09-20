"""Reproduce a frozen source sample's causal hourly/daily normalization; no PnL."""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.acquisition import object_write  # noqa: E402
from pvb24.data.archive import ArchiveRequest  # noqa: E402
from pvb24.data.dataset import ArchiveDataset, daily_last  # noqa: E402
from pvb24.ids import canonical, digest  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dataset-hash", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(ROOT)
    baseline = json.loads((ROOT / "config/manifest.json").read_text())
    request = ArchiveRequest(args.symbol, "klines", args.month, "1h")
    dataset = ArchiveDataset(
        args.root,
        args.manifest,
        expected_dataset_hash=args.dataset_hash,
        expected_config_hash=baseline["config_hash"],
    )
    window = dict(start=request.start, end=request.end, decision=request.end + timedelta(seconds=2))
    hourly = dataset.candles(args.symbol, "1h", **window)
    mark = dataset.candles(args.symbol, "1h", price_type="MARK", **window)
    daily = daily_last(hourly.candles, args.symbol, **window)
    report = {
        "schema": "PVB24_CAUSAL_ARCHIVE_NORMALIZATION_V1",
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "worktree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "implementation_hashes": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__).resolve(), ROOT / "src/pvb24/data/dataset.py")
        },
        "dataset_hash": dataset.data_hash,
        "config_hash": baseline["config_hash"],
        "source_sha256": baseline["source_sha256"],
        "symbol": args.symbol,
        "month": args.month,
        "decision": window["decision"],
        "quality": dataset.quality,
        "final_test_access": "LOCKED",
        "performance_run": False,
        "historical_universe": "NOT_RECONSTRUCTED",
        "funding_schedule_complete": False,
        "operational_paper_ready": False,
        "normalization": {},
    }
    for name, result in (("last_1h", hourly), ("mark_1h", mark), ("last_1d", daily)):
        report["normalization"][name] = {
            "rows": len(result.candles),
            "missing": result.missing,
            "normalized_hash": digest(result.candles),
            "first_start": result.candles[0].timing.interval_start if result.candles else None,
            "last_end": result.candles[-1].timing.interval_end if result.candles else None,
            "latest_available_at": max(
                (r.timing.available_at for r in result.candles), default=None
            ),
        }
    report["normalization_hash"] = digest(report["normalization"])
    name = object_write(args.output, canonical(report).encode(), ".json")
    print(canonical({"report": str(args.output / name), **report}))
    if any(item["missing"] for item in report["normalization"].values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
