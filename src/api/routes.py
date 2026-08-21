from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.api.auth import current_user, require_project_access, require_run_access, require_user
from src.auth import AuthStatus, DesktopAuthorizationStart, DesktopAuthorizationStatus, GitHubCloneSource, GitHubRepository, ProjectRole, get_auth_store
from src.auth.github import GitHubOAuth, GitHubOAuthError
from src.config import get_settings
from src.events import get_event_broker
from src.orchestrator.conversation import requires_project_work, run_conversation, run_project_clarification
from src.omniroute.router import OmniRoute, OpenRouterUnavailableError
from src.orchestrator.graph import run_agent
from src.orchestrator.schemas import AgentPlan
from src.policy import ApprovalDecisionRequest, ApprovalMode, ToolCallRequest, ToolCallResponse
from src.storage import get_run_store
from src.tools.gateway import ToolGateway
from src.tools.serena import SerenaClient
from src.workspace import (
    DeviceJob,
    DeviceJobApprovalRequest,
    DeviceJobCreateRequest,
    DevicePairing,
    DevicePairingRequest,
    DeviceRegistration,
    DeviceRegistrationRequest,
    DeviceSyncRequest,
    DeviceSyncResponse,
    GraphitiEpisodeEnvelope,
    LocalWorkspace,
    LocalWorkspaceManifest,
    ModuleCreateRequest,
    NoteCreateRequest,
    ProjectCreateRequest,
    ProjectDevice,
    ProjectSource,
    ProjectSourceSelectionRequest,
    ProjectEventType,
    RepositoryFile,
    RepositoryIndex,
    TaskCreateRequest,
    TaskStatusRequest,
    WorkspaceModule,
    WorkspaceNote,
    WorkspaceProject,
    WorkspaceSnapshot,
    WorkspaceTask,
    get_workspace_store,
)

router = APIRouter(prefix="/v1")

class DesktopAuthorizationClaim(BaseModel):
    session_token: str
    user: dict


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    user_id: str = "anonymous"
    approval_mode: ApprovalMode = ApprovalMode.CONFIRM_EACH


class AgentConnectionStatus(BaseModel):
    authenticated: bool = True
    provider: str = "OpenRouter"
    configured: bool
    state: str
    detail: str
    preferred_chat_model: str
    fallback_models: int


class PublicPlanStep(BaseModel):
    id: str
    title: str
    description: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class PublicAgentPlan(BaseModel):
    goal: str
    steps: list[PublicPlanStep] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class ChatRunResponse(BaseModel):
    run_id: str
    status: str
    answer: str = ""
    plan: PublicAgentPlan
    events: list[dict] = Field(default_factory=list)


class RunDetailResponse(ChatRunResponse):
    task: str
    created_at: str
    updated_at: str


def public_plan(plan_payload: dict | None, task: str) -> PublicAgentPlan:
    plan = AgentPlan.from_payload(plan_payload or {}, task)
    return PublicAgentPlan(
        goal=plan.goal,
        steps=[
            PublicPlanStep(
                id=step.id,
                title=step.title,
                description=step.description,
                depends_on=step.depends_on,
            )
            for step in plan.steps
        ],
        acceptance_criteria=plan.acceptance_criteria,
    )


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/agent/status", response_model=AgentConnectionStatus)
async def agent_connection_status(request: Request):
    await require_user(request)
    settings = get_settings()
    router_client = OmniRoute()
    try:
        provider = await router_client.provider_status()
    finally:
        await router_client.close()
    return AgentConnectionStatus(
        configured=bool(settings.openrouter_api_key),
        state=provider.state,
        detail=provider.detail,
        preferred_chat_model="nvidia/nemotron-3-nano-30b-a3b:free",
        fallback_models=max(0, settings.openrouter_max_fallback_models - 1),
    )


@router.get("/auth/status", response_model=AuthStatus)
async def auth_status(request: Request):
    user = await current_user(request)
    settings = get_settings()
    return AuthStatus(authenticated=user is not None, user=user, github_configured=bool(settings.github_oauth_client_id and settings.github_oauth_client_secret))


@router.post("/auth/desktop/start", response_model=DesktopAuthorizationStart, status_code=201)
async def start_desktop_authorization():
    oauth = GitHubOAuth(get_auth_store(get_run_store()))
    try:
        request_id, request_secret, authorize_url, expires_at = await oauth.desktop_authorization_url()
        return DesktopAuthorizationStart(
            request_id=request_id,
            request_secret=request_secret,
            authorize_url=authorize_url,
            expires_at=expires_at,
        )
    except GitHubOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/auth/desktop/{request_id}", response_model=DesktopAuthorizationStatus)
async def desktop_authorization_status(
    request_id: str,
    x_desktop_authorization: str | None = Header(default=None, alias="X-Desktop-Authorization"),
):
    if not x_desktop_authorization:
        raise HTTPException(status_code=401, detail="Desktop authorization secret is required")
    result = await get_auth_store(get_run_store()).desktop_authorization_status(request_id, x_desktop_authorization)
    if result is None:
        raise HTTPException(status_code=404, detail="Desktop authorization request was not found")
    status, expires_at, user = result
    return DesktopAuthorizationStatus(status=status, expires_at=expires_at, user=user)


@router.post("/auth/desktop/{request_id}/claim", response_model=DesktopAuthorizationClaim)
async def claim_desktop_authorization(
    request_id: str,
    x_desktop_authorization: str | None = Header(default=None, alias="X-Desktop-Authorization"),
):
    if not x_desktop_authorization:
        raise HTTPException(status_code=401, detail="Desktop authorization secret is required")
    result = await get_auth_store(get_run_store()).claim_desktop_authorization(request_id, x_desktop_authorization)
    if result is None:
        raise HTTPException(status_code=409, detail="Desktop authorization is not ready or has already been claimed")
    token, user = result
    return DesktopAuthorizationClaim(session_token=token, user=user.model_dump(mode="json"))


@router.get("/auth/github/login")
async def github_login():
    oauth = GitHubOAuth(get_auth_store(get_run_store()))
    try:
        return RedirectResponse(await oauth.authorization_url(), status_code=302)
    except GitHubOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/auth/github/callback")
async def github_callback(code: str, state: str):
    settings = get_settings()
    auth_store = get_auth_store(get_run_store())
    desktop_request_id = await auth_store.desktop_request_for_state(state)
    oauth = GitHubOAuth(auth_store)
    try:
        profile, github_token, github_scopes = await oauth.callback(code, state)
    except (GitHubOAuthError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=401, detail="GitHub authentication failed") from exc
    user = await auth_store.upsert_user(profile)
    await auth_store.save_github_credential(user.id, github_token, github_scopes)
    await workspace_store().ensure_default_project()
    await auth_store.claim_unowned_default(user.id)
    if desktop_request_id:
        if not await auth_store.complete_desktop_authorization(desktop_request_id, user.id):
            raise HTTPException(status_code=409, detail="Desktop authorization has expired or was already completed")
        return HTMLResponse(
            "<main style='font-family:system-ui;max-width:42rem;margin:10vh auto;padding:2rem;line-height:1.55'>"
            "<h1>Agent Room is connected</h1>"
            "<p>You can return to the Agent Room desktop application. This browser did not receive a desktop session credential.</p>"
            "<p style='color:#52606d'>You may safely close this tab.</p></main>",
            status_code=200,
        )
    token = await auth_store.create_session(user.id)
    frontend_url = settings.frontend_origins.split(",")[1] if "," in settings.frontend_origins else settings.frontend_origins
    response = RedirectResponse(frontend_url, status_code=302)
    response.set_cookie(settings.session_cookie_name, token, httponly=True, secure=True, samesite="none", max_age=60 * 60 * 24 * 7, path="/")
    return response


@router.get("/auth/github/repositories", response_model=list[GitHubRepository])
async def list_github_repositories(request: Request):
    user = await require_user(request)
    token = await get_auth_store(get_run_store()).github_token_for_user(user.id)
    if not token:
        raise HTTPException(status_code=409, detail="GitHub repository access requires a fresh GitHub authorization")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    params = {"visibility": "all", "affiliation": "owner,collaborator,organization_member", "sort": "updated", "direction": "desc", "per_page": 100}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://api.github.com/user/repos", headers=headers, params=params)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not retrieve GitHub repositories") from exc
    return [
        GitHubRepository(
            id=str(item["id"]),
            full_name=str(item["full_name"]),
            description=item.get("description"),
            private=bool(item.get("private")),
            default_branch=str(item.get("default_branch") or "main"),
            html_url=str(item["html_url"]),
            clone_url=str(item["clone_url"]),
            updated_at=item.get("updated_at"),
        )
        for item in response.json()
    ]


@router.get("/auth/github/repositories/{repository_id}/clone-source", response_model=GitHubCloneSource)
async def github_clone_source(repository_id: str, request: Request):
    user = await require_user(request)
    token = await get_auth_store(get_run_store()).github_token_for_user(user.id)
    if not token:
        raise HTTPException(status_code=409, detail="GitHub repository access requires a fresh GitHub authorization")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"https://api.github.com/repositories/{repository_id}", headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="GitHub repository is not available to this account") from exc
        raise HTTPException(status_code=502, detail="Could not resolve GitHub repository") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not resolve GitHub repository") from exc
    item = response.json()
    return GitHubCloneSource(
        id=str(item["id"]),
        full_name=str(item["full_name"]),
        clone_url=str(item["clone_url"]),
        access_token=token,
    )


@router.post("/auth/logout", status_code=204)
async def logout(request: Request):
    settings = get_settings()
    await get_auth_store(get_run_store()).revoke_session(request.cookies.get(settings.session_cookie_name))
    response = RedirectResponse(settings.frontend_origins.split(",")[1] if "," in settings.frontend_origins else settings.frontend_origins, status_code=303)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


@router.get("/serena/status")
async def serena_status():
    client = SerenaClient()
    return {
        "available": client.available,
        "mode": "read_only",
        "tools": ["get_symbols_overview", "find_symbol", "find_referencing_symbols"],
        "reason": None if client.available else "Enable the Serena MCP provider to activate semantic code queries.",
    }


def workspace_store():
    return get_workspace_store(get_run_store())


@router.get("/projects", response_model=list[WorkspaceProject])
async def list_projects(request: Request):
    store = workspace_store()
    await store.ensure_default_project()
    user = await require_user(request)
    projects = await store.list_projects()
    if not get_settings().auth_required:
        return projects
    allowed = set(await get_auth_store(get_run_store()).projects_for_user(user.id))
    return [project for project in projects if project.id in allowed]


@router.post("/projects", response_model=WorkspaceProject, status_code=201)
async def create_project(payload: ProjectCreateRequest, request: Request):
    user = await require_user(request)
    project = await workspace_store().create_project(payload)
    if get_settings().auth_required:
        await get_auth_store(get_run_store()).grant_role(project.id, user.id, ProjectRole.OWNER)
    return project


@router.get("/projects/{project_id}/workspace", response_model=WorkspaceSnapshot)
async def get_workspace(project_id: str, request: Request):
    await require_project_access(request, project_id)
    store = workspace_store()
    snapshot = await store.snapshot(project_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return snapshot


@router.get("/projects/{project_id}/repository", response_model=RepositoryIndex)
async def get_project_repository(project_id: str, request: Request):
    await require_project_access(request, project_id)
    index = await workspace_store().repository_index(project_id)
    if index is None:
        raise HTTPException(status_code=404, detail="Repository has not been indexed")
    return index


@router.get("/projects/{project_id}/files", response_model=list[RepositoryFile])
async def get_project_files(project_id: str, request: Request):
    await require_project_access(request, project_id)
    store = workspace_store()
    if await store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return await store.repository_files(project_id)


@router.post("/projects/{project_id}/index", response_model=RepositoryIndex)
async def index_project_repository(project_id: str, request: Request):
    await require_project_access(request, project_id, ProjectRole.EDITOR)
    try:
        return await workspace_store().index_repository(project_id, Path(get_settings().workspace_root))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Repository index is unavailable") from exc


@router.post("/projects/{project_id}/devices/pair", response_model=DevicePairing, status_code=201)
async def create_device_pairing(project_id: str, payload: DevicePairingRequest, request: Request):
    user = await require_project_access(request, project_id, ProjectRole.OWNER)
    try:
        return await workspace_store().create_device_pairing(project_id, user.id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@router.post("/projects/{project_id}/devices/register", response_model=DeviceRegistration, status_code=201)
async def register_project_device(project_id: str, payload: DeviceRegistrationRequest):
    try:
        return await workspace_store().register_device(project_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail="Pairing token is invalid or expired") from exc


@router.get("/projects/{project_id}/devices", response_model=list[ProjectDevice])
async def get_project_devices(project_id: str, request: Request):
    await require_project_access(request, project_id)
    return await workspace_store().list_devices(project_id)


@router.get("/projects/{project_id}/local-workspaces", response_model=list[LocalWorkspace])
async def get_project_local_workspaces(project_id: str, request: Request, device_id: str | None = None):
    await require_project_access(request, project_id)
    return await workspace_store().local_workspaces(project_id, device_id=device_id)


@router.get("/projects/{project_id}/source", response_model=ProjectSource | None)
async def get_project_source(project_id: str, request: Request):
    await require_project_access(request, project_id)
    return await workspace_store().project_source(project_id)


@router.put("/projects/{project_id}/source", response_model=ProjectSource)
async def set_project_source(project_id: str, payload: ProjectSourceSelectionRequest, request: Request):
    user = await require_project_access(request, project_id, ProjectRole.OWNER)
    try:
        return await workspace_store().select_project_source(project_id, user.id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/projects/{project_id}/devices/jobs", response_model=list[DeviceJob])
async def get_project_device_jobs(project_id: str, request: Request, device_id: str | None = None, limit: int = 50):
    await require_project_access(request, project_id)
    return await workspace_store().list_device_jobs(project_id, device_id=device_id, limit=min(max(limit, 1), 100))


@router.post("/projects/{project_id}/devices/jobs", response_model=DeviceJob, status_code=201)
async def create_project_device_job(project_id: str, payload: DeviceJobCreateRequest, request: Request):
    user = await require_project_access(request, project_id, ProjectRole.EDITOR)
    try:
        return await workspace_store().create_device_job(project_id, user.id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/projects/{project_id}/devices/jobs/{job_id}/approval", response_model=DeviceJob)
async def approve_project_device_job(project_id: str, job_id: str, payload: DeviceJobApprovalRequest, request: Request):
    user = await require_project_access(request, project_id, ProjectRole.OWNER)
    job = await workspace_store().approve_device_job(project_id, job_id, user.id, payload.approved)
    if job is None:
        raise HTTPException(status_code=409, detail="Device job cannot be approved in its current state")
    return job


async def require_registered_device(project_id: str, device_id: str, device_token: str) -> ProjectDevice:
    device = await workspace_store().authenticate_device(project_id, device_token)
    if device is None or device.id != device_id:
        raise HTTPException(status_code=401, detail="Device authentication failed")
    return device


@router.post("/projects/{project_id}/devices/{device_id}/workspaces", response_model=LocalWorkspace, status_code=201)
async def register_device_local_workspace(project_id: str, device_id: str, payload: LocalWorkspaceManifest, x_device_token: str | None = Header(default=None)):
    await require_registered_device(project_id, device_id, x_device_token or "")
    try:
        return await workspace_store().upsert_local_workspace(project_id, device_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/projects/{project_id}/devices/{device_id}/sync", response_model=DeviceSyncResponse)
async def sync_project_device(
    project_id: str,
    device_id: str,
    payload: DeviceSyncRequest,
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
):
    if not x_device_token:
        raise HTTPException(status_code=401, detail="Device authentication is required")
    await require_registered_device(project_id, device_id, x_device_token)
    try:
        return await workspace_store().sync_device(project_id, device_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail="Device authentication failed") from exc


@router.post("/projects/{project_id}/graphiti/episodes", status_code=202)
async def record_graphiti_episode(project_id: str, payload: GraphitiEpisodeEnvelope, request: Request):
    user = await require_project_access(request, project_id, ProjectRole.EDITOR)
    event = await workspace_store().record_cloud_event(
        project_id, user.id, ProjectEventType.GRAPHITI_EPISODE, payload.episode_id, payload.model_dump(), payload.occurred_at
    )
    return {"sequence": event.sequence, "episode_id": payload.episode_id}


@router.get("/projects/{project_id}/graphiti/episodes", response_model=list[GraphitiEpisodeEnvelope])
async def get_graphiti_episodes(project_id: str, request: Request, limit: int = 50):
    await require_project_access(request, project_id)
    return await workspace_store().graphiti_episodes(project_id, min(max(limit, 1), 100))


@router.post("/projects/{project_id}/modules", response_model=WorkspaceModule, status_code=201)
async def create_module(project_id: str, payload: ModuleCreateRequest, request: Request):
    await require_project_access(request, project_id, ProjectRole.EDITOR)
    store = workspace_store()
    if await store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return await store.create_module(project_id, payload)


@router.post("/projects/{project_id}/notes", response_model=WorkspaceNote, status_code=201)
async def create_note(project_id: str, payload: NoteCreateRequest, request: Request):
    user = await require_project_access(request, project_id, ProjectRole.EDITOR)
    try:
        note = await workspace_store().create_note(project_id, payload, author=user.login)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Module not found in project") from exc
    await workspace_store().record_cloud_event(
        project_id, user.id, ProjectEventType.NOTE_CREATED, note.id, {**payload.model_dump(mode="json"), "author": user.login}, note.created_at
    )
    return note


@router.post("/projects/{project_id}/tasks", response_model=WorkspaceTask, status_code=201)
async def create_workspace_task(project_id: str, payload: TaskCreateRequest, request: Request):
    user = await require_project_access(request, project_id, ProjectRole.EDITOR)
    try:
        task = await workspace_store().create_task(project_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Module not found in project") from exc
    await workspace_store().record_cloud_event(project_id, user.id, ProjectEventType.TASK_CREATED, task.id, payload.model_dump(mode="json"), task.created_at)
    return task


@router.patch("/projects/{project_id}/tasks/{task_id}", response_model=WorkspaceTask)
async def update_workspace_task(project_id: str, task_id: str, payload: TaskStatusRequest, request: Request):
    user = await require_project_access(request, project_id, ProjectRole.EDITOR)
    store = workspace_store()
    task = await store.set_task_status(task_id, payload.status)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    await store.record_cloud_event(project_id, user.id, ProjectEventType.TASK_STATUS_CHANGED, task_id, payload.model_dump(mode="json"), task.updated_at)
    return task

@router.post("/chat", response_model=ChatRunResponse)
async def chat(payload: ChatRequest, request: Request):
    user = await require_user(request)
    run_id = str(uuid4())
    store = get_run_store()
    await store.create_run(run_id, user.id, payload.message)
    try:
        state = await run_agent(payload.message, run_id, user.id)
        status = str(state.get("status") or "failed")
        answer = str(state.get("review", {}).get("comment", ""))
        plan = public_plan(state.get("plan"), payload.message)
        response_events = list(state.get("events", []))
        await store.append_events(run_id, response_events)
        await store.complete_run(run_id, status, answer, plan.model_dump())
        return ChatRunResponse(run_id=run_id, status=status, answer=answer, plan=plan, events=response_events)
    except Exception as exc:
        failure_event = {"type": "run.failed", "payload": {"message": "The agent run could not be completed."}}
        await store.append_events(run_id, [failure_event])
        await store.complete_run(run_id, "failed", "", None)
        raise HTTPException(status_code=502, detail="The agent run could not be completed.") from exc


async def execute_conversation_run(run_id: str, message: str) -> tuple[str, str]:
    """Persist a direct low-cost chat answer through the same durable event stream."""
    store = get_run_store()

    async def event_sink(event: dict) -> None:
        await store.append_events(run_id, [event])
        get_event_broker().publish(run_id)

    await event_sink({"type": "run.started", "payload": {"run_id": run_id, "mode": "chat"}})
    try:
        answer, model = await run_conversation(message, run_id, event_sink)
        plan = {"goal": message, "steps": [], "acceptance_criteria": []}
        await store.complete_run(run_id, "completed", answer, plan)
        await event_sink(
            {
                "type": "run.completed",
                "payload": {
                    "status": "completed",
                    "mode": "chat",
                    "model": model,
                    "review": {"approved": True, "comment": answer},
                },
            }
        )
        return "completed", answer
    except OpenRouterUnavailableError as exc:
        message = str(exc)
        await store.complete_run(run_id, "failed", message, None)
        await event_sink({"type": "run.failed", "payload": {"message": message, "provider_code": exc.code}})
        return "failed", message
    except Exception:
        message = "Agent Room could not complete the chat request. Retry in a moment."
        await store.complete_run(run_id, "failed", message, None)
        await event_sink({"type": "run.failed", "payload": {"message": message}})
        return "failed", message


async def execute_project_clarification_run(run_id: str, message: str) -> None:
    """Return the first clarification response before a task can become executable work."""
    store = get_run_store()

    async def event_sink(event: dict) -> None:
        await store.append_events(run_id, [event])
        get_event_broker().publish(run_id)

    await event_sink({"type": "run.started", "payload": {"run_id": run_id, "mode": "clarification"}})
    try:
        answer, model = await run_project_clarification(message, run_id, event_sink)
        plan = {"goal": message, "steps": [], "acceptance_criteria": []}
        await store.complete_run(run_id, "completed", answer, plan)
        await event_sink(
            {
                "type": "run.completed",
                "payload": {
                    "status": "completed",
                    "mode": "clarification",
                    "model": model,
                    "task_state": "clarifying",
                    "review": {"approved": True, "comment": answer},
                },
            }
        )
    except Exception:
        await store.complete_run(run_id, "failed", "", None)
        await event_sink({"type": "run.failed", "payload": {"message": "The project clarification could not be completed."}})


@router.post("/runs")
async def create_run(payload: ChatRequest, request: Request):
    user = await require_user(request)
    run_id = str(uuid4())
    store = get_run_store()
    project_mode = requires_project_work(payload.message)
    await store.create_run(run_id, user.id, payload.message)
    await store.append_events(
        run_id,
        [{"type": "run.created", "payload": {"approval_mode": payload.approval_mode, "mode": "project" if project_mode else "chat"}}],
    )

    if not project_mode:
        # A direct conversation is short and read-only. Completing it inside the
        # request means a lost/reopened SSE connection cannot leave the user
        # staring at a perpetual activity indicator with no visible answer.
        status, answer = await execute_conversation_run(run_id, payload.message)
        return {"run_id": run_id, "status": status, "task": payload.message, "mode": "chat", "answer": answer}

    asyncio.create_task(execute_project_clarification_run(run_id, payload.message), name=f"project-clarification-{run_id}")
    return {"run_id": run_id, "status": "queued", "task": payload.message, "mode": "project"}


@router.post("/runs/{run_id}/tool-calls", response_model=ToolCallResponse)
async def invoke_tool_call(run_id: str, payload: ToolCallRequest, request: Request):
    await require_run_access(request, run_id)
    return await ToolGateway(get_run_store()).invoke(run_id, payload)


@router.get("/runs/{run_id}/approvals")
async def get_approvals(run_id: str, request: Request, status: str | None = None):
    await require_run_access(request, run_id)
    store = get_run_store()
    return {"approvals": [ToolGateway._approval_model(item).model_dump() for item in await store.list_approvals(run_id, status)]}


@router.post("/runs/{run_id}/approvals/{approval_id}/decision", response_model=ToolCallResponse)
async def resolve_approval(run_id: str, approval_id: str, payload: ApprovalDecisionRequest, request: Request):
    await require_run_access(request, run_id)
    store = get_run_store()
    approval = await store.get_approval(approval_id)
    if approval is None or approval.run_id != run_id:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="Approval has already been resolved")
    response = await ToolGateway(store).resolve(approval_id, payload.approved, payload.grant_scope)
    if response is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return response


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str, request: Request):
    await require_run_access(request, run_id)
    record = await get_run_store().get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunDetailResponse(
        run_id=record.id,
        status=record.status,
        answer=record.answer,
        plan=public_plan(record.plan, record.task),
        events=await get_run_store().get_events(run_id),
        task=record.task,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/runs/{run_id}/events")
async def get_run_events(run_id: str, request: Request, after_sequence: int = 0):
    await require_run_access(request, run_id)
    return {"events": await get_run_store().get_events(run_id, after_sequence)}


@router.get("/runs/{run_id}/stream")
async def stream_run_events(
    request: Request,
    run_id: str,
    after_sequence: int = 0,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    await require_run_access(request, run_id)
    store = get_run_store()

    try:
        cursor = max(after_sequence, int(last_event_id or "0"))
    except ValueError:
        cursor = after_sequence

    async def event_stream() -> AsyncIterator[str]:
        nonlocal cursor
        broker = get_event_broker()
        subscription = broker.subscribe(run_id)
        try:
            while not await request.is_disconnected():
                events = await store.get_events(run_id, cursor)
                for event in events:
                    cursor = int(event["sequence"])
                    yield f"id: {cursor}\\nevent: timeline\\ndata: {json.dumps(event, ensure_ascii=False)}\\n\\n"

                current = await store.get_run(run_id)
                if current is not None and current.status in {"completed", "failed", "needs_revision", "cancelled"}:
                    return

                try:
                    await asyncio.wait_for(subscription.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\\n\\n"
        finally:
            broker.unsubscribe(run_id, subscription)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
