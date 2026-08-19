from __future__ import annotations

import json
import re

from src.config import get_settings
from src.omniroute.router import ChatRequest, OmniRoute
from src.orchestrator.schemas import AgentPlan
from src.tools.shell import execute_shell


_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def parse_agent_plan(content: str, task: str) -> AgentPlan:
    """Parse a model response into the agent's validated plan contract."""
    candidate = content.strip()
    fenced = _JSON_FENCE_RE.match(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        return AgentPlan.from_payload(json.loads(candidate), task)
    except (json.JSONDecodeError, ValueError, TypeError):
        return AgentPlan.fallback(task, content)


async def planner_node(state: dict) -> dict:
    router = OmniRoute()
    try:
        prompt = (
            "Составь краткий JSON-план задачи. Верни только JSON-объект с полями "
            "goal, steps (массив объектов id,title,description,depends_on), "
            "acceptance_criteria. Не предлагай shell-команды: инструменты будут добавлены через policy layer.\nЗадача: "
            + state["task"]
        )
        result = await router.chat(
            ChatRequest(
                messages=[
                    {"role": "system", "content": "Ты planner безопасного AI-агента."},
                    {"role": "user", "content": prompt},
                ],
                complexity="medium",
                request_id=state["run_id"],
            )
        )
        plan = parse_agent_plan(result.content, state["task"])
        return {
            "plan": plan.model_dump(),
            "status": "planned",
            "events": state.get("events", [])
            + [{"type": "plan.created", "model": result.model, "payload": plan.model_dump()}],
        }
    finally:
        await router.close()


async def executor_node(state: dict) -> dict:
    plan = AgentPlan.from_payload(state.get("plan") or {}, state["task"])
    results = list(state.get("tool_results", []))
    policy_events: list[dict] = []
    settings = get_settings()

    for step in plan.steps:
        if not step.command:
            continue
        if not settings.enable_unsafe_shell:
            policy_events.append(
                {
                    "type": "tool.blocked",
                    "payload": {
                        "step_id": step.id,
                        "reason": "Raw shell commands are disabled until the typed tool policy is implemented.",
                    },
                }
            )
            continue
        results.append({"step_id": step.id, "status": "completed", "result": await execute_shell(step.command)})

    return {
        "tool_results": results,
        "status": "executed",
        "events": state.get("events", []) + policy_events + [{"type": "tool.result", "payload": results}],
    }


async def reviewer_node(state: dict) -> dict:
    router = OmniRoute()
    try:
        result = await router.chat(
            ChatRequest(
                messages=[
                    {"role": "system", "content": "Ты reviewer. Верни JSON {approved:boolean, comment:string}."},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "task": state["task"],
                                "plan": state.get("plan"),
                                "results": state.get("tool_results", []),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                complexity="low",
                request_id=state["run_id"],
            )
        )
        try:
            review = json.loads(result.content)
        except json.JSONDecodeError:
            review = {"approved": False, "comment": result.content}
        return {
            "review": review,
            "status": "completed" if review.get("approved", False) else "needs_revision",
            "events": state.get("events", []) + [{"type": "review.updated", "payload": review}],
        }
    finally:
        await router.close()
