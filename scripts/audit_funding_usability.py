"""Offline funding-row usability audit; creates no schedule or eligibility evidence."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.funding_usability import qualify_history_rows  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--comparison-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    provenance = verify(ROOT)
    payload = args.comparison.read_bytes()
    if hashlib.sha256(payload).hexdigest() != args.comparison_sha256:
        raise ValueError("Pinned funding comparison hash changed")
    source = json.loads(payload)
    history = source.get("history")
    if (
        source.get("schema") != "PVB24_FUNDING_SOURCE_COMPARISON_V1"
        or source.get("final_test_access") != "LOCKED"
        or not isinstance(history, dict)
        or history.get("status") != "ACQUIRED"
    ):
        raise ValueError("Acquired locked funding source comparison required")
    report = {
        **qualify_history_rows(history["rows"]),
        "comparison_sha256": args.comparison_sha256,
        "history_data_hash": history["data_hash"],
        "history_decoder_sha256": history["decoder_sha256"],
        "source_comparison_report_hash": source["report_hash"],
        **provenance,
    }
    encoded = (json.dumps(json.loads(canonical(report)), indent=2) + "\n").encode()
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to overwrite a different funding usability report")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(canonical({"output": str(args.output), "input_hash": report["input_hash"]}))


if __name__ == "__main__":
    main()
