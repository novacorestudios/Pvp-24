import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pvb24.data import announcement_requalification as module
from pvb24.data.announcement_qualification import (
    QUALIFIED,
    SEMANTIC_UNQUALIFIED,
    qualify_candidate,
)
from pvb24.ids import canonical, digest


def candidate(code="a" * 32):
    return {
        "catalog_id": 48,
        "catalog_scope": "NEW_CRYPTOCURRENCY_LISTING",
        "article_id": 1,
        "code": code,
        "title": "Binance Futures Will Launch TEST USDT-Margined Perpetual Contract",
        "released_at": datetime(2020, 2, 13, 6, tzinfo=UTC),
        "article_url": (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?"
            f"articleCode={code}"
        ),
        "qualification": "BODY_REVIEW_REQUIRED",
        "lifecycle_fact": False,
        "source_report_sha256": "0" * 64,
    }


def source_response(code="a" * 32):
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
                                "Binance Futures will launch TEST/USDT perpetual contract, "
                                "with trading opening at 2020/02/14 08:00 AM (UTC). "
                                "Users will be able to select between 1-50x leverage."
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
                "code": code,
                "publishDate": 1581573660000,
                "lastUpdateTime": 0,
                "version": "1",
                "body": body,
            },
        }
    ).encode()


def write_source_report(root, recorded):
    requests = [row["review_request"] for row in recorded if row.get("status") == QUALIFIED]
    report = {
        "schema": "PVB24_ANNOUNCEMENT_BODY_QUALIFICATION_V3",
        "quality": "PRELIMINARY",
        "inventory_report": "reports/" + "1" * 64 + ".json",
        "inventory_report_sha256": "1" * 64,
        "inventory_hash": "inventory-hash",
        "window_start": "2020-01-01T00:00:00.000000Z",
        "window_end": "2025-07-01T00:00:00.000000Z",
        "final_test_access": "LOCKED",
        "requested_window_complete": False,
        "upper_boundary_coverage_proven": False,
        "candidate_count": len(recorded),
        "status_counts": {
            status: sum(row["status"] == status for row in recorded)
            for status in sorted({row["status"] for row in recorded})
        },
        "source_fetch_complete": True,
        "results": recorded,
        "results_hash": digest(recorded),
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
    raw = canonical(report).encode()
    sha = hashlib.sha256(raw).hexdigest()
    reports = root / "reports"
    reports.mkdir()
    (reports / f"{sha}.json").write_bytes(raw)
    return sha


def old_unqualified_from_replay(replay):
    return {
        key: value
        for key, value in replay.items()
        if key not in ("facts", "facts_hash", "review_request", "available_at")
    } | {
        "status": SEMANTIC_UNQUALIFIED,
        "reason": "legacy parser did not recognize retained wording",
        "source_retained": True,
        "source_object": f"objects/{replay['source_sha256']}.json",
        "retrieved_at": datetime(2026, 9, 21, tzinfo=UTC),
    }


def test_requalification_promotes_retained_source_without_claiming_completeness(
    tmp_path, monkeypatch
):
    item = candidate()
    raw = source_response()
    replay = qualify_candidate(item, raw)
    recorded = old_unqualified_from_replay(replay)
    report_sha = write_source_report(tmp_path, [recorded])

    monkeypatch.setattr(
        module,
        "load_inventory",
        lambda *args, **kwargs: {
            "candidates": [item],
            "inventory_hash": "inventory-hash",
        },
    )
    monkeypatch.setattr(
        module,
        "retained_source_fetch",
        lambda *args, **kwargs: lambda url: raw,
    )

    report = module.requalify_retained_qualification(
        inventory_root=tmp_path / "inventory",
        qualification_root=tmp_path,
        source_report_sha256=report_sha,
        durable_bundle_sha256="d" * 64,
    )

    assert report["schema"] == "PVB24_RETAINED_ANNOUNCEMENT_REQUALIFICATION_V1"
    assert report["status_counts"] == {QUALIFIED: 1}
    assert report["status_promoted_to_qualified_count"] == 1
    assert report["source_bytes_reverified_count"] == 1
    assert report["qualification_replayed_from_retained_bytes"] is True
    assert report["historical_universe_complete"] is False
    assert report["security_master_complete"] is False
    assert report["operational_ready"] is False
    assert report["live_enabled"] is False
    assert report["final_test_access"] == "LOCKED"


def test_requalification_rejects_previously_qualified_semantic_drift(tmp_path, monkeypatch):
    item = candidate()
    raw = source_response()
    replay = qualify_candidate(item, raw)
    recorded = {
        **replay,
        "source_object": f"objects/{replay['source_sha256']}.json",
        "retrieved_at": datetime(2026, 9, 21, tzinfo=UTC),
    }
    report_sha = write_source_report(tmp_path, [recorded])

    monkeypatch.setattr(
        module,
        "load_inventory",
        lambda *args, **kwargs: {
            "candidates": [item],
            "inventory_hash": "inventory-hash",
        },
    )
    monkeypatch.setattr(
        module,
        "retained_source_fetch",
        lambda *args, **kwargs: lambda url: raw,
    )
    changed = dict(replay)
    changed["facts"] = [{**replay["facts"][0], "max_leverage": 49}]
    changed["facts_hash"] = digest(changed["facts"])
    changed["review_request"] = {
        **changed["review_request"],
        "facts_hash": changed["facts_hash"],
    }
    monkeypatch.setattr(module, "qualify_candidate", lambda *args, **kwargs: changed)

    with pytest.raises(ValueError, match="Previously qualified announcement semantics changed"):
        module.requalify_retained_qualification(
            inventory_root=tmp_path / "inventory",
            qualification_root=tmp_path,
            source_report_sha256=report_sha,
            durable_bundle_sha256="d" * 64,
        )


def test_requalification_rejects_source_revision_change(tmp_path, monkeypatch):
    item = candidate()
    raw = source_response()
    replay = qualify_candidate(item, raw)
    recorded = old_unqualified_from_replay(replay)
    report_sha = write_source_report(tmp_path, [recorded])

    monkeypatch.setattr(
        module,
        "load_inventory",
        lambda *args, **kwargs: {
            "candidates": [item],
            "inventory_hash": "inventory-hash",
        },
    )
    monkeypatch.setattr(
        module,
        "retained_source_fetch",
        lambda *args, **kwargs: lambda url: raw,
    )
    changed = {**replay, "source_sha256": "f" * 64}
    monkeypatch.setattr(module, "qualify_candidate", lambda *args, **kwargs: changed)

    with pytest.raises(ValueError, match="Retained replay source revision changed"):
        module.requalify_retained_qualification(
            inventory_root=tmp_path / "inventory",
            qualification_root=tmp_path,
            source_report_sha256=report_sha,
            durable_bundle_sha256="d" * 64,
        )


def test_requalification_requires_content_addressed_bundle_identity(tmp_path):
    with pytest.raises(ValueError, match="durable bundle SHA-256"):
        module.requalify_retained_qualification(
            inventory_root=Path(tmp_path),
            qualification_root=Path(tmp_path),
            source_report_sha256="a" * 64,
            durable_bundle_sha256="not-a-sha",
        )
