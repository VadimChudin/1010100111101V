from __future__ import annotations
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from src.orchestrator.graph import run_agent

router = APIRouter(prefix="/v1")

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    user_id: str = "anonymous"

@router.get("/healthz")
async def healthz():
    return {"status": "ok"}

@router.post("/chat")
async def chat(request: ChatRequest):
    run_id = str(uuid4())
    try:
        state = await run_agent(request.message, run_id, request.user_id)
        return {"run_id": run_id, "status": state.get("status"), "answer": state.get("review", {}).get("comment", ""), "plan": state.get("plan"), "events": state.get("events", [])}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.post("/runs")
async def create_run(request: ChatRequest):
    run_id = str(uuid4())
    return {"run_id": run_id, "status": "queued", "task": request.message}
