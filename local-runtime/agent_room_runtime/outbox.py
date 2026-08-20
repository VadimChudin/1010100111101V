from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class LocalOutbox:
    """Durable local event queue. Cloud acknowledgement is idempotent by event_id."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS received_events (
                    sequence INTEGER PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    received_at TEXT NOT NULL
                );
                """
            )

    def enqueue(self, event: dict[str, Any], created_at: str) -> None:
        event_id = str(event["event_id"])
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO outbox_events (event_id, payload_json, created_at) VALUES (?, ?, ?) ON CONFLICT(event_id) DO NOTHING",
                (event_id, json.dumps(event, separators=(",", ":")), created_at),
            )

    def pending(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM outbox_events WHERE acknowledged_at IS NULL ORDER BY created_at, event_id LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def acknowledge(self, event_ids: list[str], acknowledged_at: str) -> None:
        if not event_ids:
            return
        with self._connect() as connection:
            connection.executemany(
                "UPDATE outbox_events SET acknowledged_at = ? WHERE event_id = ?", ((acknowledged_at, event_id) for event_id in event_ids)
            )

    def cursor(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM sync_state WHERE key = 'server_cursor'").fetchone()
        return int(row["value"]) if row else 0

    def apply_server_events(self, events: list[dict[str, Any]], server_cursor: int, received_at: str) -> None:
        with self._connect() as connection:
            for event in events:
                connection.execute(
                    "INSERT INTO received_events (sequence, payload_json, received_at) VALUES (?, ?, ?) ON CONFLICT(sequence) DO NOTHING",
                    (int(event["sequence"]), json.dumps(event, separators=(",", ":")), received_at),
                )
            connection.execute(
                "INSERT INTO sync_state (key, value) VALUES ('server_cursor', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(server_cursor),),
            )

    def received(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM received_events ORDER BY sequence").fetchall()
        return [json.loads(row["payload_json"]) for row in rows]
