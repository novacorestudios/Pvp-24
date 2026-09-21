"""Compile the integrated M11X Security Master obligation audit."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.security_master_audit import compile_security_master_obligations  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--recovery", type=Path)
    parser.add_argument("--recovery-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verify(ROOT)
    report = compile_security_master_obligations(
        args.input,
        args.input_sha256,
        args.recovery,
        args.recovery_sha256,
    )
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != encoded:
        raise ValueError("Refusing to replace different M11X Security Master audit")
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "symbol_count": report["symbol_count"],
                "selected_active_transition_count": report["selected_active_transition_count"],
                "selected_inactive_transition_count": report["selected_inactive_transition_count"],
                "unresolved_listing_count": report["unresolved_listing_count"],
                "listing_start_conflict_count": report["listing_start_conflict_count"],
                "unpaired_delisting_count": report["unpaired_delisting_count"],
                "ambiguous_delisting_count": report["ambiguous_delisting_count"],
                "security_history_complete": report["security_history_complete"],
                "historical_universe_complete": report["historical_universe_complete"],
                "audit_hash": report["audit_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
