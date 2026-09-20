from dataclasses import replace
from datetime import timedelta

import pytest
from test_entry_planner import setup

from pvb24.accounting.coordinator import save_tx
from pvb24.accounting.ledger import ReconciliationRequired
from pvb24.decimal_math import D
from pvb24.execution.book import Book
from pvb24.execution.planner import EntryPlanner
from pvb24.ids import digest
from pvb24.integrations.paper_dispatch import CONTRACT, OrderAccepted, PaperDispatch
from pvb24.state import Conflict, Journal
from pvb24.types import Quality


class Backend:
    paper_only = True
    contract = CONTRACT
    instance_id = "SYNTHETIC_TEST_ONLY"
    quality = Quality.PRELIMINARY

    def __init__(self, path):
        self.path, self.calls, self.queries, self.orders = path, [], [], {}
        self.fail = False

    def submit_entry(self, ticket):
        # A separate SQLite reader must see the write-ahead commit, not a
        # savepoint or uncommitted transaction on the caller's connection.
        with_reader = Journal(self.path)
        assert state(with_reader, ticket.client_id) == "UNKNOWN"
        assert with_reader.db.execute(
            "SELECT 1 FROM events WHERE event_id=?", ("paper-ticket:" + ticket.client_id,)
        ).fetchone()
        with_reader.close()
        self.calls.append(ticket)
        ack = OrderAccepted(ticket.client_id, "paper-order-1", digest(ticket), ticket.prepared_at)
        self.orders[ticket.client_id] = ack
        if self.fail:
            raise TimeoutError("Accepted by backend; reply lost")
        return ack

    def lookup(self, client_id):
        self.queries.append(client_id)
        return self.orders.get(client_id)


def state(db, cid):
    return db.db.execute("SELECT state FROM intents WHERE client_id=?", (cid,)).fetchone()[0]


def prepared(tmp_path):
    db, _, _, _, batch, sources = setup(tmp_path)
    inputs = replace(sources["BTCUSDT"], rules=replace(sources["BTCUSDT"].rules, tick=D("0.01")))
    result = EntryPlanner(db, "reference", Quality.PRELIMINARY).plan(
        batch, {"BTCUSDT": inputs}, batch.decision_time
    )[0]
    assert result["reason"] == "ACCEPTED"
    now = [batch.decision_time]
    book = Book("BTCUSDT")
    book.snapshot(10, [(D("101.20"), D(100))], [(D("101.21"), D(100))], now[0], now[0])
    book.update(10, 11, 9, [], [], now[0], now[0])
    backend = Backend(tmp_path / "planning.sqlite")
    host = PaperDispatch(db, "reference", Quality.PRELIMINARY, backend, lambda: now[0])
    return db, host, backend, result["client_id"], inputs, book, now


def test_committed_ticket_precedes_io_and_ack_does_not_invent_fills(tmp_path):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    with host:
        ack = host.dispatch_entry(cid, inputs, book)
        assert state(db, cid) == "ACKNOWLEDGED" and len(backend.calls) == 1
        ticket = backend.calls[0]
        assert ticket.mode == "PAPER" and ticket.time_in_force == "IOC"
        assert ticket.order_type == "LIMIT" and ticket.reduce_only is False
        assert ticket.prepared_at == now[0] and ticket.limit_price % inputs.rules.tick == 0
        assert db.snapshot("protection:reference:" + ticket.signal_id)[1]["fills"] == []
        with pytest.raises(Conflict, match="never resend"):
            host.dispatch_entry(cid, inputs, book)
        assert host.lookup(cid) == ack
    db.close()


def test_lost_ack_restart_queries_without_resend_or_releasing_risk(tmp_path):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    before = db.snapshot("portfolio:reference")
    backend.fail = True
    with host, pytest.raises(TimeoutError):
        host.dispatch_entry(cid, inputs, book)
    assert state(db, cid) == "UNKNOWN" and db.snapshot("portfolio:reference") == before
    db.close()
    db = Journal(tmp_path / "planning.sqlite")
    with PaperDispatch(db, "reference", Quality.PRELIMINARY, backend, lambda: now[0]) as restarted:
        with pytest.raises(Conflict, match="never resend"):
            restarted.dispatch_entry(cid, inputs, book)
        ack = backend.orders.pop(cid)
        assert restarted.lookup(cid) is None and state(db, cid) == "UNKNOWN"
        backend.orders[cid] = ack
        assert restarted.lookup(cid) == ack
        assert state(db, cid) == "ACKNOWLEDGED" and len(backend.calls) == 1
        assert db.snapshot("portfolio:reference") == before
    db.close()


@pytest.mark.parametrize(
    "case",
    [
        "missing_gate",
        "missing_risk",
        "paused",
        "stale_risk",
        "deadline",
        "stale_book",
        "future_input",
        "changed_rules",
        "wrong_quote",
        "higher_cost",
        "risk_reduced",
        "off_tick",
    ],
)
def test_dispatch_rechecks_all_gates_without_consuming_claim(tmp_path, case):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    if case.startswith("missing_"):
        stream = "account-gate:reference" if case == "missing_gate" else "equity-control:reference"
        db.db.execute("DELETE FROM snapshots WHERE stream=?", (stream,))
    elif case == "paused":
        with db.transaction() as tx:
            save_tx(tx, "account-gate:reference", {"ready": False, "safety_paused": True})
    elif case in ("stale_risk", "deadline", "stale_book"):
        now[0] += timedelta(seconds={"stale_risk": 60, "deadline": 91, "stale_book": 1}[case])
    elif case == "future_input":
        inputs = replace(inputs, available_at=now[0] + timedelta(seconds=1))
    elif case == "changed_rules":
        inputs = replace(inputs, rules=replace(inputs.rules, tick=D("0.1")))
    elif case in ("wrong_quote", "higher_cost"):
        original = inputs.quote_model
        field = (
            {"expected_entry": D(102)} if case == "wrong_quote" else {"entry_fee_rate": D("0.01")}
        )
        inputs = replace(inputs, quote_model=lambda q: replace(original(q), **field))
    elif case == "risk_reduced":
        raw = db.snapshot("equity-control:reference")[1]
        raw["last_status"]["risk_fraction"] = "0.005"
        with db.transaction() as tx:
            save_tx(tx, "equity-control:reference", raw)
    else:
        book.asks[D("101.211")] = D(1)
    with host, pytest.raises((Conflict, ReconciliationRequired)):
        host.dispatch_entry(cid, inputs, book)
    assert state(db, cid) == "PREPARED" and not backend.calls
    assert (
        db.db.execute("SELECT 1 FROM events WHERE event_id=?", ("paper-ticket:" + cid,)).fetchone()
        is None
    )
    db.close()


def test_slow_validation_and_outer_transactions_cannot_dispatch(tmp_path):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    original = inputs.quote_model

    def slow(q):
        now[0] += timedelta(seconds=1)
        return original(q)

    with host:
        with db.transaction(), pytest.raises(Conflict, match="inside a transaction"):
            host.dispatch_entry(cid, inputs, book)
        with pytest.raises(Conflict, match="became stale"):
            host.dispatch_entry(cid, replace(inputs, quote_model=slow), book)
    assert not backend.calls and state(db, cid) == "PREPARED"
    db.close()


def test_single_authority_across_connections_and_closed_host_refused(tmp_path):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    second = Journal(tmp_path / "planning.sqlite")
    with pytest.raises(Conflict, match="Another PAPER authority"):
        PaperDispatch(second, "reference", Quality.PRELIMINARY, backend, lambda: now[0])
    host.close()
    with pytest.raises(Conflict, match="closed"):
        host.dispatch_entry(cid, inputs, book)
    with PaperDispatch(second, "reference", Quality.PRELIMINARY, backend, lambda: now[0]):
        pass
    second.close()
    db.close()


@pytest.mark.parametrize("case", ["client", "hash", "future", "empty_order"])
def test_invalid_ack_stays_unknown_and_never_resends(tmp_path, case):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    submit = backend.submit_entry

    def bad(ticket):
        ack = submit(ticket)
        changes = {
            "client": {"client_id": "foreign"},
            "hash": {"ticket_digest": "wrong"},
            "future": {"accepted_at": now[0] + timedelta(seconds=1)},
            "empty_order": {"order_id": ""},
        }
        return replace(ack, **changes[case])

    backend.submit_entry = bad
    with host:
        with pytest.raises(Conflict, match="Invalid PAPER acknowledgement"):
            host.dispatch_entry(cid, inputs, book)
        assert state(db, cid) == "UNKNOWN"
        assert host.lookup(cid) is not None
    assert len(backend.calls) == 1
    db.close()


def test_unknown_before_io_and_failed_commit_never_resubmits(tmp_path, monkeypatch):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    original = Journal.append_tx

    def fail(tx, event_id, payload):
        if event_id == "dispatch:" + cid:
            raise RuntimeError("crash before write-ahead commit")
        return original(tx, event_id, payload)

    with host:
        monkeypatch.setattr(Journal, "append_tx", staticmethod(fail))
        with pytest.raises(RuntimeError):
            host.dispatch_entry(cid, inputs, book)
        assert not backend.calls and state(db, cid) == "PREPARED"
        monkeypatch.setattr(Journal, "append_tx", staticmethod(original))
        # Process interruption after commit but before side effect remains UNKNOWN.
        backend.submit_entry = lambda ticket: (_ for _ in ()).throw(KeyboardInterrupt())
        with pytest.raises(KeyboardInterrupt):
            host.dispatch_entry(cid, inputs, book)
        assert host.lookup(cid) is None and state(db, cid) == "UNKNOWN"
        with pytest.raises(Conflict, match="never resend"):
            host.dispatch_entry(cid, inputs, book)
    db.close()


def test_backend_cannot_switch_to_live_or_change_identity_after_restart(tmp_path):
    db, host, backend, cid, inputs, book, now = prepared(tmp_path)
    backend.paper_only = False
    with pytest.raises(ValueError, match="Explicit PAPER"):
        host.dispatch_entry(cid, inputs, book)
    host.close()
    backend.paper_only = True
    backend.instance_id = "different-simulator"
    with pytest.raises(Conflict, match="identity or quality changed"):
        PaperDispatch(db, "reference", Quality.PRELIMINARY, backend, lambda: now[0])
    assert not backend.calls
    db.close()
