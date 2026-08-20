import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as api_router
from src.auth import get_auth_store
from src.config import get_settings
from src.api.websocket import router as ws_router
from src.observability import configure_observability, metrics
from src.queueing import RunWorker, cancel_task, get_run_queue
from src.storage import get_run_store
from src.workspace import get_workspace_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    store = get_run_store()
    queue = get_run_queue()
    await store.initialize()
    await get_workspace_store(store).initialize()
    await get_auth_store(store).initialize()
    await queue.initialize()
    worker_task = asyncio.create_task(RunWorker(queue, store).serve(), name="agent-run-worker")
    try:
        yield
    finally:
        await cancel_task(worker_task)
        await queue.close()


app = FastAPI(title="AI Agent Platform", version="0.2.0", lifespan=lifespan)
configure_observability(app)

cors_origins = [origin.strip() for origin in get_settings().frontend_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Last-Event-ID", "X-Request-ID"],
)

app.include_router(api_router)
app.include_router(ws_router)

@app.get("/v1/metrics")
async def get_metrics():
    return metrics.snapshot()


@app.get("/")
async def root():
    return {"name": "AI Agent Platform", "version": "0.2.0", "docs": "/docs", "health": "/v1/healthz"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)
