from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import localcontext

import pytest

from pvb24.decimal_math import D
from pvb24.risk.costs import cost_gate, estimate_costs
from pvb24.risk.funding import FundingCoverage, FundingSettlement, reserve_rate
from pvb24.risk.portfolio import Exposure, Portfolio
from pvb24.types import Side

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def costs(side=Side.LONG, **kwargs):
    params = dict(
        side=side,
        entry=D(100),
        arrival_side_price=D("99.9"),
        atr_previous=D(1),
        tick=D("0.1"),
        entry_fee_rate=D("0.0005"),
        exit_fee_rate=D("0.0005"),
        stop_slippage_fraction=D("0.00075"),
        funding_rate_per_hour=D("0.00001"),
    )
    return estimate_costs(**(params | kwargs))


def exposure(symbol="BTCUSDT", side=Side.LONG, pending=False):
    return Exposure(symbol, symbol, side, D(10), D(10), D(10), D(50), D(100), pending)


def funding():
    start = NOW - timedelta(days=30)
    rows = [
        FundingSettlement(
            "BTCUSDT",
            start + timedelta(hours=8 * i),
            start + timedelta(hours=8 * (i + 1)),
            start + timedelta(hours=8 * (i + 1)),
            D("0.0008"),
            "synthetic",
            "v1",
        )
        for i in range(90)
    ]
    coverage = FundingCoverage("BTCUSDT", start, NOW, NOW, "synthetic", "v1")
    return rows, coverage


def test_shortfall_not_counted_in_sizing_twice():
    c = costs()
    assert c.stop == D(98)
    assert c.loss_per_unit == D("2.246")
    assert c.gate_cost_per_unit == D("0.346")
    assert c.arrival_shortfall == D("0.1")
    assert cost_gate(c)
    changed = costs(arrival_side_price=D(99))
    assert changed.loss_per_unit == c.loss_per_unit
    assert not cost_gate(changed)


@pytest.mark.parametrize("side,stop", [(Side.LONG, "98.0"), (Side.SHORT, "102.1")])
def test_stop_rounds_away_from_entry(side, stop):
    c = costs(side, entry=D("100.03"))
    assert c.stop == D(stop)
    assert c.price_risk >= D(2)


def test_cost_gate_inclusive_boundary_and_improvement_no_subsidy():
    args = dict(
        entry_fee_rate=D(0),
        exit_fee_rate=D(0),
        stop_slippage_fraction=D(0),
        funding_rate_per_hour=D(0),
    )
    assert cost_gate(costs(arrival_side_price=D("99.5"), **args))
    assert not cost_gate(costs(arrival_side_price=D("99.499999"), **args))
    assert costs(arrival_side_price=D(101)).arrival_shortfall == 0
    assert costs(Side.SHORT, arrival_side_price=D("100.5"), **args).arrival_shortfall == D("0.5")


def test_nonpositive_stop_and_float_rejected():
    with pytest.raises(ValueError, match="protective stop"):
        costs(atr_previous=D(50))
    with pytest.raises(TypeError):
        costs(entry=100.0)


def test_funding_direction_actual_intervals_and_no_credit_for_receipts():
    rows, coverage = funding()
    assert reserve_rate(rows, coverage, Side.LONG, NOW) == D("0.0001")
    assert reserve_rate(rows, coverage, Side.SHORT, NOW) == 0
    # Same hourly rate after switching from eight-hour to one-hour settlements.
    last = rows.pop()
    rows += [
        replace(
            last,
            interval_start=last.interval_start + timedelta(hours=i),
            settlement_time=last.interval_start + timedelta(hours=i + 1),
            available_at=last.interval_start + timedelta(hours=i + 1),
            rate=D("0.0001"),
        )
        for i in range(8)
    ]
    assert reserve_rate(rows, coverage, Side.LONG, NOW) == D("0.0001")


def test_funding_nearest_rank_and_future_revisions_cannot_leak():
    rows, coverage = funding()
    rows[-4:] = [replace(row, rate=D("0.008")) for row in rows[-4:]]
    # ceil(.95 * 90) = 86: the four highest are outside the selected rank.
    assert reserve_rate(rows, coverage, Side.LONG, NOW) == D("0.0001")
    future = replace(rows[0], available_at=NOW + timedelta(seconds=1), rate=D(1))
    assert reserve_rate(rows + [future], coverage, Side.LONG, NOW) == D("0.0001")
    rows[-5] = replace(rows[-5], rate=D("0.008"))
    assert reserve_rate(rows, coverage, Side.LONG, NOW) == D("0.001")


@pytest.mark.parametrize("case", ["missing", "gap", "first", "watermark", "future_coverage"])
def test_missing_funding_never_becomes_zero(case):
    rows, coverage = funding()
    if case == "missing":
        rows = []
    elif case == "gap":
        rows.pop(30)
    elif case == "first":
        rows.pop(0)
    elif case == "watermark":
        coverage = replace(coverage, through=NOW - timedelta(seconds=1))
    else:
        coverage = replace(coverage, available_at=NOW + timedelta(seconds=1))
    with pytest.raises(ValueError):
        reserve_rate(rows, coverage, Side.LONG, NOW)


def test_pending_and_open_consume_gross_not_net_and_same_direction_risk():
    p = Portfolio(D(1000), D(800), (exposure(), exposure("ETHUSDT", Side.SHORT, True)))
    assert p.slots == 2
    assert p.reserved_risk == 20
    assert p.gross_notional == 1000  # opposite sides do not net
    assert p.margin == 200
    assert p.budget(Side.LONG) == 10
    assert p.budget(Side.LONG, reduced=True) == 5
    p = replace(p, exposures=p.exposures + (exposure("SOLUSDT", pending=True),))
    assert p.slots == 3
    assert p.budget(Side.LONG) == 0


def test_equity_decline_does_not_clamp_negative_capacity_to_positive():
    p = Portfolio(D(500), D(100), (exposure(), exposure("ETHUSDT", pending=True)))
    assert p.budget(Side.LONG) == -10


def test_reserved_risk_scales_only_with_confirmed_remaining_quantity():
    original = exposure()
    marked = replace(original, valuation_price=D(80))
    assert marked.reserved_risk == original.reserved_risk
    assert marked.notional == 800 and marked.initial_margin_commitment == 100
    reduced = marked.confirmed_exit(D(4), D(40))
    assert reduced.reserved_risk == 4
    assert reduced.confirmed_exit(D(0), D(0)).reserved_risk == 0
    with pytest.raises(ValueError):
        reduced.confirmed_exit(D(5), D(50))
    with pytest.raises(ValueError):
        exposure(pending=True).confirmed_exit(D(4), D(40))


def test_no_double_count_of_open_and_pending_same_symbol():
    with pytest.raises(ValueError, match="aggregate symbol"):
        Portfolio(
            D(1000), D(800), (exposure(), replace(exposure(pending=True), position_id="other"))
        )


def test_risk_math_independent_of_ambient_decimal_precision():
    expected = costs()
    rows, coverage = funding()
    with localcontext() as ctx:
        ctx.prec = 6
        assert costs() == expected
        assert reserve_rate(rows, coverage, Side.LONG, NOW) == D("0.0001")
        assert exposure().reserved_risk == 10
