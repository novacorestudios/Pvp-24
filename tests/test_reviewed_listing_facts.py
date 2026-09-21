import pytest

from pvb24.data.reviewed_listing_facts import extract_target_listing_fact


@pytest.mark.parametrize(
    "body,target,expected,leverage",
    [
        (
            "Binance Futures will launch the USDⓈ-M GLMR perpetual contract at "
            "2023-09-26 01:30 (UTC), with up to 10x leverage. "
            "GLMRUSDTLaunch Time 2023-09-26 01:30 (UTC)",
            "GLMRUSDT",
            "2023-09-26T01:30:00+00:00",
            10,
        ),
        (
            "Binance Futures will launch USDⓈ-M ICP perpetual contracts with up to "
            "25x leverage on 2022-09-27 at 02:30 (UTC). "
            "ICPUSDTLaunch Time 2022-09-27 02:30 (UTC)",
            "ICPUSDT",
            "2022-09-27T02:30:00+00:00",
            25,
        ),
        (
            "Binance Futures will launch USDⓈ-M LDO and CVX perpetual contracts with "
            "up to 25x leverage on 2022-09-22 at 12:00 (UTC) and "
            "2022-09-22 at 12:15 (UTC) respectively. "
            "LDOUSDTCVXUSDTLaunch Time 2022-09-22 12:00 (UTC)"
            "2022-09-22 12:15 (UTC)",
            "CVXUSDT",
            "2022-09-22T12:15:00+00:00",
            25,
        ),
        (
            "Binance Futures will launch USDT-margined AMB, LEVER and TLM perpetual "
            "contracts on 2023-03-30 12:00 (UTC), 2023-03-30 12:15 (UTC) and "
            "2023-03-30 12:30 (UTC) respectively, with up to 20x leverage. "
            "AMBUSDTLEVERUSDTTLMUSDTLaunch Time 2023-03-30 12:00 (UTC)"
            "2023-03-30 12:15 (UTC)2023-03-30 12:30 (UTC)",
            "TLMUSDT",
            "2023-03-30T12:30:00+00:00",
            20,
        ),
        (
            "Binance Futures will launch USDⓈ-M Binance Bluebird Index perpetual "
            "contracts (“BLUEBIRDUSDT Perpetual Contracts”) with up to 25x leverage "
            "on 2022-11-02 at 12:00 (UTC). "
            "BLUEBIRDUSDTLaunch Time 2022-11-02 12:00 (UTC)",
            "BLUEBIRDUSDT",
            "2022-11-02T12:00:00+00:00",
            25,
        ),
    ],
)
def test_supported_listing_leads_are_table_corroborated(body, target, expected, leverage):
    fact = extract_target_listing_fact(body, target)
    assert fact["launch_at"].isoformat() == expected
    assert fact["max_leverage"] == leverage
    assert fact["contract_type"] == "PERPETUAL"
    assert fact["quote_asset"] == "USDT"


def test_prior_epoch_disclosure_is_preserved():
    body = (
        "Binance Futures will launch USDⓈ-M ICP perpetual contracts with up to 25x leverage "
        "on 2022-09-27 at 02:30 (UTC). ICPUSDTLaunch Time 2022-09-27 02:30 (UTC) "
        "The symbol for the old ICPUSDT contract, which was previously delisted at "
        "2022-06-10 09:00 (UTC), has been updated."
    )
    fact = extract_target_listing_fact(body, "ICPUSDT")
    assert fact["prior_epoch_disclosed"] is True
    assert fact["prior_epoch_delisted_at"].isoformat() == "2022-06-10T09:00:00+00:00"


def test_table_mismatch_and_wrong_target_fail_closed():
    body = (
        "Binance Futures will launch the USDⓈ-M GLMR perpetual contract at "
        "2023-09-26 01:30 (UTC), with up to 10x leverage. "
        "GLMRUSDTLaunch Time 2023-09-26 02:30 (UTC)"
    )
    with pytest.raises(ValueError, match="table"):
        extract_target_listing_fact(body, "GLMRUSDT")
    with pytest.raises(ValueError, match="target"):
        extract_target_listing_fact(body, "OTHERUSDT")
