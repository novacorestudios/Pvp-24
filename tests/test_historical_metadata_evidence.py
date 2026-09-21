import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from pvb24.data.historical_metadata_evidence import (
    compile_partial_historical_metadata,
    preliminary_listing_securities,
)
from pvb24.ids import canonical

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def write(path, value):
    raw = canonical(value).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def fixtures(tmp_path):
    listing_fact = {
        "symbol": "AAAUSDT",
        "contract_type": "PERPETUAL",
        "quote_asset": "USDT",
        "launch_at": (NOW + timedelta(days=1)).isoformat(),
        "max_leverage": 50,
    }
    unknown_fact = {
        "symbol": "BBBUSDT",
        "contract_type": "PERPETUAL",
        "quote_asset": "USDT",
        "launch_at": (NOW + timedelta(days=2)).isoformat(),
        "max_leverage": 50,
    }
    delist_fact = {
        "symbol": "CCCUSDT",
        "entry_cutoff_at": (NOW + timedelta(days=9, hours=23, minutes=30)).isoformat(),
        "scheduled_settlement_at": (NOW + timedelta(days=10)).isoformat(),
    }

    def article(code, kind, fact, source_hash):
        return {
            "code": code,
            "kind": kind,
            "status": "QUALIFIED_PRELIMINARY",
            "facts": [fact],
            "available_at": (NOW + timedelta(hours=1)).isoformat(),
            "article_url": f"https://www.binance.com/article/{code}",
            "source_sha256": source_hash,
            "source_retained": True,
        }

    results = [
        article("listing", "LISTING", listing_fact, "1" * 64),
        article("unknown", "LISTING", unknown_fact, "2" * 64),
        article("delist", "DELISTING", delist_fact, "3" * 64),
    ]
    qualification = {
        "schema": "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_V3",
        "final_test_access": "LOCKED",
        "source_fetch_complete": True,
        "results": results,
        "results_hash": "a" * 64,
        "review_requests_hash": "b" * 64,
    }
    lifecycle = {
        "schema": "PVB24_LIFECYCLE_ARCHIVE_ACTIVITY_V3",
        "final_test_access": "LOCKED",
        "source_failures": [],
        "qualification_results_hash": "a" * 64,
        "qualification_review_requests_hash": "b" * 64,
        "reconciliation_hash": "c" * 64,
        "reconciliation_count": 3,
        "reconciliations": [
            {
                "kind": "LISTING",
                "status": "CONSISTENT_EVENT_BOUNDARY_ONLY",
                "symbol": "AAAUSDT",
                "article_code": "listing",
                "article_source_sha256": "1" * 64,
                "event_at": listing_fact["launch_at"],
                "fact": listing_fact,
            },
            {
                "kind": "LISTING",
                "status": "UNKNOWN",
                "symbol": "BBBUSDT",
                "article_code": "unknown",
                "article_source_sha256": "2" * 64,
                "event_at": unknown_fact["launch_at"],
                "fact": unknown_fact,
            },
            {
                "kind": "DELISTING",
                "status": "CONSISTENT_EVENT_BOUNDARY_ONLY",
                "symbol": "CCCUSDT",
                "article_code": "delist",
                "article_source_sha256": "3" * 64,
                "event_at": delist_fact["scheduled_settlement_at"],
                "fact": delist_fact,
            },
        ],
    }
    ticks = {
        "schema": "PVB24_ANNOUNCEMENT_SOURCE_COVERAGE_V1",
        "final_test_access": "LOCKED",
        "data_hash": "d" * 64,
        "coverage": [
            {
                "kind": "TICK_CHANGE",
                "available_at": (NOW + timedelta(hours=1)).isoformat(),
                "source": "https://www.binance.com/tick",
                "source_sha256": "4" * 64,
                "facts": {
                    "symbol": "AAAUSDT",
                    "effective_at": (NOW + timedelta(days=3)).isoformat(),
                    "tick_before": "0.1",
                    "tick_after": "0.01",
                },
            },
            {
                "kind": "TICK_CHANGE",
                "available_at": (NOW + timedelta(hours=1)).isoformat(),
                "source": "https://www.binance.com/tick",
                "source_sha256": "4" * 64,
                "facts": {
                    "symbol": "AAAUSDC",
                    "effective_at": (NOW + timedelta(days=3)).isoformat(),
                    "tick_before": "0.1",
                    "tick_after": "0.01",
                },
            },
        ],
    }
    q = write(tmp_path / "q.json", qualification)
    lifecycle_ref = write(tmp_path / "l.json", lifecycle)
    tick_ref = write(tmp_path / "t.json", ticks)
    return q, lifecycle_ref, tick_ref


def compile_fixture(tmp_path):
    q, lifecycle_ref, tick_ref = fixtures(tmp_path)
    return compile_partial_historical_metadata(
        q[0],
        q[1],
        lifecycle_ref[0],
        lifecycle_ref[1],
        tick_ref[0],
        tick_ref[1],
    )


def test_compiler_emits_only_consistent_preliminary_listing_candidate(tmp_path):
    result = compile_fixture(tmp_path)
    assert result["listing_candidate_count"] == 1
    assert result["unresolved_listing_count"] == 1
    assert result["delisting_event_count"] == 1
    assert result["tick_field_event_count"] == 1
    assert result["excluded_non_usdt_tick_symbols"] == ["AAAUSDC"]
    assert result["full_security_rows_emitted"] == 0
    assert result["full_contract_rule_rows_emitted"] == 0
    assert result["classification_complete"] is False
    assert result["historical_universe_complete"] is False
    assert result["contract_rule_history_complete"] is False
    assert result["final_test_access"] == "LOCKED"


def test_preliminary_security_keeps_unknown_classification_and_causal_times(tmp_path):
    result = compile_fixture(tmp_path)
    rows = preliminary_listing_securities(result)
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "AAAUSDT"
    assert row.classification == "UNKNOWN"
    assert row.historical_verified is False
    assert row.available_at < row.trading_start
    assert row.effective_from == row.trading_start


def test_tick_evidence_is_field_level_only(tmp_path):
    result = compile_fixture(tmp_path)
    tick = result["tick_field_events"][0]
    assert tick["tick_before"] == "0.1"
    assert tick["tick_after"] == "0.01"
    assert tick["full_contract_rules_emitted"] is False
    assert "MAINTENANCE_TIERS" in result["mandatory_rule_gaps"]


@pytest.mark.parametrize("target", ["qualification", "lifecycle", "tick"])
def test_pins_are_rechecked(target, tmp_path):
    q, lifecycle_ref, tick_ref = fixtures(tmp_path)
    args = [q[0], q[1], lifecycle_ref[0], lifecycle_ref[1], tick_ref[0], tick_ref[1]]
    index = {"qualification": 1, "lifecycle": 3, "tick": 5}[target]
    args[index] = "0" * 64
    with pytest.raises(ValueError, match="hash changed"):
        compile_partial_historical_metadata(*args)



def test_source_failure_shape_and_contents_fail_closed(tmp_path):
    q, lifecycle_ref, tick_ref = fixtures(tmp_path)
    for source_failures in (1, ["failed-probe"]):
        value = json.loads(lifecycle_ref[0].read_text())
        value["source_failures"] = source_failures
        changed = write(tmp_path / f"l-{len(str(source_failures))}.json", value)
        with pytest.raises(ValueError, match="empty explicit list"):
            compile_partial_historical_metadata(
                q[0],
                q[1],
                changed[0],
                changed[1],
                tick_ref[0],
                tick_ref[1],
            )


def test_lifecycle_must_bind_same_qualification_results(tmp_path):
    q, lifecycle_ref, tick_ref = fixtures(tmp_path)
    value = json.loads(lifecycle_ref[0].read_text())
    value["qualification_results_hash"] = "9" * 64
    lifecycle_ref = write(lifecycle_ref[0], value)
    with pytest.raises(ValueError, match="identities disagree"):
        compile_partial_historical_metadata(
            q[0],
            q[1],
            lifecycle_ref[0],
            lifecycle_ref[1],
            tick_ref[0],
            tick_ref[1],
        )


def test_unknown_listing_is_never_materialized_as_security(tmp_path):
    result = compile_fixture(tmp_path)
    assert [row.symbol for row in preliminary_listing_securities(result)] == ["AAAUSDT"]
    assert result["unresolved_listings"][0]["symbol"] == "BBBUSDT"


def test_event_time_and_final_lock_fail_closed(tmp_path):
    q, lifecycle_ref, tick_ref = fixtures(tmp_path)
    value = json.loads(lifecycle_ref[0].read_text())
    value["reconciliations"][0]["event_at"] = (NOW + timedelta(days=4)).isoformat()
    lifecycle_ref = write(lifecycle_ref[0], value)
    with pytest.raises(ValueError, match="event time"):
        compile_partial_historical_metadata(
            q[0],
            q[1],
            lifecycle_ref[0],
            lifecycle_ref[1],
            tick_ref[0],
            tick_ref[1],
        )

    q, lifecycle_ref, tick_ref = fixtures(tmp_path / "final")
    value = json.loads(q[0].read_text())
    value["results"][0]["available_at"] = "2025-07-01T00:00:00+00:00"
    q = write(q[0], value)
    with pytest.raises(ValueError, match="Final Test"):
        compile_partial_historical_metadata(
            q[0],
            q[1],
            lifecycle_ref[0],
            lifecycle_ref[1],
            tick_ref[0],
            tick_ref[1],
        )
