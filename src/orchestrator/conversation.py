from __future__ import annotations

from collections.abc import Awaitable, Callable

from src.omniroute.router import ChatRequest, OmniRoute


_SIMPLE_PROJECT_SIGNALS = (
    "проект",
    "репозитор",
    "код",
    "файл",
    "модул",
    "рефактор",
    "исправ",
    "добав",
    "создай",
    "сделай",
    "измени",
    "проверь",
    "протест",
    "тест",
    "коммит",
    "commit",
    "push",
    "git ",
    "repository",
    "code",
    "file",
    "module",
    "refactor",
    "implement",
    "build ",
    "create ",
    "change ",
    "fix ",
    "test ",
)


def requires_project_work(message: str) -> bool:
    """Fast deterministic router: simple conversation must not create agent plans."""
    normalized = f" {message.casefold().strip()} "
    return any(signal in normalized for signal in _SIMPLE_PROJECT_SIGNALS)


async def _ask_model(message: str, run_id: str, system_prompt: str, complexity: str) -> tuple[str, str]:
    router = OmniRoute()
    try:
        result = await router.chat(
            ChatRequest(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                complexity=complexity,
                request_id=run_id,
            )
        )
    finally:
        await router.close()
    return result.content, result.model


async def run_conversation(
    message: str,
    run_id: str,
    event_sink: Callable[[dict], Awaitable[None]] | None = None,
) -> tuple[str, str]:
    """Return a direct low-cost answer without planner, tools, or reviewer nodes."""
    if event_sink is not None:
        await event_sink({"type": "conversation.started", "payload": {"mode": "chat"}})

    answer, model = await _ask_model(
        message,
        run_id,
        (
            "Ты Agent Room — спокойный ассистент для разработчика. "
            "Отвечай прямо, кратко и естественно. Не показывай внутренний planner, "
            "модели, инструменты, токены или технический trace. "
            "Если пользователь пока просто общается, не предлагай план действий без запроса."
        ),
        "low",
    )
    if event_sink is not None:
        await event_sink({"type": "conversation.completed", "model": model, "payload": {"mode": "chat"}})
    return answer, model


async def run_project_clarification(
    message: str,
    run_id: str,
    event_sink: Callable[[dict], Awaitable[None]] | None = None,
) -> tuple[str, str]:
    """Create a concise shared understanding before a project task can execute."""
    if event_sink is not None:
        await event_sink({"type": "task.clarifying", "payload": {"mode": "clarification"}})
    answer, model = await _ask_model(
        message,
        run_id,
        (
            "Ты Agent Room. Пользователь описал работу над программным проектом. "
            "Не составляй внутренний planner, не запускай инструменты и не утверждай, что уже менял код. "
            "Сначала кратко сформулируй, как ты понял цель, затем задай только важные вопросы, "
            "без которых рискованно начинать. Если контекста уже достаточно, явно напиши: «Готово к работе» "
            "и перечисли границы и критерии результата. Ответ должен быть на языке пользователя."
        ),
        "medium",
    )
    if event_sink is not None:
        await event_sink({"type": "task.clarified", "model": model, "payload": {"mode": "clarification"}})
    return answer, model
