"""Reproducible synthetic integration run; never historical performance evidence."""

import hashlib
import json
import subprocess
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pvb24.accounting.coordinator import AccountCoordinator
from pvb24.accounting.ledger import Ledger, LedgerStore
from pvb24.accounting.reconciliation import OpenReconciler
from pvb24.accounting.risk_service import AccountRiskService
from pvb24.data.availability import preliminary_timing
from pvb24.data.contract_rules import ContractRules, MaintenanceTier
from pvb24.data.schemas import Candle, Mark, Timing
from pvb24.data.universe import Universe
from pvb24.decimal_math import D
from pvb24.execution.market import preliminary_proxy
from pvb24.execution.planner import EntryInputs, EntryPlanner
from pvb24.ids import canonical, digest, signal_identity
from pvb24.replay import codecs
from pvb24.replay.account import AccountReplay
from pvb24.replay.bar_execution import resolve_bar
from pvb24.replay.collateral import SyntheticCollateral
from pvb24.replay.events import Event, Kind, Replay
from pvb24.replay.preliminary import MinuteOpen
from pvb24.replay.venue import PreliminaryVenue
from pvb24.risk.liquidation import isolated_liquidation
from pvb24.risk.portfolio import Portfolio
from pvb24.risk.reservations import Reservations
from pvb24.risk.sizing import Quote
from pvb24.state import Journal
from pvb24.strategy.service import SignalService
from pvb24.types import Quality, Side

START = datetime(2024, 1, 1, tzinfo=UTC)
SIGNAL_TIME = START + timedelta(hours=1)
ENTRY_TIME = SIGNAL_TIME + timedelta(minutes=1)
CLOSE_TIME = START + timedelta(hours=2)
END = CLOSE_TIME + timedelta(minutes=1)
SCOPE = "synthetic-reference-smoke"
SYMBOL = "BTCUSDT"


def event(name, kind, time, payload, available=None):
    return Event(
        name,
        kind,
        time,
        available or time,
        "PVB24_SYNTHETIC_FIXTURE_V1",
        Quality.PRELIMINARY,
        canonical(payload),
    )


def mark(price, time):
    return Mark(
        SYMBOL,
        D(price),
        Timing(time, time, time, time, time, "PVB24_SYNTHETIC_MARK_V1", "v1", "snapshot"),
    )


def hourly(start, close="100", volume="360000000"):
    value = D(close)
    return Candle(
        SYMBOL,
        preliminary_timing(start, start + timedelta(hours=1), "synthetic-last", "v1"),
        D(100),
        max(D(101), value),
        min(D(99), value),
        value,
        D(volume),
    )


def fixture(*, append_future=False):
    """Generate inputs only; do not use engine output to construct future prices."""
    rows = []
    for index in range(720):
        bar = hourly(START - timedelta(hours=720 - index))
        rows.append(
            event(
                "warmup:" + str(index),
                Kind.OBSERVATION,
                bar.timing.event_time,
                {"type": "HOURLY_LAST", "record": bar},
                bar.timing.available_at,
            )
        )
    signal = hourly(START, "101.21", "720000000")
    rows.append(
        event(
            "signal-candle",
            Kind.OBSERVATION,
            signal.timing.event_time,
            {"type": "HOURLY_LAST", "record": signal},
            signal.timing.available_at,
        )
    )
    failure = replace(
        hourly(SIGNAL_TIME, "99", "360000000"), open=D("101.21"), high=D(102), low=D("98.5")
    )
    rows.append(
        event(
            "failure-candle",
            Kind.OBSERVATION,
            failure.timing.event_time,
            {"type": "HOURLY_LAST", "record": failure},
            failure.timing.available_at,
        )
    )
    _, position_id = signal_identity("1.0", SYMBOL, Side.LONG, SIGNAL_TIME)
    rows.append(
        event(
            "early-failure",
            Kind.EXIT_DECISION,
            CLOSE_TIME,
            {"type": "HOURLY_CLOSE", "position_id": position_id, "last_price": D(99)},
            failure.timing.available_at,
        )
    )
    duration = 122 if append_future else 121
    for minute in range(duration + 1):
        time = START + timedelta(minutes=minute)
        price = "99" if time >= CLOSE_TIME else "101.3"
        if time > ENTRY_TIME:
            value = mark(price, time)
            rows.append(
                event(
                    "mark:" + str(minute), Kind.OBSERVATION, time, {"type": "MARK", "record": value}
                )
            )
        rows.append(event("risk:" + str(minute), Kind.ACCOUNT_RISK, time, {}))
    # No settlement boundary lies in the hour-long owned interval. These fixtures
    # do not derive missing funding from candles or claim historical coverage.
    for index in range(60):
        start = ENTRY_TIME + timedelta(minutes=index)
        opening = D("101.21") if index == 0 else D(99) if index == 59 else D("101.3")
        closing = D(99) if index >= 58 else D("101.3")
        high = D(100) if index == 59 else D(102)
        low = D("98.5") if index >= 58 else D("100.5")
        last = Candle(
            SYMBOL,
            preliminary_timing(start, start + timedelta(minutes=1), "synthetic-minute-last", "v1"),
            opening,
            high,
            low,
            closing,
            D(6000000),
        )
        mark_bar = Candle(
            SYMBOL,
            preliminary_timing(start, start + timedelta(minutes=1), "synthetic-minute-mark", "v1"),
            D(99) if index == 59 else D("101.3"),
            high,
            low,
            closing,
            D(6000000),
            "MARK",
        )
        rows.append(
            event(
                "bar:" + str(index),
                Kind.LIQUIDATION,
                last.timing.interval_end,
                {"type": "BAR_CHECK", "last": last, "mark": mark_bar},
                max(last.timing.available_at, mark_bar.timing.available_at),
            )
        )
    return rows


def source_fingerprint(root):
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    )
    files = [
        {"path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
        for name in sorted(set(names))
        if name and (root / name).is_file()
    ]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True))
    return {"git_sha": sha, "worktree_dirty": dirty, "source_tree_hash": digest(files)}


def run_smoke(root: Path, output: Path, *, append_future=False):
    """Outputs must be new: previous evidence is never silently overwritten."""
    output.mkdir(parents=True, exist_ok=False)
    rows = fixture(append_future=append_future)
    source = "".join(canonical(row) + "\n" for row in rows)
    (output / "synthetic-events.jsonl").write_text(source, encoding="utf-8")
    policy = {
        "purpose": "ENGINE_INTEGRATION_SMOKE",
        "quality": Quality.PRELIMINARY,
        "historical_performance": False,
        "economic_start": START,
        "economic_end": END,
        "initial_cash": D(1000),
        "max_mark_age_us": 1000000,
        "max_account_age_us": 1000000,
        "collateral_model": SyntheticCollateral.POLICY,
        "protective_ack_latency_us": 0,
        "taker_fee_rate": D("0.0005"),
        "all_in_liquidation_fee_rate": D("0.01"),
        "funding_reserve_per_hour": D("0.0000125"),
        "funding_fixture": "explicit synthetic schedule; no settlement during owned interval",
        "unverified": ["book_age", "spread", "depth", "partial_fills", "exchange_liquidation"],
    }
    policy_id = digest(policy)
    baseline = json.loads((root / "config/manifest.json").read_text())
    manifest = {
        "schema_version": "1.0.0",
        "policy": policy,
        "policy_id": policy_id,
        "config_hash": baseline["config_hash"],
        "code": source_fingerprint(root),
        "data_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "source": "DETERMINISTIC_SYNTHETIC_FIXTURE_V1",
        "live_enabled": False,
    }
    # Freeze run inputs before constructing account state or looking at outcomes.
    (output / "manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
    db = Journal(output / "account.sqlite")
    try:
        reservations = Reservations(db, SCOPE)
        reservations.initialize(Portfolio(D(1000), D(1000)))
        LedgerStore(db, SCOPE).initialize(Ledger(D(1000)))
        risk = AccountRiskService(db, SCOPE)
        risk.initialize(START, max_mark_age=timedelta(seconds=1), policy_id=policy_id)
        runtime = AccountReplay(db, SCOPE, Quality.PRELIMINARY)
        venue = PreliminaryVenue(db, SCOPE)
        collateral = SyntheticCollateral(db, SCOPE)
        collateral.freeze(policy=collateral.POLICY, manifest_id=policy_id)
        replay = Replay(Quality.PRELIMINARY)
        replay.add(rows)
        rules = ContractRules(
            SYMBOL,
            START - timedelta(days=100),
            START - timedelta(days=100),
            "synthetic-rules",
            "v1",
            D("0.1"),
            D("0.1"),
            D("0.1"),
            D(5),
            D(10000),
            D(1),
            (MaintenanceTier(D(0), D(10000000), D("0.005"), D(0), 5),),
            False,
            False,
            True,
            True,
        )
        position_id = None
        last_collateral_observation = None

        def handle(delivery):
            nonlocal last_collateral_observation
            event = delivery.event
            if event.kind is Kind.LIQUIDATION and event.payload.get("type") == "BAR_CHECK":
                if position_id is None or last_collateral_observation is None:
                    raise ValueError("Bar replay preceded confirmed entry account state")
                last = codecs.candle(event.payload["last"])
                mark_bar = codecs.candle(event.payload["mark"])
                p = last_collateral_observation.positions[0]
                # Reference model terms were observed before this completed bar.
                from pvb24.execution.protection import Protection

                state = Protection.restore(
                    db.snapshot("protection:" + SCOPE + ":" + position_id)[1]
                )
                liq = isolated_liquidation(
                    state.side, p.quantity, state.entry_vwap, p.isolated_collateral, p.rules
                )
                return resolve_bar(
                    venue,
                    position_id,
                    last,
                    mark_bar,
                    liquidation_price=liq.price,
                    sigma=D(0),
                    recent_quote_volume=D(90000000),
                    inputs_available_at=last.timing.interval_start,
                    all_in_liquidation_fee_rate=D("0.01"),
                    liquidation_terms_available_at=last_collateral_observation.event_time,
                    model_manifest_id=policy_id,
                )
            result = runtime(delivery)
            return result

        decision = SIGNAL_TIME + timedelta(seconds=2)
        replay.run(decision, handle)
        universe = Universe(
            "synthetic-universe",
            START - timedelta(hours=1),
            END + timedelta(days=1),
            (SYMBOL,),
            ((SYMBOL, D(8640000000)),),
            (),
            Quality.PRELIMINARY,
            "synthetic-security-and-volumes",
        )
        batch = SignalService(db, SCOPE, Quality.PRELIMINARY).evaluate(
            universe, SIGNAL_TIME, decision
        )

        def quote(quantity):
            proxy = preliminary_proxy(D("101.21"), quantity, Side.LONG, D(0), D(90000000))
            return Quote(
                proxy.price,
                D("101.21"),
                D("0.0005"),
                D("0.0005"),
                proxy.stop_slippage,
                D("0.0000125"),
                Quality.PRELIMINARY,
                decision,
                "synthetic-decision-snapshot",
            )

        planned = EntryPlanner(db, SCOPE, Quality.PRELIMINARY).plan(
            batch,
            {
                SYMBOL: EntryInputs(
                    rules, quote, D(90000000), decision, "synthetic-decision-snapshot"
                )
            },
            decision,
        )
        if len(planned) != 1 or planned[0]["reason"] != "ACCEPTED":
            raise ValueError("Synthetic golden entry was not accepted")
        client_id = planned[0]["client_id"]
        venue.freeze_entry(client_id, sigma=D(0), available_at=decision)
        replay.run(ENTRY_TIME, handle)
        opening = MinuteOpen(SYMBOL, ENTRY_TIME, ENTRY_TIME, D("101.21"), "synthetic-open", "v1")
        entered = venue.execute_entry(client_id, opening)
        position_id = entered["fill"]["position_id"]
        venue.acknowledge_protection(entered["action_ids"][0], ENTRY_TIME)
        # For the first owned bar, use a causal same-time synthetic collateral/Mark observation.
        last_collateral_observation = collateral.observe(
            ENTRY_TIME,
            [mark("101.3", ENTRY_TIME)],
            {SYMBOL: rules},
            max_mark_age=timedelta(seconds=1),
        )
        # Start reconciliation only after the next current minute equity sample.
        replay.run(ENTRY_TIME + timedelta(minutes=1), handle)
        proof_time = ENTRY_TIME + timedelta(minutes=1)
        proof = collateral.observe(
            proof_time,
            [mark("101.3", proof_time)],
            {SYMBOL: rules},
            max_mark_age=timedelta(seconds=1),
        )
        OpenReconciler(db, SCOPE).reconcile(
            proof,
            proof_time,
            max_account_age=timedelta(seconds=1),
            max_mark_age=timedelta(seconds=1),
            require_verified=False,
        )
        # Reopen the durable account midway; no account reset or re-seeding occurs.
        db.close()
        db = Journal(output / "account.sqlite")
        runtime = AccountReplay(db, SCOPE, Quality.PRELIMINARY)
        venue = PreliminaryVenue(db, SCOPE)
        replay.run(CLOSE_TIME + timedelta(seconds=2), handle)
        exits = db.db.execute(
            "SELECT client_id FROM intents WHERE scope=? "
            "AND purpose='EXIT_MARKET' AND state='PREPARED'",
            (SCOPE,),
        ).fetchall()
        if len(exits) != 1:
            raise ValueError("Expected one early-failure close request")
        replay.run(END, handle)
        closed = venue.execute_exit(
            exits[0]["client_id"],
            MinuteOpen(SYMBOL, END, END, D("98.9"), "synthetic-open", "v1"),
            sigma=D(0),
            recent_quote_volume=D(90000000),
            inputs_available_at=CLOSE_TIME,
        )
        view = LedgerStore(db, SCOPE).read()[1].view(END)
        if (
            any(p.quantity != 0 for p in view.positions)
            or view.cash != D(1000) + view.realized_gross - view.fees + view.funding
        ):
            raise ValueError("Synthetic ledger identity failed")
        AccountCoordinator(db, SCOPE).reconcile_flat(END, view.cash, "synthetic-flat-proof")
        summary = {
            "purpose": "ENGINE_INTEGRATION_SMOKE",
            "historical_performance": False,
            "acceptance_status": "NOT_EVALUATED",
            "quality": Quality.PRELIMINARY,
            "paper_ready": False,
            "live_enabled": False,
            "orders_sent_to_exchange": 0,
            "manifest_hash": digest(manifest),
            "replay_events": len(replay.trace),
            "trace_hash": replay.trace_hash,
            "ambiguous_event_count": replay.ambiguous_event_count,
            "ledger": asdict(view),
            "entry": entered,
            "exit": closed,
            "restart_verified": True,
        }
        (output / "trace.jsonl").write_text(
            "".join(canonical(r) + "\n" for r in replay.trace), encoding="utf-8"
        )
        (output / "summary.json").write_text(canonical(summary) + "\n", encoding="utf-8")
        return json.loads(canonical(summary))
    finally:
        db.close()
