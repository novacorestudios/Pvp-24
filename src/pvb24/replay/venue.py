"""PRELIMINARY offline venue emulator; never imports an exchange client.

Synthetic outcomes, dispatch claim, shared-core updates and receipts commit
atomically because no external side effect exists. UNKNOWN intents without a
matching emulator receipt are reconciliation-only, including after restart.
"""

import json
from dataclasses import asdict
from datetime import datetime
from decimal import localcontext

from pvb24.accounting.coordinator import read_tx, save_tx
from pvb24.accounting.ledger import FillRecord
from pvb24.decimal_math import CONTEXT, D, quantize_step, require_decimal
from pvb24.execution.market import EntryBounds, preliminary_proxy
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, digest
from pvb24.replay.account import AccountReplay
from pvb24.replay.events import Delivery, Event, Kind
from pvb24.replay.preliminary import FrozenEntry, MinuteOpen, entry_at_open
from pvb24.state import Conflict, Journal
from pvb24.types import Fill, Quality, Side, utc


class PreliminaryVenue:
    def __init__(self, journal: Journal, scope: str):
        self.journal, self.scope = journal, scope
        self.runtime = AccountReplay(journal, scope, Quality.PRELIMINARY)
        self.coordinator = self.runtime.coordinator

    def _intent(self, db, client_id, purpose):
        row = db.execute(
            "SELECT * FROM intents WHERE client_id=? AND scope=?", (client_id, self.scope)
        ).fetchone()
        if row is None or row["purpose"] != purpose:
            raise Conflict("Unknown owned intent or wrong emulator operation")
        return dict(row), json.loads(row["payload"])

    def freeze_entry(self, client_id, *, sigma, available_at):
        """Fix proxy inputs at the original decision, never from the future open."""
        require_decimal(sigma, nonnegative=True)
        with self.journal.transaction() as db:
            row, payload = self._intent(db, client_id, "ENTRY")
            if row["state"] != "PREPARED":
                raise Conflict("Freeze emulator inputs before dispatch")
            _, metadata = read_tx(db, "entry-metadata:" + self.scope + ":" + row["signal_id"])
            bounds = dict(metadata["bounds"])
            bounds["side"] = Side(bounds["side"])
            bounds["signal_time"] = datetime.fromisoformat(bounds["signal_time"])
            for key in ("signal_close", "channel", "atr_previous", "tick"):
                bounds[key] = D(bounds[key])
            request = FrozenEntry(
                EntryBounds(**bounds),
                datetime.fromisoformat(metadata["accepted_at"]),
                D(payload["sizing"]["quantity"]),
                sigma,
                D(metadata["source"]["recent_quote_volume"]),
                utc(available_at),
            )
            stream = "sim-entry:" + self.scope + ":" + client_id
            _, previous = self.journal.snapshot(stream)
            if previous is not None:
                if canonical(previous) != canonical(asdict(request)):
                    raise Conflict("Simulation inputs already frozen")
                return request
            Journal.append_tx(db, "sim-freeze:" + self.scope + ":" + client_id, request)
            save_tx(db, stream, asdict(request))
            return request

    @staticmethod
    def _restore_request(raw):
        values = dict(raw)
        bounds = dict(values["bounds"])
        bounds["side"] = Side(bounds["side"])
        bounds["signal_time"] = datetime.fromisoformat(bounds["signal_time"])
        for key in ("signal_close", "channel", "atr_previous", "tick"):
            bounds[key] = D(bounds[key])
        values["bounds"] = EntryBounds(**bounds)
        for key in ("decision_time", "inputs_available_at"):
            values[key] = datetime.fromisoformat(values[key])
        for key in ("quantity", "sigma", "recent_quote_volume"):
            values[key] = D(values[key])
        return FrozenEntry(**values)

    def _deliver(self, event_id, kind, payload, occurred, available):
        event = Event(
            event_id,
            kind,
            occurred,
            available,
            "PVB24_PRELIMINARY_EMULATOR",
            Quality.PRELIMINARY,
            canonical(payload),
        )
        return self.runtime(Delivery(event, "CONSERVATIVE_PRIORITY", 0))

    def _receipt(self, db, client_id, evidence):
        row = db.execute(
            "SELECT payload FROM events WHERE event_id=?",
            ("sim-result:" + self.scope + ":" + client_id,),
        ).fetchone()
        if row is None:
            return None
        result = json.loads(row["payload"])
        if result["evidence_hash"] != digest(evidence):
            raise Conflict("Synthetic order already resolved with different evidence")
        return result["output"]

    def _save(self, db, client_id, evidence, output):
        output = json.loads(canonical(output))
        Journal.append_tx(
            db,
            "sim-result:" + self.scope + ":" + client_id,
            {"evidence_hash": digest(evidence), "evidence": evidence, "output": output},
        )
        return output

    def _clock(self, db, now):
        _, state = read_tx(db, "replay-account:" + self.scope)
        if state["last_time"] is not None and datetime.fromisoformat(state["last_time"]) > now:
            raise Conflict("Cannot backdate synthetic execution")

    def execute_entry(self, client_id: str, opening: MinuteOpen):
        now = opening.available_at
        with self.journal.transaction() as db:
            previous = self._receipt(db, client_id, opening)
            if previous is not None:
                return previous
            row, payload = self._intent(db, client_id, "ENTRY")
            if row["state"] != "PREPARED":
                raise Conflict("Unknown dispatch outcome requires reconciliation")
            self._clock(db, now)
            _, raw = read_tx(db, "sim-entry:" + self.scope + ":" + client_id)
            request = self._restore_request(raw)
            result = entry_at_open(request, opening, now)
            _, control = read_tx(db, "equity-control:" + self.scope)
            status = control["last_status"]
            current = status is not None and datetime.fromisoformat(status["time"]) == now.replace(
                second=0, microsecond=0
            )
            _, gate = read_tx(db, self.coordinator.gate_stream)
            ready = current and status["entries_allowed"] and gate["ready"]
            if not ready or result.proxy is None:
                reason = result.reason if ready else "ACCOUNT_OR_RISK_GATE"
                db.execute("UPDATE intents SET state='CANCELED' WHERE client_id=?", (client_id,))
                Journal.append_tx(
                    db, "cancel-unsent:" + client_id, {"reason": reason, "never_dispatched": True}
                )
                ids = self.coordinator.protection_event(
                    row["signal_id"],
                    "sim-cancel:" + client_id,
                    {"never_dispatched": True, "reason": reason},
                    lambda p: p.entry_terminal(),
                    now,
                )
                return self._save(
                    db, client_id, opening, {"reason": reason, "action_ids": ids, "fill": None}
                )
            if not self.journal.claim_dispatch(client_id):
                raise Conflict("Entry dispatch claim blocked")
            with localcontext(CONTEXT):
                fee = (
                    request.quantity
                    * result.proxy.price
                    * D(payload["sizing"]["quote"]["entry_fee_rate"])
                )
            fill = Fill(
                "sim-fill:" + client_id,
                "sim-order:" + client_id,
                row["signal_id"],
                request.bounds.symbol,
                request.bounds.side,
                request.quantity,
                result.proxy.price,
                fee,
                opening.time,
                now,
            )
            result_fill = self._deliver(
                fill.fill_id, Kind.ENTRY_FILL, FillRecord(fill), fill.event_time, now
            )
            self._deliver(
                "sim-terminal:" + client_id,
                Kind.ORDER_OUTCOME,
                {
                    "position_id": row["signal_id"],
                    "operation": "ENTRY_TERMINAL",
                    "outcome": "FILLED",
                },
                now,
                now,
            )
            return self._save(
                db,
                client_id,
                opening,
                {
                    "reason": "MODELED_FULL_FILL",
                    "fill": fill,
                    "action_ids": result_fill["action_ids"],
                    "quality": Quality.PRELIMINARY,
                    "unverified": result.unverified,
                },
            )

    def acknowledge_protection(self, client_id: str, now: datetime):
        now = utc(now)
        evidence = {"type": "SYNTHETIC_STOP_ACK", "time": now}
        with self.journal.transaction() as db:
            previous = self._receipt(db, client_id, evidence)
            if previous is not None:
                return previous
            row, payload = self._intent(db, client_id, "PROTECT")
            self._clock(db, now)
            if not self.journal.claim_dispatch(client_id):
                raise Conflict("Unknown protection dispatch requires reconciliation")
            result = self._deliver(
                "sim-stop-ack:" + client_id,
                Kind.ORDER_OUTCOME,
                {
                    "position_id": row["signal_id"],
                    "operation": "STOP_ACK",
                    "sequence": payload["sequence"],
                    "quantity": payload["quantity"],
                    "stop": payload["stop"],
                    "reduce_only": payload["reduce_only"],
                    "reference": payload["stop_reference"],
                },
                now,
                now,
            )
            return self._save(db, client_id, evidence, result)

    def execute_exit(
        self,
        client_id: str,
        opening: MinuteOpen,
        *,
        sigma,
        recent_quote_volume,
        inputs_available_at,
    ):
        """Use an executable minute-open reference, not an assumed stop-trigger fill."""
        now = opening.available_at
        require_decimal(sigma, nonnegative=True)
        require_decimal(recent_quote_volume, positive=True)
        if utc(inputs_available_at) > opening.time:
            raise ValueError("Exit proxy inputs include future information")
        evidence = {
            "opening": opening,
            "sigma": sigma,
            "volume": recent_quote_volume,
            "inputs_available_at": inputs_available_at,
        }
        with self.journal.transaction() as db:
            previous = self._receipt(db, client_id, evidence)
            if previous is not None:
                return previous
            row, action = self._intent(db, client_id, "EXIT_MARKET")
            self._clock(db, opening.time)
            _, raw = read_tx(db, self.coordinator._protection_stream(row["signal_id"]))
            position = Protection.restore(raw)
            if opening.symbol != position.symbol:
                raise ValueError("Exit price belongs to a different symbol")
            if not self.journal.claim_dispatch(client_id):
                raise Conflict("Unknown exit dispatch requires reconciliation")
            quantity = min(D(action["quantity"]), max(D(0), position.remaining))
            side = Side.SHORT if position.side is Side.LONG else Side.LONG
            fill, ids = None, []
            if quantity > 0:
                proxy = preliminary_proxy(opening.price, quantity, side, sigma, recent_quote_volume)
                price = quantize_step(proxy.price, position.tick, up=side is Side.LONG)
                entry = db.execute(
                    "SELECT payload FROM intents WHERE scope=? AND signal_id=? AND purpose='ENTRY'",
                    (self.scope, position.signal_id),
                ).fetchone()
                fee_rate = D(json.loads(entry["payload"])["sizing"]["quote"]["exit_fee_rate"])
                with localcontext(CONTEXT):
                    fee = quantity * price * fee_rate
                fill = Fill(
                    "sim-fill:" + client_id,
                    "sim-order:" + client_id,
                    position.signal_id,
                    position.symbol,
                    side,
                    quantity,
                    price,
                    fee,
                    opening.time,
                    now,
                    True,
                )
                ids = self._deliver(
                    fill.fill_id, Kind.REDUCE_FILL, FillRecord(fill), opening.time, now
                )["action_ids"]
            terminal = self._deliver(
                "sim-terminal:" + client_id,
                Kind.ORDER_OUTCOME,
                {
                    "position_id": position.signal_id,
                    "operation": "EXIT_TERMINAL",
                    "sequence": action["sequence"],
                    "venue_order_id": "sim-order:" + client_id,
                    "cumulative_fill_quantity": quantity,
                    "outcome": "FILLED" if quantity == D(action["quantity"]) else "CANCELED",
                },
                now,
                now,
            )
            return self._save(
                db,
                client_id,
                evidence,
                {
                    "fill": fill,
                    "action_ids": ids + terminal["action_ids"],
                    "quality": Quality.PRELIMINARY,
                },
            )
