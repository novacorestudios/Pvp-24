import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pvb24.data.announcement_qualification import qualify_candidate
from pvb24.data.announcement_recovery import recover_retained_listing_facts
from pvb24.ids import canonical, digest


def candidate(code, title):
    return {
        "catalog_id": 48,
        "catalog_scope": "NEW_CRYPTOCURRENCY_LISTING",
        "code": code,
        "title": title,
        "released_at": datetime(2020, 7, 1, tzinfo=UTC),
        "article_url": (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?"
            f"articleCode={code}"
        ),
    }


def source(code, body):
    return canonical(
        {
            "success": True,
            "data": {
                "code": code,
                "publishDate": 1593561600000,
                "lastUpdateTime": 0,
                "version": "1",
                "body": body,
            },
        }
    ).encode()


def retained_result(root, candidate_row, raw, *, old_status, old_reason=None):
    result = qualify_candidate(candidate_row, raw)
    source_hash = hashlib.sha256(raw).hexdigest()
    (root / "objects").mkdir(parents=True, exist_ok=True)
    (root / "objects" / f"{source_hash}.json").write_bytes(raw)
    if old_status == "QUALIFIED_PRELIMINARY":
        result["retrieved_at"] = datetime(2020, 7, 1, 1, tzinfo=UTC)
        result["source_object"] = f"objects/{source_hash}.json"
        return result
    return {
        "catalog_id": candidate_row["catalog_id"],
        "catalog_scope": candidate_row["catalog_scope"],
        "code": candidate_row["code"],
        "title": candidate_row["title"],
        "catalog_released_at": candidate_row["released_at"],
        "article_url": candidate_row["article_url"],
        "kind": "LISTING",
        "source_sha256": source_hash,
        "source_retained": True,
        "historical_verified": False,
        "original_revision_as_published_verified": False,
        "lifecycle_fact": False,
        "published_at": datetime(2020, 7, 1, tzinfo=UTC),
        "known_updated_at": None,
        "cms_version": "1",
        "status": old_status,
        "reason": old_reason,
        "body_sha256": hashlib.sha256(json.loads(raw)["data"]["body"].encode()).hexdigest(),
        "retrieved_at": datetime(2020, 7, 1, 1, tzinfo=UTC),
        "source_object": f"objects/{source_hash}.json",
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
    (root / "reports").mkdir(parents=True)
    (root / "reports" / f"{sha}.json").write_bytes(raw)
    return sha


def test_recovery_promotes_only_retained_semantic_listing_failures(tmp_path):
    old_body = (
        "<p>Binance Futures will launch OMG/USDT perpetual contract and open trading at "
        "2020/07/02 09:00 AM (UTC). Users will be able to select between 1-50x leverage.</p>"
    )
    old_candidate = candidate("360000000001", "Legacy OMG listing")
    old = retained_result(
        tmp_path,
        old_candidate,
        source(old_candidate["code"], old_body),
        old_status="SEMANTIC_UNQUALIFIED",
        old_reason="Expecting value: line 1 column 1 (char 0)",
    )
    sha = write_report(tmp_path, [old])
    result = recover_retained_listing_facts(tmp_path, sha)
    assert result["recovered_article_count"] == 1
    assert result["recovered_fact_count"] == 1
    assert result["recovered_symbols"] == ["OMGUSDT"]
    assert result["remaining_semantic_unqualified_count"] == 0
    assert result["historical_universe_complete"] is False


def test_prior_qualified_result_must_replay_identically(tmp_path):
    body = canonical(
        {
            "node": "root",
            "child": [
                {
                    "node": "text",
                    "text": (
                        "Binance Futures will launch ABC/USDT perpetual contract and open trading "
                        "at 2020/07/02 09:00 AM (UTC). Users will be able to select between "
                        "1-50x leverage."
                    ),
                }
            ],
        }
    )
    item = candidate("360000000002", "ABC listing")
    row = retained_result(
        tmp_path,
        item,
        source(item["code"], body),
        old_status="QUALIFIED_PRELIMINARY",
    )
    sha = write_report(tmp_path, [row])
    result = recover_retained_listing_facts(tmp_path, sha)
    assert result["prior_qualified_count_replayed_identically"] == 1
    assert result["recovered_article_count"] == 0


def test_changed_prior_qualified_semantics_fail_closed(tmp_path):
    body = canonical(
        {
            "node": "root",
            "child": [
                {
                    "node": "text",
                    "text": (
                        "Binance Futures will launch ABC/USDT perpetual contract and open trading "
                        "at 2020/07/02 09:00 AM (UTC). Users will be able to select between "
                        "1-50x leverage."
                    ),
                }
            ],
        }
    )
    item = candidate("360000000003", "ABC listing")
    raw = source(item["code"], body)
    row = retained_result(tmp_path, item, raw, old_status="QUALIFIED_PRELIMINARY")
    row["facts"][0]["max_leverage"] = 49
    row["facts_hash"] = digest(row["facts"])
    sha = write_report(tmp_path, [row])
    with pytest.raises(ValueError, match="semantics changed"):
        recover_retained_listing_facts(tmp_path, sha)


def test_source_object_hash_is_rechecked(tmp_path):
    body = (
        "<p>Binance Futures will launch OMG/USDT perpetual contract and open trading at "
        "2020/07/02 09:00 AM (UTC). Users will be able to select between 1-50x leverage.</p>"
    )
    item = candidate("360000000004", "Legacy OMG listing")
    raw = source(item["code"], body)
    row = retained_result(
        tmp_path,
        item,
        raw,
        old_status="SEMANTIC_UNQUALIFIED",
        old_reason="Expecting value",
    )
    sha = write_report(tmp_path, [row])
    object_path = Path(tmp_path) / row["source_object"]
    object_path.write_bytes(object_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="source bytes changed"):
        recover_retained_listing_facts(tmp_path, sha)
