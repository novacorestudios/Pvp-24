from types import SimpleNamespace

import pytest

from pvb24.integrations.execution_adapter import ExecutionAdapter
from pvb24.state import Conflict


class Session:
    def __init__(self, recoveries):
        self.recoveries = iter(recoveries)
        self.entries = []
        self.actions = []
        self.pumps = []

    def recover(self, *, max_events=100):
        return next(self.recoveries)

    def dispatch_entry(self, client_id, inputs, book, *, max_events=100):
        self.entries.append((client_id, inputs, book, max_events))
        return "entry-ack"

    def dispatch_action(self, client_id, *, max_events=100):
        self.actions.append((client_id, max_events))
        return "action-ack"

    def pump_actions(self, *, max_actions=100, max_events=100):
        self.pumps.append((max_actions, max_events))
        return "pumped"


class Bridge:
    def __init__(self, session):
        self.local_session = session
        self.guards = 0

    def _guard(self):
        self.guards += 1


def recovery(*, caught_up=True, unresolved=()):
    return SimpleNamespace(caught_up=caught_up, unresolved=unresolved)


def test_entry_recovers_before_submit_and_after_pump():
    session = Session([recovery(), recovery(), recovery()])
    result = ExecutionAdapter(Bridge(session)).submit_entry("cid", "inputs", "book", max_events=7)
    assert result.response == "entry-ack"
    assert result.recovery.caught_up
    assert session.entries == [("cid", "inputs", "book", 7)]
    assert session.pumps == [(100, 7)]


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (recovery(caught_up=False), "recovery must finish"),
        (recovery(unresolved=("cid",)), "recovery must finish"),
    ],
)
def test_entry_never_submits_with_unresolved_execution(state, message):
    session = Session([state])
    with pytest.raises(Conflict, match=message):
        ExecutionAdapter(Bridge(session)).submit_entry("cid", "inputs", "book")
    assert not session.entries


def test_action_can_reconcile_unresolved_entry_but_not_backlog():
    session = Session([recovery(unresolved=("entry",)), recovery()])
    result = ExecutionAdapter(Bridge(session)).submit_action("protect")
    assert result.response == "action-ack"
    assert session.actions == [("protect", 100)]

    blocked = Session([recovery(caught_up=False)])
    with pytest.raises(Conflict, match="backlog"):
        ExecutionAdapter(Bridge(blocked)).submit_action("protect")
    assert not blocked.actions


def test_unbound_transport_fails_closed():
    with pytest.raises(RuntimeError, match="not bound"):
        ExecutionAdapter(Bridge(None)).recover()
