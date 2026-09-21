"""Acquire checksum-verified activity evidence for reviewed M11X listing facts."""

from copy import deepcopy

from pvb24.data.listing_conflict_activity import acquire_listing_conflict_activity
from pvb24.data.reviewed_listing_facts import SCHEMA as FACTS_SCHEMA
from pvb24.types import utc


def acquire_reviewed_listing_activity(root, facts_report):
    if (
        facts_report.get("schema") != FACTS_SCHEMA
        or facts_report.get("final_test_access") != "LOCKED"
        or facts_report.get("quality") != "PRELIMINARY"
        or facts_report.get("security_rows_emitted") != 0
    ):
        raise ValueError("Pinned PRELIMINARY reviewed listing facts required")
    rows = facts_report.get("results")
    if not isinstance(rows, list) or len(rows) != facts_report.get("fact_count"):
        raise ValueError("Reviewed listing fact count changed")
    candidates = []
    for row in rows:
        fact = row["fact"]
        candidates.append(
            {
                "symbol": fact["symbol"],
                "effective_from": utc(fact["launch_at"]),
                "candidate_source": row["source"],
                "revision_id": row["revision_id"],
                "prior_epoch_disclosed": fact["prior_epoch_disclosed"],
                "classification_hint": fact["classification_hint"],
            }
        )
    return acquire_listing_conflict_activity(root, deepcopy(candidates))
