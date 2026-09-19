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

from pvb24.accounting.ledger import Ledger, LedgerStore  # noqa: E402
from pvb24.accounting.risk_service import AccountRiskService  # noqa: E402
from pvb24.data.contract_rules import ContractRules, MaintenanceTier  # noqa: E402
from pvb24.data.universe import Universe  # noqa: E402
from pvb24.decimal_math import D  # noqa: E402
from pvb24.execution.planner import EntryInputs, EntryPlanner  # noqa: E402
from pvb24.ids import canonical, digest  # noqa: E402
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
                        "orders_submitted": 0,
                        "operational_paper_ready": False,
                        "native_dry_run_transport_qualified": False,
                    },
                    indent=2,
                )
            )
        finally:
            refdb.close()
            paperdb.close()


if __name__ == "__main__":
    main()
