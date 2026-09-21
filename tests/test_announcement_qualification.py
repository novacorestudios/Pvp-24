import hashlib
from datetime import UTC, datetime

from pvb24.data.announcement_qualification import (
    IDENTITY_REJECTED,
    POST_FINAL_REVISION_BLOCKED,
    QUALIFIED,
    SEMANTIC_UNQUALIFIED,
    qualify_candidate,
)
from pvb24.ids import canonical


def candidate(catalog_id=48, released=None):
    code = "a" * 32
    scope = "NEW_CRYPTOCURRENCY_LISTING" if catalog_id == 48 else "DELISTING"
    return {
        "catalog_id": catalog_id,
        "catalog_scope": scope,
        "article_id": 1,
        "code": code,
        "title": "candidate",
        "released_at": released or datetime(2020, 2, 13, 6, tzinfo=UTC),
        "article_url": (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode="
            + code
        ),
        "qualification": "BODY_REVIEW_REQUIRED",
        "lifecycle_fact": False,
        "source_report_sha256": "0" * 64,
    }


def listing_body():
    return canonical(
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
                                "Binance Futures will launch VET/USDT perpetual contract, with "
                                "trading opening at 2020/02/14 08:00 AM (UTC). Users will be able "
                                "to select between 1-50x leverage."
                            ),
                        }
                    ],
                }
            ],
        }
    )


def response(body=None, *, publish=1581573660000, update=0, code=None):
    return canonical(
        {
            "success": True,
            "data": {
                "code": code or "a" * 32,
                "publishDate": publish,
                "lastUpdateTime": update,
                "version": "1",
                "body": body if body is not None else listing_body(),
            },
        }
    ).encode()


def test_listing_body_qualifies_only_from_body_semantics():
    raw = response()
    result = qualify_candidate(candidate(), raw)
    assert result["status"] == QUALIFIED
    assert result["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["review_request"]["kind"] == "LISTING"
    assert result["review_request"]["published_day"] == "2020-02-13"
    assert result["facts"] == [
        {
            "symbol": "VETUSDT",
            "launch_at": datetime(2020, 2, 14, 8, tzinfo=UTC),
            "max_leverage": 50,
            "contract_type": "PERPETUAL",
            "quote_asset": "USDT",
        }
    ]
    assert result["source_retained"] is True
    assert result["lifecycle_fact"] is False



def test_delisting_postponement_qualifies_without_fabricating_entry_cutoff():
    released = datetime(2024, 12, 14, tzinfo=UTC)
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
                                "Binance Futures will postpone the delisting of the USDⓈ-M "
                                "OMGUSDT Perpetual Contract to 2024-12-30 09:00 (UTC). "
                                "We will conduct automatic settlements on the USDⓈ-M OMGUSDT "
                                "Perpetual Contract and then delist this contract."
                            ),
                        }
                    ],
                }
            ],
        }
    )
    published = int(datetime(2024, 12, 14, 13, 53, 34, tzinfo=UTC).timestamp() * 1000)
    result = qualify_candidate(candidate(161, released), response(body, publish=published))
    assert result["status"] == QUALIFIED
    assert result["facts"] == [
        {
            "symbol": "OMGUSDT",
            "scheduled_settlement_at": datetime(2024, 12, 30, 9, tzinfo=UTC),
            "revision_type": "POSTPONEMENT",
        }
    ]
    assert "entry_cutoff_at" not in result["facts"][0]



def test_coin_margined_or_ambiguous_listing_is_not_promoted():
    body = listing_body().replace("VET/USDT", "VET/USD")
    result = qualify_candidate(candidate(), response(body))
    assert result["status"] == SEMANTIC_UNQUALIFIED
    assert result["source_retained"] is True
    assert "facts" not in result and "review_request" not in result


def test_post_final_revision_is_blocked_before_body_semantics_and_not_retained():
    body = "not even rich text"
    result = qualify_candidate(
        candidate(),
        response(body, update=1751328000000),
    )
    assert result["status"] == POST_FINAL_REVISION_BLOCKED
    assert result["source_retained"] is False
    assert "body_sha256" not in result
    assert "facts" not in result


def test_catalog_detail_day_mismatch_fails_identity_gate():
    result = qualify_candidate(
        candidate(released=datetime(2020, 2, 12, tzinfo=UTC)),
        response(),
    )
    assert result["status"] == IDENTITY_REJECTED
    assert "publication day mismatch" in result["reason"]
    assert result["source_retained"] is False


def test_wrong_article_identity_is_never_semantically_inspected():
    result = qualify_candidate(candidate(), response(code="b" * 32))
    assert result["status"] == IDENTITY_REJECTED
    assert "identity differs" in result["reason"]
    assert result["source_retained"] is False


def test_malformed_json_is_identity_rejected_not_missing_data_zero():
    result = qualify_candidate(candidate(), b"{bad")
    assert result["status"] == IDENTITY_REJECTED
    assert result["source_retained"] is False
