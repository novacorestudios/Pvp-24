"""Acquire the frozen official release without following a moving branch."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from verify_provenance import verify

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    verify(ROOT)
    pin = json.loads((ROOT / "config/manifest.json").read_text())["freqtrade"]
    repo = ROOT / ".deps/freqtrade"
    if not repo.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                pin["tag"],
                "https://github.com/freqtrade/freqtrade.git",
                str(repo),
            ],
            check=True,
        )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if head != pin["commit"]:
        raise SystemExit("Dependency SHA differs from immutable pin; refusing to install")
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
    if dirty.strip():
        raise SystemExit("Dependency source has local modifications")
    if args.install:
        venv = repo / ".venv"
        if not venv.exists():
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        python = str(venv / "bin/python")
        subprocess.run(
            [python, "-m", "pip", "install", "-r", str(ROOT / "config/freqtrade-python312.lock")],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            [python, "-m", "pip", "install", "--no-deps", "-e", "."], cwd=repo, check=True
        )
    print(json.dumps({"tag": pin["tag"], "sha": head, "installed_this_call": args.install}))


if __name__ == "__main__":
    main()
