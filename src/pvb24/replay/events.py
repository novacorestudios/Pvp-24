"""Causal event scheduling with explicit same-time ordering evidence.

Only a complete equal-event-time group in one sequence domain can be sorted by
venue sequence. Sequence numbers from different feeds are never comparable.
The caller must supply the complete available-time batch before advancing its
watermark; unseen backdated data are rejected, not inserted into past decisions.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from itertools import groupby

from pvb24.ids import canonical, digest
from pvb24.types import Quality, utc


class Kind(IntEnum):
    OBSERVATION = 0  # install causal source inputs; cannot make trading decisions
    LIQUIDATION = 10
    PROTECTIVE_FILL = 20
    REDUCE_FILL = 30
    ENTRY_FILL = 35  # an already-dispatched order, not a new entry decision
    FUNDING = 40
    ORDER_OUTCOME = 45
    ACCOUNT_RISK = 50
    EXIT_DECISION = 60
    TRAILING = 70
    ENTRY_DECISION = 80


@dataclass(frozen=True)
class Event:
    event_id: str
    kind: Kind
    event_time: datetime
    available_at: datetime
    source: str
    quality: Quality
    payload_json: str
    exchange_sequence: int | None = None
    sequence_domain: str | None = None

    def __post_init__(self):
        if not self.event_id or not self.source:
            raise ValueError("Event identity and source required")
        if not isinstance(self.kind, Kind) or not isinstance(self.quality, Quality):
            raise TypeError("Explicit kind and quality required")
        if utc(self.event_time) > utc(self.available_at):
            raise ValueError("Event unavailable before occurrence")
        if canonical(json.loads(self.payload_json)) != self.payload_json:
            raise ValueError("Immutable canonical payload required")
        if self.exchange_sequence is None:
            if self.sequence_domain is not None:
                raise ValueError("Sequence domain without sequence")
        elif (
            type(self.exchange_sequence) is not int
            or self.exchange_sequence < 0
            or not self.sequence_domain
        ):
            raise ValueError("Nonnegative sequence and its comparable domain required")

    @property
    def payload(self):
        return json.loads(self.payload_json)


@dataclass(frozen=True)
class Delivery:
    event: Event
    ordering: str
    ambiguous_event_count: int


def ordered_batch(events: Iterable[Event]) -> tuple[Delivery, ...]:
    """Order one complete available-time batch without inspecting later data."""
    events = list(events)
    if len({e.available_at for e in events}) > 1:
        raise ValueError("One available-time batch required")
    result = []
    for _, grouped in groupby(sorted(events, key=lambda e: e.event_time), lambda e: e.event_time):
        group = list(grouped)
        sequenced = (
            all(e.exchange_sequence is not None for e in group)
            and len({e.sequence_domain for e in group}) == 1
            and len({e.exchange_sequence for e in group}) == len(group)
        )
        key = (lambda e: e.exchange_sequence) if sequenced else (lambda e: (e.kind, e.event_id))
        kinds = {e.kind for e in group}
        ambiguous = not sequenced and Kind.LIQUIDATION in kinds and Kind.PROTECTIVE_FILL in kinds
        for index, event in enumerate(sorted(group, key=key)):
            result.append(
                Delivery(
                    event,
                    "EXCHANGE_SEQUENCE" if sequenced else "CONSERVATIVE_PRIORITY",
                    int(ambiguous and index == 0),
                )
            )
    return tuple(result)


class Replay:
    """Deterministic in-memory scheduler; handlers own their state/checkpointing.

    Failed deliveries poison this instance: restart from the last coordinated
    checkpoint, rather than retry a potentially half-applied callback. This core
    alone does not promise crash-atomic account/adapter integration.
    """

    def __init__(self, quality: Quality):
        if not isinstance(quality, Quality):
            raise TypeError("Explicit replay quality required")
        self.quality = quality
        self.watermark = None
        self.events: dict[str, Event] = {}
        self.delivered: set[str] = set()
        self.trace: list[dict] = []
        self.ambiguous_event_count = 0
        self.failed = False
        self.running = False

    def add(self, events: Iterable[Event]):
        if self.running:
            raise RuntimeError("Cannot mutate an active offline replay batch")
        pending = dict(self.events)
        for event in events:
            if self.quality is Quality.VERIFIED and event.quality is not Quality.VERIFIED:
                raise ValueError("VERIFIED replay cannot promote preliminary evidence")
            previous = pending.get(event.event_id)
            if previous is not None:
                if previous != event:
                    raise ValueError("Event identity reused with revised evidence")
                continue
            if self.watermark is not None and event.available_at <= self.watermark:
                raise ValueError("Unseen event at or before sealed availability watermark")
            pending[event.event_id] = event
        self.events = pending

    def run(self, until: datetime, handle: Callable[[Delivery], object]):
        until = utc(until)
        if self.failed:
            raise RuntimeError("Failed replay requires checkpoint recovery")
        if self.watermark is not None and until < self.watermark:
            raise ValueError("Replay clock cannot go backwards")
        ready = sorted(
            (
                e
                for e in self.events.values()
                if e.event_id not in self.delivered and e.available_at <= until
            ),
            key=lambda e: e.available_at,
        )
        for _, grouped in groupby(ready, lambda e: e.available_at):
            for delivery in ordered_batch(grouped):
                try:
                    self.running = True
                    output = handle(delivery)
                    row = {
                        "event_id": delivery.event.event_id,
                        "event_hash": digest(delivery.event),
                        "available_at": delivery.event.available_at,
                        "ordering": delivery.ordering,
                        "ambiguous_event_count": delivery.ambiguous_event_count,
                        "output": output,
                    }
                    # Validate output now; mutable callback objects cannot alter history.
                    row = json.loads(canonical(row))
                except BaseException:
                    self.failed = True
                    raise
                finally:
                    self.running = False
                self.trace.append(row)
                self.delivered.add(delivery.event.event_id)
                self.ambiguous_event_count += delivery.ambiguous_event_count
        self.watermark = until
        return tuple(self.trace)

    @property
    def trace_hash(self):
        return digest(self.trace)
