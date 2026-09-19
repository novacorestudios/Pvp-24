import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import localcontext

import pytest

from pvb24.decimal_math import D, median, nearest_rank, population_std, quantize_step
from pvb24.ids import canonical, client_identity, digest, signal_identity
from pvb24.state import Conflict, Journal
from pvb24.types import Fill, Side, timestamp


@pytest.mark.parametrize("value", [0.1, True, float("nan"), "NaN", "Infinity", None])
def test_reject_float_and_invalid_financial_values(value):
    with pytest.raises((TypeError, ValueError)):
        D(value)


@pytest.mark.parametrize(
    "value,step,down,up",
    [
        ("123.456", "0.05", "123.45", "123.50"),
        ("1.999999999999999999999999999999999", "0.1", "1.9", "2.0"),
        ("0.0009", "0.001", "0", "0.001"),
        ("-1.01", "0.1", "-1.1", "-1.0"),
    ],
)
def test_rounding_does_not_cross_budget(value, step, down, up):
    with localcontext() as ctx:
        ctx.prec = 6  # An unrelated caller's context must not affect rounding.
        assert quantize_step(D(value), D(step)) == D(down)
        assert quantize_step(D(value), D(step), up=True) == D(up)


def test_frozen_statistics():
    assert median([D(1), D(8), D(3), D(2)]) == D("2.5")
    assert nearest_rank([D(x) for x in range(1, 21)], D("0.95")) == D(19)
    assert population_std([D(1), D(3)]) == D(1)


def test_canonical_json_normalizes_decimals_and_utc_without_precision_loss():
    t = datetime(2024, 1, 1, tzinfo=UTC)
    a = {"money": D("1.2300"), "t": t, "none": None, "negative_zero": D("-0")}
    b = {
        "negative_zero": D("0"),
        "none": None,
        "t": t.astimezone(timezone(timedelta(hours=3))),
        "money": D("1.23"),
    }
    assert canonical(a) == canonical(b)
    assert digest(a) == digest(b)
    assert (
        canonical(D("1234567890123456789012345678901234")) == '"1234567890123456789012345678901234"'
    )
    with pytest.raises(ValueError):
        timestamp(datetime(2024, 1, 1))
    with pytest.raises(TypeError):
        canonical({"cash": 0.1})


def test_signal_identity_is_stable_and_account_order_identity_is_distinct():
    t = datetime(2024, 1, 1, tzinfo=UTC)
    identity, signal = signal_identity("1.0", "BTCUSDT", Side.LONG, t)
    assert signal_identity("1.0", "BTCUSDT", Side.LONG, t) == (identity, signal)
    assert signal_identity("1.0", "BTCUSDT", Side.SHORT, t)[1] != signal
    a = client_identity("paper-account", signal, "ENTRY")
    b = client_identity("other-account", signal, "ENTRY")
    assert a != b
    assert len(a[1]) == 64 and len(a[2]) == 36


def test_domain_fill_is_immutable():
    t = datetime(2024, 1, 1, tzinfo=UTC)
    fill = Fill("f", "o", "p", "BTCUSDT", Side.LONG, D(1), D(100), D("0.05"), t, t)
    with pytest.raises(FrozenInstanceError):
        fill.price = D(200)
    with pytest.raises(TypeError):
        Fill("f", "o", "p", "BTCUSDT", Side.LONG, 1.0, D(100), D(0), t, t)


def test_durable_event_dedup_and_conflict(tmp_path):
    path = tmp_path / "journal.sqlite"
    j = Journal(path)
    assert j.append("fill:1", {"cash": D("1.23")})
    assert not j.append("fill:1", {"cash": D("1.230")})
    with pytest.raises(Conflict):
        j.append("fill:1", {"cash": D(2)})
    j.close()
    j = Journal(path)
    assert not j.append("fill:1", {"cash": D("1.23")})
    assert j.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    j.close()


def test_snapshot_cas_and_event_are_atomic(tmp_path):
    j = Journal(tmp_path / "journal.sqlite")
    assert j.checkpoint("BTCUSDT", 0, {"atr": D(2)}, "c:1") == 1
    with pytest.raises(Conflict):
        j.checkpoint("BTCUSDT", 0, {"atr": D(3)}, "c:2")
    assert j.snapshot("BTCUSDT") == (1, {"atr": "2"})
    assert not j.db.execute("SELECT 1 FROM events WHERE event_id='c:2'").fetchone()
    assert j.checkpoint("BTCUSDT", 1, {"atr": D(2)}, "c:1") == 1
    j.close()


def test_unknown_order_must_be_queried_and_cannot_be_sent_twice(tmp_path):
    path = tmp_path / "journal.sqlite"
    j = Journal(path)
    client, created = j.prepare_intent("paper", "signal", "ENTRY", {"quantity": D(1)})
    assert created and j.claim_dispatch(client)
    j.close()
    j = Journal(path)
    assert j.prepare_intent("paper", "signal", "ENTRY", {"quantity": D(1)}) == (client, False)
    assert not j.claim_dispatch(client)
    with pytest.raises(Conflict):
        j.prepare_intent("paper", "signal", "ENTRY", {"quantity": D(1)}, sequence=1)
    j.reconcile_intent(client, "CANCELED", {"exchange_id": "x"})
    j.reconcile_intent(client, "FILLED", {"fill_id": "late-fill"})
    with pytest.raises(Conflict):
        j.reconcile_intent(client, "ACKNOWLEDGED", {"exchange_id": "x"})
    assert not j.claim_dispatch(client)
    j.close()


def test_only_one_concurrent_caller_claims_an_order(tmp_path):
    path = tmp_path / "journal.sqlite"
    j = Journal(path)
    client, _ = j.prepare_intent("paper", "signal", "ENTRY", {"quantity": D(1)})
    j.close()

    def claim(_):
        connection = Journal(path)
        try:
            return connection.claim_dispatch(client)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(claim, range(8))) == 1


def test_process_crash_rolls_back_only_uncommitted_events(tmp_path):
    path = tmp_path / "journal.sqlite"
    script = """
import os, sys
from pvb24.state import Journal
j = Journal(sys.argv[1])
j.append('durable', {'x': 1})
with j.transaction() as db:
    j.append_tx(db, 'uncommitted', {'x': 2})
    os._exit(17)
"""
    proc = subprocess.run([sys.executable, "-c", script, str(path)], env=os.environ.copy())
    assert proc.returncode == 17
    j = Journal(path)
    assert [x[0] for x in j.db.execute("SELECT event_id FROM events")] == ["durable"]
    assert j.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    j.close()
