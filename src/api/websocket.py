"""WebSocket chat handler."""
from fastapi import WebSocket, WebSocketDisconnect
from src.orchestrator.graph import agent_graph

async def chat_websocket(websocket: WebSocket, thread_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            state = {"thread_id": thread_id, "user_message": message, "events": [], "iteration": 0}
            await websocket.send_json({"type": "started", "thread_id": thread_id})
            result = await agent_graph.ainvoke(state, config={"configurable": {"thread_id": thread_id}})
            for event in result.get("events", []):
                await websocket.send_json({"type": "event", **event})
            await websocket.send_json({"type": "completed", "result": result.get("execution_result", ""), "review": result.get("review", "")})
    except WebSocketDisconnect:
        return
