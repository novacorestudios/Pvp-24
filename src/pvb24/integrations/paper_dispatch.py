"""Write-ahead boundary for a PAPER backend hosted by the Freqtrade executor.

This contract is not an operational venue implementation or a qualification
certificate. Native Freqtrade dry-run is deliberately not a fallback backend.
Acknowledgement proves order identity only; fills/terminal outcomes must still
pass through the shared account reducer with actual execution evidence.
"""

import fcntl
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Protocol

from pvb24.accounting.coordinator import read_tx, save_tx
from pvb24.decimal_math import CONTEXT, D
from pvb24.execution.book import Book
from pvb24.execution.market import EntryBounds, preview_ioc
from pvb24.execution.planner import EntryInputs
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, digest
from pvb24.risk.portfolio import Portfolio
from pvb24.risk.reservations import restore_portfolio
from pvb24.risk.sizing import candidate, linear_margin
from pvb24.state import Conflict, Journal
from pvb24.types import Quality, Side, utc


@dataclass(frozen=True)
class EntryTicket:
    client_id: str
    signal_id: str
    symbol: str
    side: Side
    quantity: Decimal
    leverage: int
    limit_price: Decimal
    prepared_at: datetime
    deadline: datetime
    input_digest: str
    mode: str = "PAPER"
    order_type: str = "LIMIT"
    time_in_force: str = "IOC"
    reduce_only: bool = False


@dataclass(frozen=True)
class OrderAccepted:
    client_id: str
    order_id: str
    ticket_digest: str
    accepted_at: datetime


@dataclass(frozen=True)
class OrderRejected:
    """Durable backend refusal record; order_id identifies the refused request."""

    client_id: str
    order_id: str
    ticket_digest: str
    rejected_at: datetime
    reason: str


class PaperBackend(Protocol):
    # Explicit contract declarations, not proof of exchange-model fidelity.
    paper_only: bool
    contract: str
    instance_id: str
    quality: Quality

    def submit_entry(self, ticket: EntryTicket) -> OrderAccepted | OrderRejected: ...

    def lookup(self, client_id: str) -> OrderAccepted | OrderRejected | None: ...


CONTRACT = "PVB24_PAPER_DECIMAL_IOC_DURABLE_LOOKUP_V1"


class PaperDispatch:
    """One Linux process owns one durable account journal until close().

    The backend must honor the immutable ticket, enforce its deadline, and use
    durable client-ID lookup. A timeout, malformed response or absent lookup
    never grants permission to resubmit. This boundary does not release risk.
    """

    def __init__(
        self,
        journal: Journal,
        scope: str,
        quality: Quality,
        backend: PaperBackend,
        clock: Callable[[], datetime],
    ):
        if not scope or not isinstance(quality, Quality) or not callable(clock):
            raise ValueError("Explicit scope, quality and clock required")
        self.journal, self.scope, self.quality = journal, scope, quality
        self.backend, self.clock = backend, clock
        self._pid = os.getpid()
        self._lock = None
        self._backend_guard()
        if journal.db.in_transaction:
            raise Conflict("Dispatch authority cannot bind inside a transaction")
        path = journal.db.execute("PRAGMA database_list").fetchone()["file"]
        if not path:
            raise ValueError("PAPER dispatch requires a durable file journal")
        # Lock the database inode: aliases/symlinks cannot create a second host.
        lock = open(path, "rb")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            lock.close()
            raise Conflict("Another PAPER authority owns this journal") from None
        self._lock = lock
        self._binding = {
            "instance_id": backend.instance_id,
            "contract": backend.contract,
            "quality": quality,
        }
        try:
            with journal.transaction() as db:
                stream = "paper-authority:" + scope
                _, prior = journal.snapshot(stream)
                if prior is not None and canonical(prior) != canonical(self._binding):
                    raise Conflict("PAPER backend identity or quality changed across restart")
                if prior is None:
                    save_tx(db, stream, self._binding)
        except BaseException:
            self.close()
            raise

    def _backend_guard(self):
        if (
            self.backend.paper_only is not True
            or self.backend.contract != CONTRACT
            or getattr(self.backend, "quality", None) is not self.quality
            or not isinstance(self.backend.instance_id, str)
            or not self.backend.instance_id
        ):
            raise ValueError("Explicit PAPER Decimal IOC/lookup backend required")

    def _guard(self):
        self._backend_guard()
        if self.backend.instance_id != self._binding["instance_id"]:
            raise Conflict("PAPER backend identity changed")
        if self._lock is None or self._lock.closed or self._pid != os.getpid():
            raise Conflict("PAPER authority is closed or belongs to another process")
        if self.journal.db.in_transaction:
            raise Conflict("External dispatch/lookup cannot run inside a transaction")

    def close(self):
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def __enter__(self):
        self._guard()
        return self

    def __exit__(self, *args):
        self.close()

    def _intent(self, db, client_id, purposes=("ENTRY",)):
        row = db.execute("SELECT * FROM intents WHERE client_id=?", (client_id,)).fetchone()
        if row is None or row["scope"] != self.scope or row["purpose"] not in purposes:
            raise Conflict("Owned supported intent required")
        return row

    def _ready(self, db, metadata, now):
        if not (
            datetime.fromisoformat(metadata["accepted_at"])
            <= now
            <= datetime.fromisoformat(metadata["order_deadline"])
        ):
            raise Conflict("Entry dispatch deadline or clock violated")
        _, mode = read_tx(db, "replay-account:" + self.scope)
        if mode["quality"] != self.quality or metadata["quality"] != self.quality:
            raise Conflict("Dispatch quality differs from frozen account policy")
        if mode["last_time"] and datetime.fromisoformat(mode["last_time"]) > now:
            raise Conflict("Cannot backdate dispatch behind account events")
        _, gate = read_tx(db, "account-gate:" + self.scope)
        watermark = gate.get("last_evidence_at")
        if (
            gate.get("ready") is not True
            or gate.get("safety_paused") is not False
            or (watermark and datetime.fromisoformat(watermark) > now)
        ):
            raise Conflict("Account gate blocks entry dispatch")
        _, control = read_tx(db, "equity-control:" + self.scope)
        status = control.get("last_status")
        if (
            status is None
            or status.get("entries_allowed") is not True
            or datetime.fromisoformat(status["time"]) != now.replace(second=0, microsecond=0)
        ):
            raise Conflict("Current minute risk sample required at dispatch")
        return status

    def _ticket(self, db, row, inputs, book, now):
        sid = row["signal_id"]
        _, meta = read_tx(db, "entry-metadata:" + self.scope + ":" + sid)
        status = self._ready(db, meta, now)
        payload = json.loads(row["payload"])
        original = payload["sizing"]
        quantity = D(original["quantity"])
        side = Side(payload["side"])
        rules = inputs.rules
        if (
            inputs.available_at > now
            or canonical(rules) != canonical(meta["source"]["rules"])
            or rules.available_at > now
            or rules.effective_from > now
            or (rules.effective_to is not None and rules.effective_to <= now)
            or (inputs.maximum_quantity is not None and quantity > inputs.maximum_quantity)
        ):
            raise Conflict("Execution inputs unavailable, expired or changed contract rules")
        _, raw = read_tx(db, "protection:" + self.scope + ":" + sid)
        protection = Protection.restore(raw)
        _, raw = read_tx(db, "portfolio:" + self.scope)
        portfolio = restore_portfolio(raw)
        own = next((p for p in portfolio.exposures if p.position_id == sid), None)
        if (
            own is None
            or not own.pending
            or own.initial_quantity != quantity
            or own.remaining_quantity != quantity
            or own.symbol != payload["symbol"]
            or own.side is not side
            or protection.requested_quantity != quantity
            or protection.symbol != own.symbol
            or protection.side is not side
            or protection.fills
            or protection.actions
            or protection.terminal
        ):
            raise Conflict("Dispatch requires an intact owned pending reservation")
        b = meta["bounds"]
        bounds = EntryBounds(
            b["symbol"],
            Side(b["side"]),
            datetime.fromisoformat(b["signal_time"]),
            D(b["signal_close"]),
            D(b["channel"]),
            D(b["atr_previous"]),
            D(b["tick"]),
        )
        if bounds.symbol != own.symbol or bounds.side is not side or rules.symbol != own.symbol:
            raise Conflict("Entry source identity differs from reservation")
        if any(price % rules.tick for price in (*book.bids, *book.asks)):
            raise Conflict("Book contains off-tick prices")
        preview = preview_ioc(
            book,
            bounds,
            quantity,
            inputs.recent_quote_volume,
            datetime.fromisoformat(meta["accepted_at"]),
            now,
        )
        if preview.reason != "ACCEPTED":
            raise Conflict("Dispatch market gate: " + preview.reason)
        book_evidence = {
            "sequence": book.sequence,
            "event_time": book.event_time,
            "received_at": book.received_at,
            "bids": sorted(book.bids.items()),
            "asks": sorted(book.asks.items()),
        }
        quote = inputs.quote_model(quantity)
        verified = self.quality is Quality.VERIFIED
        if (
            quote is None
            or quote.available_at > now
            or quote.expected_entry != preview.sweep.vwap
            or quote.arrival_side_price != (book.best_ask if side is Side.LONG else book.best_bid)
            or (
                verified
                and (
                    quote.quality is not Quality.VERIFIED
                    or not rules.historical_verified
                    or not rules.liquidation_validated
                    or inputs.margin_model is None
                )
            )
        ):
            raise Conflict("Dispatch quote must match causal book and required quality")
        # Remove only this reservation for the feasibility calculation; it remains
        # durably held. Reject changed economics that exceed any original reserve.
        costs = original["costs"]
        obligations = quantity * sum(
            D(costs[k]) for k in ("entry_fee", "exit_fee", "stop_slippage", "funding")
        )
        available = Portfolio(
            portfolio.equity,
            portfolio.free_collateral + own.initial_margin_commitment + obligations,
            tuple(p for p in portfolio.exposures if p.position_id != sid),
        )
        reduced = D(status["risk_fraction"]) == D("0.005")
        checked = candidate(
            quantity,
            side,
            bounds.atr_previous,
            quote,
            available,
            rules,
            available.budget(side, reduced=reduced),
            inputs.margin_model or linear_margin,
            require_verified=verified,
        )
        if (
            checked is None
            or quantity * quote.expected_entry < rules.minimum_notional
            or checked.reserved_loss < D("0.0025") * portfolio.equity
            or checked.reserved_loss > own.reserved_risk
            or checked.initial_margin > own.initial_margin_commitment
            or checked.leverage != original["leverage"]
            or any(
                getattr(checked.costs, k) > D(costs[k])
                for k in ("entry_fee", "exit_fee", "stop_slippage", "funding")
            )
        ):
            raise Conflict("Current economics cannot honor the original reservation")
        # The solver/callback can take time; check deadline, book and risk again.
        sent = utc(self.clock())
        if sent < now:
            raise Conflict("Dispatch clock moved backwards")
        self._ready(db, meta, sent)
        if not book.fresh(sent):
            raise Conflict("Book became stale during dispatch validation")
        if book_evidence != {
            "sequence": book.sequence,
            "event_time": book.event_time,
            "received_at": book.received_at,
            "bids": sorted(book.bids.items()),
            "asks": sorted(book.asks.items()),
        }:
            raise Conflict("Book changed during dispatch validation")
        evidence = {
            "source": inputs.provenance(),
            "quote": quote,
            "preview": preview,
            "book": book_evidence,
            "checked": checked,
            "portfolio": portfolio,
            "status": status,
        }
        Journal.append_tx(db, "paper-inputs:" + row["client_id"], evidence)
        ticket = EntryTicket(
            row["client_id"],
            sid,
            own.symbol,
            side,
            quantity,
            original["leverage"],
            preview.limit,
            sent,
            datetime.fromisoformat(meta["order_deadline"]),
            digest(evidence),
        )
        return ticket

    def dispatch_entry(self, client_id: str, inputs: EntryInputs, book: Book):
        self._guard()
        now = utc(self.clock())
        with self.journal.transaction() as db, localcontext(CONTEXT):
            row = self._intent(db, client_id)
            if row["state"] != "PREPARED":
                raise Conflict("Previously dispatched or terminal intent: query, never resend")
            ticket = self._ticket(db, row, inputs, book, now)
            Journal.append_tx(db, "paper-ticket:" + client_id, ticket)
            if not self.journal.claim_dispatch(client_id):
                raise Conflict("Entry dispatch claim denied")
        # UNKNOWN and ticket are committed here, even if submit raises or the
        # process crashes before/after the call. No external call in SQLite tx.
        self._guard()
        response = self.backend.submit_entry(ticket)
        self._acknowledge(ticket, response)
        return response

    def _acknowledge(self, ticket, response):
        from pvb24.integrations.paper_actions import PURPOSES

        self._guard()
        now = utc(self.clock())
        rejected = isinstance(response, OrderRejected)
        if not isinstance(response, (OrderAccepted, OrderRejected)):
            raise Conflict("Invalid PAPER acknowledgement; outcome remains unresolved")
        response_time = response.rejected_at if rejected else response.accepted_at
        if (
            response.client_id != ticket.client_id
            or not isinstance(response.order_id, str)
            or not response.order_id
            or response.ticket_digest != digest(ticket)
            or (rejected and not response.reason)
            or not ticket.prepared_at
            <= utc(response_time)
            <= (min(now, ticket.deadline) if ticket.deadline is not None and not rejected else now)
        ):
            raise Conflict("Invalid PAPER acknowledgement; outcome remains unresolved")
        with self.journal.transaction() as db:
            row = self._intent(db, ticket.client_id, purposes=("ENTRY",) + PURPOSES)
            if db.execute(
                "SELECT 1 FROM events WHERE event_id=?",
                ("paper-forced-order:" + self.scope + ":" + digest(response.order_id),),
            ).fetchone():
                raise Conflict("Venue order ID already belongs to a forced liquidation")
            # Enforce one venue order per client and one client per venue order.
            response_key = "paper-rejected:" if rejected else "paper-accepted:"
            contradictory = "paper-accepted:" if rejected else "paper-rejected:"
            if db.execute(
                "SELECT 1 FROM events WHERE event_id=?", (contradictory + ticket.client_id,)
            ).fetchone():
                raise Conflict("Contradictory PAPER request receipt")
            Journal.append_tx(db, response_key + ticket.client_id, response)
            Journal.append_tx(
                db,
                "paper-order:" + self.scope + ":" + digest(response.order_id),
                {"client_id": ticket.client_id, "order_id": response.order_id},
            )
            # Protective/cancel acceptance does not prove an active/canceled
            # stop. Their shared-core outcome carries separate evidence.
            if (
                not rejected
                and row["purpose"] == "ENTRY"
                and row["state"] in ("UNKNOWN", "ACKNOWLEDGED")
            ):
                self.journal.reconcile_intent(ticket.client_id, "ACKNOWLEDGED", response)

    def dispatch_action(self, client_id: str):
        from pvb24.integrations.paper_actions import dispatch_action

        return dispatch_action(self, client_id)

    def lookup(self, client_id: str):
        from pvb24.integrations.paper_actions import PURPOSES, ActionTicket, guard_actions

        self._guard()
        row = self._intent(self.journal.db, client_id, purposes=("ENTRY",) + PURPOSES)
        if row["state"] == "PREPARED":
            raise Conflict("No committed dispatch to query")
        raw = self.journal.db.execute(
            "SELECT payload FROM events WHERE event_id=?", ("paper-ticket:" + client_id,)
        ).fetchone()
        if raw is None:
            raise Conflict("No owned PAPER transport ticket")
        t = json.loads(raw["payload"])
        for key in ("quantity", "limit_price", "stop_price"):
            if key in t and t[key] is not None:
                t[key] = D(t[key])
        for key in ("prepared_at", "deadline"):
            if t[key] is not None:
                t[key] = datetime.fromisoformat(t[key])
        t["side"] = Side(t["side"])
        if row["purpose"] == "ENTRY":
            ticket = EntryTicket(**t)
        else:
            guard_actions(self)
            ticket = ActionTicket(**t)
        response = self.backend.lookup(client_id)
        if response is not None:
            self._acknowledge(ticket, response)
        return response
