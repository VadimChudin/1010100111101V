from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.events import get_event_broker
from src.orchestrator.graph import run_agent
from src.orchestrator.schemas import AgentPlan
from src.queueing import RunJob, RunWorker, get_run_queue
from src.storage import get_run_store

router = APIRouter(prefix="/v1")

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    user_id: str = "anonymous"


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

@router.post("/chat", response_model=ChatRunResponse)
async def chat(request: ChatRequest):
    run_id = str(uuid4())
    store = get_run_store()
    await store.create_run(run_id, request.user_id, request.message)
    try:
        state = await run_agent(request.message, run_id, request.user_id)
        status = str(state.get("status") or "failed")
        answer = str(state.get("review", {}).get("comment", ""))
        plan = public_plan(state.get("plan"), request.message)
        response_events = list(state.get("events", []))
        await store.append_events(run_id, response_events)
        await store.complete_run(run_id, status, answer, plan.model_dump())
        return ChatRunResponse(run_id=run_id, status=status, answer=answer, plan=plan, events=response_events)
    except Exception as exc:
        failure_event = {"type": "run.failed", "payload": {"message": "The agent run could not be completed."}}
        await store.append_events(run_id, [failure_event])
        await store.complete_run(run_id, "failed", "", None)
        raise HTTPException(status_code=502, detail="The agent run could not be completed.") from exc


@router.post("/runs")
async def create_run(request: ChatRequest):
    run_id = str(uuid4())
    store = get_run_store()
    await store.create_run(run_id, request.user_id, request.message)
    job = RunJob(run_id=run_id, user_id=request.user_id, task=request.message)
    queue = get_run_queue()
    try:
        await queue.enqueue(job)
    except Exception as exc:
        await store.complete_run(run_id, "failed", "", None)
        await store.append_events(run_id, [{"type": "run.failed", "payload": {"message": "The run could not be queued."}}])
        raise HTTPException(status_code=503, detail="The run queue is unavailable.") from exc
    asyncio.create_task(RunWorker(queue, store).execute(job), name=f"agent-run-{run_id}")
    return {"run_id": run_id, "status": "queued", "task": request.message}


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str):
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
async def get_run_events(run_id: str, after_sequence: int = 0):
    if await get_run_store().get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"events": await get_run_store().get_events(run_id, after_sequence)}


@router.get("/runs/{run_id}/stream")
async def stream_run_events(
    request: Request,
    run_id: str,
    after_sequence: int = 0,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    store = get_run_store()
    if await store.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

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
