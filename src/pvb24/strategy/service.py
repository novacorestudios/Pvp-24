"""Shared journal-backed signal batching for reference and paper adapters."""

from datetime import timedelta

from pvb24.accounting.ledger import LedgerStore
from pvb24.data.lifecycle import entry_block_reason
from pvb24.data.universe import Universe
from pvb24.execution.protection import Protection
from pvb24.risk.reservations import Reservations
from pvb24.strategy.signals import Indicators, signal_batch
from pvb24.types import Quality, utc


class SignalService:
    def __init__(self, journal, scope, quality):
        if not scope or not isinstance(quality, Quality):
            raise ValueError("Explicit scope and quality required")
        self.journal, self.scope, self.quality = journal, scope, quality

    def evaluate(self, universe: Universe, signal_time, now):
        now, signal_time = utc(now), utc(signal_time)
        if universe.decision_time > now:
            raise ValueError("Universe is not yet available")
        if self.quality is Quality.VERIFIED and universe.quality is not Quality.VERIFIED:
            raise ValueError("Historical universe quality is not VERIFIED")
        with self.journal.transaction():
            frames, status = {}, {}
            for symbol in universe.symbols:
                _, state = self.journal.snapshot("indicators:" + self.scope + ":" + symbol)
                if state is not None:
                    frame = Indicators.restore(state).last_frame
                    if frame is not None:
                        frames[symbol] = frame
                status[symbol] = {
                    "has_position": False,
                    "pending_entry": False,
                    "entry_block_reason": entry_block_reason(
                        self.journal.db, self.scope, symbol, now
                    ),
                }
            _, portfolio = Reservations(self.journal, self.scope).read()
            for p in portfolio.exposures:
                if p.symbol in status and p.remaining_quantity > 0:
                    status[p.symbol]["pending_entry" if p.pending else "has_position"] = True
            _, ledger = LedgerStore(self.journal, self.scope).read()
            for owner in ledger.owners.values():
                if owner.symbol not in status:
                    continue
                _, state = self.journal.snapshot(
                    "protection:" + self.scope + ":" + owner.position_id
                )
                if state is None:
                    raise ValueError("Owned position missing protection state")
                protection = Protection.restore(state)
                # Actual fills remain authoritative while portfolio reconciliation is pending.
                if protection.remaining > 0:
                    status[owner.symbol]["has_position"] = True
                if not protection.terminal:
                    status[owner.symbol]["pending_entry"] = True
                if protection.full_exit_time is not None:
                    cooldown = protection.full_exit_time + timedelta(hours=6)
                    previous = status[owner.symbol].get("cooldown_end")
                    status[owner.symbol]["cooldown_end"] = max(previous or cooldown, cooldown)
            return signal_batch(frames, universe, signal_time, now, status)
