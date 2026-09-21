import hashlib
import json

import pytest

from pvb24.data.listing_conflict_resolution import compile_listing_conflict_resolution
from pvb24.ids import digest


def test_resolution_constants_are_pinned():
    # Production resolution remains bound to the reviewed source identities.
    from pvb24.data import listing_conflict_resolution as module

    assert module.POSTPONEMENT_SOURCE == (
        "cc300492f07c157cb414f9c1a0f622ece892e933c677d9526c1839b6261a5459"
    )
    assert module.BNT_2023_SOURCE == (
        "fcd9f8bd95590428bfa597fdd943dd6cf934a7b034691cbe72d798554869b898"
    )


def test_missing_pinned_sources_fail_closed(tmp_path):
    recovery = {
        "schema": "PVB24_RETAINED_ANNOUNCEMENT_RECOVERY_V2",
        "final_test_access": "LOCKED",
        "quality": "PRELIMINARY",
        "retrospective_count": 0,
        "historical_universe_complete": False,
        "security_history_complete": False,
        "recovered": [],
    }
    recovery["recovery_hash"] = digest(recovery)
    raw = (json.dumps(recovery) + "\n").encode()
    path = tmp_path / "recovery.json"
    path.write_bytes(raw)
    with pytest.raises(FileNotFoundError):
        compile_listing_conflict_resolution(
            path, hashlib.sha256(raw).hexdigest(), tmp_path / "sources"
        )
