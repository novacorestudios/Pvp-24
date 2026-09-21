"""Fetch explicit reviewed official Binance listing sources for M11X."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.data.announcements import BASE, MAX_BYTES, public_announcement  # noqa: E402
from pvb24.data.reviewed_listing_source import retain_reviewed_listing_source  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--code", action="append", required=True)
    args = parser.parse_args()
    verify(ROOT)

    if len(args.code) != len(set(args.code)):
        raise ValueError("Reviewed listing article codes must be unique")

    summaries = []
    for code in args.code:
        raw = public_announcement(BASE + code)
        if len(raw) > MAX_BYTES:
            raise ValueError("Announcement exceeds resource limit")
        report, report_sha256 = retain_reviewed_listing_source(args.root / code, code, raw)
        summaries.append(
            {
                "code": code,
                "published_at": report["published_at"],
                "known_updated_at": report["known_updated_at"],
                "source_sha256": report["source_sha256"],
                "body_sha256": report["body_sha256"],
                "report_sha256": report_sha256,
            }
        )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
