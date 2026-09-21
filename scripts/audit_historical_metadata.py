"""Offline qualification of caller-pinned historical Binance metadata snapshots."""

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.acquisition import object_write  # noqa: E402
from pvb24.data.historical_metadata import qualify_selection  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    provenance = verify(ROOT)
    report = qualify_selection(
        args.root,
        args.selection,
        expected_hash=args.selection_sha256,
    )
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    )
    implementations = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), ROOT / "src/pvb24/data/historical_metadata.py")
    }
    frozen = {
        **report,
        "code_sha": code_sha,
        "worktree_dirty": dirty,
        "implementation_hashes": implementations,
        **provenance,
    }
    name = object_write(args.output / "reports", canonical(frozen).encode(), ".json")
    print(
        canonical(
            {
                "report": str(args.output / "reports" / name),
                "snapshots": frozen["snapshots"],
                "symbols": frozen["symbols"],
                "quality": frozen["quality"],
                "input_hash": frozen["input_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
