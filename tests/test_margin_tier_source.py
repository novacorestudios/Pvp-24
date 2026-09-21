import hashlib
import json
from datetime import UTC, datetime

import pytest

from pvb24.data.margin_tier_source import inspect_margin_tier_response, retain_probe
from pvb24.ids import canonical


def node(tag, *values):
    return {
        "node": "element",
        "tag": tag,
        "child": [{"node": "text", "text": value} for value in values],
    }


def response(*, update=0):
    body = canonical(
        {
            "node": "root",
            "child": [
                {
                    "node": "element",
                    "tag": "table",
                    "child": [
                        {
                            "node": "element",
                            "tag": "tr",
                            "child": [node("td", "Previous"), node("td", "New")],
                        },
                        {
                            "node": "element",
                            "tag": "tr",
                            "child": [node("td", "0 < Position ≤ 5,000"), node("td", "0.60%")],
                        },
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
                "publishDate": 1713772800000,
                "lastUpdateTime": update,
                "version": "1",
                "body": body,
            },
        }
    ).encode()


def test_pre_final_probe_retains_exact_table_cells_and_no_rules(tmp_path):
    raw = response()
    result = inspect_margin_tier_response("a" * 32, raw)
    assert result["status"] == "PRE_FINAL_REVISION_REVIEWABLE"
    assert result["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["table_count"] == 1
    assert result["tables"] == [[["Previous", "New"], ["0 < Position ≤ 5,000", "0.60%"]]]
    assert not result["contract_rules_emitted"]
    assert not result["liquidation_validated"]

    retained, report_hash = retain_probe(tmp_path, "a" * 32, raw)
    assert retained["source_object"] == f"objects/{retained['source_sha256']}.json"
    assert (tmp_path / retained["source_object"]).read_bytes() == raw
    assert (tmp_path / "reports" / f"{report_hash}.json").exists()


def test_post_final_revision_is_not_retained_or_semantically_inspected(tmp_path):
    raw = response(update=int(datetime(2025, 7, 1, tzinfo=UTC).timestamp() * 1000))
    result, _ = retain_probe(tmp_path, "a" * 32, raw)
    assert result["status"] == "POST_FINAL_REVISION_BLOCKED"
    assert result["body_sha256"] is None
    assert result["tables"] is None
    assert result["source_object"] is None
    assert not (tmp_path / "objects").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(success=False),
        lambda value: value["data"].update(code="b" * 32),
        lambda value: value["data"].update(publishDate=1751328000000),
        lambda value: value["data"].update(lastUpdateTime=-1),
    ],
)
def test_source_identity_and_holdout_fail_closed(mutation):
    value = json.loads(response())
    mutation(value)
    with pytest.raises(ValueError):
        inspect_margin_tier_response("a" * 32, canonical(value).encode())
