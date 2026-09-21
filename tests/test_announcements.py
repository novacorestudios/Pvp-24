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
    extract_facts,
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
LEGACY_PUBLISHED = datetime(2020, 2, 13, 6, 1, tzinfo=UTC)
LEGACY_LAUNCH = datetime(2020, 2, 14, 8, tzinfo=UTC)


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


def test_postponement_extracts_only_main_causal_schedule_not_later_editor_note():
    body = {
        "node": "root",
        "child": [
            node(
                "p",
                "Note: The delisting date has been revised to 2025-01-31 09:00 (UTC).",
            ),
            node(
                "p",
                "Binance Futures will postpone the delisting of the USDⓈ-M OMGUSDT "
                "Perpetual Contract to 2024-12-30 09:00 (UTC). We will conduct automatic "
                "settlements on the USDⓈ-M OMGUSDT Perpetual Contract and then delist "
                "this contract.",
            ),
        ],
    }
    assert extract_facts("DELISTING", body) == [
        {
            "symbol": "OMGUSDT",
            "scheduled_settlement_at": datetime(2024, 12, 30, 9, tzinfo=UTC),
            "revision_type": "POSTPONEMENT",
        }
    ]


def test_listing_postponement_extracts_explicit_old_and_new_schedule_only():
    body = {
        "node": "root",
        "child": [
            node(
                "p",
                "The DOT USDT-margined perpetual contract trading start time will be delayed to "
                "2020/08/22 7:00 AM (UTC). Please note that the previous start time was at "
                "2020/08/20 7:00 AM (UTC). We apologize for any inconvenience caused.",
            )
        ],
    }
    assert extract_facts("LISTING", body) == [
        {
            "symbol": "DOTUSDT",
            "launch_at": datetime(2020, 8, 22, 7, tzinfo=UTC),
            "previous_launch_at": datetime(2020, 8, 20, 7, tzinfo=UTC),
            "revision_type": "POSTPONEMENT",
            "contract_type": "PERPETUAL",
            "quote_asset": "USDT",
        }
    ]

    backwards = {
        "node": "root",
        "child": [
            node(
                "p",
                "The DOT USDT-margined perpetual contract trading start time will be delayed to "
                "2020/08/20 7:00 AM (UTC). Please note that the previous start time was at "
                "2020/08/22 7:00 AM (UTC).",
            )
        ],
    }
    with pytest.raises(ValueError, match="strictly later"):
        extract_facts("LISTING", backwards)


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


def legacy_listing_fixture():
    body = {
        "node": "root",
        "child": [
            node(
                "p",
                "Binance Futures will launch VET/USDT perpetual contract, with trading opening "
                "at 2020/02/14 08:00 AM (UTC). Users will be able to select between 1-50x "
                "leverage.",
            )
        ],
    }
    facts = [
        {
            "symbol": "VETUSDT",
            "launch_at": LEGACY_LAUNCH,
            "max_leverage": 50,
            "contract_type": "PERPETUAL",
            "quote_asset": "USDT",
        }
    ]
    body_raw = canonical(body)
    request = AnnouncementRequest(
        "360039757391",
        "2020-02-13",
        "LISTING",
        hashlib.sha256(body_raw.encode()).hexdigest(),
        digest(facts),
    )
    response = {
        "success": True,
        "data": {
            "code": request.code,
            "publishDate": 1581573660000,
            "lastUpdateTime": 0,
            "version": "1",
            "body": body_raw,
        },
    }
    return request, response


def test_legacy_numeric_article_listing_extracts_only_announced_partial_facts():
    request, response = legacy_listing_fixture()
    report = decode(request, canonical(response).encode())
    assert report["published_at"] == LEGACY_PUBLISHED
    assert report["available_at"] == LEGACY_PUBLISHED + timedelta(seconds=2)
    assert report["facts"] == [
        {
            "symbol": "VETUSDT",
            "launch_at": LEGACY_LAUNCH,
            "max_leverage": 50,
            "contract_type": "PERPETUAL",
            "quote_asset": "USDT",
        }
    ]
    assert not report["security_master_complete"]
    assert not report["contract_rules_complete"]
    assert not report["historical_verified"]


def test_legacy_listing_is_not_promoted_to_delisting_or_full_rule_event(tmp_path):
    request, response = legacy_listing_fixture()
    report, path = acquire(request, tmp_path, fetch=lambda url: canonical(response).encode())
    pin = Path(path).stem
    assert report["kind"] == "LISTING"
    assert not delisting_events(
        tmp_path,
        path,
        expected_report_hash=pin,
        through=LEGACY_LAUNCH + timedelta(days=1),
    )


@pytest.mark.parametrize("code", ["36003975739", "3600397573910", "ABC123", "g" * 32])
def test_unreviewed_or_malformed_legacy_article_identity_is_rejected(code):
    request, _ = legacy_listing_fixture()
    with pytest.raises(ValueError, match="article code"):
        replace(request, code=code).__post_init__()


def test_legacy_listing_ambiguity_and_backdated_launch_fail_closed():
    request, response = legacy_listing_fixture()
    response["data"]["body"] = response["data"]["body"].replace(
        "VET/USDT perpetual contract",
        "VET/USDT and NEO/USDT perpetual contract",
    )
    request = replace(
        request, body_sha256=hashlib.sha256(response["data"]["body"].encode()).hexdigest()
    )
    with pytest.raises(ValueError, match="unambiguous"):
        decode(request, canonical(response).encode())

    request, response = legacy_listing_fixture()
    response["data"]["body"] = response["data"]["body"].replace(
        "2020/02/14 08:00 AM", "2020/02/12 08:00 AM"
    )
    body = response["data"]["body"]
    facts = [
        {
            "symbol": "VETUSDT",
            "launch_at": datetime(2020, 2, 12, 8, tzinfo=UTC),
            "max_leverage": 50,
            "contract_type": "PERPETUAL",
            "quote_asset": "USDT",
        }
    ]
    request = replace(
        request,
        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        facts_hash=digest(facts),
    )
    with pytest.raises(ValueError, match="must precede"):
        decode(request, canonical(response).encode())
