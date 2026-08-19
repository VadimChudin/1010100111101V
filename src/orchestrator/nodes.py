from __future__ import annotations
import json
from src.omniroute.router import OmniRoute, ChatRequest
from src.tools.shell import execute_shell

async def planner_node(state: dict) -> dict:
    router = OmniRoute()
    try:
        prompt = "Составь краткий JSON-план задачи. Верни объект с полями goal, steps (массив объектов id,title,command,depends_on), acceptance_criteria. Не выполняй команды.\nЗадача: " + state["task"]
        result = await router.chat(ChatRequest(messages=[{"role": "system", "content": "Ты planner безопасного AI-агента."}, {"role": "user", "content": prompt}], complexity="medium", request_id=state["run_id"]))
        try:
            plan = json.loads(result.content)
        except json.JSONDecodeError:
            plan = {"goal": state["task"], "steps": [{"id": "respond", "title": result.content, "command": None, "depends_on": []}], "acceptance_criteria": ["Дать ответ пользователю"]}
        return {"plan": plan, "status": "planned", "events": state.get("events", []) + [{"type": "plan.created", "model": result.model, "payload": plan}]}
    finally:
        await router.close()

async def executor_node(state: dict) -> dict:
    plan = state.get("plan") or {}
    results = list(state.get("tool_results", []))
    for step in plan.get("steps", []):
        command = step.get("command")
        if command:
            results.append({"step_id": step.get("id"), "result": await execute_shell(command)})
    return {"tool_results": results, "status": "executed", "events": state.get("events", []) + [{"type": "tool.result", "payload": results}]}

async def reviewer_node(state: dict) -> dict:
    router = OmniRoute()
    try:
        result = await router.chat(ChatRequest(messages=[{"role": "system", "content": "Ты reviewer. Верни JSON {approved:boolean, comment:string}."}, {"role": "user", "content": json.dumps({"task": state["task"], "plan": state.get("plan"), "results": state.get("tool_results", [])}, ensure_ascii=False)}], complexity="low", request_id=state["run_id"]))
        try: review = json.loads(result.content)
        except json.JSONDecodeError: review = {"approved": True, "comment": result.content}
        return {"review": review, "status": "completed" if review.get("approved", False) else "needs_revision", "events": state.get("events", []) + [{"type": "review.updated", "payload": review}]}
    finally:
        await router.close()
