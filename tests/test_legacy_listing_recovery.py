from datetime import UTC, datetime

import pytest

from pvb24.data.announcement_qualification import qualify_candidate
from pvb24.data.announcements import extract_body_facts
from pvb24.ids import canonical


def rich(text):
    return canonical({"node": "root", "child": [{"node": "text", "text": text}]})


def test_legacy_html_single_listing_is_recovered():
    body = (
        "<p>Binance Futures will launch EOS/USDT perpetual contract and open trading at "
        "2020/01/08 08:00 AM (UTC). Users will be able to select between 1-75x leverage.</p>"
    )
    facts = extract_body_facts("LISTING", body)
    assert facts == [
        {
            "symbol": "EOSUSDT",
            "launch_at": datetime(2020, 1, 8, 8, tzinfo=UTC),
            "max_leverage": 75,
            "contract_type": "PERPETUAL",
            "quote_asset": "USDT",
        }
    ]


def test_html_listing_without_explicit_launch_time_stays_unqualified():
    body = (
        "<p>Binance Futures has launched its third perpetual contract, XRP/USDT. "
        "Users will be able to select between 1-75x leverage.</p>"
    )
    with pytest.raises(ValueError, match="launch statement|unambiguous"):
        extract_body_facts("LISTING", body)


def test_multi_symbol_shared_launch_is_recovered():
    facts = extract_body_facts(
        "LISTING",
        rich(
            "Binance Futures will launch a BAL/USDT and CRV/USDT perpetual contracts, "
            "with trading opening at 2020/09/01 7:00 AM (UTC). "
            "Users will be able to select between 1-50x leverage."
        ),
    )
    assert [fact["symbol"] for fact in facts] == ["BALUSDT", "CRVUSDT"]
    assert {fact["launch_at"] for fact in facts} == {datetime(2020, 9, 1, 7, tzinfo=UTC)}


def test_compact_symbol_listing_is_recovered():
    facts = extract_body_facts(
        "LISTING",
        rich(
            "Binance Futures will launch a CTKUSDT perpetual contract with trading opening at "
            "2020/11/19 7:00 AM (UTC). Users will be able to select between 1-50x leverage."
        ),
    )
    assert facts[0]["symbol"] == "CTKUSDT"
    assert facts[0]["launch_at"] == datetime(2020, 11, 19, 7, tzinfo=UTC)


def test_scheduled_multi_symbol_rows_preserve_distinct_launch_times():
    facts = extract_body_facts(
        "LISTING",
        rich(
            "Binance Futures will launch USDT-margined XEM and BTCST perpetual contracts "
            "with up to 25x leverage with trading open scheduled as below: "
            "USDT-Margined XEM 25X Perpetual Contracts at 2021-03-03 7:00 AM (UTC) "
            "USDT-Margined BTCST 25X Perpetual Contracts at 2021-03-04 7:00 AM (UTC)"
        ),
    )
    assert [(fact["symbol"], fact["launch_at"].day) for fact in facts] == [
        ("BTCSTUSDT", 4),
        ("XEMUSDT", 3),
    ]


def test_grouped_scheduled_row_expands_each_symbol():
    facts = extract_body_facts(
        "LISTING",
        rich(
            "Binance Futures will launch USDT-margined BNT, UNFI and CHZ perpetual contracts "
            "with up to 20X leverage with trading open scheduled as below: "
            "USDT-Margined BNT, UNFI 20X Perpetual Contracts at 2020/12/28 7:00 AM (UTC) "
            "USDT-Margined CHZ 20X Perpetual Contracts at 2020/12/29 7:00 AM (UTC)"
        ),
    )
    assert [fact["symbol"] for fact in facts] == ["BNTUSDT", "CHZUSDT", "UNFIUSDT"]
    assert next(f for f in facts if f["symbol"] == "CHZUSDT")["launch_at"].day == 29


def test_grouped_scheduled_row_never_promotes_connector_word_to_symbol():
    facts = extract_body_facts(
        "LISTING",
        rich(
            "Binance Futures will launch USDT-margined BNT, UNFI and CHZ perpetual contracts "
            "with up to 20X leverage with trading open scheduled as below: "
            "USDT-Margined BNT, UNFI and CHZ 20X Perpetual Contracts at "
            "2020/12/28 7:00 AM (UTC)"
        ),
    )
    assert [fact["symbol"] for fact in facts] == ["BNTUSDT", "CHZUSDT", "UNFIUSDT"]
    assert "ANDUSDT" not in {fact["symbol"] for fact in facts}


@pytest.mark.parametrize(
    "names",
    [
        "BNT or CHZ",
        "BNT, and CHZ",
        "BNT & & CHZ",
    ],
)
def test_grouped_scheduled_row_rejects_ambiguous_connectors(names):
    with pytest.raises(ValueError, match="Explicit unique USDT-margined listing symbols"):
        extract_body_facts(
            "LISTING",
            rich(
                "Binance Futures will launch USDT-margined BNT and CHZ perpetual contracts "
                "with up to 20X leverage with trading open scheduled as below: "
                f"USDT-Margined {names} 20X Perpetual Contracts at "
                "2020/12/28 7:00 AM (UTC)"
            ),
        )


def test_coin_margined_listing_is_not_promoted():
    with pytest.raises(ValueError, match="unambiguous"):
        extract_body_facts(
            "LISTING",
            rich(
                "Binance Futures will launch ETH/USD Coin-Margined Perpetual Contract "
                "with trading opening at 2020/08/01 7:00 AM (UTC). "
                "Users will be able to select between 1-75x leverage."
            ),
        )


def test_coin_margined_launch_does_not_promote_leveraged_token_pairs():
    with pytest.raises(ValueError, match="unambiguous"):
        extract_body_facts(
            "LISTING",
            rich(
                "Binance Futures will launch a FIL/USD coin-margined perpetual contract with "
                "trading opening at 2020/10/20 7:00 AM (UTC). Users will be able to select "
                "between 1-50x leverage. Binance will also list Leveraged Tokens FILUP and "
                "FILDOWN, with FILUP/USDT and FILDOWN/USDT trading pairs at the same time."
            ),
        )


def test_qualification_accepts_retained_legacy_html_without_special_case():
    body = (
        "<p>Binance Futures will launch OMG/USDT perpetual contract and open trading at "
        "2020/07/02 09:00 AM (UTC). Users will be able to select between 1-50x leverage.</p>"
    )
    candidate = {
        "catalog_id": 48,
        "catalog_scope": "NEW_CRYPTOCURRENCY_LISTING",
        "code": "360000000000",
        "title": "Binance Futures Will Launch OMG/USDT Perpetual Contract",
        "released_at": datetime(2020, 7, 1, tzinfo=UTC),
        "article_url": (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?"
            "articleCode=360000000000"
        ),
    }
    raw = canonical(
        {
            "success": True,
            "data": {
                "code": candidate["code"],
                "publishDate": 1593561600000,
                "lastUpdateTime": 0,
                "version": "1",
                "body": body,
            },
        }
    ).encode()
    result = qualify_candidate(candidate, raw)
    assert result["status"] == "QUALIFIED_PRELIMINARY"
    assert result["facts"][0]["symbol"] == "OMGUSDT"
