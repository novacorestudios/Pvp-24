"""Pinned historical Binance contract/security snapshot ingestion and qualification.

The loader is intentionally offline.  It consumes only caller-selected, content-addressed
source captures and never treats a current exchangeInfo response as historical evidence.
A point-in-time snapshot proves what was observed at its own causal availability time; it
never proves an earlier interval or an unobserved change stream.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from pvb24.data.archive import FINAL_START, milliseconds
from pvb24.decimal_math import D, require_decimal
from pvb24.ids import canonical, digest
from pvb24.types import utc

SCHEMA = "PVB24_EXCHANGE_INFO_SELECTION_V1"
OFFICIAL_HOSTS = frozenset({"fapi.binance.com", "www.binance.com", "binance.com"})


@dataclass(frozen=True)
class MetadataObservation:
    symbol: str
    observed_at: datetime
    available_at: datetime
    effective_from: datetime
    source: str
    revision_id: str
    historical_availability_verified: bool
    historical_effective_time_verified: bool
    trading_start: datetime
    active: bool
    contract_type: str
    quote_asset: str
    tick: Decimal | None
    quantity_step: Decimal | None
    minimum_quantity: Decimal | None
    maximum_quantity: Decimal | None
    minimum_notional: Decimal | None
    supports_ioc: bool

    def __post_init__(self):
        for value in (self.observed_at, self.available_at, self.effective_from, self.trading_start):
            utc(value)
        if not self.symbol or not self.source or not self.revision_id:
            raise ValueError("Metadata observation provenance required")
        if self.observed_at > self.available_at:
            raise ValueError("Metadata cannot be available before it was observed")
        if self.effective_from < self.observed_at and not self.historical_effective_time_verified:
            raise ValueError("Unverified metadata cannot be applied before its observation")
        for flag in (
            self.historical_availability_verified,
            self.historical_effective_time_verified,
            self.active,
            self.supports_ioc,
        ):
            if type(flag) is not bool:
                raise TypeError("Explicit boolean metadata evidence required")
        for value in (
            self.tick,
            self.quantity_step,
            self.minimum_quantity,
            self.maximum_quantity,
            self.minimum_notional,
        ):
            if value is not None:
                require_decimal(value, nonnegative=True)
        for value in (self.tick, self.quantity_step, self.minimum_quantity, self.maximum_quantity):
            if value is not None:
                require_decimal(value, positive=True)
        if (
            self.minimum_quantity is not None
            and self.maximum_quantity is not None
            and self.maximum_quantity < self.minimum_quantity
        ):
            raise ValueError("Invalid quantity bounds")

    @property
    def security_gaps(self) -> tuple[str, ...]:
        # Classification is not present in exchangeInfo and must come from separate evidence.
        return ("CLASSIFICATION",)

    @property
    def rule_gaps(self) -> tuple[str, ...]:
        gaps = []
        for name, value in (
            ("TICK_SIZE", self.tick),
            ("STEP_SIZE", self.quantity_step),
            ("MIN_QTY", self.minimum_quantity),
            ("MAX_QTY", self.maximum_quantity),
            ("MIN_NOTIONAL", self.minimum_notional),
        ):
            if value is None:
                gaps.append(name)
        # These fields are deliberately not inferred from exchangeInfo.
        gaps.extend(("CONTRACT_SIZE", "MAINTENANCE_TIERS", "LAST_STOP_CAPABILITY"))
        return tuple(gaps)

    def preliminary_security(self):
        """Return only source-backed fields; UNKNOWN classification fails universe eligibility."""
        from pvb24.data.universe import Security

        return Security(
            symbol=self.symbol,
            trading_start=self.trading_start,
            effective_from=self.effective_from,
            available_at=self.available_at,
            classification="UNKNOWN",
            active=self.active,
            source=self.source,
            revision_id=self.revision_id,
            historical_verified=False,
            contract_type=self.contract_type,
            quote_asset=self.quote_asset,
        )


def _owned_object(root: Path, reference: str) -> tuple[bytes, str]:
    relative = Path(reference)
    if relative.is_absolute() or relative.parts[:1] != ("objects",) or len(relative.parts) != 2:
        raise ValueError("Owned metadata source object required")
    if not relative.name.endswith(".json") or len(relative.stem) != 64:
        raise ValueError("Content-addressed metadata JSON object required")
    raw = (root / relative).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != relative.stem:
        raise ValueError("Historical metadata source bytes changed")
    return raw, actual


def _official_source(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        raise ValueError("Official Binance HTTPS metadata source required")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Unexpected metadata source URL components")


def _filter(symbol: dict, filter_type: str) -> dict | None:
    rows = [row for row in symbol.get("filters", []) if row.get("filterType") == filter_type]
    if len(rows) > 1:
        raise ValueError("Ambiguous exchangeInfo filter")
    return rows[0] if rows else None


def _decimal_field(row: dict | None, field: str) -> Decimal | None:
    if row is None or field not in row:
        return None
    value = D(row[field])
    require_decimal(value, nonnegative=True)
    return value


def _symbol_row(payload: dict, symbol: str) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise ValueError("Binance exchangeInfo symbols array required")
    rows = [
        row
        for row in payload["symbols"]
        if isinstance(row, dict) and row.get("symbol") == symbol
    ]
    if len(rows) != 1:
        raise ValueError("Exactly one requested symbol must exist in the exchangeInfo snapshot")
    return rows[0]


def _parse_entry(root: Path, entry: dict) -> MetadataObservation:
    required = {
        "symbol",
        "source_url",
        "object",
        "observed_at",
        "available_at",
        "historical_availability_verified",
        "historical_effective_time_verified",
    }
    if not isinstance(entry, dict) or not required.issubset(entry):
        raise ValueError("Historical metadata snapshot entry is incomplete")
    if (
        not isinstance(entry["symbol"], str)
        or not entry["symbol"].isalnum()
        or not entry["symbol"].endswith("USDT")
    ):
        raise ValueError("Explicit USD-M USDT metadata symbol required")
    _official_source(entry["source_url"])
    raw, revision = _owned_object(root, entry["object"])
    if entry.get("revision_id", revision) != revision:
        raise ValueError("Metadata revision does not match retained source bytes")
    payload = json.loads(raw)
    row = _symbol_row(payload, entry["symbol"])
    observed = utc(datetime.fromisoformat(entry["observed_at"]))
    available = utc(datetime.fromisoformat(entry["available_at"]))
    effective_text = entry.get("effective_from")
    effective = observed if effective_text is None else utc(datetime.fromisoformat(effective_text))
    if max(observed, available, effective) >= FINAL_START:
        raise ValueError("Final Test metadata access is LOCKED")
    if row.get("symbol") != entry["symbol"]:
        raise ValueError("Metadata symbol identity changed")
    onboard = row.get("onboardDate")
    if not isinstance(onboard, int) or isinstance(onboard, bool) or onboard < 0:
        raise ValueError("Integer exchangeInfo onboardDate required")
    trading_start = milliseconds(str(onboard))
    price = _filter(row, "PRICE_FILTER")
    lot = _filter(row, "LOT_SIZE")
    notional = _filter(row, "MIN_NOTIONAL") or _filter(row, "NOTIONAL")
    minimum_notional = None
    if notional is not None:
        if "notional" in notional:
            minimum_notional = _decimal_field(notional, "notional")
        elif "minNotional" in notional:
            minimum_notional = _decimal_field(notional, "minNotional")
    time_in_force = row.get("timeInForce", [])
    if not isinstance(time_in_force, list) or any(not isinstance(x, str) for x in time_in_force):
        raise ValueError("exchangeInfo timeInForce must be a string array")
    return MetadataObservation(
        symbol=entry["symbol"],
        observed_at=observed,
        available_at=available,
        effective_from=effective,
        source=entry["source_url"],
        revision_id=revision,
        historical_availability_verified=entry["historical_availability_verified"],
        historical_effective_time_verified=entry["historical_effective_time_verified"],
        trading_start=trading_start,
        active=row.get("status") == "TRADING",
        contract_type=str(row.get("contractType", "")),
        quote_asset=str(row.get("quoteAsset", "")),
        tick=_decimal_field(price, "tickSize"),
        quantity_step=_decimal_field(lot, "stepSize"),
        minimum_quantity=_decimal_field(lot, "minQty"),
        maximum_quantity=_decimal_field(lot, "maxQty"),
        minimum_notional=minimum_notional,
        supports_ioc="IOC" in time_in_force,
    )


def observation_at(rows: list[MetadataObservation], symbol: str, decision: datetime):
    decision = utc(decision)
    candidates = [
        row
        for row in rows
        if row.symbol == symbol and row.effective_from <= decision and row.available_at <= decision
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x.effective_from, x.available_at, x.revision_id))
    if len(candidates) > 1:
        a, b = candidates[-2:]
        if (a.effective_from, a.available_at) == (b.effective_from, b.available_at) and a != b:
            raise ValueError("Ambiguous historical metadata revision")
    return candidates[-1]


def load_selection(root, selection_path, *, expected_hash):
    root, selection_path = Path(root), Path(selection_path)
    payload = selection_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ValueError("Historical metadata selection hash changed")
    selection = json.loads(payload)
    if selection.get("schema") != SCHEMA or selection.get("final_test_access") != "LOCKED":
        raise ValueError("Historical metadata selection schema/holdout policy not qualified")
    change_stream_complete = selection.get("change_stream_complete")
    if type(change_stream_complete) is not bool:
        raise TypeError("Explicit metadata change-stream qualification required")
    entries = selection.get("snapshots")
    if not isinstance(entries, list) or not entries:
        raise ValueError("At least one pinned historical metadata snapshot is required")
    observations, identities = [], set()
    for entry in entries:
        row = _parse_entry(root, entry)
        identity = (row.symbol, row.effective_from, row.available_at, row.revision_id)
        if identity in identities:
            raise ValueError("Duplicate historical metadata snapshot identity")
        identities.add(identity)
        observations.append(row)
    observations.sort(key=lambda x: (x.symbol, x.effective_from, x.available_at, x.revision_id))
    return observations, selection


def qualify_selection(root, selection_path, *, expected_hash):
    rows, selection = load_selection(root, selection_path, expected_hash=expected_hash)
    coverage = []
    for row in rows:
        coverage.append(
            {
                "symbol": row.symbol,
                "observed_at": row.observed_at,
                "available_at": row.available_at,
                "effective_from": row.effective_from,
                "source": row.source,
                "revision_id": row.revision_id,
                "historical_availability_verified": row.historical_availability_verified,
                "historical_effective_time_verified": row.historical_effective_time_verified,
                "security_gaps": row.security_gaps,
                "rule_gaps": row.rule_gaps,
                "extracted": {
                    "trading_start": row.trading_start,
                    "active": row.active,
                    "contract_type": row.contract_type,
                    "quote_asset": row.quote_asset,
                    "tick": row.tick,
                    "quantity_step": row.quantity_step,
                    "minimum_quantity": row.minimum_quantity,
                    "maximum_quantity": row.maximum_quantity,
                    "minimum_notional": row.minimum_notional,
                    "supports_ioc": row.supports_ioc,
                },
            }
        )
    complete_source_times = all(
        row.historical_availability_verified and row.historical_effective_time_verified
        for row in rows
    )
    report = {
        "schema": "PVB24_HISTORICAL_METADATA_QUALIFICATION_V1",
        "selection_hash": expected_hash,
        "snapshots": len(rows),
        "symbols": sorted({row.symbol for row in rows}),
        "change_stream_complete": selection["change_stream_complete"],
        "source_times_verified": complete_source_times,
        "security_history_complete": False,
        "contract_rule_history_complete": False,
        "liquidation_tiers_complete": False,
        "quality": "PRELIMINARY",
        "coverage": coverage,
        "input_hash": digest(rows),
        "final_test_access": "LOCKED",
        "operational_ready": False,
    }
    # ExchangeInfo alone can never promote the full security/rule history: classification,
    # contract-size semantics, historical maintenance tiers and LAST-stop capability remain
    # separate evidence requirements even if every snapshot timestamp is independently attested.
    return json.loads(canonical(report))
