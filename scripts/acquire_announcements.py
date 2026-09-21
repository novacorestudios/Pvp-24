"""Acquire a reviewed pre-Final announcement selection and report partial coverage."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.acquisition import object_write  # noqa: E402
from pvb24.data.announcements import AnnouncementRequest, acquire, load_acquired  # noqa: E402
from pvb24.ids import canonical, digest  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--review-hash", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(ROOT)
    review = json.loads(args.review.read_text())
    if digest(review) != args.review_hash or review["schema"] != "PVB24_ANNOUNCEMENT_REVIEW_V1":
        raise ValueError("Explicit reviewed source-selection hash required")
    # Validate the whole selection, including Final, before any network operation.
    requests = [AnnouncementRequest(**item) for item in review["requests"]]
    if not requests or len({r.code for r in requests}) != len(requests):
        raise ValueError("Unique nonempty reviewed article selection required")
    baseline = json.loads((ROOT / "config/manifest.json").read_text())
    results, failures = [], []
    for request in requests:
        try:
            report, path = acquire(request, args.output)
            checked = load_acquired(args.output, path, expected_report_hash=Path(path).stem)
            results.append({"report_path": path, "report_hash": digest(checked), **report})
        except (ValueError, TypeError, KeyError, OSError, ArithmeticError) as exc:
            failures.append(
                {"code": request.code, "error_type": type(exc).__name__, "error": str(exc)}
            )
    coverage = []
    for report in results:
        for fact in report["facts"]:
            coverage.append(
                {
                    "symbol": fact["symbol"],
                    "kind": report["kind"],
                    "source": report["source"],
                    "revision_id": report["revision_id"],
                    "source_sha256": report["source_sha256"],
                    "published_at": report["published_at"],
                    "available_at": report["available_at"],
                    "facts": fact,
                    "quality": "PRELIMINARY",
                    "history_coverage_start": None,
                    "history_coverage_end": None,
                    "full_security_record": "MISSING",
                    "full_contract_rules": "MISSING",
                    "actual_settlement_fill": "NOT_PROVEN",
                    "eligibility": "NOT_INFERRED_FROM_ANNOUNCEMENT",
                }
            )
    summary = {
        "schema": "PVB24_ANNOUNCEMENT_SOURCE_COVERAGE_V1",
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "worktree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "implementation_hashes": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), ROOT / "src/pvb24/data/announcements.py")
        },
        "config_hash": baseline["config_hash"],
        "source_sha256": baseline["source_sha256"],
        "review_hash": args.review_hash,
        "requested_articles": len(requests),
        "acquired_articles": len(results),
        "failures": failures,
        "articles": results,
        "coverage": coverage,
        "coverage_scope": "REVIEWED_ARTICLES_ONLY_NOT_MARKET_COMPLETE",
        "data_hash": digest(results),
        "final_test_access": "LOCKED",
        "historical_universe_complete": False,
        "historical_contract_rules_complete": False,
        "performance_run": False,
        "operational_ready": False,
        "live_enabled": False,
    }
    summary["report_hash"] = digest(summary)
    name = object_write(args.output / "summaries", canonical(summary).encode(), ".json")
    print(
        canonical(
            {
                "summary": str(args.output / "summaries" / name),
                "acquired": len(results),
                "requested": len(requests),
                "fact_rows": len(coverage),
                "failures": failures,
                "data_hash": summary["data_hash"],
            }
        )
    )
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
