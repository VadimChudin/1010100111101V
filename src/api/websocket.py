from __future__ import annotations
from uuid import uuid4
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.orchestrator.graph import run_agent
from src.storage import get_run_store

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
        store = get_run_store()
        await store.create_run(run_id, str(payload.get("user_id", "anonymous")), message, status="running")
        started = (await store.append_events(run_id, [{"type": "run.started", "payload": {"run_id": run_id}}]))[0]
        await websocket.send_json({"run_id": run_id, **started})

        state = await run_agent(message, run_id, str(payload.get("user_id", "anonymous")))
        persisted_events = await store.append_events(run_id, list(state.get("events", [])))
        for event in persisted_events:
            await websocket.send_json({"run_id": run_id, **event})

        status = str(state.get("status") or "failed")
        answer = str(state.get("review", {}).get("comment", ""))
        completion = {"type": "run.completed", "payload": {"status": status, "review": state.get("review", {})}}
        completed = (await store.append_events(run_id, [completion]))[0]
        await store.complete_run(run_id, status, answer, state.get("plan"))
        await websocket.send_json({"run_id": run_id, **completed})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        if "run_id" in locals():
            store = get_run_store()
            failed = (await store.append_events(run_id, [{"type": "run.failed", "payload": {"message": "The agent run could not be completed."}}]))[0]
            await store.complete_run(run_id, "failed", "", None)
            await websocket.send_json({"run_id": run_id, **failed})
        else:
            await websocket.send_json({"type": "run.failed", "error": "The agent run could not be completed."})
    finally:
        await websocket.close()
