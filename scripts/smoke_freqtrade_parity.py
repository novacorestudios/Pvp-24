"""Load the pinned Freqtrade strategy and compare shared signal/intent output offline."""

import copy
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verify_provenance import verify  # noqa: E402

from pvb24.accounting.coordinator import AccountCoordinator  # noqa: E402
from pvb24.accounting.ledger import Ledger, LedgerStore  # noqa: E402
from pvb24.accounting.risk_service import AccountRiskService  # noqa: E402
from pvb24.data.contract_rules import ContractRules, MaintenanceTier  # noqa: E402
from pvb24.data.universe import Universe  # noqa: E402
from pvb24.decimal_math import D  # noqa: E402
from pvb24.execution.book import Book  # noqa: E402
from pvb24.execution.planner import EntryInputs, EntryPlanner  # noqa: E402
from pvb24.execution.protection import Protection  # noqa: E402
from pvb24.ids import canonical, digest  # noqa: E402
from pvb24.integrations.paper_dispatch import PaperDispatch  # noqa: E402
from pvb24.integrations.paper_session import PaperSession  # noqa: E402
from pvb24.integrations.paper_venue import L2PaperVenue  # noqa: E402
from pvb24.replay.account import AccountReplay  # noqa: E402
from pvb24.replay.events import Replay  # noqa: E402
from pvb24.replay.smoke import END, SIGNAL_TIME, START, SYMBOL, fixture  # noqa: E402
from pvb24.risk.portfolio import Portfolio  # noqa: E402
from pvb24.risk.reservations import Reservations  # noqa: E402
from pvb24.risk.sizing import Quote  # noqa: E402
from pvb24.state import Journal  # noqa: E402
from pvb24.strategy.service import SignalService  # noqa: E402
from pvb24.types import Quality  # noqa: E402


def initialize(path):
    journal = Journal(path)
    Reservations(journal, "parity").initialize(Portfolio(D(1000), D(1000)))
    LedgerStore(journal, "parity").initialize(Ledger(D(1000)))
    AccountRiskService(journal, "parity").initialize(
        START, max_mark_age=timedelta(seconds=1), policy_id="SYNTHETIC_PARITY"
    )
    return journal


def execution_parity(strategy, refdb, paperdb, decision, inputs, cid, folder):
    now = [decision]
    venues, host = [], None
    try:
        books = []
        for name in ("reference", "freqtrade"):
            book = Book(SYMBOL)
            book.snapshot(10, [(D("101.20"), D(100))], [(D("101.21"), D(100))], now[0], now[0])
            book.update(10, 11, 9, [], [], now[0], now[0])
            books.append(book)
            venue = L2PaperVenue(
                folder / (name + "-model.sqlite"),
                instance_id="SYNTHETIC_PARITY_ONLY",
                scope="parity",
                manifest_id="SYNTHETIC_L2_PARITY",
                clock=lambda: now[0],
                max_last_age=timedelta(seconds=1),
            )
            venues.append(venue)
            venue.install_book(book, source_event_id="book")
            venue.set_terms(
                inputs.rules,
                entry_fee_rate=D("0.0005"),
                exit_fee_rate=D("0.0005"),
                available_at=now[0],
                source_revision="synthetic-fees",
            )
            venue.publish_last(
                SYMBOL, D("101.21"), event_time=now[0], available_at=now[0], source_event_id="last"
            )
        host = PaperDispatch(refdb, "parity", Quality.PRELIMINARY, venues[0], lambda: now[0])
        session = PaperSession(host)
        strategy.config["pvb24"]["execution_transport"] = "LOCAL_PRELIMINARY_L2"
        strategy.bind_local_paper_model(venues[1], lambda: now[0])
        session.dispatch_entry(cid, inputs, books[0])
        session.pump_actions()
        strategy.dispatch_local_entry(cid, inputs, books[1])
        sid = refdb.db.execute(
            "SELECT signal_id FROM intents WHERE client_id=?", (cid,)
        ).fetchone()[0]

        def assert_equal(stage):
            for prefix in ("ledger:parity", "protection:parity:" + sid, "paper-session:parity"):
                if refdb.snapshot(prefix) != paperdb.snapshot(prefix):
                    raise AssertionError(stage + " snapshot parity failed: " + prefix)
            intents = [
                [dict(row) for row in db.db.execute("SELECT * FROM intents ORDER BY rowid")]
                for db in (refdb, paperdb)
            ]
            if intents[0] != intents[1] or canonical(venues[0].events_after()) != canonical(
                venues[1].events_after()
            ):
                raise AssertionError(stage + " order/fill/fee/terminal parity failed")

        assert_equal("entry/protect")
        for stage in ("replacement", "exit"):
            now[0] += timedelta(milliseconds=1)
            for db in (refdb, paperdb):
                AccountCoordinator(db, "parity").protection_event(
                    sid,
                    "parity-" + stage,
                    {"fixture": stage},
                    (lambda p: p.tighten_stop(p.effective_stop + D("0.01"), D("101.21")))
                    if stage == "replacement"
                    else (lambda p: p.close()),
                    now[0],
                )
            session.pump_actions()
            strategy.bot_loop_start(now[0])
            assert_equal(stage)
        p = Protection.restore(paperdb.snapshot("protection:parity:" + sid)[1])
        if p.remaining != 0 or p.confirmed_stops - p.canceled_stops:
            raise AssertionError("Shared exit did not reach flat quantity and terminal stops")
        return {
            "local_execution_parity": True,
            "execution_evidence_hash": digest(venues[0].events_after()),
            "modeled_order_requests_per_path": refdb.db.execute(
                "SELECT COUNT(*) FROM events WHERE event_id LIKE 'paper-ticket:%'"
            ).fetchone()[0],
            "modeled_fills_per_path": len(LedgerStore(refdb, "parity").read()[1].fills),
        }
    finally:
        strategy.close_local_paper()
        if host is not None:
            host.close()
        for venue in venues:
            venue.close()


def main():
    import freqtrade
    import pandas as pd
    from freqtrade.configuration import Configuration
    from freqtrade.configuration.config_validation import validate_config_consistency
    from freqtrade.enums import RunMode
    from freqtrade.resolvers import StrategyResolver

    verify(ROOT)
    pin = json.loads((ROOT / "config/manifest.json").read_text())["freqtrade"]
    if freqtrade.__version__ != pin["version"]:
        raise RuntimeError("Unexpected Freqtrade version")
    with tempfile.TemporaryDirectory(prefix="pvb24-parity-") as folder:
        folder = Path(folder)
        userdir = folder / "user_data"
        userdir.mkdir()
        cfg = Configuration(
            {
                "config": [str(ROOT / "integrations/freqtrade/config.pvb24.paper.json")],
                "user_data_dir": str(userdir),
                "strategy_path": str(ROOT / "integrations/freqtrade/strategies"),
            },
            RunMode.DRY_RUN,
        ).get_config()
        # Fixed synthetic evidence cannot be silently promoted to VERIFIED.
        cfg["pvb24"]["quality_mode"] = "PRELIMINARY"
        strategy = StrategyResolver.load_strategy(cfg)
        validate_config_consistency(cfg)
        strategy.bot_start()
        refdb, paperdb = (
            initialize(folder / "reference.sqlite"),
            initialize(folder / "paper.sqlite"),
        )
        try:
            reference = AccountReplay(refdb, "parity", Quality.PRELIMINARY)
            strategy.bind_shared_account(paperdb, "parity")
            decision = SIGNAL_TIME + timedelta(seconds=2)
            traces = []
            for handler in (reference, strategy.shared.deliver):
                replay = Replay(Quality.PRELIMINARY)
                replay.add(fixture())
                replay.run(decision, handler)
                traces.append(replay.trace_hash)
            if traces[0] != traces[1]:
                raise AssertionError("Shared reference/paper event output differs")
            universe = Universe(
                "synthetic-universe",
                START - timedelta(hours=1),
                END + timedelta(days=1),
                (SYMBOL,),
                ((SYMBOL, D(8640000000)),),
                (),
                Quality.PRELIMINARY,
                "synthetic",
            )
            reference_batch = SignalService(refdb, "parity", Quality.PRELIMINARY).evaluate(
                universe, SIGNAL_TIME, decision
            )
            paper_batch = strategy.shared_batch(universe, SIGNAL_TIME, decision)
            if canonical(reference_batch) != canonical(paper_batch):
                raise AssertionError("Reference/paper signal parity failed")
            rules = ContractRules(
                SYMBOL,
                START - timedelta(days=100),
                START - timedelta(days=100),
                "synthetic",
                "v1",
                D("0.01"),
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

            def quote(quantity):
                return Quote(
                    D("101.21"),
                    D("101.21"),
                    D("0.0005"),
                    D("0.0005"),
                    D("0.00075"),
                    D("0.0000125"),
                    Quality.PRELIMINARY,
                    decision,
                    "synthetic-fixed-snapshot",
                )

            inputs = {
                SYMBOL: EntryInputs(rules, quote, D(90000000), decision, "synthetic-fixed-snapshot")
            }
            reference_plan = EntryPlanner(refdb, "parity", Quality.PRELIMINARY).plan(
                reference_batch, inputs, decision
            )
            paper_plan = strategy.plan_shared_batch(paper_batch, inputs, decision)
            if (
                canonical(reference_plan) != canonical(paper_plan)
                or len(paper_plan) != 1
                or paper_plan[0]["reason"] != "ACCEPTED"
            ):
                raise AssertionError("Reference/paper intent parity failed")
            native = pd.DataFrame({"close": [1.0, 1000000.0]})
            native = strategy.populate_indicators(native, {"pair": "BTC/USDT:USDT"})
            native = strategy.populate_entry_trend(native, {"pair": "BTC/USDT:USDT"})
            native = strategy.populate_exit_trend(native, {"pair": "BTC/USDT:USDT"})
            if native[["enter_long", "enter_short", "exit_long", "exit_short"]].to_numpy().any():
                raise AssertionError("Native dataframe created a second order authority")
            if strategy.confirm_trade_entry() or strategy.confirm_trade_exit():
                raise AssertionError("Ungated native execution path")
            try:
                strategy.shared.dispatch(paper_plan[0]["client_id"])
            except RuntimeError:
                pass
            else:
                raise AssertionError("Unqualified transport accepted dispatch")
            unsafe = copy.deepcopy(cfg)
            unsafe["dry_run"] = False
            try:
                type(strategy)(unsafe)
            except ValueError:
                pass
            else:
                raise AssertionError("LIVE configuration accepted")
            execution = execution_parity(
                strategy,
                refdb,
                paperdb,
                decision,
                inputs[SYMBOL],
                paper_plan[0]["client_id"],
                folder,
            )
            print(
                json.dumps(
                    {
                        "freqtrade_version": freqtrade.__version__,
                        "strategy_loaded": type(strategy).__name__,
                        "signal_parity": True,
                        "intent_parity": True,
                        "trace_hash": traces[0],
                        "signal_hash": digest(reference_batch),
                        "intent_hash": digest(reference_plan),
                        "external_orders_submitted": 0,
                        "operational_paper_ready": False,
                        "native_dry_run_transport_qualified": False,
                        **execution,
                    },
                    indent=2,
                )
            )
        finally:
            refdb.close()
            paperdb.close()


if __name__ == "__main__":
    main()
