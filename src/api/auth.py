from __future__ import annotations

from fastapi import HTTPException, Request

from src.auth import AuthUser, ProjectRole, get_auth_store
from src.config import get_settings
from src.storage import get_run_store


async def current_user(request: Request) -> AuthUser | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    return await get_auth_store(get_run_store()).get_session_user(token)


async def require_user(request: Request) -> AuthUser:
    user = await current_user(request)
    if user is not None:
        return user
    if get_settings().auth_required:
        raise HTTPException(status_code=401, detail="Authentication is required")
    # Compatibility mode exists only until production OAuth credentials are configured.
    return AuthUser(id="anonymous", github_id="anonymous", login="anonymous", created_at="")


async def require_project_access(request: Request, project_id: str, minimum: ProjectRole = ProjectRole.VIEWER) -> AuthUser:
    user = await require_user(request)
    if not get_settings().auth_required:
        return user
    role = await get_auth_store(get_run_store()).require_project_role(project_id, user.id, minimum)
    if role is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return user


async def require_run_access(request: Request, run_id: str) -> AuthUser:
    user = await require_user(request)
    if not get_settings().auth_required:
        return user
    record = await get_run_store().get_run(run_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return user
