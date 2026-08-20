import pytest

from src.orchestrator.conversation import requires_project_work


@pytest.mark.parametrize(
    "message",
    [
        "привет",
        "как дела?",
        "объясни, что такое dependency injection",
        "thanks, that is helpful",
    ],
)
def test_simple_conversation_does_not_start_project_work(message: str):
    assert requires_project_work(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "проанализируй проект и расскажи, что нужно изменить",
        "исправь ошибку в этом модуле",
        "create a new project with a React frontend",
        "проверь тесты и подготовь commit",
    ],
)
def test_explicit_project_work_routes_to_planning_path(message: str):
    assert requires_project_work(message) is True
