from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """A validated internal planning step.

    `command` is retained only for the executor's policy decision. It is never
    returned in the public chat API response.
    """

    id: str
    title: str
    description: str | None = None
    command: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class AgentPlan(BaseModel):
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)

    @classmethod
    def fallback(cls, task: str, response_text: str) -> "AgentPlan":
        return cls(
            goal=task,
            steps=[PlanStep(id="respond", title=response_text or "Provide a response")],
            acceptance_criteria=["Provide a response to the user"],
        )

    @classmethod
    def from_payload(cls, payload: Any, task: str) -> "AgentPlan":
        if not isinstance(payload, dict):
            raise ValueError("Plan payload must be a JSON object")

        raw_steps = payload.get("steps", [])
        if not isinstance(raw_steps, list):
            raise ValueError("Plan steps must be an array")

        normalized_steps: list[PlanStep] = []
        for index, raw_step in enumerate(raw_steps, start=1):
            if isinstance(raw_step, str):
                normalized_steps.append(PlanStep(id=f"step-{index}", title=raw_step))
                continue
            if not isinstance(raw_step, dict):
                raise ValueError("Each plan step must be an object or string")

            title = raw_step.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("Each plan step requires a title")

            raw_dependencies = raw_step.get("depends_on", [])
            if not isinstance(raw_dependencies, list):
                raise ValueError("Plan step dependencies must be an array")

            description = raw_step.get("description")
            command = raw_step.get("command")
            normalized_steps.append(
                PlanStep(
                    id=str(raw_step.get("id") or f"step-{index}"),
                    title=title.strip(),
                    description=description if isinstance(description, str) else None,
                    command=command if isinstance(command, str) and command.strip() else None,
                    depends_on=[str(item) for item in raw_dependencies],
                )
            )

        raw_criteria = payload.get("acceptance_criteria", [])
        if not isinstance(raw_criteria, list):
            raise ValueError("Acceptance criteria must be an array")

        goal = payload.get("goal")
        return cls(
            goal=goal.strip() if isinstance(goal, str) and goal.strip() else task,
            steps=normalized_steps,
            acceptance_criteria=[str(item) for item in raw_criteria],
        )
