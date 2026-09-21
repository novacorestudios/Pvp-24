"""Fetch selected official Binance pre-Final margin-tier announcements for source review."""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pvb24.data.acquisition import NoRedirect  # noqa: E402
from pvb24.data.margin_tier_source import retain_probe  # noqa: E402
from pvb24.data.announcements import BASE, MAX_BYTES  # noqa: E402


def fetch(code):
    url = BASE + code
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=30) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Announcement exceeds resource limit")
    return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--code", action="append", required=True)
    args = parser.parse_args()

    summaries = []
    for code in args.code:
        report, report_hash = retain_probe(args.root / code, code, fetch(code))
        summaries.append(
            {
                "code": code,
                "status": report["status"],
                "published_at": report["published_at"],
                "known_updated_at": report["known_updated_at"],
                "source_sha256": report["source_sha256"],
                "body_sha256": report["body_sha256"],
                "table_count": report["table_count"],
                "report_sha256": report_hash,
            }
        )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
