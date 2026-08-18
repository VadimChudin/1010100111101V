"""LangGraph node implementations."""
from typing import Any
from src.orchestrator.state import AgentState
from src.omniroute.router import OmniRouter

async def planner(state: AgentState, router: OmniRouter | None = None) -> AgentState:
    router = router or OmniRouter()
    message = state.get("user_message", "")
    prompt = f"Create a concise numbered execution plan for this task. Task: {message}"
    response = await router.complete([{"role": "system", "content": "You are a careful planner."}, {"role": "user", "content": prompt}], task=message)
    plan = [line.strip(" -•\t") for line in response.splitlines() if line.strip()] or [f"Analyze: {message}", "Prepare a useful response", "Review the response"]
    return {**state, "plan": plan, "status": "planned", "iteration": state.get("iteration", 0) + 1, "events": state.get("events", []) + [{"node": "planner", "status": "completed"}]}

async def executor(state: AgentState, router: OmniRouter | None = None) -> AgentState:
    router = router or OmniRouter()
    message = state.get("user_message", "")
    plan = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(state.get("plan", [])))
    prompt = f"Execute the plan and produce the best answer.\nTask: {message}\nPlan:\n{plan}"
    response = await router.complete([{"role": "system", "content": "You are an expert executor."}, {"role": "user", "content": prompt}], task=message)
    return {**state, "execution_result": response, "status": "executed", "events": state.get("events", []) + [{"node": "executor", "status": "completed"}]}

async def reviewer(state: AgentState, router: OmniRouter | None = None) -> AgentState:
    router = router or OmniRouter()
    result = state.get("execution_result", "")
    prompt = f"Review this answer for correctness, completeness and safety. Return APPROVED if acceptable; otherwise give concise fixes.\nAnswer:\n{result}"
    review = await router.complete([{"role": "system", "content": "You are a rigorous reviewer."}, {"role": "user", "content": prompt}], task=prompt)
    return {**state, "review": review, "status": "reviewed", "events": state.get("events", []) + [{"node": "reviewer", "status": "completed"}]}


def should_revise(state: AgentState) -> str:
    review = state.get("review", "").lower()
    if ("not approved" in review or "fix" in review or "incorrect" in review) and state.get("iteration", 0) < 2:
        return "executor"
    return "end"
