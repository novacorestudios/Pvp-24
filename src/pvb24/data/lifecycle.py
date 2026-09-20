"""Causal delisting evidence and durable per-symbol entry blocking (UD-13)."""

import json
from dataclasses import dataclass
from datetime import datetime

from pvb24.execution.protection import Protection
from pvb24.ids import canonical, digest
from pvb24.state import Conflict, Journal
from pvb24.types import utc


@dataclass(frozen=True)
class DelistingNotice:
    symbol: str
    announced_at: datetime
    scheduled_settlement_at: datetime
    available_at: datetime
    source: str
    revision_id: str
    historical_verified: bool

    def __post_init__(self):
        if not self.symbol or not self.source or not self.revision_id:
            raise ValueError("Delisting identity and source revision required")
        if type(self.historical_verified) is not bool:
            raise TypeError("Explicit historical-evidence qualification required")
        if utc(self.announced_at) > utc(self.available_at) or utc(self.announced_at) >= utc(
            self.scheduled_settlement_at
        ):
            raise ValueError("Invalid delisting announcement/availability/settlement times")

    @classmethod
    def restore(cls, raw):
        return cls(
            **{k: datetime.fromisoformat(v) if k.endswith("_at") else v for k, v in raw.items()}
        )


def entry_block_reason(db, scope, symbol, now=None):
    row = db.execute(
        "SELECT payload FROM snapshots WHERE stream=?", ("entry-block:" + scope + ":" + symbol,)
    ).fetchone()
    if row is None:
        return None
    state = json.loads(row["payload"])
    if now is not None and utc(now) < datetime.fromisoformat(state["blocked_at"]):
        raise Conflict("Cannot backdate entry evaluation behind received lifecycle evidence")
    return state["reason"]


def prepare_entry_cancel(db, scope, signal_id, target_client_id, reason):
    """All safety causes share one owned cancellation identity; never resubmit."""
    rows = db.execute(
        "SELECT * FROM intents WHERE scope=? AND signal_id=? AND purpose='CANCEL_ENTRY'",
        (scope, signal_id),
    ).fetchall()
    if rows:
        if (
            len(rows) != 1
            or json.loads(rows[0]["payload"]).get("target_client_id") != target_client_id
        ):
            raise Conflict("Existing cancellation ownership differs")
        return rows[0]["client_id"]
    cid, _ = Journal.prepare_intent_tx(
        db,
        scope,
        signal_id,
        "CANCEL_ENTRY",
        {"target_client_id": target_client_id, "reason": reason},
    )
    return cid


class LifecycleService:
    def __init__(self, journal, scope):
        if not scope:
            raise ValueError("Account scope required")
        self.journal, self.scope = journal, scope

    def announce(self, notice: DelistingNotice, now):
        from pvb24.accounting.coordinator import AccountCoordinator, read_tx, save_tx

        now = utc(now)
        if now < notice.available_at:
            raise ValueError("Delisting notice is not yet available")
        key = (
            "delisting-notice:"
            + self.scope
            + ":"
            + digest([notice.symbol, notice.source, notice.revision_id])
        )
        with self.journal.transaction() as db:
            prior = db.execute("SELECT payload FROM events WHERE event_id=?", (key,)).fetchone()
            if prior:
                receipt = json.loads(prior["payload"])
                if canonical(receipt["notice"]) != canonical(notice):
                    raise Conflict("Delisting source revision changed its evidence")
                return receipt["result"]
            _, replay = self.journal.snapshot("replay-account:" + self.scope)
            _, gate = read_tx(db, "account-gate:" + self.scope)
            for time in ((replay or {}).get("last_time"), gate.get("last_evidence_at")):
                if time is not None and datetime.fromisoformat(time) > now:
                    raise Conflict("Cannot backdate lifecycle evidence behind account state")
            stream = "entry-block:" + self.scope + ":" + notice.symbol
            _, blocked = self.journal.snapshot(stream)
            if blocked is None:
                save_tx(
                    db,
                    stream,
                    {"reason": "DELISTING_ANNOUNCED", "blocked_at": now, "first_notice": key},
                )
            else:
                entry_block_reason(db, self.scope, notice.symbol, now)
            canceled, actions = [], []
            rows = db.execute(
                "SELECT * FROM intents WHERE scope=? AND purpose='ENTRY' "
                "AND state IN ('PREPARED','UNKNOWN','ACKNOWLEDGED')",
                (self.scope,),
            ).fetchall()
            for row in rows:
                if json.loads(row["payload"]).get("symbol") != notice.symbol:
                    continue
                cid = row["client_id"]
                if row["state"] == "PREPARED":
                    if db.execute(
                        "SELECT 1 FROM events WHERE event_id IN (?,?)",
                        ("dispatch:" + cid, "paper-ticket:" + cid),
                    ).fetchone():
                        raise Conflict("Cannot retire an entry with dispatch evidence")
                    db.execute("UPDATE intents SET state='CANCELED' WHERE client_id=?", (cid,))
                    Journal.append_tx(
                        db,
                        "cancel-unsent:" + cid,
                        {"reason": "DELISTING_ANNOUNCED", "never_dispatched": True},
                    )
                    protection_stream = "protection:" + self.scope + ":" + row["signal_id"]
                    _, raw = self.journal.snapshot(protection_stream)
                    if raw is not None:
                        protection = Protection.restore(raw)
                        if protection.fills:
                            raise Conflict("Unsent entry has conflicting actual-fill evidence")
                        protection.entry_terminal()
                        save_tx(db, protection_stream, protection.checkpoint())
                    canceled.append(cid)
                else:
                    actions.append(
                        prepare_entry_cancel(
                            db, self.scope, row["signal_id"], cid, "DELISTING_ANNOUNCED"
                        )
                    )
            if canceled or actions:
                # Never free cash, risk or quantity on a cancellation request.
                AccountCoordinator(self.journal, self.scope)._pause(
                    db, "DELISTING_ENTRY_RECONCILIATION", now
                )
            result = {
                "blocked_symbol": notice.symbol,
                "canceled_unsent": canceled,
                "action_ids": actions,
            }
            Journal.append_tx(db, key, {"notice": notice, "processed_at": now, "result": result})
            return json.loads(canonical(result))
