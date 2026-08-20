# ADR 011: Chat-first Project Canvas and Quiet Local Runtime

**Status:** Accepted

## Context

The previous Agent Room control surface exposed a mission-control layout: planner stages, event trace, runtime panel, graph, notes, tasks, and inspector were visible at the same time. This made normal conversation unnecessarily complex and exposed implementation details that do not help the user make a decision.

The product must instead open into an ordinary, high-quality conversation for a selected project. The dashboard remains essential, but it is a separate **Project** workspace where users understand their codebase, dependencies, Git-derived structure, and linked work. Local runtime, Serena, Graphiti, Docker, model selection, tool calls, and low-level logs are implementation details that should stay quiet unless the user needs to act.

## Decision

Agent Room uses one primary desktop scene with three coordinated regions: a persistent **Chat** panel on the left, a **Project canvas** on the right, and a vertical **task lane** at the canvas edge. The header shows the selected project name, while a compact health indicator summarizes Cloud, runtime, Serena, and Graphiti availability. Deep diagnostics stay outside the primary scene.

A deterministic low-cost classifier routes ordinary conversation to a direct `low` complexity OmniRoute model path. This path emits durable events and an answer, but does not create a planner, tool trace, review sequence, or project task. Explicit project-work signals route to a clarification-first path. It returns a shared understanding and only the important missing questions; it does not run tools or claim to modify code before scope is ready.

The Project canvas visualizes tracked project modules and, through a file lens, tracked files beside the ongoing conversation. Selecting a module highlights direct dependency edges and opens an in-canvas inspector. Project tasks form a right-side work lane within the same dashboard and attach to modules as durable markers. Completed work moves into a collapsed cold archive.

| Product surface | Visible to user | Hidden by default |
|---|---|---|
| Chat panel | Messages, code/Markdown output, compact activity line, compact `Ask` / `Auto` modes, approvals when needed | Model name, token budget, planner events, raw tool traces |
| Project canvas | Map lenses, dependency focus, file/module inspector, sticky markers and adjacent task lane | Runtime transport detail, raw index logs, device protocol payloads |
| Health indicator | Healthy / attention / offline state and concise actionable explanation | Full logs, Docker commands, terminal output |
| Desktop setup | Source chooser, setup progress, final ready state | Runtime installer console, Serena server process, Graphiti Docker process |

## Approval semantics

The primary Chat UI exposes only two user-facing policies.

| User wording | Existing policy engine mapping | Meaning |
|---|---|---|
| **Ask first** | `confirm_each` | Read-only inspection is automatic; local changes and external effects need explicit approval. |
| **Green light** | `allow_workspace_edits` | Reversible local edits may proceed inside the paired workspace. External/persistent operations, including push, remain governed by their higher risk class. |

A project can later offer a trusted push rule only after two explicit successful push approvals. This rule is intentionally not enabled by the initial Green light mode.

## Quiet runtime boundary

Electron executes installer commands with `windowsHide`, starts persistent runtime and Serena processes with hidden detached children and ignored stdio, and opens the project web surface in the existing main window rather than creating a second workspace window. Graphiti remains optional: Docker is never installed silently, and Graphiti unavailability must not block Chat or Project.

## Consequences

The primary experience becomes substantially calmer. The system preserves durable runs, workspace records, policy enforcement, Git-centric project data, and local-first source boundaries, but expresses them through user-meaningful state. The implementation keeps the existing typed policy and workspace APIs rather than granting the renderer new filesystem, shell, credential, or process permissions.

## Alternatives rejected

| Alternative | Reason rejected |
|---|---|
| Always display plan / tools / event trace | Makes greetings and normal discussion feel like an operations console. |
| Hide all activity | Removes useful evidence that the agent is making progress. |
| Use planner for every message | Increases cost and friction while providing no benefit for ordinary conversation. |
| Auto-execute immediately after a project request | Creates avoidable scope drift and makes approval less meaningful. |
| Keep a separate Electron workspace window | Produces an unnecessary multi-window desktop experience. |
| Auto-install Docker to enable Graphiti | Requires administrative and user-level system changes that must remain explicit. |
