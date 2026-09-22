from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path, PurePosixPath

SOURCE_SCHEMA = "PVB24_M11T_SOURCE_ARTIFACTS_V1"
BUNDLE_SCHEMA = "PVB24_DURABLE_EVIDENCE_BUNDLE_V1"
LOCATOR_SCHEMA = "PVB24_DURABLE_EVIDENCE_LOCATOR_V1"
MAX_MEMBER_COUNT = 10_000
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def canonical_bytes(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text())


def write_canonical_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical_bytes(value))


def _safe_member(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise ValueError("Unsafe durable evidence member path")
    member = PurePosixPath(name)
    if member.is_absolute() or any(part in ("", ".", "..") for part in member.parts):
        raise ValueError("Unsafe durable evidence member path")
    return member


def _zip_inventory_bytes(data: bytes):
    rows = []
    names = set()
    total_size = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in sorted(archive.infolist(), key=lambda row: row.filename):
            if info.is_dir():
                continue
            member = _safe_member(info.filename)
            if member.as_posix() in names:
                raise ValueError("Duplicate durable evidence member path")
            names.add(member.as_posix())
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError("Symlink is not allowed in durable evidence")
            payload = archive.read(info)
            total_size += len(payload)
            if len(rows) >= MAX_MEMBER_COUNT or total_size > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Durable evidence archive exceeds safety limits")
            rows.append(
                {
                    "path": member.as_posix(),
                    "size": len(payload),
                    "sha256": sha256_bytes(payload),
                }
            )
    return rows


def _validate_source_manifest(value):
    if value.get("schema") != SOURCE_SCHEMA:
        raise ValueError("Unexpected durable evidence source schema")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Durable evidence source artifacts required")
    names = [row.get("name") for row in artifacts]
    files = [row.get("archive_file") for row in artifacts]
    ids = [row.get("artifact_id") for row in artifacts]
    if len(names) != len(set(names)) or any(not isinstance(name, str) for name in names):
        raise ValueError("Unique durable evidence artifact names required")
    if len(files) != len(set(files)) or any(not isinstance(name, str) for name in files):
        raise ValueError("Unique durable evidence archive names required")
    if len(ids) != len(set(ids)) or any(not isinstance(value, int) for value in ids):
        raise ValueError("Unique durable evidence artifact ids required")


def _verify_artifact_bytes(data: bytes, spec):
    if sha256_bytes(data) != spec["archive_sha256"]:
        raise ValueError(f"Durable evidence archive hash changed: {spec['name']}")
    if len(data) != spec["archive_size"]:
        raise ValueError(f"Durable evidence archive size changed: {spec['name']}")
    inventory = _zip_inventory_bytes(data)
    if len(inventory) != spec["member_count"]:
        raise ValueError(f"Durable evidence member count changed: {spec['name']}")
    if sum(row["size"] for row in inventory) != spec["uncompressed_size"]:
        raise ValueError(f"Durable evidence uncompressed size changed: {spec['name']}")

    by_path = {row["path"]: row for row in inventory}
    for pin in spec.get("report_pins", []):
        row = by_path.get(pin["path"])
        if row is None or row["sha256"] != pin["sha256"]:
            raise ValueError(f"Durable evidence report pin changed: {pin['path']}")
    return inventory


def _zip_info(name: str):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o100644 << 16
    return info


def build_bundle(source_manifest_path, archives_dir, output_dir):
    source_path = Path(source_manifest_path)
    source = load_json(source_path)
    _validate_source_manifest(source)
    archives_root = Path(archives_dir)
    bundled = []
    archive_payloads = {}

    for spec in sorted(source["artifacts"], key=lambda row: row["name"]):
        path = archives_root / spec["archive_file"]
        if not path.is_file():
            raise ValueError(f"Missing durable evidence archive: {spec['archive_file']}")
        data = path.read_bytes()
        inventory = _verify_artifact_bytes(data, spec)
        archive_payloads[spec["archive_file"]] = data
        bundled.append({**spec, "members": inventory})

    manifest = {
        "schema": BUNDLE_SCHEMA,
        "source_manifest_sha256": sha256_file(source_path),
        "source_run_id": source["source_run_id"],
        "source_run_name": source["source_run_name"],
        "source_head_sha": source["source_head_sha"],
        "source_branch": source["source_branch"],
        "source_conclusion": source["source_conclusion"],
        "artifact_count": len(bundled),
        "artifacts": bundled,
        "content_addressed": True,
        "actions_artifacts_required_after_preservation": False,
    }
    manifest_payload = canonical_bytes(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(_zip_info("manifest.json"), manifest_payload)
        for spec in bundled:
            archive_file = spec["archive_file"]
            bundle.writestr(
                _zip_info(f"artifacts/{archive_file}"),
                archive_payloads[archive_file],
            )

    bundle_payload = buffer.getvalue()
    bundle_sha = sha256_bytes(bundle_payload)
    manifest_sha = sha256_bytes(manifest_payload)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    bundle_path = output_root / f"m11t-evidence-{bundle_sha}.zip"
    manifest_path = output_root / f"m11t-evidence-{bundle_sha}.manifest.json"

    if bundle_path.exists() and sha256_file(bundle_path) != bundle_sha:
        raise ValueError("Existing durable evidence bundle differs")
    bundle_path.write_bytes(bundle_payload)
    manifest_path.write_bytes(manifest_payload)
    return {
        "bundle_path": bundle_path,
        "manifest_path": manifest_path,
        "bundle_sha256": bundle_sha,
        "manifest_sha256": manifest_sha,
        "manifest": manifest,
    }


def verify_bundle(bundle_path, *, expected_sha256=None, expected_manifest_sha256=None):
    bundle_path = Path(bundle_path)
    payload = bundle_path.read_bytes()
    actual_sha = sha256_bytes(payload)
    if expected_sha256 is not None and actual_sha != expected_sha256:
        raise ValueError("Durable evidence bundle hash changed")

    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        members = [row for row in bundle.infolist() if not row.is_dir()]
        names = [row.filename for row in members]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate durable evidence bundle member")
        for name in names:
            _safe_member(name)
        if "manifest.json" not in names:
            raise ValueError("Durable evidence manifest missing")
        manifest_payload = bundle.read("manifest.json")
        manifest_sha = sha256_bytes(manifest_payload)
        if expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256:
            raise ValueError("Durable evidence manifest hash changed")
        manifest = json.loads(manifest_payload)
        if manifest.get("schema") != BUNDLE_SCHEMA:
            raise ValueError("Unexpected durable evidence bundle schema")

        expected_names = {"manifest.json"}
        for spec in manifest["artifacts"]:
            member_name = f"artifacts/{spec['archive_file']}"
            expected_names.add(member_name)
            data = bundle.read(member_name)
            inventory = _verify_artifact_bytes(data, spec)
            if inventory != spec["members"]:
                raise ValueError(f"Durable evidence member inventory changed: {spec['name']}")
        if set(names) != expected_names:
            raise ValueError("Unexpected durable evidence bundle members")

    return {
        "bundle_sha256": actual_sha,
        "manifest_sha256": manifest_sha,
        "manifest": manifest,
    }


def _write_restored_file(target: Path, payload: bytes):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256_file(target) != sha256_bytes(payload):
            raise ValueError(f"Restore would overwrite different evidence: {target}")
        return
    target.write_bytes(payload)


def restore_bundle(
    bundle_path,
    destination,
    *,
    expected_sha256=None,
    expected_manifest_sha256=None,
    artifact_names=None,
):
    verified = verify_bundle(
        bundle_path,
        expected_sha256=expected_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    selected = set(artifact_names or [])
    manifest = verified["manifest"]
    known = {row["name"] for row in manifest["artifacts"]}
    if selected and not selected <= known:
        raise ValueError("Unknown durable evidence artifact requested")

    restored = []
    bundle_payload = Path(bundle_path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(bundle_payload)) as bundle:
        for spec in manifest["artifacts"]:
            if selected and spec["name"] not in selected:
                continue
            data = bundle.read(f"artifacts/{spec['archive_file']}")
            root = Path(destination) / spec["restore_dir"]
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    member = _safe_member(info.filename)
                    payload = archive.read(info)
                    _write_restored_file(root.joinpath(*member.parts), payload)
                    restored.append(
                        {
                            "artifact": spec["name"],
                            "path": f"{spec['restore_dir']}/{member.as_posix()}",
                            "size": len(payload),
                            "sha256": sha256_bytes(payload),
                        }
                    )

    return {
        "bundle_sha256": verified["bundle_sha256"],
        "manifest_sha256": verified["manifest_sha256"],
        "restored_file_count": len(restored),
        "restored_files": restored,
    }


def load_locator(locator_path, repo_root="."):
    locator = load_json(locator_path)
    if locator.get("schema") != LOCATOR_SCHEMA:
        raise ValueError("Unexpected durable evidence locator schema")
    root = Path(repo_root)
    bundle_path = root / locator["bundle_path"]
    return locator, bundle_path
