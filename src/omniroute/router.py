"""Task-aware routing through the OpenRouter-compatible API."""
from typing import Any
import httpx
from src.config import Settings, get_settings
from src.omniroute.models import ModelSpec, get_model

class OmniRouter:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client

    def classify_complexity(self, task: str) -> str:
        text = task.lower()
        complex_markers = ("архитект", "исследован", "многошаг", "сложн", "debug", "реализуй", "код", "analyze", "architecture")
        simple_markers = ("привет", "переведи", "кратко", "суммируй", "hello", "translate", "simple")
        if any(marker in text for marker in complex_markers) or len(task) > 1200:
            return "complex"
        if any(marker in text for marker in simple_markers) or len(task) < 180:
            return "simple"
        return "standard"

    def select_model(self, task: str) -> ModelSpec:
        return get_model(self.classify_complexity(task))

    async def complete(self, messages: list[dict[str, str]], task: str | None = None, model: str | None = None) -> str:
        selected = model or self.select_model(task or messages[-1].get("content", "")).model_id
        if not self.settings.openrouter_api_key:
            return "OpenRouter API key is not configured; deterministic fallback response."
        headers = {"Authorization": f"Bearer {self.settings.openrouter_api_key}", "Content-Type": "application/json", "HTTP-Referer": self.settings.openrouter_http_referer, "X-Title": self.settings.openrouter_app_title}
        payload: dict[str, Any] = {"model": selected, "messages": messages, "temperature": 0.2}
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=60.0)
        try:
            response = await client.post(f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"].get("content") or "")
        finally:
            if owns_client:
                await client.aclose()

    async def classify_and_complete(self, prompt: str) -> tuple[ModelSpec, str]:
        spec = self.select_model(prompt)
        result = await self.complete([{"role": "user", "content": prompt}], task=prompt, model=spec.model_id)
        return spec, result
