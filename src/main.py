from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as api_router
from src.api.websocket import router as ws_router
from src.storage import get_run_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    await get_run_store().initialize()
    yield


app = FastAPI(title="AI Agent Platform", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)

@app.get("/")
async def root():
    return {"name": "AI Agent Platform", "version": "0.2.0", "docs": "/docs", "health": "/v1/healthz"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)
