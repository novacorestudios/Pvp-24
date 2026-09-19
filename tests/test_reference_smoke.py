import hashlib
import json
from pathlib import Path

import pytest

from pvb24.decimal_math import D
from pvb24.replay.smoke import run_smoke

ROOT = Path(__file__).resolve().parents[1]


def test_integrated_smoke_and_future_append_keep_all_historical_decisions_and_economics(tmp_path):
    first = run_smoke(ROOT, tmp_path / "first")
    future = run_smoke(ROOT, tmp_path / "future", append_future=True)
    assert first["trace_hash"] == future["trace_hash"]
    assert first["ledger"] == future["ledger"]
    assert first["entry"] == future["entry"] and first["exit"] == future["exit"]
    assert first["manifest_hash"] != future["manifest_hash"]  # source coverage did change
    assert first["restart_verified"] and first["replay_events"] > 900
    assert first["orders_sent_to_exchange"] == 0 and not first["paper_ready"]
    assert not first["historical_performance"] and first["acceptance_status"] == "NOT_EVALUATED"
    ledger = first["ledger"]
    assert ledger["positions"][0]["quantity"] == "0"
    assert D(ledger["cash"]) == D(1000) + D(ledger["realized_gross"]) - D(ledger["fees"]) + D(
        ledger["funding"]
    )
    manifest = json.loads((tmp_path / "first" / "manifest.json").read_text())
    assert (
        hashlib.sha256((tmp_path / "first" / "synthetic-events.jsonl").read_bytes()).hexdigest()
        == manifest["data_sha256"]
    )
    assert manifest["code"]["git_sha"] and manifest["code"]["source_tree_hash"]


def test_smoke_refuses_to_overwrite_existing_evidence(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    marker = existing / "keep.txt"
    marker.write_text("original evidence")
    with pytest.raises(FileExistsError):
        run_smoke(ROOT, existing)
    assert marker.read_text() == "original evidence"
