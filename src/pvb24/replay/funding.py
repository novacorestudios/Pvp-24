"""Causal replay position-boundary evidence for exact-source funding payments.

This adapter proves only the strategy's owned replay quantity at one exact settlement
boundary from already-received fill evidence. It does not attest an exchange funding
calendar, publication history, or missing settlements.
"""

from datetime import datetime
from itertools import groupby

from pvb24.accounting.ledger import Ledger, ReconciliationRequired
from pvb24.data.funding_usability import (
    FundingEligibilityEvidence,
    funding_payment_from_exact_source,
    source_funding_economics,
)
from pvb24.decimal_math import ZERO
from pvb24.ids import digest
from pvb24.types import utc

REPLAY_BOUNDARY_SOURCE = "PVB24_CAUSAL_REPLAY_POSITION_BOUNDARY_V1"


def _boundary_quantity(
    ledger: Ledger,
    position_id: str,
    settlement: datetime,
    known_at: datetime,
):
    settlement, known_at = utc(settlement), utc(known_at)
    if known_at < settlement:
        raise ValueError("Funding boundary cannot be known before settlement")
    owner = ledger.owners.get(position_id)
    if owner is None:
        raise ReconciliationRequired("Unknown replay funding position ownership")
    if owner.available_at > settlement:
        return ZERO, ()

    selected = [
        record
        for record in ledger.fills.values()
        if record.fill.position_id == position_id
        and record.fill.event_time <= settlement
        and record.fill.received_at <= known_at
    ]
    hidden = [
        record
        for record in ledger.fills.values()
        if record.fill.position_id == position_id
        and record.fill.event_time <= settlement
        and record.fill.received_at > known_at
    ]
    if hidden:
        raise ReconciliationRequired("Future-received fill cannot certify funding boundary")

    selected.sort(key=lambda record: (record.fill.event_time, record.fill.fill_id))
    ordered = []
    for _, grouped in groupby(selected, key=lambda record: record.fill.event_time):
        group = list(grouped)
        if len(group) > 1 and all(record.exchange_sequence is not None for record in group):
            if len({record.exchange_sequence for record in group}) != len(group):
                raise ReconciliationRequired(
                    "Conflicting exchange fill sequences at funding boundary"
                )
            group.sort(key=lambda record: record.exchange_sequence)
        else:
            if len({record.fill.reduce_only for record in group}) > 1:
                raise ReconciliationRequired("Ambiguous fill ordering at funding boundary")
            group.sort(key=lambda record: (not record.liquidation, record.fill.fill_id))
        ordered.extend(group)

    quantity = ZERO
    for record in ordered:
        fill = record.fill
        if fill.reduce_only:
            if fill.quantity > quantity:
                raise ReconciliationRequired(
                    "Boundary reduction exceeds known owned quantity"
                )
            quantity -= fill.quantity
        else:
            quantity += fill.quantity
    return quantity, tuple(ordered)


def replay_funding_payments(ledger: Ledger, entry, known_at: datetime):
    """Create payments for open owned positions at one exact source settlement boundary.

    The source row supplies economics. Replay fills supply only the position quantity.
    No payment is emitted for a flat position. Evidence available after known_at is
    excluded, while fills occurring after settlement are excluded even when already
    known at payment time.
    """
    if not isinstance(ledger, Ledger):
        raise TypeError("Replay Ledger required")
    row, settlement, source_available, _, _ = source_funding_economics(entry)
    known_at = utc(known_at)
    if known_at < source_available:
        raise ValueError("Replay funding seal cannot predate source availability")

    payments = []
    for owner in sorted(ledger.owners.values(), key=lambda item: item.position_id):
        if owner.symbol != row["symbol"] or owner.available_at > settlement:
            continue
        quantity, fills = _boundary_quantity(
            ledger,
            owner.position_id,
            settlement,
            known_at,
        )
        if quantity == 0:
            continue
        revision = digest(
            {
                "schema": REPLAY_BOUNDARY_SOURCE,
                "owner": owner,
                "settlement_time": settlement,
                "known_at": known_at,
                "fills": fills,
            }
        )
        eligibility = FundingEligibilityEvidence(
            position_id=owner.position_id,
            symbol=owner.symbol,
            side=owner.side,
            eligible_quantity=quantity,
            settlement_time=settlement,
            available_at=known_at,
            source=REPLAY_BOUNDARY_SOURCE,
            revision_id=revision,
            boundary_verified=True,
        )
        payments.append(funding_payment_from_exact_source(entry, eligibility))
    return tuple(payments)
