"""Durable PRELIMINARY L2 PAPER model, without sockets or exchange credentials.

Visible-book IOC simulation is explicit, not a queue/latency model or proof of
actual venue behavior. Operational PAPER remains blocked until source/account
qualification and the sole Freqtrade process integration are complete.
"""

import json
from datetime import datetime, timedelta
from decimal import localcontext

from pvb24.accounting.coordinator import read_tx, save_tx
from pvb24.accounting.ledger import FillRecord
from pvb24.data.contract_rules import ContractRules, MaintenanceTier
from pvb24.decimal_math import CONTEXT, ZERO, D, require_decimal
from pvb24.execution.book import Book
from pvb24.ids import canonical, client_identity, digest
from pvb24.integrations.paper_actions import ACTION_CONTRACT
from pvb24.integrations.paper_dispatch import CONTRACT, EntryTicket, OrderAccepted, OrderRejected
from pvb24.integrations.paper_evidence import PaperEvent
from pvb24.state import Conflict, Journal
from pvb24.types import Fill, Quality, utc


def book_record(book):
    return {
        "symbol": book.symbol,
        "sequence": book.sequence,
        "synced": book.synced,
        "event_time": book.event_time,
        "received_at": book.received_at,
        "bids": sorted(book.bids.items()),
        "asks": sorted(book.asks.items()),
    }


def restore_book(raw):
    book = Book(raw["symbol"])
    book.sequence, book.synced = raw["sequence"], raw["synced"]
    for key in ("event_time", "received_at"):
        setattr(book, key, None if raw[key] is None else datetime.fromisoformat(raw[key]))
    book.bids = {D(p): D(q) for p, q in raw["bids"]}
    book.asks = {D(p): D(q) for p, q in raw["asks"]}
    return book


def restore_rules(raw):
    values = dict(raw)
    for key in ("effective_from", "effective_to", "available_at"):
        values[key] = None if values[key] is None else datetime.fromisoformat(values[key])
    for key in (
        "tick",
        "quantity_step",
        "minimum_quantity",
        "minimum_notional",
        "maximum_quantity",
        "contract_size",
    ):
        values[key] = D(values[key])
    values["tiers"] = tuple(
        MaintenanceTier(
            D(t["notional_floor"]),
            D(t["notional_cap"]),
            D(t["rate"]),
            D(t["deduction"]),
            t["max_leverage"],
        )
        for t in values["tiers"]
    )
    return ContractRules(**values)


def receipt(raw):
    values = dict(raw)
    rejected = "rejected_at" in values
    key = "rejected_at" if rejected else "accepted_at"
    values[key] = datetime.fromisoformat(values[key])
    return OrderRejected(**values) if rejected else OrderAccepted(**values)


class L2PaperVenue:
    paper_only = True
    contract = CONTRACT
    quality = Quality.PRELIMINARY
    action_contract = ACTION_CONTRACT

    def __init__(self, path, *, instance_id, scope, manifest_id, clock, max_last_age=None):
        if not instance_id or not scope or not manifest_id or not callable(clock):
            raise ValueError("Explicit PAPER model identity, policy manifest and clock required")
        self.instance_id, self.scope, self.clock = instance_id, scope, clock
        if max_last_age is not None and (
            not isinstance(max_last_age, timedelta) or max_last_age <= timedelta(0)
        ):
            raise ValueError("Explicit positive LAST freshness policy required")
        self.max_last_age = max_last_age
        self.journal = Journal(path)
        self.policy = {
            "instance_id": instance_id,
            "scope": scope,
            "manifest_id": manifest_id,
            "quality": Quality.PRELIMINARY,
            "model": "L2_VISIBLE_ORDERS_LAST_STOP_V2",
            "last_max_age_microseconds": None
            if max_last_age is None
            else (
                max_last_age.days * 86400000000
                + max_last_age.seconds * 1000000
                + max_last_age.microseconds
            ),
            "simultaneous_stop_ordering": "ACCEPTANCE_SEQUENCE",
            "insufficient_market_depth": "PENDING_UNTIL_EXPLICIT_DEPTH_UPDATE",
            "live_enabled": False,
            "operational_ready": False,
        }
        self._frozen_policy = canonical(self.policy)
        try:
            with self.journal.transaction() as db:
                _, previous = self.journal.snapshot("paper-model")
                if previous is not None and canonical(previous) != canonical(self.policy):
                    raise Conflict("Durable PAPER model policy changed")
                if previous is None:
                    save_tx(db, "paper-model", self.policy)
        except BaseException:
            self.journal.close()
            raise

    def close(self):
        self.journal.close()

    def _now(self):
        if self.journal.db.in_transaction:
            raise Conflict("PAPER backend command requires its own durable transaction")
        if self.paper_only is not True:
            raise ValueError("PAPER model cannot enable LIVE")
        if self.quality is not Quality.PRELIMINARY:
            raise ValueError("This execution model has PRELIMINARY quality only")
        if self.instance_id != self.policy["instance_id"] or self.scope != self.policy["scope"]:
            raise Conflict("Bound PAPER model identity changed")
        age = self.max_last_age
        age_us = (
            None
            if age is None
            else age.days * 86400000000 + age.seconds * 1000000 + age.microseconds
        )
        if (
            canonical(self.policy) != self._frozen_policy
            or age_us != self.policy["last_max_age_microseconds"]
        ):
            raise Conflict("Frozen PAPER execution policy changed")
        return utc(self.clock())

    def _advance(self, db, now):
        _, previous = self.journal.snapshot("model-clock")
        if previous is not None and datetime.fromisoformat(previous["time"]) > now:
            raise Conflict("PAPER model clock moved backwards")
        save_tx(db, "model-clock", {"time": now})

    def install_book(self, book: Book, *, source_event_id: str):
        now = self._now()
        if not source_event_id or not book.fresh(now):
            raise ValueError("Causal synchronized fresh book and source identity required")
        payload = book_record(book)
        with self.journal.transaction() as db:
            self._advance(db, now)
            if not Journal.append_tx(db, "model-book-source:" + source_event_id, payload):
                return False  # never replenish a consumed level from a duplicate source
            stream = "model-book:" + book.symbol
            _, old = self.journal.snapshot(stream)
            if old is not None and (
                book.received_at <= datetime.fromisoformat(old["received_at"])
                or (old["sequence"] is not None and book.sequence <= old["sequence"])
            ):
                raise Conflict("Fresh resnapshot must advance book source time and sequence")
            save_tx(db, stream, payload)
            self._run_pending(db, book.symbol, now)
            return True

    def update_book(
        self,
        symbol,
        *,
        first,
        final,
        previous,
        bids,
        asks,
        event_time,
        received_at,
        source_event_id,
    ):
        now = self._now()
        if not source_event_id or utc(received_at) > now:
            raise ValueError("Causal book update required")
        evidence = {
            "symbol": symbol,
            "first": first,
            "final": final,
            "previous": previous,
            "bids": bids,
            "asks": asks,
            "event_time": event_time,
            "received_at": received_at,
        }
        error = None
        with self.journal.transaction() as db:
            self._advance(db, now)
            if not Journal.append_tx(db, "model-book-source:" + source_event_id, evidence):
                return False
            stream = "model-book:" + symbol
            _, raw = read_tx(db, stream)
            book = restore_book(raw)
            try:
                changed = book.update(first, final, previous, bids, asks, event_time, received_at)
            except (ValueError, TypeError) as exc:
                error, changed = exc, False
                book.synced = False
                book.sequence = None
            save_tx(db, stream, book_record(book))
            if error is None:
                self._run_pending(db, symbol, now)
        if error is not None:
            raise error  # persist the unsynced state before reporting the gap
        return changed

    def set_terms(
        self, rules, *, entry_fee_rate, available_at, source_revision, exit_fee_rate=None
    ):
        now = self._now()
        require_decimal(entry_fee_rate, nonnegative=True)
        if exit_fee_rate is not None:
            require_decimal(exit_fee_rate, nonnegative=True)
        if not source_revision or utc(available_at) > now or rules.available_at > available_at:
            raise ValueError("Causal execution fee/rule terms required")
        payload = {
            "rules": rules,
            "entry_fee_rate": entry_fee_rate,
            "exit_fee_rate": exit_fee_rate,
            "available_at": available_at,
            "source_revision": source_revision,
        }
        with self.journal.transaction() as db:
            self._advance(db, now)
            if not Journal.append_tx(
                db, "model-terms-source:" + rules.symbol + ":" + source_revision, payload
            ):
                return False
            stream = "model-terms:" + rules.symbol
            _, old = self.journal.snapshot(stream)
            if old is not None and datetime.fromisoformat(old["available_at"]) >= available_at:
                raise Conflict("Execution terms must advance their source availability")
            save_tx(db, stream, payload)
            return True

    def lookup(self, client_id):
        self._now()
        _, row = self.journal.snapshot("model-order:" + client_id)
        return None if row is None else receipt(row["receipt"])

    def _emit(self, db, ticket, order_id, kind, suffix, now, payload):
        event = PaperEvent(
            order_id + ":" + suffix,
            self.instance_id,
            ticket.client_id,
            kind,
            now,
            now,
            Quality.PRELIMINARY,
            canonical(payload),
        )
        Journal.append_tx(db, "model-evidence:" + event.event_id, event)

    def events_after(self, cursor=0, *, limit=None):
        """Durable source cursor; consumer advances it only after account commit."""
        self._now()
        if type(cursor) is not int or cursor < 0:
            raise ValueError("Nonnegative durable event cursor required")
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError("Positive event page size required")
        result = []
        rows = self.journal.db.execute(
            "SELECT seq,payload FROM events WHERE seq>? "
            "AND event_id LIKE 'model-evidence:%' ORDER BY seq LIMIT ?",
            (cursor, -1 if limit is None else limit),
        ).fetchall()
        for row in rows:
            raw = json.loads(row["payload"])
            for key in ("event_time", "available_at"):
                raw[key] = datetime.fromisoformat(raw[key])
            raw["quality"] = Quality(raw["quality"])
            result.append((row["seq"], PaperEvent(**raw)))
        return tuple(result)

    def submit_entry(self, ticket: EntryTicket):
        now = self._now()
        if not isinstance(ticket, EntryTicket):
            raise TypeError("Immutable entry ticket required")
        with self.journal.transaction() as db, localcontext(CONTEXT):
            self._advance(db, now)
            stream = "model-order:" + ticket.client_id
            _, existing = self.journal.snapshot(stream)
            if existing is not None:
                if canonical(existing["ticket"]) != canonical(ticket):
                    raise Conflict("Backend client identity reused with changed ticket")
                return receipt(existing["receipt"])
            _, _, expected_id = client_identity(self.scope, ticket.signal_id, "ENTRY")
            if (
                ticket.client_id != expected_id
                or ticket.mode != "PAPER"
                or ticket.reduce_only is not False
                or ticket.order_type != "LIMIT"
                or ticket.time_in_force != "IOC"
            ):
                raise Conflict("Ticket violates PAPER ownership or IOC contract")
            require_decimal(ticket.quantity, positive=True)
            require_decimal(ticket.limit_price, positive=True)
            if now < ticket.prepared_at:
                raise Conflict("Backend clock precedes committed dispatch")
            _, raw_book = self.journal.snapshot("model-book:" + ticket.symbol)
            _, raw_terms = self.journal.snapshot("model-terms:" + ticket.symbol)
            _, owned = self.journal.snapshot("model-position:" + ticket.signal_id)
            reason = None
            book = None if raw_book is None else restore_book(raw_book)
            rules = None if raw_terms is None else restore_rules(raw_terms["rules"])
            if now > ticket.deadline:
                reason = "ORDER_DEADLINE"
            elif book is None or not book.fresh(now):
                reason = "STALE_OR_UNSYNCED_BOOK"
            elif (
                rules is None
                or rules.available_at > now
                or rules.effective_from > now
                or (rules.effective_to is not None and rules.effective_to <= now)
            ):
                reason = "CONTRACT_RULES_UNAVAILABLE"
            elif (
                ticket.quantity % (rules.quantity_step * rules.contract_size)
                or not rules.minimum_quantity * rules.contract_size
                <= ticket.quantity
                <= rules.maximum_quantity * rules.contract_size
                or ticket.limit_price % rules.tick
                or not rules.supports_ioc
                or ticket.quantity * ticket.limit_price < rules.minimum_notional
                or type(ticket.leverage) is not int
                or not 1 <= ticket.leverage <= 5
            ):
                reason = "CONTRACT_FILTER"
            elif any(
                price % rules.tick or quantity % (rules.quantity_step * rules.contract_size)
                for price, quantity in (*book.bids.items(), *book.asks.items())
            ):
                reason = "BOOK_CONTRACT_FILTER"
            elif owned is not None and D(owned["quantity"]) != 0:
                reason = "POSITION_ALREADY_EXISTS"
            order_id = (
                "paper_" + digest({"instance": self.instance_id, "client": ticket.client_id})[:32]
            )
            response = (
                OrderRejected(ticket.client_id, order_id, digest(ticket), now, reason)
                if reason
                else OrderAccepted(ticket.client_id, order_id, digest(ticket), now)
            )
            filled = ZERO
            if reason is None:
                sweep = book.sweep(ticket.side, ticket.quantity, ticket.limit_price, consume=True)
                filled = sweep.filled
                _, counter = self.journal.snapshot("model-fill-sequence")
                sequence = 0 if counter is None else counter["value"]
                for index, part in enumerate(sweep.fills):
                    sequence += 1
                    fill = Fill(
                        order_id + ":fill:" + str(index),
                        order_id,
                        ticket.signal_id,
                        ticket.symbol,
                        ticket.side,
                        part.quantity,
                        part.price,
                        part.quantity * part.price * D(raw_terms["entry_fee_rate"]),
                        now,
                        now,
                    )
                    self._emit(
                        db,
                        ticket,
                        order_id,
                        "FILL",
                        "fill:" + str(index),
                        now,
                        {"record": FillRecord(fill, sequence)},
                    )
                save_tx(db, "model-fill-sequence", {"value": sequence})
                save_tx(db, "model-book:" + ticket.symbol, book_record(book))
                save_tx(
                    db,
                    "model-position:" + ticket.signal_id,
                    {"symbol": ticket.symbol, "side": ticket.side, "quantity": filled},
                )
            outcome = (
                "REJECTED" if reason else "FILLED" if filled == ticket.quantity else "CANCELED"
            )
            self._emit(
                db,
                ticket,
                order_id,
                "TERMINAL",
                "terminal",
                now,
                {
                    "venue_order_id": order_id,
                    "outcome": outcome,
                    "cumulative_fill_quantity": filled,
                },
            )
            save_tx(
                db,
                stream,
                {
                    "ticket": ticket,
                    "receipt": response,
                    "outcome": outcome,
                    "filled_quantity": filled,
                    "market": raw_book,
                    "terms": raw_terms,
                    "quality": Quality.PRELIMINARY,
                },
            )
            return response

    def _run_pending(self, db, symbol, now):
        from pvb24.integrations.paper_venue_actions import run_pending

        return run_pending(self, db, symbol, now)

    def submit_action(self, ticket):
        from pvb24.integrations.paper_venue_actions import submit_action

        return submit_action(self, ticket)

    def publish_last(self, symbol, price, *, event_time, available_at, source_event_id):
        from pvb24.integrations.paper_venue_actions import publish_last

        return publish_last(
            self,
            symbol,
            price,
            event_time=event_time,
            available_at=available_at,
            source_event_id=source_event_id,
        )
