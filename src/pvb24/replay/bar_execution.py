"""Adverse completed-bar protective/forced fills for preliminary sensitivity only."""

import json
from decimal import localcontext

from pvb24.accounting.coordinator import read_tx
from pvb24.accounting.ledger import FillRecord, ReconciliationRequired
from pvb24.decimal_math import CONTEXT, D, quantize_step, require_decimal
from pvb24.execution.market import preliminary_proxy
from pvb24.execution.protection import Protection
from pvb24.ids import canonical, client_identity, digest
from pvb24.replay.events import Delivery, Event, Kind
from pvb24.replay.preliminary import adverse_bar_exit
from pvb24.replay.venue import PreliminaryVenue
from pvb24.types import Fill, Quality, Side, utc


def resolve_bar(
    venue: PreliminaryVenue,
    position_id,
    last,
    mark,
    *,
    liquidation_price,
    sigma,
    recent_quote_volume,
    inputs_available_at,
    all_in_liquidation_fee_rate,
    liquidation_terms_available_at,
    model_manifest_id,
):
    """Inputs/model policy must be frozen before this bar; no intrabar timestamp claim.

    The forced-fill price uses the adverse Mark extreme, and its all-in fee rate
    is explicit. This is a labelled sensitivity assumption, not a venue-validated
    liquidation execution price. Missing model/rule history must remain a gap in
    the run's coverage report. Stop execution embeds doubled impact once.
    """
    require_decimal(all_in_liquidation_fee_rate, nonnegative=True)
    if (
        not model_manifest_id
        or utc(inputs_available_at) > last.timing.interval_start
        or utc(liquidation_terms_available_at) > last.timing.interval_start
    ):
        raise ValueError("Bar execution inputs must predate its unresolved path")
    now = max(last.timing.available_at, mark.timing.available_at)
    evidence = {
        "position_id": position_id,
        "last": last,
        "mark": mark,
        "liquidation_price": liquidation_price,
        "sigma": sigma,
        "recent_quote_volume": recent_quote_volume,
        "inputs_available_at": inputs_available_at,
        "all_in_liquidation_fee_rate": all_in_liquidation_fee_rate,
        "liquidation_terms_available_at": liquidation_terms_available_at,
        "model_manifest_id": model_manifest_id,
    }
    result_key = "bar:" + position_id + ":" + last.timing.interval_start.isoformat()
    with venue.journal.transaction() as db:
        previous = venue._receipt(db, result_key, evidence)
        if previous is not None:
            return previous
        venue._clock(db, now)
        _, raw = read_tx(db, venue.coordinator._protection_stream(position_id))
        position = Protection.restore(raw)
        if position.remaining == 0:
            return venue._save(db, result_key, evidence, {"reason": "ALREADY_FLAT", "fill": None})
        if last.symbol != position.symbol or mark.symbol != position.symbol:
            raise ValueError("Bar identity differs from owned position")
        if any(
            last.timing.interval_start < f.event_time < last.timing.interval_end
            for f in position.fills.values()
        ):
            raise ReconciliationRequired("Intrabar quantity change requires finer data")
        active = []
        for sequence in sorted(position.confirmed_stops - position.canceled_stops):
            action = position.actions[sequence]
            if action.quantity < position.remaining:
                continue
            _, _, client_id = client_identity(venue.scope, position_id, "PROTECT", sequence)
            row = db.execute(
                "SELECT payload FROM events WHERE event_id=?",
                ("sim-result:" + venue.scope + ":" + client_id,),
            ).fetchone()
            if row is None:
                continue
            from datetime import datetime

            acknowledged_at = datetime.fromisoformat(json.loads(row["payload"])["evidence"]["time"])
            # A later acknowledged replacement cannot erase a still-live old stop
            # from an earlier bar. Select among orders effective at bar start only.
            if last.timing.interval_start < acknowledged_at < last.timing.interval_end:
                raise ReconciliationRequired("Intrabar protection change requires finer data")
            if acknowledged_at <= last.timing.interval_start:
                active.append((action, client_id, acknowledged_at))
        if not active:
            raise ReconciliationRequired("Bar has no confirmed pre-existing full protection")
        action, client_id, effective_at = max(
            active, key=lambda item: position.side.sign * item[0].stop
        )
        outcome = adverse_bar_exit(
            last,
            mark,
            position.side,
            stop=action.stop,
            stop_effective_at=effective_at,
            first_fill_time=position.first_fill_time,
            liquidation=liquidation_price,
            now=now,
        )
        if outcome.reason == "FINER_DATA_REQUIRED":
            raise ReconciliationRequired("Partial ownership/protection bar requires finer data")
        if outcome.reason is None:
            return venue._save(db, result_key, evidence, {"reason": "NO_TRIGGER", "fill": None})
        side = Side.SHORT if position.side is Side.LONG else Side.LONG
        forced = outcome.reason == "MODELED_LIQUIDATION"
        if forced:
            price, fee_rate = outcome.reference_price, all_in_liquidation_fee_rate
            order_id = "sim-liquidation:" + digest([position_id, last.timing.interval_start])
        else:
            proxy = preliminary_proxy(
                outcome.reference_price,
                position.remaining,
                side,
                sigma,
                recent_quote_volume,
                stop_exit=True,
            )
            price = quantize_step(proxy.price, position.tick, up=side is Side.LONG)
            row = db.execute(
                "SELECT payload FROM intents WHERE scope=? AND signal_id=? AND purpose='ENTRY'",
                (venue.scope, position_id),
            ).fetchone()
            fee_rate = D(json.loads(row["payload"])["sizing"]["quote"]["exit_fee_rate"])
            order_id = "sim-order:" + client_id
        with localcontext(CONTEXT):
            fee = position.remaining * price * fee_rate
        fill = Fill(
            "sim-bar-fill:" + digest([position_id, last.timing.interval_start]),
            order_id,
            position_id,
            position.symbol,
            side,
            position.remaining,
            price,
            fee,
            last.timing.interval_end,
            now,
            True,
        )
        event = Event(
            fill.fill_id,
            Kind.LIQUIDATION if forced else Kind.PROTECTIVE_FILL,
            fill.event_time,
            now,
            "PVB24_PRELIMINARY_BAR_EMULATOR",
            Quality.PRELIMINARY,
            canonical(FillRecord(fill, liquidation=forced)),
        )
        output = venue.runtime(
            Delivery(event, "CONSERVATIVE_PRIORITY", outcome.ambiguous_event_count)
        )
        if not forced:
            venue.journal.reconcile_intent(
                client_id, "FILLED", {"fill": fill, "bar_assumption": True}
            )
        return venue._save(
            db,
            result_key,
            evidence,
            {
                "reason": outcome.reason,
                "fill": fill,
                "action_ids": output["action_ids"],
                "ambiguous_event_count": outcome.ambiguous_event_count,
                "quality": Quality.PRELIMINARY,
                "time_assumption": "BAR_END; exact intrabar time unresolved",
            },
        )
