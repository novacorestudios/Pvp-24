import hashlib
import json

import pytest

from pvb24.data.reviewed_listing_source import (
    inspect_reviewed_listing_source,
    retain_reviewed_listing_source,
)
from pvb24.ids import canonical


def response(*, code="a" * 32, publish=1672531200000, update=0):
    body = canonical(
        {
            "node": "root",
            "child": [
                {
                    "node": "element",
                    "tag": "p",
                    "child": [{"node": "text", "text": "Reviewed official listing source."}],
                }
            ],
        }
    )
    return canonical(
        {
            "success": True,
            "data": {
                "code": code,
                "publishDate": publish,
                "lastUpdateTime": update,
                "version": "1",
                "body": body,
            },
        }
    ).encode()


def test_source_retention_is_exact_and_non_promoting(tmp_path):
    raw = response()
    result = inspect_reviewed_listing_source("a" * 32, raw)
    assert result["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["semantic_listing_facts_emitted"] is False
    assert result["security_rows_emitted"] == 0
    assert result["historical_universe_complete"] is False

    retained, report_sha = retain_reviewed_listing_source(tmp_path, "a" * 32, raw)
    assert (tmp_path / retained["source_object"]).read_bytes() == raw
    assert (tmp_path / "reports" / f"{report_sha}.json").exists()


@pytest.mark.parametrize(
    "mutator,match",
    [
        (lambda value: value.update(success=False), "Successful CMS"),
        (lambda value: value["data"].update(code="b" * 32), "identity differs"),
        (lambda value: value["data"].update(lastUpdateTime=-1), "update clock"),
        (
            lambda value: value["data"].update(publishDate=1751328000000),
            "Final-period",
        ),
    ],
)
def test_identity_and_holdout_fail_closed(mutator, match):
    value = json.loads(response())
    mutator(value)
    with pytest.raises(ValueError, match=match):
        inspect_reviewed_listing_source("a" * 32, canonical(value).encode())
