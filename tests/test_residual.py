from dataclasses import replace
from datetime import timedelta

import pytest
from test_data import NOW
from test_sizing import rules

from pvb24.decimal_math import D
from pvb24.risk.residual import ReductionProjection, ResidualPosition, liquidation_remedy
from pvb24.types import Quality, Side


def position(side=Side.LONG, collateral="50"):
    return ResidualPosition(
        "BTCUSDT", side, D(10), D(100), D(98) if side is Side.LONG else D(102), D(collateral)
    )


def project(remaining):
    return ReductionProjection(
        remaining,
        D(100),
        (D(10) - remaining) * D("0.05"),
        D(0),
        NOW,
        "synthetic-retained-collateral",
        "v1",
        Quality.PRELIMINARY,
    )


def remedy(p=None, projection=project, **kwargs):
    return liquidation_remedy(
        p or position(), rules(), NOW, projection, require_verified=False, **kwargs
    )


def test_smallest_reduction_restores_3r_after_reduction_fees():
    result = remedy()
    assert result.remaining_quantity == D("7.7")
    assert result.reduce_only_quantity == D("2.3")
    assert result.expected_collateral == D("49.885")
    assert result.liquidation.price <= D(94)
    assert result.reason == "REDUCE_ONLY"


@pytest.mark.parametrize("side", [Side.LONG, Side.SHORT])
def test_already_compliant_position_does_not_reduce_or_add_collateral(side):
    result = remedy(position(side, "100"))
    assert result.remaining_quantity == 10 and result.reduce_only_quantity == 0
    assert result.expected_collateral == 100 and result.reason == "COMPLIANT"


def test_proportional_collateral_release_can_make_reduction_unable_to_repair_buffer():
    def release(remaining):
        return replace(project(remaining), collateral_released=(D(10) - remaining) * D(5))

    result = remedy(projection=release)
    assert result.remaining_quantity == 0 and result.reduce_only_quantity == 10
    assert result.reason == "NO_BUFFER_REPAIR_CLOSE"


def test_adverse_reduction_price_lowers_safe_residual_quantity():
    result = remedy(projection=lambda q: replace(project(q), execution_price=D(99)))
    assert result.remaining_quantity < D("7.7")
    assert result.expected_collateral < D("49.885")


def test_funding_debit_to_actual_collateral_increases_required_reduction():
    after_funding = remedy(position(collateral="45"))
    before_funding = remedy()
    assert after_funding.remaining_quantity < before_funding.remaining_quantity


def test_unknown_or_future_projection_requires_full_close():
    assert remedy(projection=lambda q: None).reduce_only_quantity == 10
    result = remedy(
        projection=lambda q: replace(project(q), available_at=NOW + timedelta(seconds=1))
    )
    assert result.reason == "REDUCTION_ECONOMICS_UNKNOWN_CLOSE"


def test_verified_requires_actual_validated_rules_not_synthetic_fixture_success():
    result = liquidation_remedy(position(), rules(), NOW, project)
    assert result.reason == "LIQUIDATION_UNVERIFIED_CLOSE"
    assert result.remaining_quantity == 0


def test_original_stop_is_not_redefined_by_hypothetical_smaller_entry():
    ordinary = remedy()
    wider_original = remedy(replace(position(), initial_stop=D(97)))
    assert wider_original.remaining_quantity < ordinary.remaining_quantity
    assert wider_original.liquidation.price <= 91
