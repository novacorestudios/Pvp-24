"""Inventory three reviewed public directory roots; no price archives or orders."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.catalog import ALLOWED_PREFIXES, inventory  # noqa: E402
from pvb24.ids import canonical  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    verify(ROOT)
    failed = False
    for prefix in ALLOWED_PREFIXES:
        report, path = inventory(prefix, args.output)
        print(
            canonical(
                {
                    "report": str(path),
                    "prefix": prefix,
                    "status": report["status"],
                    "directories": len(report["children"]),
                    "pages": len(report["pages"]),
                }
            ),
            flush=True,
        )
        failed |= report["status"] != "COMPLETE"
    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
