"""Check immutable inputs before any research or paper process starts."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "098a3ca390bce81d506bdec011fc3a936ecbb793f46c2f117f337998bfc1c5d8"


def verify(root: Path = ROOT) -> dict:
    manifest = json.loads((root / "config/manifest.json").read_text())
    source = (root / "reference/PVB24_ENGINEERING_SPEC_v1.0.txt").read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("Immutable source checksum mismatch")
    master = (root / "reference/PVB24_MASTER_IMPLEMENTATION_PROMPT.txt").read_bytes()
    if hashlib.sha256(master).hexdigest() != manifest["master_sha256"]:
        raise ValueError("Execution directive checksum mismatch")
    config = json.loads((root / "config/pvb24_v1.json").read_text())
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if digest != manifest["config_hash"]:
        raise ValueError("Frozen configuration checksum mismatch")
    if manifest["seed"] != int(digest[:16], 16):
        raise ValueError("Seed does not derive from frozen config")
    if config["live_enabled"] is not False or manifest["live_enabled"] is not False:
        raise ValueError("LIVE is prohibited")
    if config["freqtrade"] != manifest["freqtrade"]:
        raise ValueError("Inconsistent Freqtrade pin")
    return {"source_sha256": SOURCE_SHA256, "config_hash": digest, "live_enabled": False}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
