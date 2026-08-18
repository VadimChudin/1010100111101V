"""REST API routes."""
from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from src.orchestrator.graph import agent_graph

router = APIRouter(prefix="/api/v1")

class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    thread_id: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)

@router.post("/agent/run")
async def run_agent(request: AgentRequest) -> dict[str, Any]:
    state = {"thread_id": request.thread_id, "user_message": request.message, "metadata": request.metadata, "events": [], "iteration": 0}
    result = await agent_graph.ainvoke(state, config={"configurable": {"thread_id": request.thread_id}})
    return {"thread_id": request.thread_id, "status": result.get("status"), "plan": result.get("plan", []), "result": result.get("execution_result", ""), "review": result.get("review", ""), "events": result.get("events", [])}
