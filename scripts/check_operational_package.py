#!/usr/bin/env python3
"""Fail-closed CLI for validating the PVB-24 operational package."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from pvb24.operational_preflight import require_operational_package


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate PVB-24 PAPER package wiring without running strategy performance."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to this checkout).",
    )
    args = parser.parse_args()

    report = require_operational_package(args.root)
    print(json.dumps(asdict(report), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
