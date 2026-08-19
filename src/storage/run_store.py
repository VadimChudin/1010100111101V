from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import get_settings


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    plan_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(run_id, sequence)
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    decided_at TEXT,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_events_run_sequence ON run_events(run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_approvals_run_status ON approvals(run_id, status);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class PersistedRun:
    id: str
    user_id: str
    task: str
    status: str
    answer: str
    plan: dict[str, Any] | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PersistedApproval:
    id: str
    run_id: str
    action_type: str
    scope: dict[str, Any]
    status: str
    requested_at: str
    decided_at: str | None
    expires_at: str | None


class SQLiteRunStore:
    """Small, durable single-service store for the non-voice MVP.

    SQLite WAL is intentional here: it keeps the first Railway deployment within
    a single service + attached volume. The repository interface isolates this
    choice so a PostgreSQL implementation can replace it later without changing
    API, agent, or UI contracts.
    """

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_sync(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    async def initialize(self) -> None:
        if self._initialized:
            return
        await asyncio.to_thread(self._initialize_sync)
        self._initialized = True

    def _create_run_sync(self, run_id: str, user_id: str, task: str, status: str) -> PersistedRun:
        timestamp = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs (id, user_id, task, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, user_id, task, status, timestamp, timestamp),
            )
        return PersistedRun(run_id, user_id, task, status, "", None, timestamp, timestamp)

    async def create_run(self, run_id: str, user_id: str, task: str, status: str = "queued") -> PersistedRun:
        await self.initialize()
        return await asyncio.to_thread(self._create_run_sync, run_id, user_id, task, status)

    def _append_events_sync(self, run_id: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not events:
            return []
        timestamp = utc_now()
        persisted: list[dict[str, Any]] = []
        with self._connect() as connection:
            current_sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM run_events WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            for offset, event in enumerate(events, start=1):
                sequence = current_sequence + offset
                payload = event.get("payload", {})
                normalized = {
                    "sequence": sequence,
                    "type": str(event.get("type") or "system"),
                    "payload": payload if isinstance(payload, dict) else {"value": payload},
                    "created_at": timestamp,
                }
                connection.execute(
                    "INSERT INTO run_events (run_id, sequence, type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (run_id, sequence, normalized["type"], json.dumps(normalized["payload"], ensure_ascii=False), timestamp),
                )
                persisted.append(normalized)
        return persisted

    async def append_events(self, run_id: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        await self.initialize()
        return await asyncio.to_thread(self._append_events_sync, run_id, events)

    def _claim_run_sync(self, run_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
                ("running", utc_now(), run_id, "queued"),
            )
            return cursor.rowcount == 1

    async def claim_run(self, run_id: str) -> bool:
        await self.initialize()
        return await asyncio.to_thread(self._claim_run_sync, run_id)

    def _set_status_sync(self, run_id: str, status: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), run_id),
            )

    async def set_status(self, run_id: str, status: str) -> None:
        await self.initialize()
        await asyncio.to_thread(self._set_status_sync, run_id, status)

    def _complete_run_sync(self, run_id: str, status: str, answer: str, plan: dict[str, Any] | None) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, answer = ?, plan_json = ?, updated_at = ? WHERE id = ?",
                (status, answer, json.dumps(plan, ensure_ascii=False) if plan else None, utc_now(), run_id),
            )

    async def complete_run(self, run_id: str, status: str, answer: str, plan: dict[str, Any] | None) -> None:
        await self.initialize()
        await asyncio.to_thread(self._complete_run_sync, run_id, status, answer, plan)

    def _get_run_sync(self, run_id: str) -> PersistedRun | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return PersistedRun(
            id=row["id"],
            user_id=row["user_id"],
            task=row["task"],
            status=row["status"],
            answer=row["answer"],
            plan=json.loads(row["plan_json"]) if row["plan_json"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_run(self, run_id: str) -> PersistedRun | None:
        await self.initialize()
        return await asyncio.to_thread(self._get_run_sync, run_id)

    def _get_events_sync(self, run_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT sequence, type, payload_json, created_at FROM run_events WHERE run_id = ? AND sequence > ? ORDER BY sequence",
                (run_id, after_sequence),
            ).fetchall()
        return [
            {
                "sequence": row["sequence"],
                "type": row["type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def get_events(self, run_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        await self.initialize()
        return await asyncio.to_thread(self._get_events_sync, run_id, after_sequence)

    @staticmethod
    def _approval_from_row(row: sqlite3.Row) -> PersistedApproval:
        return PersistedApproval(
            id=row["id"],
            run_id=row["run_id"],
            action_type=row["action_type"],
            scope=json.loads(row["scope_json"]),
            status=row["status"],
            requested_at=row["requested_at"],
            decided_at=row["decided_at"],
            expires_at=row["expires_at"],
        )

    def _create_approval_sync(self, approval_id: str, run_id: str, action_type: str, scope: dict[str, Any]) -> PersistedApproval:
        timestamp = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO approvals (id, run_id, action_type, scope_json, status, requested_at) VALUES (?, ?, ?, ?, ?, ?)",
                (approval_id, run_id, action_type, json.dumps(scope, ensure_ascii=False), "pending", timestamp),
            )
        return PersistedApproval(approval_id, run_id, action_type, scope, "pending", timestamp, None, None)

    async def create_approval(self, approval_id: str, run_id: str, action_type: str, scope: dict[str, Any]) -> PersistedApproval:
        await self.initialize()
        return await asyncio.to_thread(self._create_approval_sync, approval_id, run_id, action_type, scope)

    def _get_approval_sync(self, approval_id: str) -> PersistedApproval | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return self._approval_from_row(row) if row else None

    async def get_approval(self, approval_id: str) -> PersistedApproval | None:
        await self.initialize()
        return await asyncio.to_thread(self._get_approval_sync, approval_id)

    def _resolve_approval_sync(self, approval_id: str, approved: bool, grant_scope: str) -> PersistedApproval | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if row is None or row["status"] != "pending":
                return self._approval_from_row(row) if row else None
            scope = json.loads(row["scope_json"])
            scope["grant_scope"] = grant_scope
            status = "approved" if approved else "denied"
            connection.execute(
                "UPDATE approvals SET status = ?, scope_json = ?, decided_at = ? WHERE id = ?",
                (status, json.dumps(scope, ensure_ascii=False), utc_now(), approval_id),
            )
            updated = connection.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return self._approval_from_row(updated)

    async def resolve_approval(self, approval_id: str, approved: bool, grant_scope: str) -> PersistedApproval | None:
        await self.initialize()
        return await asyncio.to_thread(self._resolve_approval_sync, approval_id, approved, grant_scope)

    def _list_approvals_sync(self, run_id: str, status: str | None = None) -> list[PersistedApproval]:
        query = "SELECT * FROM approvals WHERE run_id = ?"
        parameters: tuple[Any, ...] = (run_id,)
        if status:
            query += " AND status = ?"
            parameters = (run_id, status)
        query += " ORDER BY requested_at"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._approval_from_row(row) for row in rows]

    async def list_approvals(self, run_id: str, status: str | None = None) -> list[PersistedApproval]:
        await self.initialize()
        return await asyncio.to_thread(self._list_approvals_sync, run_id, status)

    async def approval_grants(self, run_id: str) -> set[str]:
        approvals = await self.list_approvals(run_id, status="approved")
        grants: set[str] = set()
        for approval in approvals:
            grant_scope = str(approval.scope.get("grant_scope", "once"))
            tool = str(approval.scope.get("tool", ""))
            if grant_scope == "all_approved_run":
                grants.add("all_approved_run")
            elif grant_scope in {"run", "workspace"} and tool:
                grants.add(tool)
        return grants


_store: SQLiteRunStore | None = None


def get_run_store() -> SQLiteRunStore:
    global _store
    if _store is None:
        _store = SQLiteRunStore(get_settings().state_database_path)
    return _store
