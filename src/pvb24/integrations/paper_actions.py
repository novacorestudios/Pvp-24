"""Owned reduce-only and cancellation tickets for the PAPER dispatch contract.

Order acceptance is not proof of an active stop or successful cancellation.
Those outcomes must be ingested separately by the shared account reducer.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from pvb24.accounting.coordinator import read_tx
from pvb24.decimal_math import CONTEXT, ZERO, D
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, client_identity, digest
from pvb24.state import Conflict, Journal
from pvb24.types import Side, utc

ACTION_CONTRACT = "PVB24_PAPER_REDUCE_ONLY_LAST_STOP_CANCEL_V1"
PURPOSES = ("PROTECT", "EXIT_MARKET", "CANCEL_PROTECTION", "CANCEL_ENTRY")


@dataclass(frozen=True)
class ActionTicket:
    client_id: str
    signal_id: str
    symbol: str
    side: Side
    purpose: str
    sequence: int
    quantity: Decimal
    stop_price: Decimal | None
    target_client_id: str | None
    target_order_id: str | None
    prepared_at: datetime
    input_digest: str
    order_type: str
    mode: str = "PAPER"
    reduce_only: bool = True
    stop_reference: str = "CONTRACT_PRICE"
    deadline: datetime | None = None


def guard_actions(host):
    host._guard()
    if getattr(host.backend, "action_contract", None) != ACTION_CONTRACT:
        raise ValueError("PAPER backend must explicitly support reduce-only/LAST/cancel contract")


def accepted_order(db, client_id):
    row = db.execute(
        "SELECT payload FROM events WHERE event_id IN (?,?)",
        ("paper-accepted:" + client_id, "paper-rejected:" + client_id),
    ).fetchone()
    if row is None:
        raise Conflict("Target order identity is unresolved; query before cancellation")
    return json.loads(row["payload"])["order_id"]


def _build(host, db, row, now):
    sid, purpose = row["signal_id"], row["purpose"]
    _, mode = read_tx(db, "replay-account:" + host.scope)
    if mode["quality"] != host.quality:
        raise Conflict("Action quality differs from frozen account policy")
    _, gate = read_tx(db, "account-gate:" + host.scope)
    for stamp in (mode["last_time"], gate.get("last_evidence_at")):
        if stamp is not None and datetime.fromisoformat(stamp) > now:
            raise Conflict("Cannot backdate action behind confirmed account evidence")
    # A paused entry gate must never block owned protective or exit requests.
    _, raw = read_tx(db, "protection:" + host.scope + ":" + sid)
    p = Protection.restore(raw)
    payload = json.loads(row["payload"])
    sequence = 0 if purpose == "CANCEL_ENTRY" else payload["sequence"]
    if purpose not in PURPOSES:
        raise Conflict("Unsupported PAPER action")
    if purpose != "CANCEL_ENTRY":
        action = p.actions.get(sequence)
        if action is None or canonical(action) != canonical(payload) or action.purpose != purpose:
            raise Conflict("Action intent differs from owned protection state")
        if action.reduce_only is not True or action.stop_reference != "CONTRACT_PRICE":
            raise Conflict("Only reduce-only actions with LAST reference are permitted")
    else:
        action = None
    quantity = ZERO if action is None else action.quantity
    stop = None if action is None else action.stop
    target_id = target_order = None
    if purpose in ("PROTECT", "EXIT_MARKET"):
        if not ZERO < quantity <= p.remaining:
            raise Conflict("Action quantity exceeds confirmed remaining position")
        if purpose == "PROTECT":
            if stop is None or stop <= 0 or stop % p.tick or stop != p.effective_stop:
                raise Conflict("Stale or invalid protective stop proposal")
        else:
            # Already-sent exits reserve only their not-yet-filled amount. An
            # UNKNOWN order without a mapped venue ID reserves its full quantity.
            pending = db.execute(
                "SELECT client_id,payload FROM intents WHERE scope=? AND signal_id=? "
                "AND purpose='EXIT_MARKET' AND state IN ('UNKNOWN','ACKNOWLEDGED')",
                (host.scope, sid),
            ).fetchall()
            outstanding = ZERO
            for other in pending:
                requested = D(json.loads(other["payload"])["quantity"])
                try:
                    order_id = accepted_order(db, other["client_id"])
                except Conflict:
                    filled = ZERO
                else:
                    filled = sum(
                        (
                            f.quantity
                            for f in p.fills.values()
                            if f.reduce_only and f.order_id == order_id
                        ),
                        ZERO,
                    )
                outstanding += max(ZERO, requested - filled)
            if quantity + outstanding > p.remaining:
                raise Conflict("Unresolved exit already reserves this remaining quantity")
    else:
        if purpose == "CANCEL_ENTRY":
            _, _, target_id = client_identity(host.scope, sid, "ENTRY")
            if payload.get("target_client_id") != target_id:
                raise Conflict("Cancel target differs from owned entry")
        else:
            target = action.target_sequence
            if target not in p.confirmed_stops - p.canceled_stops:
                raise Conflict("Cancel target is not an acknowledged active stop")
            replacement = any(
                i != target
                and p.actions[i].quantity >= p.remaining
                and p.actions[i].stop == p.effective_stop
                for i in p.confirmed_stops - p.canceled_stops
            )
            if p.remaining != 0 and not replacement:
                raise Conflict("Cancellation would remove the only confirmed protection")
            _, _, target_id = client_identity(host.scope, sid, "PROTECT", target)
        target = db.execute("SELECT * FROM intents WHERE client_id=?", (target_id,)).fetchone()
        if target is None or target["state"] not in ("UNKNOWN", "ACKNOWLEDGED"):
            raise Conflict("Cancel target has no unresolved dispatched order")
        target_order = accepted_order(db, target_id)
    # Confirmed fills can be received after an action was prepared; retain the
    # exact immutable action quantity or reject, never silently resize its ID.
    evidence = {
        "position": p.checkpoint(),
        "intent": payload,
        "target_client_id": target_id,
        "target_order_id": target_order,
        "action_contract": ACTION_CONTRACT,
    }
    Journal.append_tx(db, "paper-inputs:" + row["client_id"], evidence)
    return ActionTicket(
        row["client_id"],
        sid,
        p.symbol,
        Side.SHORT if p.side is Side.LONG else Side.LONG,
        purpose,
        sequence,
        quantity,
        stop,
        target_id,
        target_order,
        now,
        digest(evidence),
        "STOP_MARKET"
        if purpose == "PROTECT"
        else "MARKET"
        if purpose == "EXIT_MARKET"
        else "CANCEL",
    )


def dispatch_action(host, client_id):
    guard_actions(host)
    now = utc(host.clock())
    with host.journal.transaction() as db, localcontext(CONTEXT):
        row = host._intent(db, client_id, purposes=PURPOSES)
        if row["state"] != "PREPARED":
            raise Conflict("Previously dispatched or terminal action: query, never resend")
        ticket = _build(host, db, row, now)
        Journal.append_tx(db, "paper-ticket:" + client_id, ticket)
        if not host.journal.claim_dispatch(client_id):
            raise Conflict("Action dispatch claim denied")
    guard_actions(host)
    response = host.backend.submit_action(ticket)
    host._acknowledge(ticket, response)
    return response
