import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.durable_evidence import load_locator, verify_bundle  # noqa: E402
from pvb24.data.evidence_replay import (  # noqa: E402
    replay_durable_evidence_chain,
    write_replay_report,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--locator", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--inventory-root", type=Path, required=True)
    parser.add_argument("--qualification-root", type=Path, required=True)
    parser.add_argument("--lifecycle-root", type=Path, required=True)
    parser.add_argument("--tick-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    locator, bundle_path = load_locator(args.locator, ROOT)
    verified = verify_bundle(
        bundle_path,
        expected_sha256=locator["bundle_sha256"],
        expected_manifest_sha256=locator["manifest_sha256"],
    )
    tick_sha = __import__("hashlib").sha256(args.tick_evidence.read_bytes()).hexdigest()
    report = replay_durable_evidence_chain(
        baseline_path=args.baseline,
        bundle_sha256=verified["bundle_sha256"],
        inventory_root=args.inventory_root,
        qualification_root=args.qualification_root,
        lifecycle_root=args.lifecycle_root,
        tick_path=args.tick_evidence,
        tick_sha256=tick_sha,
    )
    write_replay_report(args.output, report)
    print(json.dumps(report, indent=2))
    if not report["all_match"]:
        raise SystemExit("Durable evidence replay differs from audited baseline")


if __name__ == "__main__":
    main()
