import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pvb24.accounting.ledger import Ledger, LedgerStore
from pvb24.data.announcements import (
    AnnouncementRequest,
    acquire,
    decode,
    delisting_events,
    load_acquired,
)
from pvb24.data.lifecycle import entry_block_reason
from pvb24.decimal_math import D
from pvb24.ids import canonical, digest
from pvb24.replay.account import AccountReplay
from pvb24.replay.events import Delivery
from pvb24.risk.reservations import Portfolio, Reservations
from pvb24.state import Journal
from pvb24.types import Quality

PUBLISHED = datetime(2024, 3, 19, 5, 5, 2, 6000, tzinfo=UTC)
SETTLEMENT = datetime(2024, 3, 26, 9, tzinfo=UTC)


def node(tag, *children):
    return {
        "node": "element",
        "tag": tag,
        "child": [{"node": "text", "text": c} if isinstance(c, str) else c for c in children],
    }


def fixture(kind="DELISTING"):
    if kind == "DELISTING":
        body = {
            "node": "root",
            "child": [
                node(
                    "p",
                    "Binance Futures will close all positions and conduct an automatic "
                    "settlement on the USDⓈ-M ABCUSDT and XYZUSDT perpetual contracts at "
                    "2024-03-26 09:00 (UTC). The contracts will be delisted after settlement.",
                ),
                node(
                    "p",
                    "Users are not allowed to open new positions for the aforementioned "
                    "contracts starting from 2024-03-26 08:30 (UTC).",
                ),
            ],
        }
        facts = [
            {
                "symbol": s,
                "scheduled_settlement_at": SETTLEMENT,
                "entry_cutoff_at": SETTLEMENT - timedelta(minutes=30),
            }
            for s in ("ABCUSDT", "XYZUSDT")
        ]
    else:
        body = {
            "node": "root",
            "child": [
                node(
                    "p",
                    "Binance will adjust the tick size of the following USDⓈ-M perpetual "
                    "futures contracts at 2024-03-26 09:00 (UTC).",
                ),
                node(
                    "table",
                    node(
                        "tbody",
                        node(
                            "tr",
                            *[
                                node("td", s)
                                for s in ("Contract Type", "Trading Pair", "Before", "After")
                            ],
                        ),
                        node(
                            "tr",
                            *[
                                node("td", s)
                                for s in ("USDⓈ-M Futures", "ABCUSDT", "0.01", "0.001")
                            ],
                        ),
                        node("tr", *[node("td", s) for s in ("XYZUSDC", "0.1", "0.01")]),
                    ),
                ),
            ],
        }
        facts = [
            {
                "symbol": "ABCUSDT",
                "effective_at": SETTLEMENT,
                "tick_before": "0.01",
                "tick_after": "0.001",
            },
            {
                "symbol": "XYZUSDC",
                "effective_at": SETTLEMENT,
                "tick_before": "0.1",
                "tick_after": "0.01",
            },
        ]
    body_raw = canonical(body)
    request = AnnouncementRequest(
        "a" * 32, "2024-03-19", kind, hashlib.sha256(body_raw.encode()).hexdigest(), digest(facts)
    )
    response = {
        "success": True,
        "data": {
            "code": request.code,
            "publishDate": 1710824702006,
            "lastUpdateTime": 0,
            "version": "1",
            "body": body_raw,
        },
    }
    return request, response


def acquired(tmp_path, kind="DELISTING"):
    request, response = fixture(kind)
    report, path = acquire(request, tmp_path, fetch=lambda url: canonical(response).encode())
    return report, path, Path(path).stem


def test_original_clock_precision_preliminary_policy_and_no_fabricated_metadata():
    request, response = fixture()
    report = decode(request, canonical(response).encode())
    assert report["published_at"] == PUBLISHED
    assert report["available_at"] == PUBLISHED + timedelta(seconds=2)
    assert report["known_updated_at"] is None
    assert report["actual_received_at_historical"] is None
    assert (
        not report["historical_verified"] and not report["original_revision_as_published_verified"]
    )
    assert not report["security_master_complete"] and not report["contract_rules_complete"]
    assert not report["settlement_execution_proven"]


def test_known_revision_update_is_never_backdated_to_initial_publication(tmp_path):
    request, response = fixture()
    response["data"]["lastUpdateTime"] += 1710911102006
    report, path = acquire(request, tmp_path, fetch=lambda url: canonical(response).encode())
    args = dict(expected_report_hash=Path(path).stem)
    assert not delisting_events(tmp_path, path, through=PUBLISHED + timedelta(hours=2), **args)
    events = delisting_events(tmp_path, path, through=PUBLISHED + timedelta(days=2), **args)
    assert len(events) == 2
    assert events[0].available_at == PUBLISHED + timedelta(days=1, seconds=2)
    assert events[0].event_time == PUBLISHED
    assert report["known_updated_at"] is not None


def test_revalidated_real_adapter_events_gate_account_and_survive_restart(tmp_path):
    report, path, pin = acquired(tmp_path)
    available = PUBLISHED + timedelta(seconds=2)
    assert not delisting_events(
        tmp_path, path, expected_report_hash=pin, through=available - timedelta(microseconds=1)
    )
    events = delisting_events(tmp_path, path, expected_report_hash=pin, through=available)
    db = Journal(tmp_path / "account.sqlite")
    LedgerStore(db, "research").initialize(Ledger(D("1000")))
    Reservations(db, "research").initialize(Portfolio(D("1000"), D("1000")))
    replay = AccountReplay(db, "research", Quality.PRELIMINARY)
    for event in events:
        delivery = Delivery(event, "CONSERVATIVE_PRIORITY", 0)
        result = replay(delivery)
        assert replay(delivery) == result
        assert (
            entry_block_reason(db.db, "research", event.payload["record"]["symbol"])
            == "DELISTING_ANNOUNCED"
        )
    assert not list(db.db.execute("SELECT * FROM intents"))  # No fabricated orders or fills.
    db.close()
    db = Journal(tmp_path / "account.sqlite")
    replay = AccountReplay(db, "research", Quality.PRELIMINARY)
    assert replay(Delivery(events[0], "CONSERVATIVE_PRIORITY", 0))["blocked_symbol"] == "ABCUSDT"
    db.close()
    assert report["quality"] == "PRELIMINARY"


def test_preliminary_announcement_cannot_enter_verified_replay(tmp_path):
    _, path, pin = acquired(tmp_path)
    event = delisting_events(
        tmp_path, path, expected_report_hash=pin, through=PUBLISHED + timedelta(seconds=2)
    )[0]
    db = Journal(tmp_path / "account.sqlite")
    LedgerStore(db, "verified").initialize(Ledger(D("1000")))
    replay = AccountReplay(db, "verified", Quality.VERIFIED)
    with pytest.raises(ValueError):
        replay(Delivery(event, "CONSERVATIVE_PRIORITY", 0))
    assert entry_block_reason(db.db, "verified", "ABCUSDT") is None
    db.close()


def test_tick_delta_retains_unsupported_quote_and_never_becomes_full_rules(tmp_path):
    report, path, pin = acquired(tmp_path, "TICK_CHANGE")
    assert [r["symbol"] for r in report["facts"]] == ["ABCUSDT", "XYZUSDC"]
    assert report["facts"][0]["tick_after"] == "0.001"
    assert not report["contract_rules_complete"]
    assert not delisting_events(tmp_path, path, expected_report_hash=pin, through=SETTLEMENT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("code", "b" * 32),
        ("publishDate", 1710824702.006),
        ("publishDate", 1751328000000),
        ("lastUpdateTime", None),
        ("lastUpdateTime", 1),
        ("lastUpdateTime", 1751328000000),
        ("version", None),
    ],
)
def test_malformed_or_final_source_identity_clocks_fail_closed(field, value):
    request, response = fixture()
    response["data"][field] = value
    with pytest.raises(ValueError):
        decode(request, json.dumps(response).encode())


def test_body_revision_and_independently_reviewed_facts_are_both_pinned():
    request, response = fixture()
    raw = canonical(response).encode()
    with pytest.raises(ValueError, match="facts differ"):
        decode(replace(request, facts_hash="0" * 64), raw)
    response["data"]["body"] = response["data"]["body"].replace("ABCUSDT", "NEWUSDT")
    with pytest.raises(ValueError, match="body changed"):
        decode(request, canonical(response).encode())


def test_unrelated_current_recommendations_do_not_change_semantic_revision():
    request, response = fixture()
    original = decode(request, canonical(response).encode())
    response["data"]["relatedArticles"] = [{"code": "other", "publishDate": 1751328000000}]
    later = decode(request, canonical(response).encode())
    assert original["source_sha256"] != later["source_sha256"]
    assert original["revision_id"] == later["revision_id"]
    assert original["facts"] == later["facts"]


def test_duplicate_json_keys_and_duplicate_contract_rows_are_rejected():
    request, response = fixture()
    raw = canonical(response).encode().replace(b'"success":true', b'"success":false,"success":true')
    with pytest.raises(ValueError, match="Duplicate"):
        decode(request, raw)
    response["data"]["body"] = response["data"]["body"].replace("XYZUSDT", "ABCUSDT")
    request = replace(
        request, body_sha256=hashlib.sha256(response["data"]["body"].encode()).hexdigest()
    )
    with pytest.raises(ValueError, match="unique"):
        decode(request, canonical(response).encode())


def test_retained_raw_bytes_report_paths_and_pin_tampering_are_detected(tmp_path):
    report, path, pin = acquired(tmp_path)
    assert load_acquired(tmp_path, path, expected_report_hash=pin) == report
    for wrong in ("../" + path, str((tmp_path / path).resolve())):
        with pytest.raises(ValueError, match="pinned"):
            load_acquired(tmp_path, wrong, expected_report_hash=pin)
    with pytest.raises(ValueError):
        load_acquired(tmp_path, path, expected_report_hash="0" * 64)
    raw_path = tmp_path / report["source_object"]
    raw_path.write_bytes(raw_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="source bytes"):
        load_acquired(tmp_path, path, expected_report_hash=pin)


def test_final_request_fails_before_network_and_final_replay_before_file_io(tmp_path):
    request, _ = fixture()
    object.__setattr__(request, "published_day", "2025-07-01")
    calls = []
    with pytest.raises(ValueError, match="Final"):
        acquire(request, tmp_path, fetch=lambda url: calls.append(url))
    assert not calls
    with pytest.raises(ValueError, match="Pre-Final"):
        delisting_events(
            tmp_path,
            "absent",
            expected_report_hash="0" * 64,
            through=datetime(2025, 7, 1, tzinfo=UTC),
        )
