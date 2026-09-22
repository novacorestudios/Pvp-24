import hashlib
import json
from pathlib import Path

from pvb24.data.listing_boundary_refinement import (
    compile_listing_boundary_refinement,
)
from pvb24.ids import digest


def write(path, value):
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def fixture(tmp_path):
    unresolved = [
        {
            "symbol": "AAAUSDT",
            "event_at": "2020-01-02T08:00:00.000000Z",
            "available_at": "2020-01-01T08:00:00.000000Z",
            "source": "https://example.test/a",
            "revision_id": "a" * 64,
            "article_code": "article-a",
            "requalified_boundary_status": "UNKNOWN",
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        },
        {
            "symbol": "BBBUSDT",
            "event_at": "2020-01-03T08:00:00.000000Z",
            "available_at": "2020-01-02T08:00:00.000000Z",
            "source": "https://example.test/b",
            "revision_id": "b" * 64,
            "article_code": "article-b",
            "requalified_boundary_status": "UNKNOWN",
            "blocking_obligation": "RESOLVE_LISTING_BOUNDARY",
        },
    ]
    security_master = {
        "schema": "PVB24_SECURITY_MASTER_OBLIGATION_AUDIT_V6",
        "inputs": {"requalified_lifecycle_reconciliation_hash": "lifecycle-hash"},
        "unresolved_listing_count": 2,
        "unresolved_listings": unresolved,
        "quality": "PRELIMINARY",
        "security_history_complete": False,
        "historical_universe_complete": False,
        "full_security_rows_emitted": 0,
        "complete_attestation_emitted": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    security_master["audit_hash"] = digest(security_master)

    def lifecycle_row(item, event_status, first_interval=None, first_active=None):
        return {
            "article_code": item["article_code"],
            "article_source_sha256": item["revision_id"],
            "kind": "LISTING",
            "symbol": item["symbol"],
            "event_at": item["event_at"],
            "fact": {"symbol": item["symbol"], "launch_at": item["event_at"]},
            "event_day": {
                "status": event_status,
                "url": f"https://data.example/{item['symbol']}",
                "attempt": f"attempts/{item['symbol']}.json",
                "rows": 10 if event_status == "ACQUIRED" else None,
                "active_rows": 10 if event_status == "ACQUIRED" else None,
                "first_interval_start": first_interval,
                "last_interval_end": None,
                "first_active_interval_start": first_active,
                "last_active_interval_start": None,
                "last_active_interval_end": None,
                "internal_gaps": [] if event_status == "ACQUIRED" else None,
                "zero_volume_last_bars": 0 if event_status == "ACQUIRED" else None,
                "missing_object_means_inactive": False,
            },
            "boundary_day": {
                "status": "UNAVAILABLE",
                "url": f"https://data.example/{item['symbol']}-prior",
                "attempt": f"attempts/{item['symbol']}-prior.json",
                "rows": None,
                "active_rows": None,
                "first_interval_start": None,
                "last_interval_end": None,
                "first_active_interval_start": None,
                "last_active_interval_start": None,
                "last_active_interval_end": None,
                "internal_gaps": None,
                "zero_volume_last_bars": None,
                "missing_object_means_inactive": False,
            },
            "status": "UNKNOWN",
            "contradictions": [],
            "notes": (
                [
                    "EVENT_DAY_ACTIVITY_STARTS_AFTER_ANNOUNCED_LAUNCH",
                    "BOUNDARY_ARCHIVE_OBJECT_MISSING_IS_UNKNOWN",
                ]
                if event_status == "ACQUIRED"
                else [
                    "EVENT_DAY_ARCHIVE_NOT_ACQUIRED",
                    "BOUNDARY_ARCHIVE_OBJECT_MISSING_IS_UNKNOWN",
                ]
            ),
            "archive_absence_proves_inactivity": False,
            "historical_lifecycle_verified": False,
        }

    rows = [
        lifecycle_row(
            unresolved[0],
            "ACQUIRED",
            "2020-01-02T08:05:00.000000Z",
            "2020-01-02T08:05:00.000000Z",
        ),
        lifecycle_row(unresolved[1], "UNAVAILABLE"),
    ]
    lifecycle = {
        "schema": "PVB24_REQUALIFIED_LIFECYCLE_ARCHIVE_ACTIVITY_V1",
        "quality": "PRELIMINARY",
        "source_failures": [],
        "reconciliation_count": len(rows),
        "status_counts": {"UNKNOWN": 2},
        "reconciliations": rows,
        "reconciliation_hash": digest(rows),
        "historical_universe_complete": False,
        "security_master_complete": False,
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    security_master["inputs"]["requalified_lifecycle_reconciliation_hash"] = lifecycle[
        "reconciliation_hash"
    ]
    security_master.pop("audit_hash")
    security_master["audit_hash"] = digest(security_master)

    return write(Path(tmp_path) / "v6.json", security_master), write(
        Path(tmp_path) / "lifecycle.json", lifecycle
    )


def test_refinement_separates_post_launch_corroboration_from_true_unknown(tmp_path):
    security_master, lifecycle = fixture(tmp_path)
    report = compile_listing_boundary_refinement(
        security_master[0],
        security_master[1],
        lifecycle[0],
        lifecycle[1],
    )

    assert report["input_unresolved_listing_count"] == 2
    assert report["resolved_announcement_boundary_count"] == 1
    assert report["remaining_unresolved_listing_count"] == 1
    resolved = report["resolved_announcement_boundaries"][0]
    assert resolved["symbol"] == "AAAUSDT"
    assert resolved["archive_proves_exact_launch"] is False
    assert resolved["prior_day_absence_used_as_proof"] is False
    assert report["remaining_unresolved_listings"][0]["symbol"] == "BBBUSDT"
    assert report["historical_universe_complete"] is False
    assert report["final_test_access"] == "LOCKED"


def test_activity_before_announced_launch_never_refines_unknown_boundary(tmp_path):
    security_master, lifecycle = fixture(tmp_path)
    payload = json.loads(lifecycle[0].read_text())
    payload["reconciliations"][0]["event_day"]["first_interval_start"] = (
        "2020-01-02T07:59:00.000000Z"
    )
    payload["reconciliation_hash"] = digest(payload["reconciliations"])
    security_payload = json.loads(security_master[0].read_text())
    security_payload["inputs"]["requalified_lifecycle_reconciliation_hash"] = payload[
        "reconciliation_hash"
    ]
    security_payload.pop("audit_hash")
    security_payload["audit_hash"] = digest(security_payload)
    security_master = write(security_master[0], security_payload)
    lifecycle = write(lifecycle[0], payload)

    report = compile_listing_boundary_refinement(
        security_master[0],
        security_master[1],
        lifecycle[0],
        lifecycle[1],
    )
    assert report["resolved_announcement_boundary_count"] == 0
    assert report["remaining_unresolved_listing_count"] == 2
