"""SQLite WAL journal, atomic snapshots and write-ahead order identity."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from pvb24.ids import canonical, client_identity


class Conflict(RuntimeError):
    pass


class Journal:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(path, isolation_level=None, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots (
                stream TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intents (
                client_id TEXT PRIMARY KEY, full_digest TEXT UNIQUE NOT NULL,
                identity TEXT UNIQUE NOT NULL, scope TEXT NOT NULL,
                signal_id TEXT NOT NULL, purpose TEXT NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_entry_per_signal
                ON intents(scope, signal_id) WHERE purpose = 'ENTRY';
        """)

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    @staticmethod
    def append_tx(db, event_id: str, payload) -> bool:
        encoded = canonical(payload)
        row = db.execute("SELECT payload FROM events WHERE event_id=?", (event_id,)).fetchone()
        if row:
            if row["payload"] != encoded:
                raise Conflict("Event identity reused with a different payload")
            return False
        db.execute("INSERT INTO events(event_id,payload) VALUES (?,?)", (event_id, encoded))
        return True

    def append(self, event_id: str, payload) -> bool:
        with self.transaction() as db:
            return self.append_tx(db, event_id, payload)

    def checkpoint(self, stream: str, expected_version: int, payload, event_id: str) -> int:
        with self.transaction() as db:
            row = db.execute("SELECT version FROM snapshots WHERE stream=?", (stream,)).fetchone()
            if (row["version"] if row else 0) != expected_version:
                raise Conflict("Snapshot changed concurrently")
            if not self.append_tx(db, event_id, {"stream": stream, "state": payload}):
                return expected_version
            version = expected_version + 1
            db.execute(
                "INSERT INTO snapshots VALUES(?,?,?) ON CONFLICT(stream) DO UPDATE SET "
                "version=excluded.version,payload=excluded.payload",
                (stream, version, canonical(payload)),
            )
            return version

    def snapshot(self, stream: str):
        row = self.db.execute("SELECT * FROM snapshots WHERE stream=?", (stream,)).fetchone()
        return (row["version"], json.loads(row["payload"])) if row else (0, None)

    def prepare_intent(self, scope: str, signal_id: str, purpose: str, payload, sequence=0):
        identity, full_digest, client_id = client_identity(scope, signal_id, purpose, sequence)
        encoded = canonical(payload)
        with self.transaction() as db:
            row = db.execute("SELECT * FROM intents WHERE client_id=?", (client_id,)).fetchone()
            if row:
                if row["identity"] != identity or row["payload"] != encoded:
                    raise Conflict("Client ID collision or changed intent")
                return client_id, False
            try:
                db.execute(
                    "INSERT INTO intents VALUES(?,?,?,?,?,?,?,?)",
                    (
                        client_id,
                        full_digest,
                        identity,
                        scope,
                        signal_id,
                        purpose,
                        encoded,
                        "PREPARED",
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise Conflict("Signal consumed or identity collision") from exc
            self.append_tx(db, "intent:" + full_digest, {"identity": identity, "payload": payload})
            return client_id, True

    def claim_dispatch(self, client_id: str) -> bool:
        # Must commit UNKNOWN before invoking an external order authority.
        # A second caller/restart cannot dispatch UNKNOWN; it must query first.
        with self.transaction() as db:
            result = db.execute(
                "UPDATE intents SET state='UNKNOWN' WHERE client_id=? AND state='PREPARED'",
                (client_id,),
            )
            if result.rowcount == 1:
                self.append_tx(db, "dispatch:" + client_id, {"state": "UNKNOWN"})
            return result.rowcount == 1

    def reconcile_intent(self, client_id: str, outcome: str, evidence):
        if outcome not in ("ACKNOWLEDGED", "FILLED", "CANCELED", "REJECTED"):
            raise ValueError("A proven external outcome is required; no automatic resubmission")
        with self.transaction() as db:
            row = db.execute("SELECT state FROM intents WHERE client_id=?", (client_id,)).fetchone()
            if not row:
                raise Conflict("Unknown order ownership")
            if row["state"] == "PREPARED":
                raise Conflict("Cannot reconcile an intent never dispatched")
            if row["state"] == "FILLED" and outcome != "FILLED":
                raise Conflict("A confirmed fill cannot be undone")
            if row["state"] in ("CANCELED", "REJECTED") and outcome == "ACKNOWLEDGED":
                raise Conflict("Terminal order cannot return to acknowledged")
            self.append_tx(db, "outcome:" + client_id + ":" + outcome, evidence)
            db.execute("UPDATE intents SET state=? WHERE client_id=?", (outcome, client_id))

    def close(self):
        self.db.close()
