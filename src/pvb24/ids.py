"""Stable canonical identities; no run identifier in signal identity."""

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pvb24.decimal_math import require_decimal
from pvb24.types import Side, timestamp


def decimal_text(value: Decimal) -> str:
    require_decimal(value)
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def normalize(value):
    if isinstance(value, float):
        raise TypeError("Binary float prohibited in canonical records")
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, datetime):
        return timestamp(value)
    if isinstance(value, Enum):
        return normalize(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return normalize(asdict(value))
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise TypeError("Canonical keys must be strings")
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [normalize(v) for v in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError("Unsupported canonical type")


def canonical(value) -> str:
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def signal_identity(version: str, symbol: str, side: Side, when: datetime) -> tuple[str, str]:
    if not version or not symbol or not isinstance(side, Side):
        raise ValueError("Invalid signal identity")
    identity = canonical([version, symbol, side, when])
    return identity, hashlib.sha256(identity.encode()).hexdigest()


def client_identity(account_scope: str, signal_id: str, purpose: str, sequence: int = 0):
    if not account_scope or not signal_id or not purpose or sequence < 0:
        raise ValueError("Invalid order identity")
    identity = canonical([account_scope, signal_id, purpose, sequence])
    full_digest = hashlib.sha256(identity.encode()).hexdigest()
    return identity, full_digest, "p24_" + full_digest[:32]
