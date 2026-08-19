from __future__ import annotations
from uuid import uuid4
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.orchestrator.graph import run_agent

router = APIRouter()

@router.websocket("/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        payload = await websocket.receive_json()
        message = str(payload.get("message", "")).strip()
        if not message:
            await websocket.send_json({"type": "run.failed", "error": "message is required"})
            return
        run_id = str(uuid4())
        await websocket.send_json({"type": "run.started", "run_id": run_id})
        state = await run_agent(message, run_id, str(payload.get("user_id", "anonymous")))
        for event in state.get("events", []):
            await websocket.send_json({"run_id": run_id, **event})
        await websocket.send_json({"type": "run.completed", "run_id": run_id, "status": state.get("status"), "review": state.get("review")})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "run.failed", "error": str(exc)})
    finally:
        await websocket.close()
