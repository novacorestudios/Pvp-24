import argparse
import json
from pathlib import Path

from pvb24.data.durable_evidence import (
    LOCATOR_SCHEMA,
    build_bundle,
    load_locator,
    restore_bundle,
    verify_bundle,
    write_canonical_json,
)


def build_command(args):
    result = build_bundle(args.source_manifest, args.archives_dir, args.output_dir)
    bundle_path = Path(result["bundle_path"])
    try:
        repository_path = bundle_path.resolve().relative_to(Path(args.repo_root).resolve())
    except ValueError as exc:
        raise ValueError("Durable bundle must live under repository root") from exc
    locator = {
        "schema": LOCATOR_SCHEMA,
        "bundle_path": repository_path.as_posix(),
        "bundle_sha256": result["bundle_sha256"],
        "manifest_sha256": result["manifest_sha256"],
        "source_run_id": result["manifest"]["source_run_id"],
        "source_head_sha": result["manifest"]["source_head_sha"],
        "artifact_count": result["manifest"]["artifact_count"],
        "actions_artifacts_required": False,
    }
    write_canonical_json(args.locator, locator)
    print(json.dumps(locator, sort_keys=True))


def verify_command(args):
    locator, bundle_path = load_locator(args.locator, args.repo_root)
    result = verify_bundle(
        bundle_path,
        expected_sha256=locator["bundle_sha256"],
        expected_manifest_sha256=locator["manifest_sha256"],
    )
    print(
        json.dumps(
            {
                "bundle_sha256": result["bundle_sha256"],
                "manifest_sha256": result["manifest_sha256"],
                "artifact_count": result["manifest"]["artifact_count"],
            },
            sort_keys=True,
        )
    )


def restore_command(args):
    locator, bundle_path = load_locator(args.locator, args.repo_root)
    result = restore_bundle(
        bundle_path,
        args.destination,
        expected_sha256=locator["bundle_sha256"],
        expected_manifest_sha256=locator["manifest_sha256"],
        artifact_names=args.artifact,
    )
    print(
        json.dumps(
            {
                "bundle_sha256": result["bundle_sha256"],
                "manifest_sha256": result["manifest_sha256"],
                "restored_file_count": result["restored_file_count"],
            },
            sort_keys=True,
        )
    )


def parser():
    value = argparse.ArgumentParser()
    sub = value.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--source-manifest", required=True)
    build.add_argument("--archives-dir", required=True)
    build.add_argument("--output-dir", required=True)
    build.add_argument("--locator", required=True)
    build.add_argument("--repo-root", default=".")
    build.set_defaults(func=build_command)

    verify = sub.add_parser("verify")
    verify.add_argument("--locator", required=True)
    verify.add_argument("--repo-root", default=".")
    verify.set_defaults(func=verify_command)

    restore = sub.add_parser("restore")
    restore.add_argument("--locator", required=True)
    restore.add_argument("--repo-root", default=".")
    restore.add_argument("--destination", required=True)
    restore.add_argument("--artifact", action="append")
    restore.set_defaults(func=restore_command)
    return value


def main():
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
