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


@pytest.mark.asyncio
async def test_direct_conversation_persists_a_terminal_answer(monkeypatch, tmp_path):
    from src.api import routes
    from src.storage.run_store import SQLiteRunStore

    store = SQLiteRunStore(str(tmp_path / "runs.db"))
    await store.create_run("run-1", "user-1", "hello")

    async def fake_conversation(message: str, run_id: str, event_sink):
        await event_sink({"type": "conversation.started", "payload": {"mode": "chat"}})
        return "Hello from the direct path.", "test/free-model"

    monkeypatch.setattr(routes, "get_run_store", lambda: store)
    monkeypatch.setattr(routes, "run_conversation", fake_conversation)

    status, answer = await routes.execute_conversation_run("run-1", "hello")

    persisted = await store.get_run("run-1")
    assert status == "completed"
    assert answer == "Hello from the direct path."
    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.answer == "Hello from the direct path."
    assert any(event["type"] == "run.completed" for event in await store.get_events("run-1"))
