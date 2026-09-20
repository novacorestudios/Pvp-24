"""Reconcile owned open positions against causal account and Mark observations."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.accounting.coordinator import AccountCoordinator, read_tx, save_tx
from pvb24.accounting.ledger import Ledger, ReconciliationRequired
from pvb24.data.contract_rules import ContractRules
from pvb24.data.schemas import Mark
from pvb24.decimal_math import CONTEXT, ZERO, D, require_decimal
from pvb24.execution.protection import Protection
from pvb24.ids import digest
from pvb24.risk.portfolio import Exposure, Portfolio
from pvb24.risk.reservations import restore_portfolio
from pvb24.risk.residual import ReductionProjection, ResidualPosition, liquidation_remedy
from pvb24.state import Journal
from pvb24.types import Quality, utc


@dataclass(frozen=True)
class PositionObservation:
    position_id: str
    quantity: Decimal
    initial_margin_commitment: Decimal
    isolated_collateral: Decimal
    leverage: int
    mark: Mark
    rules: ContractRules

    def __post_init__(self):
        if not self.position_id or type(self.leverage) is not int or not 1 <= self.leverage <= 5:
            raise ValueError("Owned position and allowed leverage required")
        require_decimal(self.quantity, positive=True)
        require_decimal(self.initial_margin_commitment, positive=True)
        require_decimal(self.isolated_collateral)


@dataclass(frozen=True)
class AccountObservation:
    event_time: datetime
    available_at: datetime
    cash: Decimal
    free_collateral: Decimal  # venue spendable collateral before local strategy reserves
    positions: tuple[PositionObservation, ...]
    quality: Quality
    source: str
    revision_id: str

    def __post_init__(self):
        if utc(self.event_time) > utc(self.available_at):
            raise ValueError("Invalid account availability")
        require_decimal(self.cash)
        require_decimal(self.free_collateral)
        if not self.source or not self.revision_id or not isinstance(self.quality, Quality):
            raise ValueError("Account observation provenance required")
        if not isinstance(self.positions, tuple):
            raise TypeError("Immutable position observations required")
        if len({x.position_id for x in self.positions}) != len(self.positions):
            raise ValueError("Duplicate account position")


@dataclass(frozen=True)
class ReconciledAccount:
    portfolio: Portfolio
    entry_gate_ready: bool
    action_ids: tuple[str, ...]
    reasons: tuple[str, ...]


class OpenReconciler:
    def __init__(self, journal: Journal, scope: str):
        self.journal, self.scope = journal, scope
        self.coordinator = AccountCoordinator(journal, scope)

    def _close_uncovered(self, db, protection, quantity):
        rows = db.execute(
            "SELECT payload FROM intents WHERE scope=? AND signal_id=? "
            "AND purpose='EXIT_MARKET' AND state IN ('PREPARED','UNKNOWN','ACKNOWLEDGED')",
            (self.scope, protection.signal_id),
        ).fetchall()
        committed = sum((D(json.loads(row["payload"])["quantity"]) for row in rows), ZERO)
        return self.coordinator._actions(
            db, protection, protection.close(max(ZERO, quantity - committed))
        )

    def reconcile(
        self,
        observed: AccountObservation,
        time: datetime,
        *,
        max_account_age: timedelta,
        max_mark_age: timedelta,
        require_verified=True,
        reduction_models: dict[str, Callable[[Decimal], ReductionProjection | None]] | None = None,
    ):
        """Required freshness horizons belong to the caller's precommitted source policy.

        Reconciliation is not permission to enter: the durable minute risk overlay,
        signal deadline and market gates remain separate mandatory checks.
        """
        time = utc(time)
        if type(require_verified) is not bool:
            raise TypeError("Explicit quality requirement required")
        if any(
            not isinstance(x, timedelta) or x < timedelta(0)
            for x in (max_account_age, max_mark_age)
        ):
            raise ValueError("Explicit account and Mark freshness policies required")
        try:
            with self.journal.transaction() as db, localcontext(CONTEXT):
                return self._reconcile(
                    db,
                    observed,
                    time,
                    max_account_age,
                    max_mark_age,
                    require_verified,
                    reduction_models or {},
                )
        except (ReconciliationRequired, ValueError, ArithmeticError):
            # Failure must persist an entry pause even though the proof transaction rolls back.
            with self.journal.transaction() as db:
                self.coordinator._pause(db, "ACCOUNT_RECONCILIATION_FAILED", time)
            raise

    def _reconcile(self, db, observed, time, account_age, mark_age, verified, models):
        _, gate = read_tx(db, self.coordinator.gate_stream)
        watermark = gate.get("last_evidence_at")
        if observed.available_at > time or time - observed.event_time > account_age:
            raise ReconciliationRequired("Account observation unavailable or stale")
        if watermark is not None and observed.event_time < datetime.fromisoformat(watermark):
            raise ReconciliationRequired("Account observation predates known account evidence")
        if verified and observed.quality is not Quality.VERIFIED:
            raise ReconciliationRequired("Account evidence is not VERIFIED")
        _, state = read_tx(db, self.coordinator.ledger_stream)
        ledger = Ledger.restore(state)
        view = ledger.view(time)
        if view.cash != observed.cash:
            raise ReconciliationRequired("Observed cash does not match fill ledger")
        open_positions = {p.owner.position_id: p for p in view.positions if p.quantity > 0}
        if set(open_positions) != {p.position_id for p in observed.positions}:
            raise ReconciliationRequired(
                "Owned position set mismatch; do not touch foreign positions"
            )
        _, state = read_tx(db, self.coordinator.portfolio_stream)
        old = restore_portfolio(state)
        old_by_id = {p.position_id: p for p in old.exposures}
        equity = view.equity([p.mark for p in observed.positions], max_mark_age=mark_age)
        _, control = read_tx(db, "equity-control:" + self.scope)
        status = control["last_status"]
        if status is None or datetime.fromisoformat(status["time"]) != time.replace(
            second=0, microsecond=0
        ):
            raise ReconciliationRequired("Current minute equity risk sample required")
        risk_fraction = D(status["risk_fraction"])
        exposures, actions, reasons, newly_frozen = [], [], [], set()
        available = observed.free_collateral
        for p in observed.positions:
            balance = open_positions[p.position_id]
            _, payload = read_tx(db, self.coordinator._protection_stream(p.position_id))
            protection = Protection.restore(payload)
            if (
                p.quantity != balance.quantity
                or p.quantity != protection.remaining
                or p.mark.symbol != balance.owner.symbol
                or p.rules.symbol != balance.owner.symbol
            ):
                raise ReconciliationRequired("Observed quantity/symbol differs from owned position")
            if not protection.terminal or not protection.protected:
                raise ReconciliationRequired("Terminal entry and confirmed protection required")
            rules = p.rules
            if (
                rules.available_at > time
                or rules.effective_from > time
                or (rules.effective_to is not None and time >= rules.effective_to)
            ):
                raise ReconciliationRequired("Effective contract rules missing")
            prior = old_by_id.get(p.position_id)
            first = (
                prior is None
                or prior.pending
                or prior.initial_quantity != protection.entry_quantity
            )
            row = db.execute(
                "SELECT payload FROM intents WHERE scope=? AND signal_id=? AND purpose='ENTRY'",
                (self.scope, p.position_id),
            ).fetchone()
            if row is None:
                raise ReconciliationRequired("Missing original entry cost assumptions")
            quote = json.loads(row["payload"])["sizing"]["quote"]
            # Entry fees are already realized in cash. Keep only remaining exit,
            # stop-slip and funding commitments outside venue spendable balance.
            available -= p.quantity * (
                protection.initial_stop * D(quote["exit_fee_rate"])
                + protection.entry_vwap * D(quote["stop_slippage_fraction"])
                + protection.entry_vwap * D(quote["funding_rate_per_hour"]) * 72
            )
            if first:
                fees = sum((f.fee for f in protection.fills.values() if not f.reduce_only), ZERO)
                entry_fee = max(ZERO, fees / protection.entry_quantity)
                entry, stop = protection.entry_vwap, protection.initial_stop
                reserves = (
                    entry_fee
                    + stop * D(quote["exit_fee_rate"])
                    + entry * D(quote["stop_slippage_fraction"])
                    + entry * D(quote["funding_rate_per_hour"]) * 72
                )
                per_unit_risk = abs(entry - stop) + reserves
                original_risk = protection.entry_quantity * per_unit_risk
                shortfall = max(
                    ZERO, protection.side.sign * (entry - D(quote["arrival_side_price"]))
                )
                if (reserves + shortfall) / abs(entry - stop) > D("0.25"):
                    reasons.append(p.position_id + ":POST_FILL_COST_GATE")
                newly_frozen.add(p.position_id)
            else:
                original_risk = prior.initial_reserved_risk
            exposure = Exposure(
                p.position_id,
                balance.owner.symbol,
                balance.owner.side,
                protection.entry_quantity,
                p.quantity,
                original_risk,
                p.mark.price,
                p.initial_margin_commitment,
                False,
            )
            exposures.append(exposure)
            if first and (
                exposure.reserved_risk > risk_fraction * equity
                or exposure.reserved_risk < D("0.0025") * equity
                or exposure.notional > equity
                or p.initial_margin_commitment > D("0.20") * equity
            ):
                reasons.append(p.position_id + ":POST_FILL_POSITION_LIMIT")
            position = ResidualPosition(
                balance.owner.symbol,
                balance.owner.side,
                p.quantity,
                protection.entry_vwap,
                protection.initial_stop,
                p.isolated_collateral,
            )
            remedy = liquidation_remedy(
                position,
                rules,
                time,
                models.get(p.position_id, lambda q: None),
                require_verified=verified,
            )
            if remedy.reduce_only_quantity > 0:
                reasons.append(p.position_id + ":" + remedy.reason)
                actions.extend(self._close_uncovered(db, protection, remedy.reduce_only_quantity))
            save_tx(db, self.coordinator._protection_stream(p.position_id), protection.checkpoint())
        for prior in old.exposures:
            if prior.position_id in open_positions:
                continue
            _, payload = read_tx(db, self.coordinator._protection_stream(prior.position_id))
            protection = Protection.restore(payload)
            if protection.remaining == 0 and not protection.terminal:
                intent = db.execute(
                    "SELECT client_id,state,payload FROM intents WHERE scope=? AND signal_id=? "
                    "AND purpose='ENTRY'",
                    (self.scope, prior.position_id),
                ).fetchone()
                if intent is not None and intent["state"] == "PREPARED":
                    sizing = json.loads(intent["payload"])["sizing"]
                    if (
                        not prior.pending
                        or protection.fills
                        or protection.actions
                        or prior.initial_quantity != protection.requested_quantity
                        or prior.remaining_quantity != prior.initial_quantity
                        or D(sizing["quantity"]) != prior.initial_quantity
                        or D(sizing["reserved_loss"]) != prior.initial_reserved_risk
                        or D(sizing["initial_margin"]) != prior.initial_margin_commitment
                    ):
                        raise ReconciliationRequired(
                            "Unsent reservation ownership/economics mismatch"
                        )
                    _, metadata = self.journal.snapshot(
                        "entry-metadata:" + self.scope + ":" + prior.position_id
                    )
                    costs = sizing["costs"]
                    commitment = prior.initial_margin_commitment + prior.initial_quantity * sum(
                        (
                            D(costs[k])
                            for k in ("entry_fee", "exit_fee", "stop_slippage", "funding")
                        ),
                        ZERO,
                    )
                    current = Portfolio(equity, available, tuple(exposures))
                    timely = metadata is not None and (
                        datetime.fromisoformat(metadata["accepted_at"])
                        <= time
                        <= datetime.fromisoformat(metadata["order_deadline"])
                    )
                    capacity = (
                        current.slots < 3
                        and not any(x.symbol == prior.symbol for x in exposures)
                        and D("0.0025") * equity
                        <= prior.reserved_risk
                        <= current.budget(prior.side, reduced=risk_fraction == D("0.005"))
                        and prior.notional <= equity
                        and current.gross_notional + prior.notional <= 3 * equity
                        and prior.initial_margin_commitment <= D("0.20") * equity
                        and current.margin + prior.initial_margin_commitment <= D("0.60") * equity
                        and commitment <= available
                    )
                    if (
                        timely
                        and capacity
                        and status["entries_allowed"]
                        and not gate.get("safety_paused", False)
                        and not reasons
                    ):
                        # Keep accepted batch order and exact original quantity.
                        # Dispatch still rechecks current quote/book/clock limits.
                        exposures.append(prior)
                        available -= commitment
                        continue
                    db.execute(
                        "UPDATE intents SET state='CANCELED' WHERE client_id=?",
                        (intent["client_id"],),
                    )
                    Journal.append_tx(
                        db,
                        "cancel-unsent:" + intent["client_id"],
                        {"reason": "UNSENT_DEADLINE_OR_CAPACITY", "never_dispatched": True},
                    )
                    protection.entry_terminal()
                    save_tx(
                        db,
                        self.coordinator._protection_stream(prior.position_id),
                        protection.checkpoint(),
                    )
            if protection.remaining != 0 or not protection.terminal:
                raise ReconciliationRequired("Pending/closed position has unresolved IOC outcome")
        portfolio = Portfolio(equity, available, tuple(exposures))
        if available < 0:
            reasons.append("LOCAL_COLLATERAL_RESERVES_EXCEED_AVAILABLE")
        portfolio_breach = (
            portfolio.slots > 3
            or portfolio.reserved_risk > D("0.03") * equity
            or portfolio.gross_notional > 3 * equity
            or portfolio.margin > D("0.60") * equity
            or any(
                sum((p.reserved_risk for p in exposures if p.side is side), ZERO)
                > D("0.02") * equity
                for side in {p.side for p in exposures}
            )
        )
        if portfolio_breach and newly_frozen:
            for position_id in sorted(newly_frozen):
                reasons.append(position_id + ":POST_FILL_PORTFOLIO_LIMIT")
        # A residual solver for all portfolio constraints requires venue release/fee
        # projections. If that compliance cannot be proved, UD-09 requires full close.
        breached = {r.split(":", 1)[0] for r in reasons if ":POST_FILL_" in r}
        for position_id in sorted(breached):
            _, payload = read_tx(db, self.coordinator._protection_stream(position_id))
            protection = Protection.restore(payload)
            actions.extend(self._close_uncovered(db, protection, protection.remaining))
            save_tx(db, self.coordinator._protection_stream(position_id), protection.checkpoint())
        pending_exits = db.execute(
            "SELECT signal_id FROM intents WHERE scope=? AND purpose='EXIT_MARKET' "
            "AND state IN ('PREPARED','UNKNOWN','ACKNOWLEDGED')",
            (self.scope,),
        ).fetchall()
        for row in pending_exits:
            if row["signal_id"] in open_positions:
                reasons.append(row["signal_id"] + ":EXIT_OUTCOME_PENDING")
        safe = (
            not reasons
            and not gate.get("safety_paused", False)
            and equity > 0
            and status["entries_allowed"]
        )
        proof = {"observed": observed, "time": time, "portfolio": portfolio, "reasons": reasons}
        Journal.append_tx(db, "account-open:" + self.scope + ":" + digest(proof), proof)
        save_tx(db, self.coordinator.portfolio_stream, asdict(portfolio))
        save_tx(
            db,
            self.coordinator.gate_stream,
            {
                "ready": safe,
                "reason": "OPEN_RECONCILED" if safe else "COMPLIANCE_OR_SAFETY_PAUSE",
                "last_evidence_at": time,
                "safety_paused": gate.get("safety_paused", False),
            },
        )
        return ReconciledAccount(portfolio, safe, tuple(actions), tuple(reasons))
