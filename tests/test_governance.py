"""Milestone 0 evidence; no strategy or performance claims."""

import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify_provenance.py")
module = importlib.util.module_from_spec(loader)
loader.loader.exec_module(module)


def test_source_extraction_matches_directive_and_external_hash():
    master = (ROOT / "reference/PVB24_MASTER_IMPLEMENTATION_PROMPT.txt").read_text()
    extracted = master.split("----- BEGIN FROZEN SOURCE SPECIFICATION -----")[1]
    extracted = extracted.split("----- END FROZEN SOURCE SPECIFICATION -----")[0].strip() + "\n"
    assert (ROOT / "reference/PVB24_ENGINEERING_SPEC_v1.0.txt").read_bytes() == extracted.encode()
    assert hashlib.sha256(extracted.encode()).hexdigest() == module.SOURCE_SHA256


def test_provenance():
    assert module.verify()["live_enabled"] is False


def test_all_authorized_decisions_preserved_verbatim():
    master = (ROOT / "reference/PVB24_MASTER_IMPLEMENTATION_PROMPT.txt").read_text()
    section = master.split("6. PRE-AUTHORIZED IMPLEMENTATION DECISIONS")[1]
    section = section.split("7. MILESTONE EXECUTION PLAN")[0]
    expected = re.findall(
        r"\n(UD-\d{2}) ([^\n]+)\n(.*?)(?=\nUD-\d{2} |\nSPEC_CONFLICT resolution summary:)",
        section,
        re.S,
    )
    config = json.loads((ROOT / "config/pvb24_v1.json").read_text())
    assert len(expected) == len(config["decisions"]) == 20
    for decision, (identity, title, body) in zip(config["decisions"], expected, strict=True):
        assert decision["decision_id"] == identity
        assert decision["title"] == title
        assert decision["decision"] == body.strip()
        assert decision["alpha_semantics_changed"] is False


@pytest.mark.parametrize("target", ["source", "config", "seed", "live"])
def test_mutations_fail_closed(tmp_path, target):
    for name in ["config", "reference"]:
        shutil.copytree(ROOT / name, tmp_path / name)
    if target == "source":
        path = tmp_path / "reference/PVB24_ENGINEERING_SPEC_v1.0.txt"
        path.write_bytes(path.read_bytes() + b" ")
    elif target == "config":
        path = tmp_path / "config/pvb24_v1.json"
        data = json.loads(path.read_text())
        data["risk"]["normal_fraction"] = "0.02"
        path.write_text(json.dumps(data))
    else:
        path = tmp_path / "config/manifest.json"
        data = json.loads(path.read_text())
        data["seed" if target == "seed" else "live_enabled"] = 42 if target == "seed" else True
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        module.verify(tmp_path)


def test_final_is_locked_and_reference_equity_is_preselected():
    research = json.loads((ROOT / "config/pvb24_v1.json").read_text())["research"]
    assert research["final_access"] == "LOCKED"
    assert research["reference_equity"] == "1000"
    assert research["capacity_equities"] == ["200", "10000"]


def test_pin_matches_ci_and_documentation():
    pin = json.loads((ROOT / "config/manifest.json").read_text())["freqtrade"]
    for name in ["README.md", "docs/FREQTRADE_PIN.md", ".github/workflows/ci.yml"]:
        text = (ROOT / name).read_text()
        assert pin["commit"] in text
        assert pin["version"] in text
