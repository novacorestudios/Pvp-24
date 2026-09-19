"""Exercise a deterministic synthetic lifecycle; no historical or live execution."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.replay.smoke import run_smoke  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New output directory; cannot overwrite"
    )
    args = parser.parse_args()
    verify(ROOT)
    result = run_smoke(ROOT, args.output)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "purpose",
                    "historical_performance",
                    "replay_events",
                    "trace_hash",
                    "restart_verified",
                    "orders_sent_to_exchange",
                    "paper_ready",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
