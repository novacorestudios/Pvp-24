"""Check the content-pinned pre-Final historical evaluation readiness matrix."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pvb24.evaluation.readiness import evaluate_readiness  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/data/11m-pre-final-readiness.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate_readiness(ROOT, args.manifest)
    rendered = json.dumps(json.loads(canonical(report)), indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if report["ready_for_performance_run"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
