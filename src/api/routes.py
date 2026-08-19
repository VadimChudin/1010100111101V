from __future__ import annotations
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.orchestrator.graph import run_agent
from src.orchestrator.schemas import AgentPlan
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
    await get_run_store().create_run(run_id, request.user_id, request.message)
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
