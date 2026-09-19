"""Atomic offline event delivery into the shared accounting and exit cores.

There are no sockets, exchange clients, order senders or synthetic acknowledgments
here. Order outcomes are explicit input evidence, never inferred from a request.
"""

import json
from datetime import datetime

from pvb24.accounting.coordinator import AccountCoordinator, read_tx, save_tx
from pvb24.accounting.ledger import LedgerStore, ReconciliationRequired
from pvb24.accounting.reconciliation import OpenReconciler
from pvb24.accounting.risk_service import AccountRiskService
from pvb24.decimal_math import D
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, client_identity, digest
from pvb24.replay import codecs
from pvb24.replay.events import Delivery, Kind
from pvb24.state import Conflict, Journal
from pvb24.strategy.exits import Entry, Exits
from pvb24.strategy.signals import Indicators
from pvb24.types import Quality


class AccountReplay:
    def __init__(self, journal: Journal, scope: str, quality: Quality):
        if not scope or not isinstance(quality, Quality):
            raise ValueError("Explicit scope and replay quality required")
        self.journal, self.scope, self.quality = journal, scope, quality
        self.coordinator = AccountCoordinator(journal, scope)
        self.risk = AccountRiskService(journal, scope)
        self.stream = "replay-account:" + scope
        with journal.transaction() as db:
            row = db.execute(
                "SELECT payload FROM snapshots WHERE stream=?", (self.stream,)
            ).fetchone()
            if row is None:
                _, ledger = LedgerStore(journal, scope).read()
                if ledger.fills or ledger.funding:
                    raise Conflict("Freeze replay quality before account cashflows")
                save_tx(
                    db,
                    self.stream,
                    {"quality": quality, "last_time": None, "ambiguous_event_count": 0},
                )
            elif json.loads(row["payload"])["quality"] != quality:
                raise Conflict("Replay quality cannot change during an account run")

    def freeze_exit_channels(self, signal_id, high, low):
        """Freeze original signal channels before the first actual fill."""
        with self.journal.transaction() as db:
            _, raw = read_tx(db, self.coordinator._protection_stream(signal_id))
            p = Protection.restore(raw)
            if p.fills:
                raise Conflict("Cannot change signal channels after observing fills")
            from pvb24.decimal_math import require_decimal

            require_decimal(high, positive=True)
            require_decimal(low, positive=True)
            if low > high:
                raise ValueError("Invalid frozen channel")
            stream = "replay-entry-terms:" + self.scope + ":" + signal_id
            if db.execute("SELECT 1 FROM snapshots WHERE stream=?", (stream,)).fetchone():
                raise Conflict("Original channels already frozen")
            save_tx(db, stream, {"channel_high": high, "channel_low": low})

    def _exit_stream(self, signal_id):
        return "exits:" + self.scope + ":" + signal_id

    def _initialize_exit(self, db, position):
        if not position.terminal or position.remaining <= 0:
            return
        stream = self._exit_stream(position.signal_id)
        if db.execute("SELECT 1 FROM snapshots WHERE stream=?", (stream,)).fetchone():
            return
        _, terms = read_tx(db, "replay-entry-terms:" + self.scope + ":" + position.signal_id)
        exits = Exits(
            Entry(
                position.signal_id,
                position.symbol,
                position.side,
                position.first_fill_time,
                position.entry_vwap,
                position.initial_stop,
                D(terms["channel_high"]),
                D(terms["channel_low"]),
                position.tick,
            )
        )
        save_tx(db, stream, exits.checkpoint())

    def __call__(self, delivery: Delivery):
        event = delivery.event
        if self.quality is Quality.VERIFIED and event.quality is not Quality.VERIFIED:
            raise ValueError("Cannot promote preliminary account events")
        key = "replay-delivery:" + self.scope + ":" + event.event_id
        evidence_hash = digest(delivery)
        try:
            with self.journal.transaction() as db:
                previous = db.execute(
                    "SELECT payload FROM events WHERE event_id=?", (key,)
                ).fetchone()
                if previous:
                    receipt = json.loads(previous["payload"])
                    if receipt["evidence_hash"] != evidence_hash:
                        raise Conflict("Changed replay delivery")
                    return receipt["output"]
                _, state = read_tx(db, self.stream)
                if state["last_time"] is not None and event.available_at < datetime.fromisoformat(
                    state["last_time"]
                ):
                    raise Conflict("Cannot backdate account replay")
                output = self._apply(db, event)
                # Store exactly the value returned, so restart produces the same trace.
                output = json.loads(canonical(output))
                Journal.append_tx(db, key, {"evidence_hash": evidence_hash, "output": output})
                state["last_time"] = event.available_at
                state["ambiguous_event_count"] += delivery.ambiguous_event_count
                save_tx(db, self.stream, state)
                return output
        except Exception:
            # Outer rollback cannot leave a committed cash/protection half-update.
            # Persist a separate pause and let the scheduler stop for recovery.
            with self.journal.transaction() as db:
                self.coordinator._pause(db, "REPLAY_DELIVERY_FAILED", event.available_at)
            raise

    @staticmethod
    def _timing(event, occurred, available):
        if occurred != event.event_time or available != event.available_at:
            raise ValueError("Payload timing differs from replay envelope")

    def _apply(self, db, event):
        payload, now = event.payload, event.available_at
        if event.kind in (
            Kind.LIQUIDATION,
            Kind.PROTECTIVE_FILL,
            Kind.REDUCE_FILL,
            Kind.ENTRY_FILL,
        ):
            record = codecs.fill_record(payload)
            self._timing(event, record.fill.event_time, record.fill.received_at)
            if record.exchange_sequence != event.exchange_sequence:
                raise ValueError("Fill sequence differs from replay envelope")
            if record.liquidation != (event.kind is Kind.LIQUIDATION):
                raise ValueError("Liquidation identity differs from event priority")
            if record.fill.reduce_only != (event.kind is not Kind.ENTRY_FILL):
                raise ValueError("Fill priority incompatible with reduce-only flag")
            return {"action_ids": self.coordinator.confirmed_fill(record)}
        if event.kind is Kind.FUNDING:
            payment = codecs.funding(payload)
            self._timing(event, payment.settlement_time, payment.available_at)
            return {"ingested": self.coordinator.confirmed_funding(payment)}
        if event.kind is Kind.OBSERVATION:
            if payload["type"] == "MARK":
                mark = codecs.mark(payload["record"])
                self._timing(event, mark.timing.event_time, mark.timing.available_at)
                stream = "replay-marks:" + self.scope
                _, state = self.journal.snapshot(stream)
                rows = [] if state is None else state["rows"]
                # Keep late/revised observations; Mark equity handles as-of conflicts.
                save_tx(db, stream, {"rows": rows + [payload["record"]]})
                return {"mark": mark}
            if payload["type"] == "HOURLY_LAST":
                candle = codecs.candle(payload["record"])
                self._timing(event, candle.timing.event_time, candle.timing.available_at)
                stream = "indicators:" + self.scope + ":" + candle.symbol
                _, state = self.journal.snapshot(stream)
                core = Indicators(candle.symbol) if state is None else Indicators.restore(state)
                frame = core.push(candle, now)
                save_tx(db, stream, core.checkpoint())
                return {"frame": frame}
            raise ValueError("Unsupported replay observation")
        if event.kind is Kind.ACCOUNT_RISK:
            if event.event_time != now or now.second or now.microsecond:
                raise ValueError("Risk samples must occur on the current minute grid")
            _, rows = self.journal.snapshot("replay-marks:" + self.scope)
            marks = [] if rows is None else [codecs.mark(r) for r in rows["rows"]]
            status, ids = self.risk.sample(now, marks)
            return {"status": status, "action_ids": ids}
        if event.kind is Kind.ORDER_OUTCOME:
            return self._outcome(db, event)
        if event.kind in (Kind.EXIT_DECISION, Kind.TRAILING):
            return self._exit(db, event)
        raise ValueError("Unsupported account replay event; entry decisions require signal adapter")

    def _outcome(self, db, event):
        raw, now = event.payload, event.available_at
        signal_id = raw["position_id"]
        operation = raw["operation"]

        def apply(position):
            if operation == "ENTRY_TERMINAL":
                return position.entry_terminal()
            if operation == "STOP_ACK":
                return position.confirm_stop(
                    raw["sequence"],
                    D(raw["quantity"]),
                    D(raw["stop"]),
                    reduce_only=raw["reduce_only"],
                    reference=raw["reference"],
                )
            if operation == "EXIT_TERMINAL":
                return ()
            raise ValueError("Unsupported order outcome")

        if operation == "ENTRY_TERMINAL":
            purpose, sequence, outcome = "ENTRY", 0, raw["outcome"]
            if outcome not in ("FILLED", "CANCELED", "REJECTED"):
                raise ValueError("Terminal entry outcome required")
        elif operation == "STOP_ACK":
            purpose, sequence, outcome = "PROTECT", raw["sequence"], "ACKNOWLEDGED"
        elif operation == "EXIT_TERMINAL":
            purpose, sequence, outcome = "EXIT_MARKET", raw["sequence"], raw["outcome"]
            if outcome not in ("FILLED", "CANCELED", "REJECTED"):
                raise ValueError("Terminal exit outcome required")
        else:
            raise ValueError("Unsupported order outcome")
        _, _, client_id = client_identity(self.scope, signal_id, purpose, sequence)
        _, protection_state = read_tx(db, self.coordinator._protection_stream(signal_id))
        owned = Protection.restore(protection_state)
        if operation == "ENTRY_TERMINAL" and outcome == "FILLED":
            if owned.entry_quantity != owned.requested_quantity:
                raise ReconciliationRequired("Full entry outcome requires all confirmed fills")
        if operation == "EXIT_TERMINAL":
            action = owned.actions.get(sequence)
            if action is None or action.purpose != "EXIT_MARKET":
                raise Conflict("Unknown owned exit sequence")
            from decimal import localcontext

            from pvb24.decimal_math import CONTEXT, ZERO

            with localcontext(CONTEXT):
                confirmed = sum(
                    (
                        f.quantity
                        for f in owned.fills.values()
                        if f.reduce_only and f.order_id == raw["venue_order_id"]
                    ),
                    ZERO,
                )
            if confirmed != D(raw["cumulative_fill_quantity"]):
                raise ReconciliationRequired("Terminal exit has missing fill evidence")
            if outcome == "FILLED" and confirmed != action.quantity:
                raise ReconciliationRequired("Full exit outcome requires all confirmed fills")
        self.journal.reconcile_intent(client_id, outcome, raw)
        ids = self.coordinator.protection_event(signal_id, event.event_id, raw, apply, now)
        _, state = read_tx(db, self.coordinator._protection_stream(signal_id))
        position = Protection.restore(state)
        self._initialize_exit(db, position)
        if operation == "STOP_ACK":
            stream = self._exit_stream(signal_id)
            _, state = self.journal.snapshot(stream)
            if state is not None:
                exits = Exits.restore(state)
                if (
                    raw["sequence"] in position.confirmed_stops - position.canceled_stops
                    and D(raw["stop"]) == exits.proposed_stop
                    and D(raw["quantity"]) >= position.remaining
                ):
                    exits.acknowledge_stop(D(raw["stop"]), now)
                    save_tx(db, stream, exits.checkpoint())
        if operation == "EXIT_TERMINAL" and position.remaining > 0:
            _, state = self.journal.snapshot(self._exit_stream(signal_id))
            if state is not None and Exits.restore(state).exit_decision is not None:
                ids += OpenReconciler(self.journal, self.scope)._close_uncovered(
                    db, position, position.remaining
                )
                save_tx(db, self.coordinator._protection_stream(signal_id), position.checkpoint())
        return {"action_ids": ids}

    def _exit(self, db, event):
        raw, now = event.payload, event.available_at
        position_id = raw["position_id"]
        _, state = read_tx(db, self.coordinator._protection_stream(position_id))
        position = Protection.restore(state)
        if position.remaining == 0:
            return {"reason": "ALREADY_FLAT", "action_ids": ()}
        stream = self._exit_stream(position_id)
        _, state = read_tx(db, stream)
        exits = Exits.restore(state)
        if (
            position.entry_vwap != exits.entry.vwap
            or position.initial_stop != exits.entry.initial_stop
        ):
            raise ReconciliationRequired("Late entry economics require exit-state reconciliation")
        if event.kind is Kind.TRAILING:
            decision = exits.last_decision
            if decision is None or decision.decided_at != now:
                raise ReconciliationRequired("Current close decision required before trailing")
            actions = ()
            if decision.proposed_stop is not None and decision.reason is None:
                actions = position.tighten_stop(decision.proposed_stop, D(raw["last_price"]))
        else:
            if raw["type"] == "TIMER":
                decision = exits.timer(now)
            elif raw["type"] == "HOURLY_CLOSE":
                _, state = read_tx(db, "indicators:" + self.scope + ":" + position.symbol)
                frame = Indicators.restore(state).last_frame
                if (
                    frame is None
                    or frame.candle.timing.interval_end != event.event_time
                    or frame.atr_current is None
                ):
                    raise ReconciliationRequired("Current completed ATR/candle required")
                decision = exits.push(frame.candle, frame.atr_current, now, D(raw["last_price"]))
            else:
                raise ValueError("Unsupported close decision")
            actions = ()
            if decision is not None and decision.reason is not None:
                # Reuse a stable decision ID across timer/close callbacks.
                if Journal.append_tx(
                    db, "exit-decision:" + self.scope + ":" + decision.decision_id, decision
                ):
                    ids = OpenReconciler(self.journal, self.scope)._close_uncovered(
                        db, position, position.remaining
                    )
                    # These bounded actions were already persisted by the coordinator.
                    save_tx(db, stream, exits.checkpoint())
                    save_tx(
                        db, self.coordinator._protection_stream(position_id), position.checkpoint()
                    )
                    if ids:
                        self.coordinator._pause(db, "EXIT_OR_TRAILING_RECONCILIATION_REQUIRED", now)
                    return {"decision": decision, "action_ids": ids}
        ids = self.coordinator._actions(db, position, actions)
        save_tx(db, stream, exits.checkpoint())
        save_tx(db, self.coordinator._protection_stream(position_id), position.checkpoint())
        if ids:
            self.coordinator._pause(db, "EXIT_OR_TRAILING_RECONCILIATION_REQUIRED", now)
        return {"decision": decision, "action_ids": ids}
