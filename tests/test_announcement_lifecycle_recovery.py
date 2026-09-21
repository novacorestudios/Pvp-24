import hashlib
import json
from datetime import UTC, datetime

import pytest

from pvb24.data.announcement_recovery import recover_retained_lifecycle_facts
from pvb24.ids import canonical, digest


def candidate(code, kind):
    catalog_id = 48 if kind == "LISTING" else 161
    return {
        "catalog_id": catalog_id,
        "catalog_scope": "NEW_CRYPTOCURRENCY_LISTING" if catalog_id == 48 else "DELISTING",
        "code": code,
        "title": f"{kind} fixture",
        "catalog_released_at": datetime(2022, 4, 1, tzinfo=UTC),
        "article_url": (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?"
            f"articleCode={code}"
        ),
        "kind": kind,
    }


def body(text_value):
    return canonical(
        {
            "node": "root",
            "child": [{"node": "text", "text": text_value}],
        }
    )


def retained_source(code, body_value, publish_ms=1648771200000, update_ms=0):
    return canonical(
        {
            "success": True,
            "data": {
                "code": code,
                "publishDate": publish_ms,
                "lastUpdateTime": update_ms,
                "version": "1",
                "body": body_value,
            },
        }
    ).encode()


def semantic_row(root, item, raw, reason="old semantic failure"):
    source_hash = hashlib.sha256(raw).hexdigest()
    (root / "objects").mkdir(parents=True, exist_ok=True)
    (root / "objects" / f"{source_hash}.json").write_bytes(raw)
    parsed = json.loads(raw)
    return {
        **item,
        "title": item["title"],
        "catalog_released_at": item["catalog_released_at"],
        "source_sha256": source_hash,
        "source_retained": True,
        "source_object": f"objects/{source_hash}.json",
        "historical_verified": False,
        "original_revision_as_published_verified": False,
        "lifecycle_fact": False,
        "published_at": datetime.fromtimestamp(
            parsed["data"]["publishDate"] / 1000, UTC
        ),
        "known_updated_at": (
            datetime.fromtimestamp(parsed["data"]["lastUpdateTime"] / 1000, UTC)
            if parsed["data"]["lastUpdateTime"]
            else None
        ),
        "cms_version": "1",
        "status": "SEMANTIC_UNQUALIFIED",
        "reason": reason,
        "body_sha256": hashlib.sha256(parsed["data"]["body"].encode()).hexdigest(),
        "retrieved_at": datetime(2022, 4, 1, 1, tzinfo=UTC),
    }


def write_report(root, rows):
    report = {
        "schema": "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_V3",
        "quality": "PRELIMINARY",
        "final_test_access": "LOCKED",
        "source_fetch_complete": True,
        "candidate_count": len(rows),
        "results": rows,
        "results_hash": digest(rows),
        "historical_universe_complete": False,
        "security_master_complete": False,
        "lifecycle_complete": False,
        "operational_ready": False,
        "live_enabled": False,
    }
    raw = canonical(report).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "reports" / f"{sha}.json").write_bytes(raw)
    return sha


def recover_one(tmp_path, kind, text_value, *, update_ms=0):
    code = "a" * 32
    item = candidate(code, kind)
    raw = retained_source(code, body(text_value), update_ms=update_ms)
    row = semantic_row(tmp_path, item, raw)
    sha = write_report(tmp_path, [row])
    return recover_retained_lifecycle_facts(tmp_path, sha)


def test_recovers_two_legacy_listing_schedules_from_retained_body(tmp_path):
    report = recover_one(
        tmp_path,
        "LISTING",
        "Binance Futures will launch a SRM/USDT perpetual contract with trading opening at "
        "2022/04/05 2:00 AM (UTC) and a BZRX/USDT perpetual contract with trading opening "
        "at 2022/04/05 3:00 AM (UTC). Users will be able to select between 1-50x leverage.",
    )
    assert report["recovered_listing_fact_count"] == 2
    assert report["recovered_listing_symbols"] == ["BZRXUSDT", "SRMUSDT"]
    assert report["recovered_delisting_fact_count"] == 0


def test_recovers_legacy_usdt_delisting_without_inventing_cutoff(tmp_path):
    report = recover_one(
        tmp_path,
        "DELISTING",
        "Binance Futures will conduct an automatic settlement on the USDT-Margined ANC "
        "Perpetual Contract and delist this contract at 2022-05-13 04:00 AM (UTC). "
        "Users are advised to close positions prior to the delisting time.",
    )
    fact = report["recovered"][0]["facts"][0]
    assert fact["symbol"] == "ANCUSDT"
    assert fact["scheduled_settlement_at"] == "2022-05-13T04:00:00.000000Z"
    assert "entry_cutoff_at" not in fact


def test_respectively_maps_base_symbols_to_separate_settlements(tmp_path):
    report = recover_one(
        tmp_path,
        "DELISTING",
        "Binance Futures will conduct automatic settlements on the 1000BTTC and YFII "
        "USDT-Margined Contracts, and delist these contracts at 2022-04-11 09:00 AM "
        "(UTC) and 2022-04-12 09:00 AM (UTC) respectively.",
    )
    facts = {fact["symbol"]: fact for fact in report["recovered"][0]["facts"]}
    assert facts["1000BTTCUSDT"]["scheduled_settlement_at"] == "2022-04-11T09:00:00.000000Z"
    assert facts["YFIIUSDT"]["scheduled_settlement_at"] == "2022-04-12T09:00:00.000000Z"


def test_grouped_modern_delisting_requires_and_maps_cutoffs(tmp_path):
    report = recover_one(
        tmp_path,
        "DELISTING",
        "Binance Futures will close all positions and conduct an automatic settlement on the "
        "USDⓈ-M AAAUSDT and BBBUSDT USDⓈ-M perpetual contracts at 2022-05-13 09:00 (UTC), "
        "and CCCUSDT USDⓈ-M perpetual contract at 2022-05-14 09:00 (UTC). "
        "The contracts will be delisted after the settlement is complete. "
        "Users are not allowed to open new positions for the aforementioned contracts starting "
        "from the following dates: 2022-05-13 08:30 (UTC): AAAUSDT and BBBUSDT USDⓈ-M "
        "perpetual contracts 2022-05-14 08:30 (UTC): CCCUSDT USDⓈ-M perpetual contract.",
    )
    facts = {fact["symbol"]: fact for fact in report["recovered"][0]["facts"]}
    assert facts["AAAUSDT"]["entry_cutoff_at"] == "2022-05-13T08:30:00.000000Z"
    assert facts["BBBUSDT"]["scheduled_settlement_at"] == "2022-05-13T09:00:00.000000Z"
    assert facts["CCCUSDT"]["entry_cutoff_at"] == "2022-05-14T08:30:00.000000Z"


def test_busd_only_contract_never_becomes_fake_usdt_symbol(tmp_path):
    report = recover_one(
        tmp_path,
        "DELISTING",
        "Binance Futures will conduct an automatic settlement on the FTTBUSD USDT-Margined "
        "Contract and delist this contract at 2022-05-19 09:00 AM (UTC).",
    )
    assert report["recovered_delisting_fact_count"] == 0
    assert report["remaining_semantic_unqualified_count"] == 1
    assert "FTTBUSDUSDT" not in report["recovered_symbols"]


def test_post_effective_known_update_is_retrospective_not_causal(tmp_path):
    update_ms = int(datetime(2022, 5, 14, tzinfo=UTC).timestamp() * 1000)
    report = recover_one(
        tmp_path,
        "DELISTING",
        "Binance Futures will conduct an automatic settlement on the USDT-Margined ANC "
        "Perpetual Contract and delist this contract at 2022-05-13 04:00 AM (UTC).",
        update_ms=update_ms,
    )
    assert report["recovered_delisting_fact_count"] == 0
    assert report["retrospective_count"] == 1
    assert report["historical_universe_complete"] is False


def test_malformed_grouped_cutoff_fails_closed(tmp_path):
    report = recover_one(
        tmp_path,
        "DELISTING",
        "Binance Futures will close all positions and conduct an automatic settlement on the "
        "AAAUSDT and BBBUSDT USDⓈ-M perpetual contracts at 2022-05-13 09:00 (UTC). "
        "The contracts will be delisted after settlement. Users are not allowed to open new "
        "positions for the aforementioned contracts starting from 2022-05-13 08:30 (UTC): "
        "AAAUSDT.",
    )
    assert report["recovered_delisting_fact_count"] == 0
    assert report["remaining_semantic_unqualified_count"] == 1
