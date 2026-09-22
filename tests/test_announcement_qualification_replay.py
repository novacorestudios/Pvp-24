import hashlib
from datetime import UTC, datetime

import pytest

from pvb24.data import announcement_qualification as module
from pvb24.ids import canonical, digest


def candidate():
    code = "a" * 32
    return {
        "catalog_id": 48,
        "catalog_scope": "NEW_CRYPTOCURRENCY_LISTING",
        "article_id": 1,
        "code": code,
        "title": "Binance Futures Will Launch TEST USDT-Margined Perpetual Contract",
        "released_at": datetime(2020, 2, 13, 6, tzinfo=UTC),
        "article_url": (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode="
            + code
        ),
        "qualification": "BODY_REVIEW_REQUIRED",
        "lifecycle_fact": False,
        "source_report_sha256": "0" * 64,
    }


def source_response():
    body = canonical(
        {
            "node": "root",
            "child": [
                {
                    "node": "element",
                    "tag": "p",
                    "child": [
                        {
                            "node": "text",
                            "text": (
                                "Binance Futures will launch TEST/USDT perpetual contract, with "
                                "trading opening at 2020/02/14 08:00 AM (UTC). Users will be able "
                                "to select between 1-50x leverage."
                            ),
                        }
                    ],
                }
            ],
        }
    )
    return canonical(
        {
            "success": True,
            "data": {
                "code": "a" * 32,
                "publishDate": 1581573660000,
                "lastUpdateTime": 0,
                "version": "1",
                "body": body,
            },
        }
    ).encode()


def build_report(tmp_path, monkeypatch):
    item = candidate()
    inventory = {"candidates": [item], "inventory_hash": "inventory-hash"}
    monkeypatch.setattr(module, "load_inventory", lambda *args, **kwargs: inventory)
    raw = source_response()
    replay = module.qualify_candidate(item, raw)
    source_sha = hashlib.sha256(raw).hexdigest()
    objects = tmp_path / "objects"
    objects.mkdir()
    (objects / f"{source_sha}.json").write_bytes(raw)
    result = {
        **replay,
        "retrieved_at": datetime(2026, 9, 21, tzinfo=UTC),
        "source_object": f"objects/{source_sha}.json",
    }
    requests = [result["review_request"]]
    report = {
        "schema": module.SCHEMA,
        "quality": "PRELIMINARY",
        "inventory_report": "reports/" + "1" * 64 + ".json",
        "inventory_report_sha256": "1" * 64,
        "inventory_hash": "inventory-hash",
        "final_test_access": "LOCKED",
        "requested_window_complete": False,
        "upper_boundary_coverage_proven": False,
        "candidate_count": 1,
        "status_counts": {module.QUALIFIED: 1},
        "source_fetch_complete": True,
        "results": [result],
        "results_hash": digest([result]),
        "review_requests": requests,
        "review_requests_hash": digest(requests),
        "historical_publication_times_verified": False,
        "historical_universe_complete": False,
        "security_master_complete": False,
        "lifecycle_complete": False,
        "performance_run": False,
        "operational_ready": False,
        "live_enabled": False,
    }
    encoded = canonical(report).encode()
    report_sha = hashlib.sha256(encoded).hexdigest()
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / f"{report_sha}.json").write_bytes(encoded)
    return report_sha, source_sha


def test_retained_source_fetch_replays_content_addressed_body(tmp_path, monkeypatch):
    report_sha, source_sha = build_report(tmp_path, monkeypatch)
    fetch = module.retained_source_fetch(tmp_path, report_sha)
    assert fetch(candidate()["article_url"]) == (
        tmp_path / "objects" / f"{source_sha}.json"
    ).read_bytes()


def test_retained_source_fetch_rejects_source_tamper(tmp_path, monkeypatch):
    report_sha, source_sha = build_report(tmp_path, monkeypatch)
    (tmp_path / "objects" / f"{source_sha}.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="source bytes changed"):
        module.retained_source_fetch(tmp_path, report_sha)


def test_load_qualification_replays_retained_source_bytes(tmp_path, monkeypatch):
    report_sha, _ = build_report(tmp_path, monkeypatch)
    loaded = module.load_qualification(
        tmp_path,
        f"reports/{report_sha}.json",
        expected_sha256=report_sha,
        inventory_root=tmp_path / "inventory",
    )
    assert loaded["status_counts"] == {module.QUALIFIED: 1}
    assert loaded["source_fetch_complete"] is True


def test_load_qualification_rejects_retained_source_tamper(tmp_path, monkeypatch):
    report_sha, source_sha = build_report(tmp_path, monkeypatch)
    (tmp_path / "objects" / f"{source_sha}.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="source bytes changed"):
        module.load_qualification(
            tmp_path,
            f"reports/{report_sha}.json",
            expected_sha256=report_sha,
            inventory_root=tmp_path / "inventory",
        )
