# Chat-first Project Canvas Sprint

**Status:** Approved product brief and implementation backlog  
**Owner:** Manus AI  
**Scope:** Agent Room web control surface and paired desktop experience  
**Deferred:** Voice / OpenAI Realtime / LiveKit, Git branch UI, and `entire.io` integration.

## 1. Product decision

Agent Room is becoming a **chat-first environment for autonomous work on a software project**. The ordinary experience must feel as simple as a thoughtful chat application: the user writes a thought, receives a direct response, and does not need to manage models, planners, tool calls, terminals, Serena, Graphiti, Docker, or background processes.

The project dashboard is a second deliberate surface, entered through the **Project** item in the left navigation. It is not a bot-status page. It is a living visual representation of the selected local or GitHub project: files, modules, dependencies, Git-derived metadata, code context, notes, tasks, and the relationship between them.

> **Design principle:** the user sees intent, progress, and outcome. The system keeps orchestration, model selection, tool invocation, indexing, and local services under the surface unless there is an actionable problem.

## 2. Agreed interaction model

| Area | Decision |
|---|---|
| Default launch | Open **Chat** for the already selected project. A first-run source chooser remains Local folder / GitHub repository only. |
| Primary navigation | A narrow left rail with exactly two primary destinations: **Chat** and **Project**. Settings is deliberately deferred to a secondary menu, not a third persistent workspace. |
| Header | Show the selected **project name**. Do not show a Git branch in this sprint. `entire.io` is explicitly deferred. |
| Chat | ChatGPT-like conversation, lower composer, streaming answer, Markdown, code blocks, copy action, and file attachments. Styling is product-specific rather than a clone. |
| Lightweight conversation | Greeting, clarification, explanation, and ordinary questions use the cheapest adequate route. They do not launch a project planner. |
| Project work | An explicit request to analyse, create, change, test, commit, or ship project work creates a task card and starts structured clarification. |
| Clarification-first execution | A project task gathers questions, answers, affected modules, acceptance criteria, and proposed scope inside its card. Implementation begins only after the picture is sufficiently complete or the user explicitly allows the agent to proceed. |
| Approval modes | **Green light** allows the agreed execution scope. **Ask before changes** pauses before creating or modifying files. Read-only inspection remains silent in both modes. |
| Visible agent activity | Show a compact live execution line beneath the relevant assistant message, e.g. `Mapping 14 files · Serena`, never a raw planner trace. |
| Dashboard default | Build and show the project as an atomic dependency map; selecting a node highlights its direct relationships to prevent visual noise. |
| Task placement | Active tasks form a right-hand, scrollable card lane. Tasks may also create compact sticky markers attached to the affected files or modules on the map. |
| Completed work | Completed task cards collapse into a **cold archive**. They do not clutter active work. |
| Local services | Runtime, Serena, Graphiti and Docker run quietly in the background. They must not open terminal or console windows. |
| Service fault | A non-blocking red status dot appears in the app chrome. Hovering it opens a compact slide-out diagnostic message; full logs remain only in Settings / Diagnostics. |

## 3. Visual direction: **Obsidian Paper**

The visual language combines the composure and operational clarity of Devin with the high-contrast editorial confidence associated with Anthropic. It is neither a neon developer dashboard nor a generic ChatGPT clone.

The default theme is dark and intentionally sparse: a near-black graphite canvas, high-contrast warm-white reading surfaces, restrained cool-cyan interaction accents, and a small semantic color system. Cyan marks selectable/navigation affordances; green marks healthy completed states; amber marks a user decision required; red is reserved solely for an actionable failure. Color is never used to decorate a dense graph.

Typography uses **Inter** for product UI and prose, paired with **JetBrains Mono** for file paths, language labels, identifiers, short operational lines, and compact status. The scale should prefer large calm whitespace in Chat and crisp, compact information density in Project. Rounded corners are soft but not playful; shadows are shallow; motion is limited to purposeful transition, streaming, node-focus, and live-activity feedback.

| Token family | Initial direction | Usage |
|---|---|---|
| Canvas | `#0B0D10` graphite | App background and map field |
| Surface | `#13161B` / `#191D23` | Composer, cards, inspectors |
| Primary text | Warm `#F5F1E8` | Long-form reading and hierarchy |
| Muted text | Neutral grey-blue | Metadata, paths, timestamps |
| Action accent | Ice cyan | Selected navigation, active node, primary action |
| Healthy | Controlled green | Connected, complete, working safely |
| Requires attention | Warm amber | Approval needed, missing information |
| Failure | Restrained red | Actionable fault only |

## 4. Chat workspace specification

### 4.1 Structure

Chat is the initial and dominant workspace. Its reading column stays focused and does not share the screen with the dependency map. The left rail remains available but unobtrusive. The top bar contains the project name and a small system-presence indicator; it does not expose raw runtime controls.

The composer is anchored at the bottom, supports Markdown-friendly multiline text, attachments, and a single clear send control. Assistant messages support Markdown, code blocks, copy, and citations to project files where relevant. The interaction status is one short line immediately under the message currently being generated or executed.

### 4.2 Routing and planner policy

A low-cost router classifies each message before allocating a model or tools. Simple chat routes to the lowest-cost suitable model with no planning ceremony. A project request creates a task in **Clarifying** state and asks only the questions necessary to close material gaps. The task card is the durable record of decisions, constraints, answers, acceptance criteria, and later the execution log.

The router must escalate to a stronger model only where complexity, ambiguity, repository scope, risk, or a user-requested high-quality result requires it. The model name, token budget, internal planner trace, and raw tool payload remain hidden. The user sees the meaningful summary: `Understanding task`, `Reading workspace`, `Preparing change`, `Waiting for approval`, `Reviewing result`, or `Done`.

### 4.3 Task lifecycle

| User-facing state | Meaning | Card behavior |
|---|---|---|
| **Clarifying** | The request needs context or decisions | Shows focused questions and captured answers |
| **Ready** | Scope and acceptance criteria are adequate | Shows concise implementation plan and affected areas |
| **Working** | Agent is executing agreed work | Shows live readable milestones, not raw logs |
| **Needs you** | Approval or a missing decision is required | Emphasized single choice or compact approval control |
| **Review** | Result is ready to inspect | Shows summary, files affected, diff/test links where applicable |
| **Done** | Task completed or accepted | Collapses to the cold archive |

## 5. Project workspace specification

### 5.1 Map and focus behavior

The Project canvas is the default project dashboard. It begins with an atomic graph of files, modules, and dependency edges derived from the selected workspace. The first view applies sensible grouping and progressive disclosure rather than showing every edge at full opacity. Selecting a node reveals its immediate inbound and outbound links while all other graph content recedes.

A node always exposes file name, language, and size/line count. Hovering a node opens a small summary card with purpose, top-level exports or symbols, recent change signal, and attached task count. Clicking opens a right inspector, not a separate OS window. The inspector contains code preview, dependency links, Git-derived metadata, linked notes, error markers when available, and task markers. Opening a full file editor is deferred; the first sprint uses a readable code preview and precise file navigation.

### 5.2 Filters and semantic groups

The map provides calm, color-coded filters for **Files**, **Modules**, **Dependencies**, **Git changes**, and **Tasks**. They are filters and lenses, not separate dashboards. The graph retains the same spatial context as a user moves between them.

### 5.3 Task lane and sticky markers

The right-side task lane is the canonical active-work stack. It supports a vertical scroll and collapses completed work to the cold archive. Each task may be attached to zero or more map nodes. Attachments render as minimal sticky markers near the relevant file/module node; they never obscure node labels or dependency paths.

Hovering a marker previews the task title, current state, intent, and latest activity. Clicking it opens the same task drawer with clarification answers, scope, approvals, milestones, logs, diff/test summary, and related files.

## 6. Silent local runtime specification

Runtime, Serena, Graphiti and Docker are part of the implementation, not the daily interface. The desktop client starts them with no terminal/PowerShell windows and maintains one compact background supervisor status.

The visible health model is intentionally small:

| Indicator | Normal state | Failure state |
|---|---|---|
| Cloud | Green dot, no extra text | Red dot opens a short network/session explanation |
| Runtime | Green dot, local service active | Red dot identifies pairing/sync problem |
| Serena | Green dot after semantic service is ready | Amber/red only when project navigation is degraded |
| Graphiti | Green when Docker-backed profile is available | Neutral/amber if deferred because Docker is unavailable; never blocks Chat or Project |

The user’s reference to a “key” is implemented as this **single system-presence indicator**, not as a literal key icon. Its first job is to communicate healthy / attention needed / offline without expanding the interface. Hover or click reveals the compact diagnostic sheet; Settings retains the deeper technical view.

## 7. Implementation sprint backlog

### Sprint 1 — Product shell and visual system

| ID | Deliverable | Acceptance criteria |
|---|---|---|
| S1.1 | UX specification and design tokens | This document is translated into shared Tailwind tokens, typography, spacing, semantic status colors, and component states. |
| S1.2 | Chat-first app shell | App opens to Chat; rail has only Chat and Project; header shows project name; no branch UI. |
| S1.3 | Product-specific Chat UI | Composer, streaming messages, Markdown, code blocks, copy, attachments, and compact activity line meet the specification. |
| S1.4 | Planner suppression | Greeting / simple chat has no planner UI; explicit project work enters task clarification. |
| S1.5 | Two-mode approval control | Green-light and ask-before-changes modes are translated to current policy engine behavior without broadening tool permissions. |

### Sprint 2 — Project canvas and durable task work

| ID | Deliverable | Acceptance criteria |
|---|---|---|
| S2.1 | Graph reading model | Workspace index supplies node metadata, dependency edges, and stable module/file identifiers. |
| S2.2 | Focused Project map | Selected node emphasizes direct edges; filters and grouping prevent a dense unreadable mesh. |
| S2.3 | Node hover and inspector | Hover summary and click inspector work without leaving the dashboard or opening a new window. |
| S2.4 | Task card lane | Clarifying → Ready → Working → Needs you → Review → Done is durable, visible, and archives completed work. |
| S2.5 | Map markers | Tasks can be attached to files/modules as non-obstructive sticky markers with previews and drawer navigation. |

### Sprint 3 — Quiet desktop reliability and model routing

| ID | Deliverable | Acceptance criteria |
|---|---|---|
| S3.1 | Silent background service supervisor | Desktop never displays PowerShell/terminal windows for runtime, Serena, Graphiti, Git, or Docker setup. |
| S3.2 | Compact health indicator | Normal state is quiet; error indicator opens an actionable compact diagnostic sheet; detailed logs reside in Settings. |
| S3.3 | Serena / Graphiti lifecycle clarity | Service health reports are accurate; unavailable Graphiti does not block Project or Chat. |
| S3.4 | Cost-aware router | Low-cost path handles ordinary chat; explicit rules escalate model/tool use for project tasks; all choices remain auditable server-side. |
| S3.5 | Durable task context | Clarifications, decisions, relevant map nodes, approved scope, and outcomes persist as project context. |

### Sprint 4 — Quality gate and release

| ID | Deliverable | Acceptance criteria |
|---|---|---|
| S4.1 | Test coverage | Chat routing, task state transitions, graph focus logic, service indicators, approval modes, and desktop no-console startup have automated coverage. |
| S4.2 | Visual verification | Desktop and web views are checked at common laptop and wide-screen sizes; graph remains legible. |
| S4.3 | Documentation | ADRs cover chat planner suppression, task lifecycle, local service visibility, and eventual `entire.io` boundary. |
| S4.4 | Verified release | Backend, Vercel frontend, runtime release, and desktop installer pass CI, deploy from `main`, and receive smoke verification. |

## 8. Explicit exclusions from this sprint

Voice, realtime interruption, speech-to-text, text-to-speech, LiveKit, and OpenAI Realtime are not included. Git branch selection and the `entire.io` integration remain intentionally deferred. A full code editor, terminal emulator, generic shell, multi-workspace concurrent profiles, and an always-visible diagnostics console are also outside this sprint.

## 9. Success criteria

The sprint is successful when a new user can choose a local or GitHub project, open Agent Room directly to an elegant Chat screen, casually converse without planner friction, give a real project task that becomes a well-scoped clarifying task card, switch to Project to see a calm and navigable dependency map with linked work, and never see a terminal window unless they deliberately enter Diagnostics.

The system must feel alive through compact execution feedback, yet quiet because all orchestration is encapsulated. The dashboard must make the project more understandable than a file tree, not more complex than one.
