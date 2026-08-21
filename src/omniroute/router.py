from __future__ import annotations
import time
import httpx
from pydantic import BaseModel, Field
from .models import FREE_MODELS, get_model_for_complexity
from src.config import get_settings


class OpenRouterUnavailableError(RuntimeError):
    """A safe, user-actionable description of an LLM provider failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


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
            raise OpenRouterUnavailableError(
                "not_configured",
                "Agent Room is connected, but its OpenRouter key is not configured. Add the server-side OPENROUTER_API_KEY before sending Chat messages.",
            )
        preferred = get_model_for_complexity(request.complexity).name
        ordered = ([preferred] + [m.name for m in FREE_MODELS if m.name != preferred])[: self.settings.openrouter_max_fallback_models]
        last_error: Exception | None = None
        last_status_code: int | None = None
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
                    timeout=self.settings.openrouter_attempt_timeout_s,
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise ValueError("OpenRouter returned an empty response")
                return ChatResponse(model=model, content=content, usage=data.get("usage", {}),
                                    latency_ms=int((time.perf_counter() - started) * 1000),
                                    fallback_used=index > 0)
            except httpx.HTTPStatusError as exc:
                last_error = exc
                last_status_code = exc.response.status_code
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc

        if last_status_code in {401, 403}:
            raise OpenRouterUnavailableError(
                "authentication_failed",
                "OpenRouter rejected the configured key. Update the server-side OPENROUTER_API_KEY and retry.",
            ) from last_error
        if last_status_code == 429:
            raise OpenRouterUnavailableError(
                "capacity_limited",
                "All available free Chat models are temporarily busy or quota-limited. Retry in a moment.",
            ) from last_error
        raise OpenRouterUnavailableError(
            "unavailable",
            "Agent Room could not reach an available OpenRouter model. Retry in a moment or inspect the agent connection status.",
        ) from last_error
