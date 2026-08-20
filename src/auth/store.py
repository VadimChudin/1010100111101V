from __future__ import annotations

import asyncio
import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from src.storage import SQLiteRunStore

from .models import AuthUser, GitHubProfile, ProjectRole


AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    github_id TEXT NOT NULL UNIQUE,
    login TEXT NOT NULL,
    email TEXT,
    avatar_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_oauth_states (
    state_hash TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id);
"""


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def expires_in(minutes: int) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def valid_until(value: str) -> bool:
    return datetime.fromisoformat(value) > datetime.now(UTC)


class AuthStore:
    def __init__(self, run_store: SQLiteRunStore) -> None:
        self.run_store = run_store
        self.database_path = Path(run_store.database_path)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self.run_store.initialize()

        def create_schema() -> None:
            with self._connect() as connection:
                connection.executescript(AUTH_SCHEMA)

        await asyncio.to_thread(create_schema)
        self._initialized = True

    @staticmethod
    def _user(row: sqlite3.Row) -> AuthUser:
        return AuthUser(
            id=row["id"], github_id=row["github_id"], login=row["login"], email=row["email"], avatar_url=row["avatar_url"], created_at=row["created_at"],
        )

    def _save_oauth_state_sync(self, state: str, verifier: str) -> None:
        now = timestamp()
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_oauth_states WHERE expires_at < ?", (now,))
            connection.execute(
                "INSERT INTO auth_oauth_states (state_hash, code_verifier, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (digest(state), verifier, expires_in(10), now),
            )

    async def create_oauth_state(self) -> tuple[str, str]:
        await self.initialize()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        await asyncio.to_thread(self._save_oauth_state_sync, state, verifier)
        return state, verifier

    def _consume_oauth_state_sync(self, state: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM auth_oauth_states WHERE state_hash = ?", (digest(state),)).fetchone()
            connection.execute("DELETE FROM auth_oauth_states WHERE state_hash = ?", (digest(state),))
        if row is None or not valid_until(row["expires_at"]):
            return None
        return str(row["code_verifier"])

    async def consume_oauth_state(self, state: str) -> str | None:
        await self.initialize()
        return await asyncio.to_thread(self._consume_oauth_state_sync, state)

    def _upsert_user_sync(self, profile: GitHubProfile) -> AuthUser:
        now = timestamp()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE github_id = ?", (profile.github_id,)).fetchone()
            if row is None:
                user_id = str(uuid4())
                connection.execute(
                    "INSERT INTO users (id, github_id, login, email, avatar_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, profile.github_id, profile.login, profile.email, profile.avatar_url, now, now),
                )
            else:
                user_id = str(row["id"])
                connection.execute(
                    "UPDATE users SET login = ?, email = ?, avatar_url = ?, updated_at = ? WHERE id = ?",
                    (profile.login, profile.email, profile.avatar_url, now, user_id),
                )
            saved = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user(saved)

    async def upsert_user(self, profile: GitHubProfile) -> AuthUser:
        await self.initialize()
        return await asyncio.to_thread(self._upsert_user_sync, profile)

    def _create_session_sync(self, user_id: str) -> str:
        token = secrets.token_urlsafe(48)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, expires_at, created_at, revoked_at) VALUES (?, ?, ?, ?, NULL)",
                (digest(token), user_id, expires_in(60 * 24 * 7), timestamp()),
            )
        return token

    async def create_session(self, user_id: str) -> str:
        await self.initialize()
        return await asyncio.to_thread(self._create_session_sync, user_id)

    def _get_session_user_sync(self, token: str) -> AuthUser | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT users.* FROM auth_sessions JOIN users ON users.id = auth_sessions.user_id WHERE auth_sessions.token_hash = ? AND auth_sessions.revoked_at IS NULL",
                (digest(token),),
            ).fetchone()
            if row is None:
                return None
            session = connection.execute("SELECT expires_at FROM auth_sessions WHERE token_hash = ?", (digest(token),)).fetchone()
        return self._user(row) if session is not None and valid_until(session["expires_at"]) else None

    async def get_session_user(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        await self.initialize()
        return await asyncio.to_thread(self._get_session_user_sync, token)

    def _revoke_session_sync(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ?", (timestamp(), digest(token)))

    async def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        await self.initialize()
        await asyncio.to_thread(self._revoke_session_sync, token)

    def _grant_role_sync(self, project_id: str, user_id: str, role: ProjectRole) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO project_members (project_id, user_id, role, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
                (project_id, user_id, role, timestamp()),
            )

    async def grant_role(self, project_id: str, user_id: str, role: ProjectRole) -> None:
        await self.initialize()
        await asyncio.to_thread(self._grant_role_sync, project_id, user_id, role)

    def _role_sync(self, project_id: str, user_id: str) -> ProjectRole | None:
        with self._connect() as connection:
            row = connection.execute("SELECT role FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id)).fetchone()
        return ProjectRole(row["role"]) if row else None

    async def role_for_project(self, project_id: str, user_id: str) -> ProjectRole | None:
        await self.initialize()
        return await asyncio.to_thread(self._role_sync, project_id, user_id)

    async def require_project_role(self, project_id: str, user_id: str, minimum: ProjectRole = ProjectRole.VIEWER) -> ProjectRole | None:
        role = await self.role_for_project(project_id, user_id)
        levels = {ProjectRole.VIEWER: 1, ProjectRole.EDITOR: 2, ProjectRole.OWNER: 3}
        return role if role is not None and levels[role] >= levels[minimum] else None

    def _projects_for_user_sync(self, user_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT project_id FROM project_members WHERE user_id = ? ORDER BY created_at", (user_id,)).fetchall()
        return [str(row["project_id"]) for row in rows]

    async def projects_for_user(self, user_id: str) -> list[str]:
        await self.initialize()
        return await asyncio.to_thread(self._projects_for_user_sync, user_id)

    def _claim_unowned_default_sync(self, user_id: str) -> bool:
        with self._connect() as connection:
            default = connection.execute("SELECT id FROM projects WHERE id = 'default'").fetchone()
            if default is None:
                return False
            assigned = connection.execute("SELECT 1 FROM project_members WHERE project_id = 'default' LIMIT 1").fetchone()
            if assigned is not None:
                return False
            connection.execute(
                "INSERT INTO project_members (project_id, user_id, role, created_at) VALUES ('default', ?, ?, ?)",
                (user_id, ProjectRole.OWNER, timestamp()),
            )
        return True

    async def claim_unowned_default(self, user_id: str) -> bool:
        await self.initialize()
        return await asyncio.to_thread(self._claim_unowned_default_sync, user_id)


_store: AuthStore | None = None


def get_auth_store(run_store: SQLiteRunStore) -> AuthStore:
    global _store
    if _store is None or _store.run_store is not run_store:
        _store = AuthStore(run_store)
    return _store
