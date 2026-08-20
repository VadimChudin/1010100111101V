from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_expires_at TEXT,
    last_error TEXT,
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


def utc_after(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


@dataclass(frozen=True)
class PersistedRun:
    id: str
    user_id: str
    task: str
    status: str
    answer: str
    plan: dict[str, Any] | None
    attempt_count: int
    lease_expires_at: str | None
    last_error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RecoveryResult:
    queued: list[PersistedRun]
    exhausted: list[PersistedRun]


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
            existing = {row["name"] for row in connection.execute("PRAGMA table_info(runs)").fetchall()}
            migrations = {
                "attempt_count": "ALTER TABLE runs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
                "lease_expires_at": "ALTER TABLE runs ADD COLUMN lease_expires_at TEXT",
                "last_error": "ALTER TABLE runs ADD COLUMN last_error TEXT",
            }
            for column, statement in migrations.items():
                if column not in existing:
                    connection.execute(statement)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_runs_status_lease ON runs(status, lease_expires_at)")

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
        return PersistedRun(run_id, user_id, task, status, "", None, 0, None, None, timestamp, timestamp)

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

    def _claim_run_sync(self, run_id: str, lease_seconds: int) -> bool:
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET status = ?, attempt_count = attempt_count + 1, lease_expires_at = ?, updated_at = ? WHERE id = ? AND status = ?",
                ("running", utc_after(lease_seconds), now, run_id, "queued"),
            )
            return cursor.rowcount == 1

    async def claim_run(self, run_id: str, lease_seconds: int = 120) -> bool:
        await self.initialize()
        return await asyncio.to_thread(self._claim_run_sync, run_id, lease_seconds)

    def _renew_lease_sync(self, run_id: str, lease_seconds: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET lease_expires_at = ?, updated_at = ? WHERE id = ? AND status = ?",
                (utc_after(lease_seconds), utc_now(), run_id, "running"),
            )
            return cursor.rowcount == 1

    async def renew_lease(self, run_id: str, lease_seconds: int) -> bool:
        await self.initialize()
        return await asyncio.to_thread(self._renew_lease_sync, run_id, lease_seconds)

    def _release_for_retry_sync(self, run_id: str, error: str, max_attempts: int) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT attempt_count FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return False
            retry = int(row["attempt_count"] or 0) < max_attempts
            connection.execute(
                "UPDATE runs SET status = ?, lease_expires_at = NULL, last_error = ?, updated_at = ? WHERE id = ?",
                ("queued" if retry else "failed", error[:1000], utc_now(), run_id),
            )
        return retry

    async def release_for_retry(self, run_id: str, error: str, max_attempts: int) -> bool:
        await self.initialize()
        return await asyncio.to_thread(self._release_for_retry_sync, run_id, error, max_attempts)

    def _recover_runs_sync(self, max_attempts: int, limit: int, include_queued: bool) -> RecoveryResult:
        now = utc_now()
        stale_clause = "(status = 'running' AND (lease_expires_at IS NULL OR lease_expires_at <= ?))"
        queued_clause = "status = 'queued' OR " if include_queued else ""
        query = f"SELECT * FROM runs WHERE {queued_clause}{stale_clause} ORDER BY updated_at LIMIT ?"
        with self._connect() as connection:
            rows = connection.execute(query, (now, limit)).fetchall()
            queued: list[PersistedRun] = []
            exhausted: list[PersistedRun] = []
            for row in rows:
                run = self._run_from_row(row)
                if run.status == "running" and run.attempt_count >= max_attempts:
                    connection.execute("UPDATE runs SET status = 'failed', lease_expires_at = NULL, last_error = ?, updated_at = ? WHERE id = ?", ("Worker lease expired after maximum attempts.", now, run.id))
                    exhausted.append(run)
                    continue
                if run.status == "running":
                    connection.execute("UPDATE runs SET status = 'queued', lease_expires_at = NULL, last_error = ?, updated_at = ? WHERE id = ?", ("Worker lease expired; run recovered for retry.", now, run.id))
                queued.append(run)
        return RecoveryResult(queued=queued, exhausted=exhausted)

    async def recover_runs(self, max_attempts: int, limit: int, include_queued: bool = True) -> RecoveryResult:
        await self.initialize()
        return await asyncio.to_thread(self._recover_runs_sync, max_attempts, limit, include_queued)

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
                "UPDATE runs SET status = ?, answer = ?, plan_json = ?, lease_expires_at = NULL, updated_at = ? WHERE id = ?",
                (status, answer, json.dumps(plan, ensure_ascii=False) if plan else None, utc_now(), run_id),
            )

    async def complete_run(self, run_id: str, status: str, answer: str, plan: dict[str, Any] | None) -> None:
        await self.initialize()
        await asyncio.to_thread(self._complete_run_sync, run_id, status, answer, plan)

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> PersistedRun:
        return PersistedRun(
            id=row["id"],
            user_id=row["user_id"],
            task=row["task"],
            status=row["status"],
            answer=row["answer"],
            plan=json.loads(row["plan_json"]) if row["plan_json"] else None,
            attempt_count=int(row["attempt_count"] or 0),
            lease_expires_at=row["lease_expires_at"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _get_run_sync(self, run_id: str) -> PersistedRun | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._run_from_row(row) if row is not None else None

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
