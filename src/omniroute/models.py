from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    name: str
    strengths: tuple[str, ...]
    max_tokens: int = 4096
    context_length: int = 128000


# Current free models on OpenRouter (August 2026)
FREE_MODELS = (
    ModelSpec("nvidia/nemotron-3-ultra-550b-a55b:free", ("general", "reasoning", "complex"), context_length=1000000),
    ModelSpec("nvidia/nemotron-3-super-120b-a12b:free", ("general", "coding", "reasoning"), context_length=262144),
    ModelSpec("google/gemma-4-26b-a4b-it:free", ("general", "structured", "fast"), context_length=262144),
    ModelSpec("google/gemma-4-31b-it:free", ("general", "structured"), context_length=262144),
    ModelSpec("nvidia/nemotron-3-nano-30b-a3b:free", ("general", "fast", "simple"), context_length=256000),
    ModelSpec("cohere/north-mini-code:free", ("coding", "fast"), context_length=256000),
    ModelSpec("z-ai/glm-5.2:free", ("general", "reasoning"), context_length=256000),
    ModelSpec("nvidia/nemotron-3.5-lightning:free", ("general", "fast"), context_length=1000000),
    ModelSpec("openai/gpt-oss-20b:free", ("general", "coding"), context_length=131072),
    ModelSpec("nvidia/nemotron-nano-9b-v2:free", ("general", "fast", "simple"), context_length=128000),
)

MODEL_BY_COMPLEXITY = {
    "low": FREE_MODELS[4],       # nemotron-nano-30b - fast, simple tasks
    "medium": FREE_MODELS[2],    # gemma-4-26b - balanced
    "high": FREE_MODELS[1],      # nemotron-super-120b - complex tasks
    "critical": FREE_MODELS[0],  # nemotron-ultra-550b - most complex
    "coding": FREE_MODELS[5],    # north-mini-code - coding tasks
}


def get_model_for_complexity(complexity: str) -> ModelSpec:
    return MODEL_BY_COMPLEXITY.get(complexity, MODEL_BY_COMPLEXITY["medium"])


def get_model_for_task(task_type: str, complexity: str) -> ModelSpec:
    if task_type == "coding":
        return MODEL_BY_COMPLEXITY["coding"]
    return get_model_for_complexity(complexity)
