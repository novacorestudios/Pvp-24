from dataclasses import replace
from datetime import timedelta

import pytest
from test_paper_dispatch import prepared, state

from pvb24.accounting.coordinator import AccountCoordinator
from pvb24.accounting.ledger import LedgerStore
from pvb24.decimal_math import D
from pvb24.ids import canonical, client_identity
from pvb24.integrations.paper_dispatch import OrderRejected, PaperDispatch
from pvb24.integrations.paper_evidence import PaperEvidence
from pvb24.integrations.paper_venue import L2PaperVenue
from pvb24.state import Conflict, Journal
from pvb24.types import Quality


def setup(tmp_path, *, partial=False):
    db, host, _, cid, inputs, book, now = prepared(tmp_path)
    host.close()
    if partial:
        book.asks = {D("101.21"): D(1), D(102): D(100)}
    venue = L2PaperVenue(
        tmp_path / "venue.sqlite",
        instance_id="SYNTHETIC_TEST_ONLY",
        scope="reference",
        manifest_id="SYNTHETIC_L2_ONLY",
        clock=lambda: now[0],
    )
    venue.install_book(book, source_event_id="initial-book")
    venue.set_terms(
        inputs.rules,
        entry_fee_rate=D("0.0005"),
        available_at=now[0],
        source_revision="synthetic-terms",
    )
    host = PaperDispatch(db, "reference", Quality.PRELIMINARY, venue, lambda: now[0])
    return db, host, venue, cid, inputs, book, now


def ingest_all(host, venue):
    service = PaperEvidence(host)
    return [service.ingest(event) for _, event in venue.events_after()]


def test_durable_ioc_actual_fees_events_and_idempotent_backend_lookup(tmp_path):
    db, host, venue, cid, inputs, book, now = setup(tmp_path)
    with host:
        response = host.dispatch_entry(cid, inputs, book)
        assert venue.lookup(cid) == response
        events = venue.events_after()
        assert [e.kind for _, e in events] == ["FILL", "TERMINAL"]
        ingest_all(host, venue)
        ledger = LedgerStore(db, "reference").read()[1]
        view = ledger.view(now[0])
        fill = next(iter(ledger.fills.values())).fill
        assert fill.price == D("101.21")
        assert fill.fee == fill.quantity * fill.price * D("0.0005")
        assert view.cash == D(1000) - fill.fee and state(db, cid) == "FILLED"
        assert not venue.events_after(events[-1][0])
        ingest_all(host, venue)
        assert LedgerStore(db, "reference").read()[1].view(now[0]) == view
    venue.close()
    db.close()


def test_partial_ioc_never_reuses_consumed_depth_until_explicit_later_update(tmp_path):
    db, host, venue, cid, inputs, book, now = setup(tmp_path, partial=True)
    with host:
        host.dispatch_entry(cid, inputs, book)
        order = venue.journal.snapshot("model-order:" + cid)[1]
        assert order["outcome"] == "CANCELED" and D(order["filled_quantity"]) == 1
        assert venue.install_book(book, source_event_id="initial-book") is False
        # Different signal, same book: only a later explicit level update can
        # replenish the visible ask consumed by the first simulated order.
        import json

        raw = json.loads(
            db.db.execute(
                "SELECT payload FROM events WHERE event_id=?", ("paper-ticket:" + cid,)
            ).fetchone()[0]
        )
        from pvb24.integrations.paper_dispatch import EntryTicket
        from pvb24.types import Side

        for key in ("quantity", "limit_price"):
            raw[key] = D(raw[key])
        for key in ("prepared_at", "deadline"):
            from datetime import datetime

            raw[key] = datetime.fromisoformat(raw[key])
        raw["side"] = Side(raw["side"])
        t = EntryTicket(**raw)
        another = replace(
            t, signal_id="second", client_id=client_identity("reference", "second", "ENTRY")[2]
        )
        venue.submit_entry(another)
        assert (
            D(venue.journal.snapshot("model-order:" + another.client_id)[1]["filled_quantity"]) == 0
        )
        now[0] += timedelta(milliseconds=1)
        venue.update_book(
            book.symbol,
            first=12,
            final=12,
            previous=11,
            bids=[],
            asks=[(D("101.21"), D(1))],
            event_time=now[0],
            received_at=now[0],
            source_event_id="later-ask",
        )
        third = replace(
            t, signal_id="third", client_id=client_identity("reference", "third", "ENTRY")[2]
        )
        venue.submit_entry(third)
        assert (
            D(venue.journal.snapshot("model-order:" + third.client_id)[1]["filled_quantity"]) == 1
        )
    venue.close()
    db.close()


def test_timeout_after_backend_commit_restart_recovers_exact_events_and_no_second_fill(tmp_path):
    db, host, venue, cid, inputs, book, now = setup(tmp_path)
    submit = venue.submit_entry

    def lost(ticket):
        submit(ticket)
        raise TimeoutError("Backend committed, response lost")

    venue.submit_entry = lost
    with host, pytest.raises(TimeoutError):
        host.dispatch_entry(cid, inputs, book)
    assert state(db, cid) == "UNKNOWN"
    original = canonical(venue.events_after())
    venue.close()
    db.close()
    db = Journal(tmp_path / "planning.sqlite")
    venue = L2PaperVenue(
        tmp_path / "venue.sqlite",
        instance_id="SYNTHETIC_TEST_ONLY",
        scope="reference",
        manifest_id="SYNTHETIC_L2_ONLY",
        clock=lambda: now[0],
    )
    with PaperDispatch(db, "reference", Quality.PRELIMINARY, venue, lambda: now[0]) as host:
        assert host.lookup(cid) is not None
        assert canonical(venue.events_after()) == original
        ingest_all(host, venue)
        with pytest.raises(Conflict, match="never resend"):
            host.dispatch_entry(cid, inputs, book)
        assert len(LedgerStore(db, "reference").read()[1].fills) == 1
    venue.close()
    db.close()


def test_deadline_expiry_between_claim_and_backend_returns_proven_refusal(tmp_path):
    db, host, venue, cid, inputs, book, now = setup(tmp_path)
    submit = venue.submit_entry

    def delayed(ticket):
        now[0] = ticket.deadline + timedelta(milliseconds=1)
        return submit(ticket)

    venue.submit_entry = delayed
    with host:
        response = host.dispatch_entry(cid, inputs, book)
        assert isinstance(response, OrderRejected) and response.reason == "ORDER_DEADLINE"
        assert state(db, cid) == "UNKNOWN"  # account has not processed terminal proof yet
        ingest_all(host, venue)
        assert state(db, cid) == "REJECTED" and not LedgerStore(db, "reference").read()[1].fills
        assert AccountCoordinator(db, "reference").reconcile_flat(now[0], D(1000), "refused-flat")
        assert db.snapshot("portfolio:reference")[1]["exposures"] == []
    venue.close()
    db.close()


def test_gap_persists_unsynced_book_and_backend_refuses_without_fills(tmp_path):
    db, host, venue, cid, inputs, book, now = setup(tmp_path)
    with host:
        with pytest.raises(ValueError, match="sequence gap"):
            venue.update_book(
                book.symbol,
                first=14,
                final=14,
                previous=13,
                bids=[],
                asks=[],
                event_time=now[0],
                received_at=now[0],
                source_event_id="gap",
            )
        response = host.dispatch_entry(cid, inputs, book)
        assert isinstance(response, OrderRejected) and response.reason == "STALE_OR_UNSYNCED_BOOK"
        ingest_all(host, venue)
        assert state(db, cid) == "REJECTED"
        assert venue.journal.snapshot("model-book:" + book.symbol)[1]["synced"] is False
    venue.close()
    db.close()


def test_backend_commit_failure_preserves_book_and_host_unknown_without_resend(
    tmp_path, monkeypatch
):
    db, host, venue, cid, inputs, book, _ = setup(tmp_path)
    original = Journal.append_tx
    before = venue.journal.snapshot("model-book:" + book.symbol)

    def fail(tx, event_id, payload):
        if event_id.startswith("model-evidence:"):
            raise RuntimeError("Backend commit failed")
        return original(tx, event_id, payload)

    monkeypatch.setattr(Journal, "append_tx", staticmethod(fail))
    with host:
        with pytest.raises(RuntimeError, match="Backend commit failed"):
            host.dispatch_entry(cid, inputs, book)
        assert state(db, cid) == "UNKNOWN" and host.lookup(cid) is None
        assert venue.journal.snapshot("model-book:" + book.symbol) == before
        assert not venue.events_after()
    venue.close()
    db.close()


def test_model_policy_cannot_be_changed_on_reopen(tmp_path):
    db, host, venue, _, _, _, now = setup(tmp_path)
    with host, pytest.raises(Conflict, match="policy changed"):
        L2PaperVenue(
            tmp_path / "venue.sqlite",
            instance_id="SYNTHETIC_TEST_ONLY",
            scope="reference",
            manifest_id="REFITTED_AFTER_RESULTS",
            clock=lambda: now[0],
        )
    venue.close()
    db.close()


def test_preliminary_execution_model_cannot_bind_to_verified_dispatch(tmp_path):
    db, host, venue, _, _, _, now = setup(tmp_path)
    host.close()
    with pytest.raises(ValueError, match="Explicit PAPER"):
        PaperDispatch(db, "reference", Quality.VERIFIED, venue, lambda: now[0])
    assert not venue.events_after()
    venue.close()
    db.close()
