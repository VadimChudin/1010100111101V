from __future__ import annotations

import pytest

from src.auth import GitHubProfile, ProjectRole, get_auth_store
from src.storage.run_store import SQLiteRunStore
from src.workspace import get_workspace_store


@pytest.mark.asyncio
async def test_auth_state_session_and_project_role_are_durable(tmp_path):
    run_store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    await get_workspace_store(run_store).ensure_default_project()
    store = get_auth_store(run_store)

    state, verifier = await store.create_oauth_state()
    assert await store.consume_oauth_state(state) == verifier
    assert await store.consume_oauth_state(state) is None

    user = await store.upsert_user(GitHubProfile(github_id="42", login="octo", email="octo@example.com"))
    token = await store.create_session(user.id)
    assert (await store.get_session_user(token)).login == "octo"
    await store.revoke_session(token)
    assert await store.get_session_user(token) is None

    assert await store.claim_unowned_default(user.id) is True
    assert await store.require_project_role("default", user.id, ProjectRole.VIEWER) == ProjectRole.OWNER


@pytest.mark.asyncio
async def test_cors_only_allows_registered_frontend_origin():
    from httpx import ASGITransport, AsyncClient
    from src.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        allowed = await client.options("/v1/healthz", headers={"Origin": "https://frontend-swart-alpha-20.vercel.app", "Access-Control-Request-Method": "POST"})
        denied = await client.options("/v1/healthz", headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"})

    assert allowed.headers["access-control-allow-origin"] == "https://frontend-swart-alpha-20.vercel.app"
    assert "access-control-allow-origin" not in denied.headers
