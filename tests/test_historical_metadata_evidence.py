import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from pvb24.data.historical_metadata_evidence import (
    compile_partial_historical_metadata,
    preliminary_listing_securities,
)
from pvb24.ids import canonical, digest

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def write(path, value):
    raw = canonical(value).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def refresh_qualification(value):
    results = value["results"]
    counts = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    requests = [
        row["review_request"] for row in results if row["status"] == "QUALIFIED_PRELIMINARY"
    ]
    value["candidate_count"] = len(results)
    value["status_counts"] = dict(sorted(counts.items()))
    value["source_fetch_complete"] = counts.get("SOURCE_ERROR", 0) == 0
    value["results_hash"] = digest(results)
    value["review_requests"] = requests
    value["review_requests_hash"] = digest(requests)
    return value


def refresh_lifecycle(value):
    reconciliations = value["reconciliations"]
    counts = {}
    for row in reconciliations:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    value["reconciliation_count"] = len(reconciliations)
    value["status_counts"] = dict(sorted(counts.items()))
    value["reconciliation_hash"] = digest(reconciliations)
    return value


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
        facts = [fact]
        facts_hash = digest(facts)
        body_sha256 = hashlib.sha256(f"{code}-body".encode()).hexdigest()
        review_request = {
            "code": code,
            "published_day": NOW.date().isoformat(),
            "kind": kind,
            "body_sha256": body_sha256,
            "facts_hash": facts_hash,
        }
        return {
            "code": code,
            "kind": kind,
            "status": "QUALIFIED_PRELIMINARY",
            "body_sha256": body_sha256,
            "facts": facts,
            "facts_hash": facts_hash,
            "review_request": review_request,
            "published_at": NOW.isoformat(),
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
    qualification = refresh_qualification(
        {
            "schema": "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_V3",
            "final_test_access": "LOCKED",
            "results": results,
        }
    )

    reconciliations = [
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
    ]
    lifecycle = refresh_lifecycle(
        {
            "schema": "PVB24_LIFECYCLE_ARCHIVE_ACTIVITY_V3",
            "quality": "PRELIMINARY",
            "final_test_access": "LOCKED",
            "source_failures": [],
            "qualification_results_hash": qualification["results_hash"],
            "qualification_review_requests_hash": qualification["review_requests_hash"],
            "qualified_fact_count": 3,
            "effective_fact_count": 3,
            "superseded_count": 0,
            "superseded_facts": [],
            "superseded_hash": digest([]),
            "late_revision_count": 0,
            "late_revisions": [],
            "late_revision_hash": digest([]),
            "probe_count": 6,
            "reconciliations": reconciliations,
        }
    )

    tick_facts = [
        {
            "symbol": "AAAUSDT",
            "effective_at": (NOW + timedelta(days=3)).isoformat(),
            "tick_before": "0.1",
            "tick_after": "0.01",
        },
        {
            "symbol": "AAAUSDC",
            "effective_at": (NOW + timedelta(days=3)).isoformat(),
            "tick_before": "0.1",
            "tick_after": "0.01",
        },
    ]
    tick_article_payload = {
        "kind": "TICK_CHANGE",
        "source": "https://www.binance.com/tick",
        "revision_id": "5" * 64,
        "source_sha256": "4" * 64,
        "published_at": NOW.isoformat(),
        "available_at": (NOW + timedelta(hours=1)).isoformat(),
        "facts": tick_facts,
        "facts_hash": digest(tick_facts),
    }
    tick_article = {
        "report_path": "reports/tick.json",
        "report_hash": digest(tick_article_payload),
        **tick_article_payload,
    }
    coverage = [
        {
            "symbol": fact["symbol"],
            "kind": "TICK_CHANGE",
            "source": tick_article["source"],
            "revision_id": tick_article["revision_id"],
            "source_sha256": tick_article["source_sha256"],
            "published_at": tick_article["published_at"],
            "available_at": tick_article["available_at"],
            "facts": fact,
            "quality": "PRELIMINARY",
            "history_coverage_start": None,
            "history_coverage_end": None,
            "full_security_record": "MISSING",
            "full_contract_rules": "MISSING",
            "actual_settlement_fill": "NOT_PROVEN",
            "eligibility": "NOT_INFERRED_FROM_ANNOUNCEMENT",
        }
        for fact in tick_facts
    ]
    ticks = {
        "schema": "PVB24_ANNOUNCEMENT_SOURCE_COVERAGE_V1",
        "final_test_access": "LOCKED",
        "requested_articles": 1,
        "acquired_articles": 1,
        "failures": [],
        "articles": [tick_article],
        "coverage": coverage,
        "data_hash": digest([tick_article]),
    }
    ticks["report_hash"] = digest(ticks)

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


@pytest.mark.parametrize("field", ["candidate_count", "results_hash", "review_requests_hash"])
def test_qualification_internal_summaries_are_recomputed(field, tmp_path):
    q, lifecycle_ref, tick_ref = fixtures(tmp_path)
    value = json.loads(q[0].read_text())
    value[field] = 999 if field == "candidate_count" else "0" * 64
    changed = write(tmp_path / f"q-{field}.json", value)
    with pytest.raises(ValueError, match="Qualification"):
        compile_partial_historical_metadata(
            changed[0],
            changed[1],
            lifecycle_ref[0],
            lifecycle_ref[1],
            tick_ref[0],
            tick_ref[1],
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("reconciliation_count", 99),
        ("reconciliation_hash", "0" * 64),
        ("superseded_hash", "0" * 64),
        ("probe_count", 99),
    ],
)
def test_lifecycle_internal_summaries_are_recomputed(field, value, tmp_path):
    q, lifecycle_ref, tick_ref = fixtures(tmp_path)
    payload = json.loads(lifecycle_ref[0].read_text())
    payload[field] = value
    changed = write(tmp_path / f"l-{field}.json", payload)
    with pytest.raises(ValueError, match="Lifecycle"):
        compile_partial_historical_metadata(
            q[0],
            q[1],
            changed[0],
            changed[1],
            tick_ref[0],
            tick_ref[1],
        )


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("data_hash", "article count/data hash"),
        ("article_report_hash", "article report hash"),
        ("report_hash", "report hash"),
        ("acquired_articles", "article count/data hash"),
    ],
)
def test_tick_internal_hashes_and_counts_are_recomputed(mutation, match, tmp_path):
    q, lifecycle_ref, tick_ref = fixtures(tmp_path)
    payload = json.loads(tick_ref[0].read_text())
    if mutation == "data_hash":
        payload["data_hash"] = "0" * 64
    elif mutation == "article_report_hash":
        payload["articles"][0]["report_hash"] = "0" * 64
        payload["data_hash"] = digest(payload["articles"])
        unhashed = dict(payload)
        unhashed.pop("report_hash")
        payload["report_hash"] = digest(unhashed)
    elif mutation == "report_hash":
        payload["report_hash"] = "0" * 64
    else:
        payload["acquired_articles"] = 99
        unhashed = dict(payload)
        unhashed.pop("report_hash")
        payload["report_hash"] = digest(unhashed)
    changed = write(tmp_path / f"t-{mutation}.json", payload)
    with pytest.raises(ValueError, match=match):
        compile_partial_historical_metadata(
            q[0],
            q[1],
            lifecycle_ref[0],
            lifecycle_ref[1],
            changed[0],
            changed[1],
        )


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


@pytest.mark.parametrize("reconciliation_index", [0, 2])
def test_lifecycle_symbol_must_match_qualified_fact(reconciliation_index, tmp_path):
    q, lifecycle_ref, tick_ref = fixtures(tmp_path)
    value = json.loads(lifecycle_ref[0].read_text())
    value["reconciliations"][reconciliation_index]["symbol"] = "ZZZUSDT"
    refresh_lifecycle(value)
    lifecycle_ref = write(lifecycle_ref[0], value)
    with pytest.raises(ValueError, match="Lifecycle symbol differs from qualified fact"):
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
    refresh_lifecycle(value)
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
    refresh_qualification(value)
    q = write(q[0], value)
    lifecycle_value = json.loads(lifecycle_ref[0].read_text())
    lifecycle_value["qualification_results_hash"] = value["results_hash"]
    lifecycle_value["qualification_review_requests_hash"] = value["review_requests_hash"]
    lifecycle_ref = write(lifecycle_ref[0], lifecycle_value)
    with pytest.raises(ValueError, match="pre-Final"):
        compile_partial_historical_metadata(
            q[0],
            q[1],
            lifecycle_ref[0],
            lifecycle_ref[1],
            tick_ref[0],
            tick_ref[1],
        )
