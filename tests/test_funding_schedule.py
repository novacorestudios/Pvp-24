import hashlib
import json

import pytest
from test_funding_coverage import REQ, pair

from pvb24.data.funding_coverage import summarize
from pvb24.data.funding_schedule import audit_funding_schedule
from pvb24.ids import canonical


def selection(tmp_path, **pair_kwargs):
    monthly, name = pair(tmp_path, **pair_kwargs)
    summary = summarize((REQ,), ((monthly, name),))
    path = tmp_path / "schedule-summary.json"
    path.write_text(canonical(summary))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_schedule_audit_preserves_exact_jitter_without_promoting_coverage(tmp_path):
    path, pin = selection(tmp_path)
    result = audit_funding_schedule(tmp_path, path, expected_summary_sha256=pin)
    assert result["archive_settlement_rows"] == 2
    assert result["adjacent_archive_pairs"] == 1
    assert result["declared_interval_hours"] == ["8"]
    assert result["exact_declared_elapsed_pairs"] == 0
    assert result["nonexact_declared_elapsed_pairs"] == 1
    assert result["minimum_difference_microseconds"] == 1000
    assert result["maximum_difference_microseconds"] == 1000
    assert result["maximum_absolute_difference_microseconds"] == 1000
    assert result["possible_missing_declared_interval_pairs"] == 0
    assert result["timestamp_rounding_applied"] is False
    assert result["source_query_reconsumption_complete"] is True
    assert result["ex_post_settlement_index_corroborated"] is True
    assert result["causal_next_settlement_time_verified"] is False
    assert result["funding_schedule_complete"] is False
    assert result["funding_coverage_attestation_emitted"] is False
    assert result["funding_reserve_coverage_qualified"] is False
    assert result["final_test_access"] == "LOCKED"


def test_archive_unavailability_stays_visible_and_cannot_be_called_schedule_coverage(tmp_path):
    path, pin = selection(tmp_path, missing_archive=True)
    result = audit_funding_schedule(tmp_path, path, expected_summary_sha256=pin)
    assert result["archive_unavailable_months"] == ["2024-01"]
    assert result["archive_settlement_rows"] == 0
    assert result["source_query_reconsumption_complete"] is True
    assert result["ex_post_settlement_index_corroborated"] is False
    assert result["funding_schedule_complete"] is False


def test_schedule_reconsumption_detects_underlying_archive_tamper(tmp_path):
    path, pin = selection(tmp_path)
    archive = next((tmp_path / "archives" / "objects").glob("*.zip"))
    archive.write_bytes(archive.read_bytes() + b" ")
    with pytest.raises(ValueError):
        audit_funding_schedule(tmp_path, path, expected_summary_sha256=pin)


def test_schedule_summary_pin_and_final_lock_fail_closed(tmp_path):
    path, pin = selection(tmp_path)
    with pytest.raises(ValueError, match="hash changed"):
        audit_funding_schedule(tmp_path, path, expected_summary_sha256="0" * 64)

    value = json.loads(path.read_text())
    value["final_test_access"] = "OPEN"
    path.write_text(canonical(value))
    changed = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Locked"):
        audit_funding_schedule(tmp_path, path, expected_summary_sha256=changed)
