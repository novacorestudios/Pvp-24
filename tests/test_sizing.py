from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import pytest
from test_data import NOW
from test_data import rules as base_rules
from test_risk import exposure

from pvb24.data.contract_rules import MaintenanceTier
from pvb24.decimal_math import D
from pvb24.risk.liquidation import buffer_ok, isolated_liquidation
from pvb24.risk.portfolio import Portfolio
from pvb24.risk.reservations import Reservations
from pvb24.risk.sizing import Quote, SizingResult, post_fill_reduction, size_entry
from pvb24.state import Conflict, Journal
from pvb24.types import Quality, Side


def rules():
    return replace(
        base_rules(),
        quantity_step=D("0.1"),
        supports_ioc=True,
        supports_last_stop=True,
        tiers=(MaintenanceTier(D(0), D(10000000), D("0.005"), D(0), 5),),
    )


def quote(quantity):
    return Quote(
        D(100),
        D(100),
        D("0.0005"),
        D("0.0005"),
        D("0.00075"),
        D(0),
        Quality.PRELIMINARY,
        NOW,
        "synthetic",
    )


def solve(**kwargs):
    defaults = dict(
        symbol="BTCUSDT",
        side=Side.LONG,
        atr_previous=D(1),
        decision=NOW,
        portfolio=Portfolio(D(1000), D(1000)),
        rules=rules(),
        quote_model=quote,
        require_verified=False,
    )
    return size_entry(**(defaults | kwargs))


@pytest.mark.parametrize("side", [Side.LONG, Side.SHORT])
def test_liquidation_solves_balance_and_tier_at_liquidation_mark(side):
    tiers = (
        MaintenanceTier(D(0), D(1000), D("0.01"), D(0), 5),
        MaintenanceTier(D(1000), D(100000), D("0.02"), D(10), 4),
    )
    r = replace(rules(), tiers=tiers)
    result = isolated_liquidation(side, D(10), D(110), D(300), r)
    tier = tiers[result.tier_index]
    price = result.price
    assert abs(
        D(300) + side.sign * D(10) * (price - D(110)) - (D(10) * price * tier.rate - tier.deduction)
    ) < D("1e-24")
    assert result.tier_index == (0 if side is Side.LONG else 1)
    assert result.quality is Quality.PRELIMINARY


def test_liquidation_missing_discontinuous_tiers_and_nonpositive_collateral_reject():
    with pytest.raises(ValueError):
        isolated_liquidation(Side.LONG, D(1), D(100), D(20), base_rules())
    with pytest.raises(ValueError):
        isolated_liquidation(Side.LONG, D(1), D(100), D(0), rules())
    r = replace(
        rules(),
        tiers=(
            MaintenanceTier(D(0), D(100), D("0.01"), D(0), 5),
            MaintenanceTier(D(100), D(10000), D("0.02"), D(0), 4),
        ),
    )
    with pytest.raises(ValueError, match="Discontinuous"):
        isolated_liquidation(Side.LONG, D(1), D(100), D(20), r)


def test_3r_buffer_strict_order_and_inclusive_distance():
    assert buffer_ok(Side.LONG, D(100), D(98), D(94))
    assert not buffer_ok(Side.LONG, D(100), D(98), D("94.0001"))
    assert buffer_ok(Side.SHORT, D(100), D(102), D(106))
    assert not buffer_ok(Side.SHORT, D(100), D(102), D("105.9999"))
    assert not buffer_ok(Side.LONG, D(100), D(98), D(106))


@pytest.mark.parametrize("side", [Side.LONG, Side.SHORT])
def test_largest_step_minimum_leverage_and_no_risk_rounding_up(side):
    result = solve(side=side)
    assert result.reason == "ACCEPTED" and result.iterations == 2
    entry = result.entry
    assert entry.quantity == D("4.5")
    assert entry.leverage == 3
    assert entry.initial_margin == 150
    assert entry.reserved_loss <= 10
    # One step higher would exceed the risk cap, irrespective of leverage.
    assert D("4.6") * entry.costs.loss_per_unit > 10
    assert solve(side=side, reduced=True).entry.quantity == D("2.2")


def test_price_impact_recomputed_for_every_candidate():
    seen = []

    def impact(q):
        seen.append(q)
        return replace(quote(q), expected_entry=D(100) + q / 100)

    r = solve(quote_model=impact)
    assert r.entry is not None
    assert r.entry.costs.entry == D(100) + r.entry.quantity / 100
    assert len(set(seen)) > 1


def test_minimums_never_round_quantity_up():
    assert solve(rules=replace(rules(), minimum_quantity=D(5))).entry is None
    assert solve(rules=replace(rules(), minimum_notional=D(500))).entry is None
    assert solve(maximum_quantity=D("0.9")).entry is None  # below .25% planned risk
    assert solve(rules=replace(rules(), maximum_quantity=D("3.11"))).entry.quantity == D("3.1")


def test_contract_count_rules_convert_to_base_units():
    r = solve(rules=replace(rules(), contract_size=D(10), maximum_quantity=D("0.3")))
    assert r.entry.quantity == 3


def test_insufficient_capacity_duplicate_symbol_and_three_slots():
    assert solve(portfolio=Portfolio(D(0), D(0))).reason == "NONPOSITIVE_EQUITY_OR_COLLATERAL"
    assert (
        solve(portfolio=Portfolio(D(1000), D(1000), (exposure(),))).reason
        == "SLOT_OR_SYMBOL_RESERVED"
    )
    p = Portfolio(D(1000), D(1000), tuple(exposure(x, Side.SHORT) for x in ("A", "B", "C")))
    assert solve(portfolio=p).reason == "SLOT_OR_SYMBOL_RESERVED"
    p = Portfolio(D(500), D(1000), (exposure("A"), exposure("B")))
    assert solve(portfolio=p).reason == "INSUFFICIENT_RISK_CAPACITY"


def test_margin_and_free_collateral_are_binding_at_smallest_valid_leverage():
    limited = solve(portfolio=Portfolio(D(1000), D(100)))
    assert limited.entry.quantity == D("4.5") and limited.entry.leverage == 5
    denied = solve(portfolio=Portfolio(D(1000), D(10)))
    assert denied.entry is None
    r = solve(rules=replace(rules(), tiers=(replace(rules().tiers[0], max_leverage=1),)))
    assert r.entry.quantity == D(2) and r.entry.leverage == 1


def test_notional_cap_and_margin_commitments():
    # Tiny ATR cannot obtain leverage-inflated exposure beyond equity.
    r = solve(
        atr_previous=D("0.5"),
        quote_model=lambda q: replace(
            quote(q),
            expected_entry=D(200),
            arrival_side_price=D(200),
            entry_fee_rate=D("0.0001"),
            exit_fee_rate=D("0.0001"),
            stop_slippage_fraction=D("0.0001"),
        ),
    )
    assert r.entry.quantity * r.entry.costs.entry <= 1000
    p = Portfolio(
        D(1000), D(1000), (replace(exposure("A", Side.SHORT), initial_margin_commitment=D(590)),)
    )
    assert solve(portfolio=p).entry is None


def test_verified_requires_rules_margin_and_quote_evidence():
    assert solve(require_verified=True).reason == "RULES_OR_MARGIN_UNVERIFIED"
    assert (
        solve(rules=replace(rules(), supports_ioc=False)).reason == "ORDER_CAPABILITIES_UNVERIFIED"
    )
    assert (
        solve(
            quote_model=lambda q: replace(quote(q), available_at=NOW + timedelta(seconds=1))
        ).entry
        is None
    )
    assert (
        solve(
            rules=replace(rules(), effective_to=NOW + timedelta(seconds=1)),
            decision=NOW + timedelta(seconds=1),
        ).reason
        == "RULES_EXPIRED"
    )


def test_five_iteration_limit_fails_closed_on_nonconvergence():
    calls = 0

    def moving(q):
        nonlocal calls
        # Every pass starts at exactly five units; alternate execution availability.
        if q == 5:
            calls += 1
        return quote(q) if q <= (D(4) if calls % 2 else D(3)) else None

    result = solve(quote_model=moving)
    assert result.entry is None and result.reason == "SIZING_NOT_CONVERGED"
    assert result.iterations == 5


def test_postfill_reduce_only_never_increases_and_unknown_closes():
    result = solve()
    action = post_fill_reduction(D(5), lambda maximum: result)
    assert action.remaining_quantity == D("4.5") and action.reduce_only_quantity == D("0.5")
    assert post_fill_reduction(D(4), lambda maximum: result).remaining_quantity == 0
    unknown = SizingResult(None, "SIZING_NOT_CONVERGED", 5, 0)
    assert post_fill_reduction(D(5), lambda maximum: unknown).reduce_only_quantity == 5


def test_atomic_pending_reservation_intent_and_restart(tmp_path):
    path = tmp_path / "risk.sqlite"
    journal = Journal(path)
    reservations = Reservations(journal, "paper")
    reservations.initialize(Portfolio(D(1000), D(1000)))
    cid = reservations.reserve(1, "signal", "BTCUSDT", Side.LONG, solve())
    journal.close()
    journal = Journal(path)
    version, p = Reservations(journal, "paper").read()
    assert version == 2 and p.slots == 1 and p.exposures[0].pending
    assert p.reserved_risk == solve().entry.reserved_loss
    assert p.free_collateral < 850
    assert journal.claim_dispatch(cid)
    assert not journal.claim_dispatch(cid)
    journal.close()


def test_competing_snapshot_reservations_cannot_double_spend(tmp_path):
    path = tmp_path / "risk.sqlite"
    journal = Journal(path)
    Reservations(journal, "paper").initialize(Portfolio(D(1000), D(1000)))
    journal.close()
    barrier = Barrier(2)

    def worker(symbol):
        db = Journal(path)
        book = Reservations(db, "paper")
        version, p = book.read()
        result = solve(symbol=symbol, rules=replace(rules(), symbol=symbol), portfolio=p)
        barrier.wait()
        try:
            book.reserve(version, symbol, symbol, Side.LONG, result)
            return True
        except Conflict:
            return False
        finally:
            db.close()

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(worker, ("BTCUSDT", "ETHUSDT"))) == [False, True]
    db = Journal(path)
    assert Reservations(db, "paper").read()[1].slots == 1
    assert db.db.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 1
    db.close()


def test_reservation_failure_rolls_back_intent_and_portfolio(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "risk.sqlite")
    reservations = Reservations(journal, "paper")
    reservations.initialize(Portfolio(D(1000), D(1000)))
    original = Journal.append_tx

    def fail(db, event_id, payload):
        if event_id.startswith("reservation:"):
            raise RuntimeError("injected crash before commit")
        return original(db, event_id, payload)

    monkeypatch.setattr(Journal, "append_tx", staticmethod(fail))
    with pytest.raises(RuntimeError):
        reservations.reserve(1, "signal", "BTCUSDT", Side.LONG, solve())
    assert reservations.read()[0] == 1
    assert journal.db.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 0
    journal.close()
