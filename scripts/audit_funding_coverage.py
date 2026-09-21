"""Audit an explicit pre-Final monthly range without dropping failed source periods."""

import argparse
import hashlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.acquisition import object_write  # noqa: E402
from pvb24.data.archive import ArchiveRequest  # noqa: E402
from pvb24.data.funding_coverage import (  # noqa: E402
    audit_month,
    monthly_requests,
    resume_results,
    summarize,
)
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--first-month", required=True)
    parser.add_argument("--last-month", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument("--resume-summary", type=Path)
    parser.add_argument("--resume-hash")
    args = parser.parse_args()
    provenance = verify(ROOT)
    requests = monthly_requests(args.symbol, args.first_month, args.last_month)
    if bool(args.resume_summary) != bool(args.resume_hash):
        raise ValueError("Both resume summary and its explicit hash are required")
    code = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    )
    implementations = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (
            Path(__file__),
            ROOT / "src/pvb24/data/funding_coverage.py",
            ROOT / "src/pvb24/data/funding_dataset.py",
        )
    }
    results = []
    if args.resume_summary:
        results = resume_results(
            args.output,
            args.resume_summary,
            expected_hash=args.resume_hash,
            requests=requests,
            config_hash=provenance["config_hash"],
        )
    completed = {ArchiveRequest(**r["request"]) for r, _ in results}

    def checkpoint():
        report = {
            **summarize(requests, results),
            "code_sha": code,
            "worktree_dirty": dirty,
            "implementation_hashes": implementations,
            "resumed_from_summary_hash": args.resume_hash,
            **provenance,
        }
        name = object_write(args.output / "summaries", canonical(report).encode(), ".json")
        print(
            canonical(
                {
                    "summary": str(args.output / "summaries" / name),
                    "completed": len(results),
                    "requested": len(requests),
                    "matched": report["matched_months"],
                    "data_hash": report["data_hash"],
                }
            ),
            flush=True,
        )
        return report

    report = checkpoint()  # An interrupted audit retains all not-yet-completed periods.
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(audit_month, r, args.output) for r in requests if r not in completed
        ]
        for future in as_completed(futures):
            results.append(future.result())
            report = checkpoint()
    if not report["source_time_rate_comparison_complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
