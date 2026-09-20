"""Durable visible-L2 reductions and LAST stop activation for the PAPER model.

Pending market residuals and acceptance-order stop processing are explicit
PRELIMINARY model assumptions, not a reconstruction of exchange queue priority.
"""

import json
from datetime import datetime, timedelta
from decimal import localcontext

from pvb24.accounting.coordinator import read_tx, save_tx
from pvb24.accounting.ledger import FillRecord
from pvb24.decimal_math import CONTEXT, ZERO, D, require_decimal
from pvb24.ids import canonical, client_identity, digest
from pvb24.integrations.paper_actions import PURPOSES, ActionTicket
from pvb24.integrations.paper_dispatch import OrderAccepted, OrderRejected
from pvb24.integrations.paper_venue import book_record, receipt, restore_book, restore_rules
from pvb24.state import Conflict, Journal
from pvb24.types import Fill, Quality, Side, utc


def restore_ticket(raw):
    values = dict(raw)
    values["side"] = Side(values["side"])
    values["quantity"] = D(values["quantity"])
    if values["stop_price"] is not None:
        values["stop_price"] = D(values["stop_price"])
    values["prepared_at"] = datetime.fromisoformat(values["prepared_at"])
    return ActionTicket(**values)


def _orders(venue, symbol, outcomes):
    rows = venue.journal.db.execute(
        "SELECT payload FROM snapshots WHERE stream LIKE 'model-order:%'"
    ).fetchall()
    selected = [json.loads(row["payload"]) for row in rows]
    return sorted(
        (r for r in selected if r["ticket"]["symbol"] == symbol and r["outcome"] in outcomes),
        key=lambda r: (r["order_sequence"], r["ticket"]["client_id"]),
    )


def _finish(venue, db, row, outcome, now):
    ticket = restore_ticket(row["ticket"])
    row["outcome"] = outcome
    venue._emit(
        db,
        ticket,
        row["receipt"]["order_id"],
        "TERMINAL",
        "terminal",
        now,
        {
            "venue_order_id": row["receipt"]["order_id"],
            "outcome": outcome,
            "cumulative_fill_quantity": D(row["filled_quantity"]),
        },
    )
    save_tx(db, "model-order:" + ticket.client_id, row)


def run_pending(venue, db, symbol, now):
    """Fill only available visible depth; never mark an unfilled residual closed."""
    with localcontext(CONTEXT):
        for row in _orders(venue, symbol, ("PENDING",)):
            ticket = restore_ticket(row["ticket"])
            _, position = read_tx(db, "model-position:" + ticket.signal_id)
            remaining = D(position["quantity"])
            already = D(row["filled_quantity"])
            requested = ticket.quantity - already
            if remaining == 0:
                _finish(venue, db, row, "CANCELED", now)
                continue
            _, raw_book = venue.journal.snapshot("model-book:" + symbol)
            _, terms = venue.journal.snapshot("model-terms:" + symbol)
            book = None if raw_book is None else restore_book(raw_book)
            rules = None if terms is None else restore_rules(terms["rules"])
            if book is None or not book.fresh(now) or not book.bids or not book.asks:
                reason = "NO_FRESH_VISIBLE_DEPTH"
            elif (
                rules is None
                or terms.get("exit_fee_rate") is None
                or rules.available_at > now
                or rules.effective_from > now
                or (rules.effective_to is not None and rules.effective_to <= now)
            ):
                reason = "EXIT_TERMS_UNAVAILABLE"
            elif any(
                p % rules.tick or q % (rules.quantity_step * rules.contract_size)
                for p, q in (*book.bids.items(), *book.asks.items())
            ):
                reason = "BOOK_CONTRACT_FILTER"
            else:
                reason = None
            if reason:
                row["pending_reason"] = reason
                save_tx(db, "model-order:" + ticket.client_id, row)
                continue
            levels = book.asks if ticket.side is Side.LONG else book.bids
            limit = max(levels) if ticket.side is Side.LONG else min(levels)
            sweep = book.sweep(ticket.side, min(requested, remaining), limit, consume=True)
            _, counter = venue.journal.snapshot("model-fill-sequence")
            sequence = 0 if counter is None else counter["value"]
            for part in sweep.fills:
                sequence += 1
                suffix = "fill:" + str(sequence)
                fill = Fill(
                    row["receipt"]["order_id"] + ":" + suffix,
                    row["receipt"]["order_id"],
                    ticket.signal_id,
                    symbol,
                    ticket.side,
                    part.quantity,
                    part.price,
                    part.quantity * part.price * D(terms["exit_fee_rate"]),
                    now,
                    now,
                    reduce_only=True,
                )
                venue._emit(
                    db,
                    ticket,
                    fill.order_id,
                    "FILL",
                    suffix,
                    now,
                    {"record": FillRecord(fill, sequence)},
                )
            save_tx(db, "model-fill-sequence", {"value": sequence})
            save_tx(db, "model-book:" + symbol, book_record(book))
            position["quantity"] = remaining - sweep.filled
            save_tx(db, "model-position:" + ticket.signal_id, position)
            row["filled_quantity"] = already + sweep.filled
            row["last_execution_inputs"] = {"book": raw_book, "terms": terms, "time": now}
            if row["filled_quantity"] == ticket.quantity:
                _finish(venue, db, row, "FILLED", now)
            elif position["quantity"] == 0:
                _finish(venue, db, row, "CANCELED", now)
            else:
                row["pending_reason"] = "VISIBLE_DEPTH_EXHAUSTED"
                save_tx(db, "model-order:" + ticket.client_id, row)


def _rejection(venue, ticket, now, position, terms, last):
    if position is None or D(position["quantity"]) <= 0 or position["symbol"] != ticket.symbol:
        return "NO_OWNED_POSITION"
    exit_side = Side.SHORT if Side(position["side"]) is Side.LONG else Side.LONG
    if ticket.side is not exit_side or ticket.quantity <= 0:
        return "INVALID_REDUCTION_SIDE_OR_QUANTITY"
    if terms is None:
        return "CONTRACT_RULES_UNAVAILABLE"
    rules = restore_rules(terms["rules"])
    if (
        rules.available_at > now
        or rules.effective_from > now
        or (rules.effective_to is not None and rules.effective_to <= now)
        or ticket.quantity % (rules.quantity_step * rules.contract_size)
    ):
        return "CONTRACT_FILTER"
    if ticket.purpose == "PROTECT":
        if (
            not rules.supports_last_stop
            or ticket.stop_price is None
            or ticket.stop_price <= 0
            or ticket.stop_price % rules.tick
        ):
            return "INVALID_LAST_STOP"
        if (
            venue.max_last_age is None
            or last is None
            or any(
                not timedelta(0) <= now - datetime.fromisoformat(last[key]) <= venue.max_last_age
                for key in ("event_time", "available_at")
            )
        ):
            return "LAST_SOURCE_UNAVAILABLE"
        if Side(position["side"]).sign * (D(last["price"]) - ticket.stop_price) <= 0:
            return "STOP_ALREADY_CROSSED"
    return None


def submit_action(venue, ticket):
    now = venue._now()
    if not isinstance(ticket, ActionTicket) or ticket.purpose not in PURPOSES:
        raise TypeError("Immutable supported action ticket required")
    _, _, expected_id = client_identity(
        venue.scope, ticket.signal_id, ticket.purpose, ticket.sequence
    )
    expected_type = (
        "STOP_MARKET"
        if ticket.purpose == "PROTECT"
        else "MARKET"
        if ticket.purpose == "EXIT_MARKET"
        else "CANCEL"
    )
    if (
        ticket.client_id != expected_id
        or ticket.mode != "PAPER"
        or ticket.reduce_only is not True
        or ticket.stop_reference != "CONTRACT_PRICE"
        or ticket.order_type != expected_type
        or ticket.deadline is not None
        or ticket.prepared_at > now
    ):
        raise Conflict("Action violates owned PAPER reduce-only/LAST contract")
    with venue.journal.transaction() as db, localcontext(CONTEXT):
        venue._advance(db, now)
        stream = "model-order:" + ticket.client_id
        _, existing = venue.journal.snapshot(stream)
        if existing is not None:
            if canonical(existing["ticket"]) != canonical(ticket):
                raise Conflict("Backend action identity reused with changed ticket")
            return receipt(existing["receipt"])
        _, position = venue.journal.snapshot("model-position:" + ticket.signal_id)
        _, terms = venue.journal.snapshot("model-terms:" + ticket.symbol)
        _, last = venue.journal.snapshot("model-last:" + ticket.symbol)
        target = None
        if ticket.purpose.startswith("CANCEL_"):
            _, target = venue.journal.snapshot("model-order:" + str(ticket.target_client_id))
            target_purpose = "ENTRY" if ticket.purpose == "CANCEL_ENTRY" else "PROTECT"
            actual_purpose = None if target is None else target["ticket"].get("purpose", "ENTRY")
            reason = (
                "UNKNOWN_CANCEL_TARGET"
                if (
                    target is None
                    or target["ticket"]["signal_id"] != ticket.signal_id
                    or target["receipt"]["order_id"] != ticket.target_order_id
                    or actual_purpose != target_purpose
                )
                else None
            )
        else:
            reason = _rejection(venue, ticket, now, position, terms, last)
        order_id = (
            "paper_" + digest({"instance": venue.instance_id, "client": ticket.client_id})[:32]
        )
        response = (
            OrderRejected(ticket.client_id, order_id, digest(ticket), now, reason)
            if reason
            else OrderAccepted(ticket.client_id, order_id, digest(ticket), now)
        )
        _, counter = venue.journal.snapshot("model-order-sequence")
        sequence = 1 if counter is None else counter["value"] + 1
        save_tx(db, "model-order-sequence", {"value": sequence})
        row = json.loads(
            canonical(
                {
                    "ticket": ticket,
                    "receipt": response,
                    "order_sequence": sequence,
                    "filled_quantity": ZERO,
                    "outcome": "REJECTED" if reason else "OPEN",
                    "terms": terms,
                    "last": last,
                    "quality": Quality.PRELIMINARY,
                }
            )
        )
        save_tx(db, stream, row)
        if reason:
            _finish(venue, db, row, "REJECTED", now)
        elif ticket.purpose == "PROTECT":
            venue._emit(
                db,
                ticket,
                order_id,
                "STOP_ACTIVE",
                "active",
                now,
                {
                    "venue_order_id": order_id,
                    "quantity": ticket.quantity,
                    "stop": ticket.stop_price,
                    "reduce_only": True,
                    "reference": "CONTRACT_PRICE",
                },
            )
        elif ticket.purpose == "EXIT_MARKET":
            row["outcome"] = "PENDING"
            save_tx(db, stream, row)
            run_pending(venue, db, ticket.symbol, now)
        else:
            if target["outcome"] in ("OPEN", "PENDING"):
                _finish(venue, db, target, "CANCELED", now)
            # Terminal entry/stop can win the race; never erase its fills.
            row["outcome"] = "ACKNOWLEDGED"
            save_tx(db, stream, row)
            venue._emit(
                db,
                ticket,
                order_id,
                "CANCEL_CONFIRMED",
                "cancel",
                now,
                {
                    "request_order_id": order_id,
                    "target_client_id": ticket.target_client_id,
                    "venue_order_id": ticket.target_order_id,
                    "outcome": target["outcome"],
                    "cumulative_fill_quantity": D(target["filled_quantity"]),
                },
            )
        return response


def publish_last(venue, symbol, price, *, event_time, available_at, source_event_id):
    now = venue._now()
    require_decimal(price, positive=True)
    if (
        venue.max_last_age is None
        or not source_event_id
        or not utc(event_time) <= utc(available_at) <= now
    ):
        raise ValueError("Explicit LAST policy and causal source observation required")
    evidence = {
        "symbol": symbol,
        "price": price,
        "event_time": event_time,
        "available_at": available_at,
        "price_type": "LAST",
    }
    with venue.journal.transaction() as db, localcontext(CONTEXT):
        venue._advance(db, now)
        if not Journal.append_tx(db, "model-last-source:" + source_event_id, evidence):
            return False
        stream = "model-last:" + symbol
        _, previous = venue.journal.snapshot(stream)
        if previous is not None and (
            datetime.fromisoformat(previous["available_at"]) > available_at
            or datetime.fromisoformat(previous["event_time"]) > event_time
        ):
            raise Conflict("LAST source clock moved backwards")
        save_tx(db, stream, evidence)
        for row in _orders(venue, symbol, ("OPEN",)):
            if row["ticket"]["purpose"] != "PROTECT":
                continue
            ticket = restore_ticket(row["ticket"])
            if event_time < datetime.fromisoformat(row["receipt"]["accepted_at"]):
                continue  # pre-activation trades cannot retroactively hit the stop
            if now - event_time > venue.max_last_age or now - available_at > venue.max_last_age:
                continue
            # Sell stops trigger at/below stop; buy stops at/above stop.
            if ticket.side.sign * (price - ticket.stop_price) >= 0:
                row["outcome"] = "PENDING"
                row["trigger"] = evidence
                save_tx(db, "model-order:" + ticket.client_id, row)
        run_pending(venue, db, symbol, now)
        return True
