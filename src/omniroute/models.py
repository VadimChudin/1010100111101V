"""Model registry used by OmniRoute.

IDs are OpenRouter-compatible defaults and can be overridden through code when
providers change their catalog.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    tier: str
    description: str
    input_price: float
    output_price: float
    capabilities: frozenset[str]

MODEL_REGISTRY: dict[str, ModelSpec] = {
    "simple": ModelSpec("openai/gpt-4o-mini", "simple", "Fast and economical", 0.15, 0.60, frozenset({"chat", "json"})),
    "standard": ModelSpec("anthropic/claude-3.5-sonnet", "standard", "Balanced reasoning and coding", 3.0, 15.0, frozenset({"chat", "code", "json"})),
    "complex": ModelSpec("anthropic/claude-3.7-sonnet", "complex", "Advanced multi-step reasoning", 3.0, 15.0, frozenset({"chat", "code", "reasoning", "json"})),
}

def get_model(tier: str) -> ModelSpec:
    return MODEL_REGISTRY.get(tier, MODEL_REGISTRY["standard"])
