"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from src.api.routes import router as api_router
from src.api.websocket import chat_websocket
from src.config import get_settings
from src.memory.graphiti_memory import GraphitiMemory
from src.memory.short_term import ShortTermMemory

settings = get_settings()
graphiti_memory = GraphitiMemory(settings)
short_term_memory = ShortTermMemory(settings)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await graphiti_memory.connect()
    yield
    await graphiti_memory.close()
    await short_term_memory.close()

app = FastAPI(title="1010100111101V", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)

@app.get("/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "service": "1010100111101V", "environment": settings.app_env, "graphiti_enabled": settings.graphiti_enabled}

@app.websocket("/ws/chat/{thread_id}")
async def websocket_chat(websocket: WebSocket, thread_id: str) -> None:
    await chat_websocket(websocket, thread_id)
