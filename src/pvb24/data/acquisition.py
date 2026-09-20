"""Bounded public archive acquisition with immutable content-addressed objects."""

import csv
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
import zipfile
import zlib
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from pvb24.data.archive import ArchiveRequest, checksum_digest, coverage
from pvb24.ids import canonical, digest

MAX_ARCHIVE = 128 * 1024 * 1024
DECODER_SHA256 = hashlib.sha256(Path(__file__).with_name("archive.py").read_bytes()).hexdigest()
ACQUIRER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Archive download redirects require separate source review")


def public_bytes(url, *, max_bytes):
    # The caller supplies only ArchiveRequest-generated official URLs. Do not
    # accept arbitrary user URLs or trade API endpoints in this acquisition path.
    if not url.startswith("https://data.binance.vision/data/futures/um/monthly/"):
        raise ValueError("Official monthly USD-M archive URL required")
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(url, timeout=30) as response:
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("Archive response exceeds its resource limit")
        return raw


def object_write(root, content, suffix):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(content).hexdigest() + suffix
    path = root / name
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("Existing content-addressed object is corrupt")
        return name
    descriptor, temporary = tempfile.mkstemp(prefix=".acquire-", dir=root)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return name


def acquire(request: ArchiveRequest, root, *, fetch=public_bytes):
    request.__post_init__()  # holdout/path validation before any network request
    root = Path(root)
    result = {
        "request": asdict(request),
        "url": request.url,
        "checksum_url": request.url + ".CHECKSUM",
        "started_at": datetime.now(UTC),
        "status": "IN_PROGRESS",
        "quality": "PRELIMINARY",
        "decoder_sha256": DECODER_SHA256,
        "acquirer_sha256": ACQUIRER_SHA256,
    }
    try:
        checksum = fetch(result["checksum_url"], max_bytes=4096)
        expected = checksum_digest(checksum, request.filename)
        result["checksum_object"] = object_write(root / "objects", checksum, ".checksum")
        result["expected_sha256"] = expected
        cached = root / "objects" / (expected + ".zip")
        raw = cached.read_bytes() if cached.exists() else fetch(request.url, max_bytes=MAX_ARCHIVE)
        if len(raw) > MAX_ARCHIVE:
            raise ValueError("Archive object exceeds its resource limit")
        result["actual_sha256"] = hashlib.sha256(raw).hexdigest()
        if result["actual_sha256"] != expected:
            raise ValueError("Downloaded archive failed official SHA-256 verification")
        result["archive_object"] = object_write(root / "objects", raw, ".zip")
        result["bytes"] = len(raw)
        result["coverage"] = coverage(request, raw, checksum)
        result["status"] = "ACQUIRED" if result["coverage"]["rows"] else "EMPTY"
    except urllib.error.HTTPError as exc:
        result.update(
            status="UNAVAILABLE" if exc.code == 404 else "HTTP_ERROR", http_status=exc.code
        )
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        ArithmeticError,
        zipfile.BadZipFile,
        csv.Error,
        EOFError,
        zlib.error,
    ) as exc:
        result.update(status="INVALID_OR_FAILED", error_type=type(exc).__name__, error=str(exc))
    # A failed archive never supplies normalized input, even if the bytes were
    # already persisted for audit. Each attempt is separate and never overwrites
    # a previously acquired revision or silently selects a newer one.
    result["completed_at"] = datetime.now(UTC)
    encoded = canonical(result).encode()
    result_name = object_write(root / "attempts", encoded, ".json")
    return json.loads(encoded), "attempts/" + result_name


def load_acquired(root, attempt):
    """Verify every object again before consumption; no filename-only trust."""
    root = Path(root)
    relative = Path(attempt)
    if relative.is_absolute() or relative.parts[:1] != ("attempts",) or len(relative.parts) != 2:
        raise ValueError("Owned acquisition attempt path required")
    payload = (root / relative).read_bytes()
    if hashlib.sha256(payload).hexdigest() + ".json" != relative.name:
        raise ValueError("Acquisition attempt content hash changed")
    result = json.loads(payload)
    request = ArchiveRequest(**result["request"])
    if result["status"] != "ACQUIRED" or result["url"] != request.url:
        raise ValueError("A validated acquired archive is required")
    if result["decoder_sha256"] != DECODER_SHA256:
        raise ValueError("Explicit revalidation required after archive decoder changes")
    objects = []
    for field, suffix in (("archive_object", ".zip"), ("checksum_object", ".checksum")):
        name = result[field]
        if Path(name).name != name:
            raise ValueError("Invalid archive object path")
        raw = (root / "objects" / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() + suffix != name:
            raise ValueError("Acquired object content hash changed")
        objects.append(raw)
    if digest(coverage(request, *objects)) != digest(result["coverage"]):
        raise ValueError("Decoded archive coverage differs from acquisition record")
    return request, *objects
