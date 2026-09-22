import argparse
import os
from pathlib import Path

from pvb24.data.evidence_ci import qualify_same_sha_ci, write_ci_attestation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="build/pvb24-v1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--poll-seconds", type=int, default=5)
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN is required")
    value = qualify_same_sha_ci(
        repository=args.repository,
        sha=args.sha,
        branch=args.branch,
        token=token,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
    )
    write_ci_attestation(args.output, value)
    print(args.output.read_text(), end="")


if __name__ == "__main__":
    main()
