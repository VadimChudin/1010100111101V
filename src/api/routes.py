from __future__ import annotations
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.orchestrator.graph import run_agent
from src.orchestrator.schemas import AgentPlan

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
    try:
        state = await run_agent(request.message, run_id, request.user_id)
        return ChatRunResponse(
            run_id=run_id,
            status=str(state.get("status") or "failed"),
            answer=str(state.get("review", {}).get("comment", "")),
            plan=public_plan(state.get("plan"), request.message),
            events=list(state.get("events", [])),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The agent run could not be completed.") from exc

@router.post("/runs")
async def create_run(request: ChatRequest):
    run_id = str(uuid4())
    return {"run_id": run_id, "status": "queued", "task": request.message}
