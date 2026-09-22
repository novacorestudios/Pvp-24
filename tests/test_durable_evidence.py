import hashlib
import io
import json
import zipfile

import pytest

from pvb24.data.durable_evidence import build_bundle, restore_bundle, verify_bundle


def digest(value):
    return hashlib.sha256(value).hexdigest()


def archive_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in sorted(files.items()):
            archive.writestr(name, value)
    return buffer.getvalue()


def fixture(tmp_path):
    archives = tmp_path / "archives"
    archives.mkdir()
    payload = archive_bytes(
        {
            "objects/abc.json": b'{"source":"pinned"}\n',
            "reports/report.json": b'{"result":"pinned"}\n',
        }
    )
    archive = archives / "sample.zip"
    archive.write_bytes(payload)
    report_sha = digest(b'{"result":"pinned"}\n')
    source = {
        "schema": "PVB24_M11T_SOURCE_ARTIFACTS_V1",
        "source_run_id": 123,
        "source_run_name": "fixture",
        "source_head_sha": "a" * 40,
        "source_branch": "build/pvb24-v1",
        "source_conclusion": "success",
        "artifacts": [
            {
                "artifact_id": 7,
                "name": "sample",
                "archive_file": "sample.zip",
                "archive_sha256": digest(payload),
                "archive_size": len(payload),
                "member_count": 2,
                "uncompressed_size": len(b'{"source":"pinned"}\n')
                + len(b'{"result":"pinned"}\n'),
                "restore_dir": "sample",
                "expires_at": "2026-10-05T00:00:00Z",
                "report_pins": [
                    {"path": "reports/report.json", "sha256": report_sha},
                ],
            }
        ],
    }
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(source))
    return source_path, archives


def test_durable_bundle_is_deterministic_and_restorable(tmp_path):
    source, archives = fixture(tmp_path)
    first = build_bundle(source, archives, tmp_path / "one")
    second = build_bundle(source, archives, tmp_path / "two")
    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert first["manifest_sha256"] == second["manifest_sha256"]

    verified = verify_bundle(
        first["bundle_path"],
        expected_sha256=first["bundle_sha256"],
        expected_manifest_sha256=first["manifest_sha256"],
    )
    assert verified["manifest"]["actions_artifacts_required_after_preservation"] is False

    restored = restore_bundle(
        first["bundle_path"],
        tmp_path / "restored",
        expected_sha256=first["bundle_sha256"],
        expected_manifest_sha256=first["manifest_sha256"],
    )
    assert restored["restored_file_count"] == 2
    assert (tmp_path / "restored/sample/objects/abc.json").read_bytes() == (
        b'{"source":"pinned"}\n'
    )
    assert (tmp_path / "restored/sample/reports/report.json").read_bytes() == (
        b'{"result":"pinned"}\n'
    )


def test_bundle_hash_tampering_fails_closed(tmp_path):
    source, archives = fixture(tmp_path)
    result = build_bundle(source, archives, tmp_path / "bundle")
    tampered = tmp_path / "tampered.zip"
    value = bytearray(result["bundle_path"].read_bytes())
    value[-1] ^= 1
    tampered.write_bytes(value)
    with pytest.raises(ValueError, match="bundle hash changed"):
        verify_bundle(tampered, expected_sha256=result["bundle_sha256"])


def test_source_archive_hash_change_fails_closed(tmp_path):
    source, archives = fixture(tmp_path)
    (archives / "sample.zip").write_bytes(b"changed")
    with pytest.raises(ValueError, match="archive hash changed"):
        build_bundle(source, archives, tmp_path / "bundle")


def test_archive_path_traversal_is_rejected(tmp_path):
    source, archives = fixture(tmp_path)
    unsafe = archive_bytes({"../escape.json": b"bad", "reports/report.json": b"ok"})
    (archives / "sample.zip").write_bytes(unsafe)
    value = json.loads(source.read_text())
    spec = value["artifacts"][0]
    spec["archive_sha256"] = digest(unsafe)
    spec["archive_size"] = len(unsafe)
    spec["member_count"] = 2
    spec["uncompressed_size"] = 5
    spec["report_pins"] = []
    source.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="Unsafe durable evidence member path"):
        build_bundle(source, archives, tmp_path / "bundle")
