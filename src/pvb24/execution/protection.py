"""Confirmed-fill protection state machine; requests are not acknowledgements."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.decimal_math import CONTEXT, ZERO, D, quantize_step, require_decimal
from pvb24.ids import canonical
from pvb24.state import Conflict, Journal
from pvb24.types import Fill, Side, SymbolState, utc


@dataclass(frozen=True)
class Action:
    sequence: int
    purpose: str
    quantity: Decimal
    stop: Decimal | None = None
    target_sequence: int | None = None
    reduce_only: bool = True
    stop_reference: str = "CONTRACT_PRICE"


class Protection:
    def __init__(
        self,
        signal_id: str,
        symbol: str,
        side: Side,
        requested_quantity: Decimal,
        atr_previous: Decimal,
        tick: Decimal,
    ):
        if not signal_id or not symbol or not isinstance(side, Side):
            raise ValueError("Position identity required")
        for value in (requested_quantity, atr_previous, tick):
            require_decimal(value, positive=True)
        self.signal_id, self.symbol, self.side = signal_id, symbol, side
        self.requested_quantity, self.atr_previous, self.tick = (
            requested_quantity,
            atr_previous,
            tick,
        )
        self.fills = {}
        self.actions = {}
        self.confirmed_stops = set()
        self.canceled_stops = set()
        self.terminal = False
        self.safety_paused = False
        self.initial_stop = None
        self.effective_stop = None
        self.first_fill_time = None
        self.full_exit_time = None
        self.sequence = 0

    @property
    def entry_quantity(self):
        with localcontext(CONTEXT):
            return sum((f.quantity for f in self.fills.values() if not f.reduce_only), ZERO)

    @property
    def remaining(self):
        with localcontext(CONTEXT):
            return self.entry_quantity - sum(
                (f.quantity for f in self.fills.values() if f.reduce_only), ZERO
            )

    @property
    def entry_vwap(self):
        with localcontext(CONTEXT):
            quantity = self.entry_quantity
            return (
                sum((f.quantity * f.price for f in self.fills.values() if not f.reduce_only), ZERO)
                / quantity
                if quantity
                else None
            )

    @property
    def initial_price_risk(self):
        with localcontext(CONTEXT):
            return (
                abs(self.entry_vwap - self.initial_stop) if self.initial_stop is not None else None
            )

    @property
    def state(self):
        if self.full_exit_time is not None and self.remaining == 0:
            return SymbolState.COOLDOWN
        if self.remaining > 0:
            if any(a.purpose == "EXIT_MARKET" for a in self.actions.values()):
                return SymbolState.EXIT_PENDING
            covered = any(
                self.actions[i].quantity >= self.remaining
                for i in self.confirmed_stops - self.canceled_stops
            )
            return SymbolState.OPEN if covered else SymbolState.ENTRY_PENDING
        return SymbolState.READY if self.terminal else SymbolState.ENTRY_PENDING

    @property
    def protected(self):
        return self.remaining > 0 and any(
            self.actions[i].quantity >= self.remaining
            and self.actions[i].stop == self.effective_stop
            for i in self.confirmed_stops - self.canceled_stops
        )

    def cooldown_finished(self, now: datetime):
        return self.full_exit_time is None or utc(now) >= self.full_exit_time + timedelta(hours=6)

    def _action(self, purpose, quantity, stop=None, target_sequence=None):
        self.sequence += 1
        action = Action(self.sequence, purpose, quantity, stop, target_sequence)
        self.actions[action.sequence] = action
        return action

    def close(self, quantity: Decimal | None = None):
        """All exits are reduce-only and bounded by the known remaining position."""
        if quantity is not None:
            require_decimal(quantity, nonnegative=True)
        remaining = max(ZERO, self.remaining)
        amount = remaining if quantity is None else min(remaining, quantity)
        return (self._action("EXIT_MARKET", amount),) if amount > 0 else ()

    def protection_failed(self):
        self.safety_paused = True
        return self.close()

    def fill(self, fill: Fill):
        if fill.position_id != self.signal_id or fill.symbol != self.symbol:
            raise Conflict("Fill belongs to a different position")
        expected_side = (
            (Side.SHORT if self.side is Side.LONG else Side.LONG) if fill.reduce_only else self.side
        )
        if fill.side is not expected_side:
            raise Conflict("Fill side incompatible with position ownership")
        if fill.fill_id in self.fills:
            if self.fills[fill.fill_id] != fill:
                raise Conflict("Fill identity reused with different economics")
            return ()
        was_closed = self.full_exit_time is not None
        self.fills[fill.fill_id] = fill  # retain authoritative evidence even in anomalies
        with localcontext(CONTEXT):
            if self.remaining < 0:
                self.safety_paused = True
                return (self._action("RECONCILE", ZERO),)
            if not fill.reduce_only:
                self.first_fill_time = min(
                    f.event_time for f in self.fills.values() if not f.reduce_only
                )
                self.initial_stop = quantize_step(
                    self.entry_vwap - self.side.sign * 2 * self.atr_previous,
                    self.tick,
                    up=self.side is Side.SHORT,
                )
                if self.effective_stop is None:
                    self.effective_stop = self.initial_stop
                else:
                    chooser = max if self.side is Side.LONG else min
                    self.effective_stop = chooser(self.effective_stop, self.initial_stop)
                if (
                    self.initial_stop <= 0
                    or self.entry_quantity > self.requested_quantity
                    or was_closed
                ):
                    return self.protection_failed()
            if self.remaining == 0 and self.entry_quantity > 0:
                self.full_exit_time = max(
                    f.event_time for f in self.fills.values() if f.reduce_only
                )
                return tuple(
                    self._action("CANCEL_PROTECTION", ZERO, target_sequence=i)
                    for i in sorted(self.confirmed_stops - self.canceled_stops)
                )
            if self.safety_paused:
                return self.close()
            if self.remaining > 0:
                return (self._action("PROTECT", self.remaining, self.effective_stop),)
        return ()

    def entry_terminal(self):
        # A cancel acknowledgement never erases an authoritative late fill.
        self.terminal = True
        return ()

    def tighten_stop(self, stop: Decimal, last_price: Decimal):
        """Apply a causal exit-engine proposal; confirmed protection is still separate."""
        require_decimal(stop, positive=True)
        require_decimal(last_price, positive=True)
        if self.remaining <= 0 or self.effective_stop is None:
            raise Conflict("Cannot trail a position without confirmed entry quantity")
        if quantize_step(stop, self.tick) != stop:
            raise ValueError("Trailing proposal must already satisfy tick rounding")
        with localcontext(CONTEXT):
            if self.side.sign * (stop - self.effective_stop) < 0:
                raise ValueError("Protective stop cannot widen")
            if self.side.sign * (last_price - stop) <= 0:
                return self.close()
            if stop == self.effective_stop:
                return ()
            self.effective_stop = stop
            return (self._action("PROTECT", self.remaining, stop),)

    def confirm_stop(
        self, sequence: int, quantity: Decimal, stop: Decimal, *, reduce_only: bool, reference: str
    ):
        action = self.actions.get(sequence)
        if action is None or action.purpose != "PROTECT":
            raise Conflict("Unknown protective order")
        require_decimal(quantity, positive=True)
        require_decimal(stop, positive=True)
        if (
            quantity != action.quantity
            or stop != action.stop
            or reduce_only is not True
            or reference != "CONTRACT_PRICE"
        ):
            return self.protection_failed()
        if sequence in self.confirmed_stops:
            return ()
        self.confirmed_stops.add(sequence)
        if self.remaining == 0:
            return (self._action("CANCEL_PROTECTION", ZERO, target_sequence=sequence),)
        if self.protected and (
            action.quantity < self.remaining or action.stop != self.effective_stop
        ):
            return (self._action("CANCEL_PROTECTION", ZERO, target_sequence=sequence),)
        if not self.protected:
            return ()  # earlier partial protection cannot masquerade as full coverage
        # New protection is proven active before requesting removal of old protection.
        return tuple(
            self._action("CANCEL_PROTECTION", ZERO, target_sequence=i)
            for i in sorted(self.confirmed_stops - self.canceled_stops - {sequence})
            if self.actions[sequence].quantity >= self.remaining
            and self.actions[sequence].stop == self.effective_stop
        )

    def confirm_cancel(self, sequence: int):
        if sequence not in self.actions or self.actions[sequence].purpose != "PROTECT":
            raise Conflict("Unknown protective order cancellation")
        self.canceled_stops.add(sequence)
        if self.remaining > 0 and not self.protected:
            return self.protection_failed()
        return ()

    def checkpoint(self):
        return dict(
            signal_id=self.signal_id,
            symbol=self.symbol,
            side=self.side,
            requested_quantity=self.requested_quantity,
            atr_previous=self.atr_previous,
            tick=self.tick,
            fills=[asdict(x) for x in self.fills.values()],
            actions=[asdict(x) for x in self.actions.values()],
            confirmed_stops=sorted(self.confirmed_stops),
            canceled_stops=sorted(self.canceled_stops),
            terminal=self.terminal,
            safety_paused=self.safety_paused,
            initial_stop=self.initial_stop,
            effective_stop=self.effective_stop,
            first_fill_time=self.first_fill_time,
            full_exit_time=self.full_exit_time,
            sequence=self.sequence,
        )

    @classmethod
    def restore(cls, payload):
        # Accept canonical serialized state, not binary-float coercion.
        p = payload
        result = cls(
            p["signal_id"],
            p["symbol"],
            Side(p["side"]),
            D(p["requested_quantity"]),
            D(p["atr_previous"]),
            D(p["tick"]),
        )
        for item in p["fills"]:
            f = dict(item)
            f["side"] = Side(f["side"])
            for key in ("quantity", "price", "fee"):
                f[key] = D(f[key])
            for key in ("event_time", "received_at"):
                f[key] = datetime.fromisoformat(f[key])
            result.fills[f["fill_id"]] = Fill(**f)
        for item in p["actions"]:
            a = dict(item)
            a["quantity"] = D(a["quantity"])
            a["stop"] = None if a["stop"] is None else D(a["stop"])
            result.actions[a["sequence"]] = Action(**a)
        for key in ("confirmed_stops", "canceled_stops"):
            setattr(result, key, set(p[key]))
        for key in ("terminal", "safety_paused", "sequence"):
            setattr(result, key, p[key])
        for key in ("initial_stop", "effective_stop"):
            setattr(result, key, None if p[key] is None else D(p[key]))
        for key in ("first_fill_time", "full_exit_time"):
            setattr(result, key, None if p[key] is None else datetime.fromisoformat(p[key]))
        return result


class ProtectionStore:
    """Persist input evidence, resulting state and action intents in one transaction.

    The operation callback is pure/local. Sending orders inside it is prohibited.
    The later Freqtrade executor claims committed intents through Journal.
    """

    def __init__(self, journal: Journal, scope: str):
        self.journal, self.scope = journal, scope

    def initialize(self, state: Protection):
        return self.journal.checkpoint(
            "protection:" + self.scope + ":" + state.signal_id,
            0,
            state.checkpoint(),
            "position:" + self.scope + ":" + state.signal_id,
        )

    def apply(self, signal_id: str, event_id: str, evidence, operation):
        stream = "protection:" + self.scope + ":" + signal_id
        with self.journal.transaction() as db:
            row = db.execute("SELECT * FROM snapshots WHERE stream=?", (stream,)).fetchone()
            if row is None:
                raise Conflict("Unknown protection state")
            if not Journal.append_tx(
                db,
                "protection-event:" + self.scope + ":" + event_id,
                {"signal_id": signal_id, "evidence": evidence},
            ):
                return ()
            state = Protection.restore(json.loads(row["payload"]))
            actions = operation(state)
            ids = []
            for action in actions:
                cid, _ = Journal.prepare_intent_tx(
                    db, self.scope, signal_id, action.purpose, asdict(action), action.sequence
                )
                ids.append(cid)
            db.execute(
                "UPDATE snapshots SET version=?,payload=? WHERE stream=?",
                (row["version"] + 1, canonical(state.checkpoint()), stream),
            )
            return tuple(ids)
