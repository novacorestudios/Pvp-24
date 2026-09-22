import argparse
from pathlib import Path

from pvb24.data.evidence_ci import qualify_artifact_root, verify_artifact_root


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--ci-attestation", type=Path, required=True)
    create.add_argument("--manifest-name", default="evidence-qualification.json")

    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--ci-attestation", type=Path, required=True)
    verify.add_argument("--manifest-name", default="evidence-qualification.json")
    verify.add_argument("--expected-sha")

    args = parser.parse_args()
    if args.command == "create":
        value = qualify_artifact_root(
            root=args.root,
            ci_attestation_path=args.ci_attestation,
            manifest_name=args.manifest_name,
        )
    else:
        value = verify_artifact_root(
            root=args.root,
            ci_attestation_path=args.ci_attestation,
            manifest_name=args.manifest_name,
            expected_sha=args.expected_sha,
        )
    print(
        f"qualified={str(value['qualified']).lower()} "
        f"producer_sha={value['producer_sha']} "
        f"ci_run_id={value['ci_run_id']} "
        f"file_count={value['file_count']} "
        f"payload_hash={value['payload_hash']}"
    )


if __name__ == "__main__":
    main()
