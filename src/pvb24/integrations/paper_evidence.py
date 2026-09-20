"""Causal owned PAPER execution evidence, never inferred from transport receipts."""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import localcontext

from pvb24.accounting.coordinator import AccountCoordinator, read_tx, save_tx
from pvb24.decimal_math import CONTEXT, ZERO, D, require_decimal
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, digest
from pvb24.integrations.paper_actions import PURPOSES, accepted_order
from pvb24.replay import codecs
from pvb24.replay.account import AccountReplay
from pvb24.replay.events import Delivery, Event, Kind
from pvb24.state import Conflict, Journal
from pvb24.types import Quality, Side, utc


@dataclass(frozen=True)
class PaperEvent:
    event_id: str
    instance_id: str
    client_id: str
    kind: str
    event_time: datetime
    available_at: datetime
    quality: Quality
    data_json: str

    def __post_init__(self):
        if not self.event_id or not self.instance_id or not self.client_id:
            raise ValueError("PAPER evidence identity required")
        if self.kind not in ("FILL", "LIQUIDATION", "STOP_ACTIVE", "TERMINAL", "CANCEL_CONFIRMED"):
            raise ValueError("Unsupported PAPER evidence kind")
        if not isinstance(self.quality, Quality) or utc(self.event_time) > utc(self.available_at):
            raise ValueError("Explicit quality and causal evidence timing required")
        if canonical(json.loads(self.data_json)) != self.data_json:
            raise ValueError("Immutable canonical execution evidence required")


class PaperEvidence:
    def __init__(self, host):
        host._guard()
        self.host = host
        self.journal, self.scope = host.journal, host.scope
        self.account = AccountReplay(self.journal, self.scope, host.quality)

    def _owned(self, db, cid):
        row = self.host._intent(db, cid, purposes=("ENTRY",) + PURPOSES)
        if row["state"] == "PREPARED":
            raise Conflict("Evidence has no committed dispatch")
        raw = db.execute(
            "SELECT payload FROM events WHERE event_id=?", ("paper-ticket:" + cid,)
        ).fetchone()
        if raw is None:
            raise Conflict("Evidence has no owned transport ticket")
        return row, json.loads(raw["payload"]), accepted_order(db, cid)

    def _deliver(self, event, suffix, kind, payload, sequence=None):
        normalized = Event(
            "paper:" + self.scope + ":" + event.event_id + ":" + suffix,
            kind,
            event.event_time,
            event.available_at,
            "paper:" + event.instance_id,
            event.quality,
            canonical(payload),
            sequence,
            None if sequence is None else "paper:" + event.instance_id,
        )
        return self.account(Delivery(normalized, "CONSERVATIVE_PRIORITY", 0))

    def _terminal(self, db, event, row, ticket, order_id, raw, suffix):
        if row["purpose"] not in ("ENTRY", "PROTECT", "EXIT_MARKET"):
            raise Conflict("Terminal proof must describe an owned order")
        if raw["venue_order_id"] != order_id:
            raise Conflict("Terminal proof belongs to a different venue order")
        outcome = raw["outcome"]
        if outcome not in ("FILLED", "CANCELED", "REJECTED"):
            raise ValueError("Explicit terminal order outcome required")
        cumulative = D(raw["cumulative_fill_quantity"])
        require_decimal(cumulative, nonnegative=True)
        _, state = read_tx(db, "protection:" + self.scope + ":" + row["signal_id"])
        p = Protection.restore(state)
        actual = sum((f.quantity for f in p.fills.values() if f.order_id == order_id), ZERO)
        if cumulative != actual or (outcome == "FILLED" and actual != D(ticket["quantity"])):
            raise Conflict("Terminal order proof has missing or inconsistent fill evidence")
        if outcome == "REJECTED" and actual != 0:
            raise Conflict("A rejected order cannot contain confirmed fills")
        if row["state"] in ("FILLED", "CANCELED", "REJECTED"):
            if row["state"] != outcome:
                raise Conflict("Terminal evidence conflicts with the proven order outcome")
            # A later cancel/query can repeat the same terminal proof. Preserve
            # the original journal outcome; the outer receipt retains new evidence.
            return {"action_ids": ()}
        purpose = row["purpose"]
        payload = {
            "position_id": row["signal_id"],
            "operation": {
                "ENTRY": "ENTRY_TERMINAL",
                "PROTECT": "STOP_TERMINAL",
                "EXIT_MARKET": "EXIT_TERMINAL",
            }[purpose],
            "outcome": outcome,
            "venue_order_id": order_id,
            "cumulative_fill_quantity": cumulative,
        }
        if purpose != "ENTRY":
            payload["sequence"] = ticket["sequence"]
        return self._deliver(event, suffix, Kind.ORDER_OUTCOME, payload)

    def _apply(self, db, event):
        row, ticket, order_id = self._owned(db, event.client_id)
        if event.event_time < datetime.fromisoformat(ticket["prepared_at"]):
            raise Conflict("Evidence predates its committed order ticket")
        raw = json.loads(event.data_json)
        if event.kind == "LIQUIDATION":
            # Forced venue orders have no submitted client intent. The entry
            # ticket anchors owned position identity; the bound backend must
            # provide explicit forced-fill evidence, never an OHLC inference.
            record = codecs.fill_record(raw["record"])
            f = record.fill
            exit_side = Side.SHORT if Side(ticket["side"]) is Side.LONG else Side.LONG
            if (
                row["purpose"] != "ENTRY"
                or not record.liquidation
                or not f.reduce_only
                or f.position_id != row["signal_id"]
                or f.symbol != ticket["symbol"]
                or f.side is not exit_side
                or db.execute(
                    "SELECT 1 FROM events WHERE event_id=?",
                    ("paper-order:" + self.scope + ":" + digest(f.order_id),),
                ).fetchone()
            ):
                raise Conflict("Forced liquidation evidence has invalid owned position/order")
            Journal.append_tx(
                db,
                "paper-forced-order:" + self.scope + ":" + digest(f.order_id),
                {"position_id": row["signal_id"], "order_id": f.order_id},
            )
            return self._deliver(
                event, "liquidation", Kind.LIQUIDATION, record, record.exchange_sequence
            )
        if event.kind == "FILL":
            if row["purpose"] not in ("ENTRY", "PROTECT", "EXIT_MARKET"):
                raise Conflict("Cancellation requests cannot own trade fills")
            record = codecs.fill_record(raw["record"])
            f = record.fill
            reducing = row["purpose"] != "ENTRY"
            if (
                f.order_id != order_id
                or f.position_id != row["signal_id"]
                or f.symbol != ticket["symbol"]
                or f.side is not Side(ticket["side"])
                or f.reduce_only is not reducing
                or record.liquidation
            ):
                raise Conflict("Fill ownership or execution side differs from transport ticket")
            kind = (
                Kind.ENTRY_FILL
                if not reducing
                else (Kind.PROTECTIVE_FILL if row["purpose"] == "PROTECT" else Kind.REDUCE_FILL)
            )
            result = self._deliver(event, "fill", kind, record, record.exchange_sequence)
            # Retain authoritative overfills instead of hiding a cash/quantity
            # anomaly. Force safety reconciliation and bounded closure afterward.
            _, state = read_tx(db, "protection:" + self.scope + ":" + row["signal_id"])
            p = Protection.restore(state)
            total = sum((f.quantity for f in p.fills.values() if f.order_id == order_id), ZERO)
            if total > D(ticket["quantity"]) and not p.safety_paused:
                extra = self.account.coordinator.protection_event(
                    row["signal_id"],
                    "paper-overfill:" + event.event_id,
                    {
                        "client_id": event.client_id,
                        "actual": total,
                        "requested": ticket["quantity"],
                    },
                    lambda p: p.protection_failed(),
                    event.available_at,
                )
                result["action_ids"] = tuple(result["action_ids"]) + extra
            return result
        if event.kind == "STOP_ACTIVE":
            if row["purpose"] != "PROTECT" or raw["venue_order_id"] != order_id:
                raise Conflict("Active stop proof belongs to a different owned order")
            return self._deliver(
                event,
                "active",
                Kind.ORDER_OUTCOME,
                {
                    "position_id": row["signal_id"],
                    "operation": "STOP_ACK",
                    "sequence": ticket["sequence"],
                    "quantity": raw["quantity"],
                    "stop": raw["stop"],
                    "reduce_only": raw["reduce_only"],
                    "reference": raw["reference"],
                },
            )
        if event.kind == "TERMINAL":
            return self._terminal(db, event, row, ticket, order_id, raw, "terminal")
        if row["purpose"] not in ("CANCEL_ENTRY", "CANCEL_PROTECTION"):
            raise Conflict("Cancellation proof requires an owned cancel request")
        target_id = ticket["target_client_id"]
        if raw["target_client_id"] != target_id or raw["request_order_id"] != order_id:
            raise Conflict("Cancellation proof targets a different request/order")
        target, target_ticket, target_order = self._owned(db, target_id)
        if target["signal_id"] != row["signal_id"] or target_order != ticket["target_order_id"]:
            raise Conflict("Cancellation target ownership changed")
        if raw["outcome"] not in ("CANCELED", "FILLED", "REJECTED"):
            raise Conflict("Cancellation response lacks a proven target terminal outcome")
        result = self._terminal(
            db, event, target, target_ticket, target_order, raw, "cancel-target"
        )
        self.journal.reconcile_intent(event.client_id, "ACKNOWLEDGED", raw)
        return result

    def ingest(self, event: PaperEvent):
        self.host._guard()
        now = utc(self.host.clock())
        key = "paper-evidence:" + self.scope + ":" + event.event_id
        evidence_hash = digest(event)
        try:
            if (
                event.instance_id != self.host.backend.instance_id
                or event.quality is not self.host.quality
                or event.available_at > now
            ):
                raise Conflict("PAPER source, quality or availability differs from bound authority")
            with self.journal.transaction() as db, localcontext(CONTEXT):
                previous = db.execute(
                    "SELECT payload FROM events WHERE event_id=?", (key,)
                ).fetchone()
                if previous:
                    receipt = json.loads(previous["payload"])
                    if receipt["evidence_hash"] != evidence_hash:
                        raise Conflict("Changed PAPER execution event")
                    return receipt["result"]
                _, mode = read_tx(db, "replay-account:" + self.scope)
                if (
                    mode["last_time"]
                    and datetime.fromisoformat(mode["last_time"]) > event.available_at
                ):
                    raise Conflict("Cannot backdate PAPER evidence delivery")
                result = json.loads(canonical(self._apply(db, event)))
                _, mode = read_tx(db, "replay-account:" + self.scope)
                mode["last_time"] = event.available_at
                save_tx(db, "replay-account:" + self.scope, mode)
                Journal.append_tx(db, key, {"evidence_hash": evidence_hash, "result": result})
                return result
        except Exception:
            # AccountReplay may have used nested savepoints: its pause rolls back
            # with this outer transaction. Persist the pause after full rollback.
            with self.journal.transaction() as db:
                AccountCoordinator(self.journal, self.scope)._pause(
                    db, "PAPER_EVIDENCE_RECONCILIATION_REQUIRED", now
                )
            raise
