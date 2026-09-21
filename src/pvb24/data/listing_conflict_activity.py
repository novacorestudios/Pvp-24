"""Checksum-verified Binance Vision probes for M11X listing-start conflicts."""

import json
from datetime import timedelta
from pathlib import Path

from pvb24.data.daily_activity import DailyKlineRequest, acquire_daily_activity
from pvb24.ids import canonical, digest
from pvb24.types import utc

SCHEMA = "PVB24_LISTING_CONFLICT_ACTIVITY_V1"


def _probe_spec(symbol, event):
    event = utc(event)
    return (
        DailyKlineRequest(symbol, (event.date() - timedelta(days=1)).isoformat()),
        DailyKlineRequest(symbol, event.date().isoformat()),
    )


def acquire_listing_conflict_activity(root, candidates):
    root = Path(root)
    observations = []
    source_failures = []
    for candidate in candidates:
        symbol = candidate["symbol"]
        event = utc(candidate["effective_from"])
        if event.second or event.microsecond:
            raise ValueError("Minute-aligned listing candidate required")
        prior_req, event_req = _probe_spec(symbol, event)
        acquired = {}
        for role, request in (("PRIOR_DAY", prior_req), ("EVENT_DAY", event_req)):
            result, attempt = acquire_daily_activity(request, root / "archive")
            status = result["status"]
            activity = result.get("activity")
            row = {
                "role": role,
                "symbol": symbol,
                "candidate_effective_from": event,
                "day": request.day,
                "status": status,
                "attempt": attempt,
                "archive_absence_proves_inactivity": False,
            }
            if activity is not None:
                row.update(
                    {
                        "rows": activity["rows"],
                        "active_rows": activity["active_rows"],
                        "first_active_interval_start": activity["first_active_interval_start"],
                        "last_active_interval_start": activity["last_active_interval_start"],
                        "source_revision_sha256": activity["source_revision_sha256"],
                    }
                )
            observations.append(row)
            acquired[role] = row
            if status in ("HTTP_ERROR", "INVALID_OR_FAILED"):
                source_failures.append(
                    {"symbol": symbol, "day": request.day, "status": status}
                )

        event_row = acquired["EVENT_DAY"]
        prior_row = acquired["PRIOR_DAY"]
        first_active = event_row.get("first_active_interval_start")
        if event_row["status"] == "ACQUIRED" and first_active is not None:
            exact = utc(first_active) == event
            precedes = utc(first_active) < event
        else:
            exact = False
            precedes = False
        candidate["archive_exact_boundary"] = exact
        candidate["archive_contradicted"] = precedes or (
            prior_row["status"] == "ACQUIRED" and prior_row.get("active_rows", 0) > 0
        )
        candidate["archive_boundary_status"] = (
            "CONTRADICTED_BY_ARCHIVE_ACTIVITY"
            if candidate["archive_contradicted"]
            else "CONSISTENT_EVENT_BOUNDARY_ONLY"
            if exact
            else "UNKNOWN"
        )

    result = {
        "schema": SCHEMA,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "observation_count": len(observations),
        "observations": observations,
        "source_failures": source_failures,
        "archive_absence_proves_inactivity": False,
        "historical_lifecycle_verified": False,
        "historical_universe_complete": False,
        "quality": "PRELIMINARY",
        "operational_ready": False,
        "live_enabled": False,
        "final_test_access": "LOCKED",
    }
    result["activity_hash"] = digest(result)
    return json.loads(canonical(result))
