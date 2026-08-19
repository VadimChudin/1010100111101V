from __future__ import annotations
import time
import httpx
from pydantic import BaseModel, Field
from .models import FREE_MODELS, get_model_for_complexity
from src.config import get_settings

class ChatRequest(BaseModel):
    messages: list[dict] = Field(min_length=1)
    complexity: str = "medium"
    max_tokens: int = 1024
    temperature: float = 0.2
    request_id: str = ""

class ChatResponse(BaseModel):
    model: str
    content: str
    usage: dict = Field(default_factory=dict)
    latency_ms: int
    fallback_used: bool = False

class OmniRoute:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.settings = get_settings()
        self.client = client or httpx.AsyncClient(timeout=self.settings.request_timeout_s)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if not self.settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        preferred = get_model_for_complexity(request.complexity).name
        ordered = [preferred] + [m.name for m in FREE_MODELS if m.name != preferred]
        last_error: Exception | None = None
        for index, model in enumerate(ordered):
            started = time.perf_counter()
            try:
                response = await self.client.post(
                    f"{self.settings.openrouter_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": self.settings.openrouter_http_referer,
                        "X-Title": self.settings.openrouter_app_name,
                    },
                    json={
                        "model": model,
                        "messages": request.messages,
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise ValueError("OpenRouter returned an empty response")
                return ChatResponse(model=model, content=content, usage=data.get("usage", {}),
                                    latency_ms=int((time.perf_counter() - started) * 1000),
                                    fallback_used=index > 0)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
        raise RuntimeError(f"All OpenRouter models failed: {last_error}")
