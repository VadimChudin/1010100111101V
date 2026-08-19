from dataclasses import dataclass

@dataclass(frozen=True)
class ModelSpec:
    name: str
    strengths: tuple[str, ...]
    max_tokens: int = 2048

FREE_MODELS = (
    ModelSpec("meta-llama/llama-3.1-8b-instruct:free", ("general", "fast")),
    ModelSpec("google/gemma-2-9b-it:free", ("general", "structured")),
    ModelSpec("qwen/qwen-2-7b-instruct:free", ("coding", "reasoning", "fast")),
)

MODEL_BY_COMPLEXITY = {
    "low": FREE_MODELS[2],
    "medium": FREE_MODELS[1],
    "high": FREE_MODELS[0],
}

def get_model_for_complexity(complexity: str) -> ModelSpec:
    return MODEL_BY_COMPLEXITY.get(complexity, MODEL_BY_COMPLEXITY["medium"])
