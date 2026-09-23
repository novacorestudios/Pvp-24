"""Execution adapter over the durable PVB-24 PAPER authority.

The adapter adds no exchange path.  It normalizes the runtime's entry/action
lifecycle around PaperSession so every submit is write-ahead, recoverable and
idempotent. LIVE and unqualified transports remain outside this boundary.
"""

from dataclasses import dataclass

from pvb24.state import Conflict


@dataclass(frozen=True)
class ExecutionResult:
    response: object
    recovery: object


class ExecutionAdapter:
    def __init__(self, bridge):
        self.bridge = bridge

    def _session(self):
        self.bridge._guard()
        session = self.bridge.local_session
        if session is None:
            raise RuntimeError("Qualified local PAPER session is not bound")
        return session

    def recover(self, *, max_events=100):
        return self._session().recover(max_events=max_events)

    def submit_entry(self, client_id, inputs, book, *, max_events=100):
        session = self._session()
        recovery = session.recover(max_events=max_events)
        if not recovery.caught_up or recovery.unresolved:
            raise Conflict("Execution recovery must finish before entry submission")
        response = session.dispatch_entry(client_id, inputs, book, max_events=max_events)
        session.pump_actions(max_events=max_events)
        return ExecutionResult(response, session.recover(max_events=max_events))

    def submit_action(self, client_id, *, max_events=100):
        session = self._session()
        recovery = session.recover(max_events=max_events)
        if not recovery.caught_up:
            raise Conflict("Execution evidence backlog must drain before action submission")
        response = session.dispatch_action(client_id, max_events=max_events)
        return ExecutionResult(response, session.recover(max_events=max_events))

    def pump(self, *, max_actions=100, max_events=100):
        session = self._session()
        recovery = session.recover(max_events=max_events)
        if not recovery.caught_up:
            raise Conflict("Execution evidence backlog must drain before action pump")
        return session.pump_actions(max_actions=max_actions, max_events=max_events)
