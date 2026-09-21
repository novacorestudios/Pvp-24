import hashlib
import json
from datetime import UTC, datetime, timedelta
import pytest

from pvb24.data.historical_metadata import load_selection, observation_at, qualify_selection
from pvb24.ids import canonical

NOW = datetime(2024, 1, 2, tzinfo=UTC)


def source(symbol="BTCUSDT", *, filters=True, tif=True):
    row = {
        "symbol": symbol,
        "onboardDate": 1569398400000,
        "status": "TRADING",
        "contractType": "PERPETUAL",
        "quoteAsset": "USDT",
    }
    if tif:
        row["timeInForce"] = ["GTC", "IOC"]
    if filters:
        row["filters"] = [
            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.001",
                "maxQty": "1000",
                "stepSize": "0.001",
            },
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ]
    return {"symbols": [row]}


def frozen(tmp_path, payload=None, **entry_changes):
    payload = source() if payload is None else payload
    (tmp_path / "objects").mkdir(parents=True, exist_ok=True)
    raw = canonical(payload).encode()
    revision = hashlib.sha256(raw).hexdigest()
    (tmp_path / "objects" / f"{revision}.json").write_bytes(raw)
    entry = {
        "symbol": "BTCUSDT",
        "source_url": "https://fapi.binance.com/fapi/v1/exchangeInfo",
        "object": f"objects/{revision}.json",
        "revision_id": revision,
        "observed_at": NOW.isoformat(),
        "available_at": (NOW + timedelta(seconds=1)).isoformat(),
        "historical_availability_verified": True,
        "historical_effective_time_verified": False,
    }
    entry.update(entry_changes)
    selection = {
        "schema": "PVB24_EXCHANGE_INFO_SELECTION_V1",
        "final_test_access": "LOCKED",
        "change_stream_complete": False,
        "snapshots": [entry],
    }
    raw_selection = canonical(selection).encode()
    path = tmp_path / "selection.json"
    path.write_bytes(raw_selection)
    return path, hashlib.sha256(raw_selection).hexdigest(), revision


def test_exact_source_snapshot_extracts_only_source_backed_exchange_fields(tmp_path):
    path, pin, revision = frozen(tmp_path)
    rows, selection = load_selection(tmp_path, path, expected_hash=pin)
    row = rows[0]
    assert selection["change_stream_complete"] is False
    assert row.revision_id == revision and str(row.tick) == "0.10"
    assert row.quantity_step.as_tuple().exponent == -3
    assert row.minimum_quantity.as_tuple().exponent == -3
    assert row.maximum_quantity == 1000 and row.minimum_notional == 5
    assert row.supports_ioc and row.active
    assert row.contract_type == "PERPETUAL" and row.quote_asset == "USDT"


def test_exchange_info_alone_cannot_promote_full_security_or_rule_history(tmp_path):
    path, pin, _ = frozen(tmp_path)
    report = qualify_selection(tmp_path, path, expected_hash=pin)
    assert report["quality"] == "PRELIMINARY"
    assert not report["security_history_complete"]
    assert not report["contract_rule_history_complete"]
    assert not report["liquidation_tiers_complete"]
    coverage = report["coverage"][0]
    assert coverage["security_gaps"] == ["CLASSIFICATION"]
    assert coverage["rule_gaps"] == [
        "CONTRACT_SIZE",
        "MAINTENANCE_TIERS",
        "LAST_STOP_CAPABILITY",
    ]
    assert not report["operational_ready"] and report["final_test_access"] == "LOCKED"


def test_preliminary_security_preserves_unknown_classification_instead_of_guessing(tmp_path):
    path, pin, _ = frozen(tmp_path)
    row = load_selection(tmp_path, path, expected_hash=pin)[0][0]
    security = row.preliminary_security()
    assert security.classification == "UNKNOWN"
    assert not security.historical_verified
    assert security.source == row.source and security.revision_id == row.revision_id


def test_snapshot_is_not_available_before_causal_receipt(tmp_path):
    path, pin, _ = frozen(tmp_path)
    row = load_selection(tmp_path, path, expected_hash=pin)[0][0]
    assert observation_at([row], "BTCUSDT", NOW) is None
    assert observation_at([row], "BTCUSDT", NOW + timedelta(seconds=1)) == row


def test_later_revision_cannot_leak_into_earlier_decision(tmp_path):
    path, pin, revision = frozen(tmp_path)
    first = load_selection(tmp_path, path, expected_hash=pin)[0][0]
    later = first.__class__(
        **{
            **first.__dict__,
            "available_at": NOW + timedelta(days=1),
            "effective_from": NOW + timedelta(days=1),
            "revision_id": revision[:-1] + ("0" if revision[-1] != "0" else "1"),
        }
    )
    assert observation_at([first, later], "BTCUSDT", NOW + timedelta(hours=1)) == first
    assert observation_at([first, later], "BTCUSDT", NOW + timedelta(days=1)) == later


@pytest.mark.parametrize("change", ["selection", "object", "revision"])
def test_content_addressing_rejects_changed_selection_or_source_bytes(tmp_path, change):
    path, pin, revision = frozen(tmp_path)
    if change == "selection":
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "object":
        (tmp_path / "objects" / f"{revision}.json").write_bytes(b"{}")
    else:
        value = json.loads(path.read_text())
        value["snapshots"][0]["revision_id"] = "0" * 64
        path.write_text(canonical(value))
        pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        load_selection(tmp_path, path, expected_hash=pin)


@pytest.mark.parametrize(
    "change,match",
    [
        ({"source_url": "https://example.com/exchangeInfo"}, "Official Binance"),
        ({"available_at": (NOW - timedelta(seconds=1)).isoformat()}, "available before"),
        (
            {"effective_from": (NOW - timedelta(days=1)).isoformat()},
            "cannot be applied before",
        ),
        ({"symbol": "BTCUSD"}, "USD-M USDT"),
    ],
)
def test_invalid_provenance_and_retroactive_unverified_effective_time_fail_closed(
    tmp_path, change, match
):
    path, pin, _ = frozen(tmp_path, **change)
    with pytest.raises((ValueError, TypeError), match=match):
        load_selection(tmp_path, path, expected_hash=pin)


def test_verified_effective_time_may_precede_observation_but_not_availability(tmp_path):
    path, pin, _ = frozen(
        tmp_path,
        effective_from=(NOW - timedelta(days=1)).isoformat(),
        historical_effective_time_verified=True,
    )
    row = load_selection(tmp_path, path, expected_hash=pin)[0][0]
    assert row.effective_from == NOW - timedelta(days=1)
    assert observation_at([row], "BTCUSDT", NOW) is None


def test_final_test_metadata_is_rejected_before_normalization(tmp_path):
    path, pin, _ = frozen(
        tmp_path,
        observed_at=datetime(2025, 7, 1, tzinfo=UTC).isoformat(),
        available_at=datetime(2025, 7, 1, tzinfo=UTC).isoformat(),
    )
    with pytest.raises(ValueError, match="LOCKED"):
        load_selection(tmp_path, path, expected_hash=pin)


def test_missing_exchange_filters_remain_explicit_gaps(tmp_path):
    path, pin, _ = frozen(tmp_path, payload=source(filters=False))
    report = qualify_selection(tmp_path, path, expected_hash=pin)
    assert report["coverage"][0]["rule_gaps"] == [
        "TICK_SIZE",
        "STEP_SIZE",
        "MIN_QTY",
        "MAX_QTY",
        "MIN_NOTIONAL",
        "CONTRACT_SIZE",
        "MAINTENANCE_TIERS",
        "LAST_STOP_CAPABILITY",
    ]


def test_duplicate_symbol_or_filter_is_ambiguous_not_last_write_wins(tmp_path):
    payload = source()
    payload["symbols"].append(dict(payload["symbols"][0]))
    path, pin, _ = frozen(tmp_path, payload=payload)
    with pytest.raises(ValueError, match="Exactly one"):
        load_selection(tmp_path, path, expected_hash=pin)

    payload = source()
    payload["symbols"][0]["filters"].append({"filterType": "PRICE_FILTER", "tickSize": "0.20"})
    path, pin, _ = frozen(tmp_path / "other", payload=payload)
    with pytest.raises(ValueError, match="Ambiguous exchangeInfo filter"):
        load_selection(tmp_path / "other", path, expected_hash=pin)


def test_change_stream_completeness_is_explicit_and_never_inferred(tmp_path):
    path, pin, _ = frozen(tmp_path)
    value = json.loads(path.read_text())
    del value["change_stream_complete"]
    path.write_text(canonical(value))
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(TypeError, match="change-stream"):
        load_selection(tmp_path, path, expected_hash=pin)


def test_duplicate_snapshot_identity_is_rejected(tmp_path):
    path, _, _ = frozen(tmp_path)
    value = json.loads(path.read_text())
    value["snapshots"].append(dict(value["snapshots"][0]))
    path.write_text(canonical(value))
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Duplicate"):
        load_selection(tmp_path, path, expected_hash=pin)
