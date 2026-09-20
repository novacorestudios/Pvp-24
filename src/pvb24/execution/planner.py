"""Ranked shared-core sizing and atomic entry reservation; no order dispatch."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pvb24.accounting.coordinator import AccountCoordinator, read_tx, save_tx
from pvb24.data.contract_rules import ContractRules
from pvb24.data.lifecycle import entry_block_reason
from pvb24.decimal_math import CONTEXT, D, require_decimal
from pvb24.execution.market import EntryBounds
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, digest
from pvb24.risk.reservations import Reservations
from pvb24.risk.sizing import MarginModel, QuoteModel, size_entry
from pvb24.state import Conflict, Journal
from pvb24.strategy.signals import Batch, rank_signals
from pvb24.types import Quality, Side, utc


@dataclass(frozen=True)
class EntryInputs:
    rules: ContractRules
    quote_model: QuoteModel
    recent_quote_volume: Decimal
    available_at: datetime
    snapshot_id: str
    margin_model: MarginModel | None = None
    maximum_quantity: Decimal | None = None

    def __post_init__(self):
        require_decimal(self.recent_quote_volume, positive=True)
        utc(self.available_at)
        if not self.snapshot_id or not callable(self.quote_model):
            raise ValueError("Immutable source snapshot and quote model required")
        if self.maximum_quantity is not None:
            require_decimal(self.maximum_quantity, nonnegative=True)

    def provenance(self):
        # The source adapter binds callback behavior to this immutable input identity.
        return {
            "rules": self.rules,
            "recent_quote_volume": self.recent_quote_volume,
            "available_at": self.available_at,
            "snapshot_id": self.snapshot_id,
            "maximum_quantity": self.maximum_quantity,
        }


class EntryPlanner:
    def __init__(self, journal: Journal, scope: str, quality: Quality):
        if not scope or not isinstance(quality, Quality):
            raise ValueError("Explicit scope and quality required")
        self.journal, self.scope, self.quality = journal, scope, quality
        self.reservations = Reservations(journal, scope)
        self.coordinator = AccountCoordinator(journal, scope)

    def plan(self, batch: Batch, inputs: dict[str, EntryInputs], now: datetime):
        now = utc(now)
        if now < batch.decision_time or tuple(rank_signals(list(batch.decisions))) != batch.ranked:
            raise ValueError("Invalid batch clock or priority order")
        if not batch.decisions:
            return []
        times = {s.signal_time for s in batch.decisions}
        if len(times) != 1 or any(s.decision_time != batch.decision_time for s in batch.decisions):
            raise ValueError("One complete immutable signal batch required")
        signal_time = next(iter(times))
        key = "entry-plan:" + self.scope + ":" + signal_time.isoformat()
        evidence = digest(
            {
                "batch": batch,
                "inputs": {k: v.provenance() for k, v in inputs.items()},
                "now": now,
                "quality": self.quality,
            }
        )
        with self.journal.transaction() as db:
            previous = db.execute("SELECT payload FROM events WHERE event_id=?", (key,)).fetchone()
            if previous:
                receipt = json.loads(previous["payload"])
                if receipt["evidence"] != evidence:
                    raise Conflict("Hourly entry batch already consumed with different inputs")
                return receipt["results"]
            _, mode = read_tx(db, "replay-account:" + self.scope)
            if mode["last_time"] is not None and datetime.fromisoformat(mode["last_time"]) > now:
                raise Conflict("Cannot backdate entry planning")
            if mode["quality"] != self.quality:
                raise Conflict("Entry planner quality differs from account policy")
            _, control = read_tx(db, "equity-control:" + self.scope)
            status = control["last_status"]
            current = status is not None and datetime.fromisoformat(status["time"]) == now.replace(
                second=0, microsecond=0
            )
            _, gate = read_tx(db, self.coordinator.gate_stream)
            watermark = gate.get("last_evidence_at")
            if watermark is not None and datetime.fromisoformat(watermark) > now:
                raise Conflict("Account evidence is later than entry planning time")
            ready = current and status["entries_allowed"] and gate["ready"]
            results = []
            for signal in batch.ranked:
                source = inputs.get(signal.symbol)
                if now > signal.signal_time + timedelta(seconds=90):
                    reason = "ORDER_DEADLINE"
                elif entry_block_reason(db, self.scope, signal.symbol, now):
                    reason = entry_block_reason(db, self.scope, signal.symbol, now)
                elif not ready:
                    reason = "ACCOUNT_OR_RISK_GATE"
                elif source is None or source.available_at > now:
                    reason = "EXECUTION_INPUTS_UNAVAILABLE"
                else:
                    reason = None
                result = {
                    "signal_id": signal.signal_id,
                    "symbol": signal.symbol,
                    "side": signal.side,
                    "reason": reason,
                    "client_id": None,
                }
                if reason is None:
                    version, portfolio = self.reservations.read()
                    bounds = EntryBounds(
                        signal.symbol,
                        signal.side,
                        signal.signal_time,
                        signal.frame.candle.close,
                        signal.frame.channel_high
                        if signal.side is Side.LONG
                        else signal.frame.channel_low,
                        signal.frame.atr_previous,
                        source.rules.tick,
                    )

                    def quote(quantity, source=source, bounds=bounds):
                        q = source.quote_model(quantity)
                        if q is None or q.available_at > now:
                            return None
                        if not bounds.valid_price(q.expected_entry) or not bounds.valid_price(
                            q.arrival_side_price
                        ):
                            return None
                        try:
                            limit = bounds.ioc_limit(q.arrival_side_price)
                        except ValueError:
                            return None
                        with localcontext(CONTEXT):
                            if bounds.side.sign * (
                                q.expected_entry - limit
                            ) > 0 or quantity * q.expected_entry / source.recent_quote_volume > D(
                                "0.001"
                            ):
                                return None
                        return q

                    reduced = D(status["risk_fraction"]) == D("0.005")
                    sized = size_entry(
                        signal.symbol,
                        signal.side,
                        signal.frame.atr_previous,
                        now,
                        portfolio,
                        source.rules,
                        quote,
                        reduced=reduced,
                        require_verified=self.quality is Quality.VERIFIED,
                        margin_model=source.margin_model,
                        maximum_quantity=source.maximum_quantity,
                    )
                    result["reason"] = sized.reason
                    result["sizing"] = sized
                    if sized.entry is not None:
                        cid = self.reservations.reserve(
                            version,
                            signal.signal_id,
                            signal.symbol,
                            signal.side,
                            sized,
                            reduced=reduced,
                        )
                        self.coordinator.register_pending(
                            Protection(
                                signal.signal_id,
                                signal.symbol,
                                signal.side,
                                sized.entry.quantity,
                                signal.frame.atr_previous,
                                source.rules.tick,
                            ),
                            now,
                        )
                        save_tx(
                            db,
                            "replay-entry-terms:" + self.scope + ":" + signal.signal_id,
                            {
                                "channel_high": signal.frame.channel_high,
                                "channel_low": signal.frame.channel_low,
                            },
                        )
                        save_tx(
                            db,
                            "entry-metadata:" + self.scope + ":" + signal.signal_id,
                            {
                                "signal": signal,
                                "accepted_at": now,
                                "bounds": bounds,
                                "order_deadline": signal.signal_time + timedelta(seconds=90),
                                "source": source.provenance(),
                                "quality": self.quality,
                            },
                        )
                        result["client_id"] = cid
                results.append(result)
            results = json.loads(canonical(results))
            Journal.append_tx(
                db,
                key,
                {
                    "evidence": evidence,
                    "batch": batch,
                    "inputs": {k: v.provenance() for k, v in inputs.items()},
                    "results": results,
                },
            )
            return results
