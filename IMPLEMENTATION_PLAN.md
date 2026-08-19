# План реализации AI-agent платформы уровня Devin/Manus

**Версия:** 1.0  
**Язык:** русский  
**Автор:** Manus AI  
**Целевой результат:** управляемая платформа автономных AI-агентов, которая принимает задачи через REST/WebSocket и голос, строит план, выполняет действия в изолированном окружении, использует долговременную временную память и предоставляет пользователю поток событий, статусов и визуализацию графа зависимостей.

> **Ключевое решение.** Система строится как событийная платформа вокруг LangGraph: граф управляет состоянием и переходами агента, OmniRoute скрывает детали LLM-провайдера, Graphiti + Neo4j хранят временной контекст и происхождение фактов, Serena предоставляет семантическую навигацию по коду, а FastAPI/WebSocket и React обеспечивают интерактивный интерфейс. Для первого релиза используются бесплатные модели OpenRouter, но все контракты допускают замену моделей без изменений в оркестраторе.

## 1. Цели, границы и критерии готовности

В первой версии агент должен уметь принять текстовую задачу, классифицировать её сложность, составить структурированный план, запросить контекст из памяти, выполнить безопасные операции с файлами и shell, провести проверку результата, вернуть поток промежуточных событий и сохранить значимые факты. Агент не должен по умолчанию выполнять разрушительные команды, публиковать изменения, читать секреты или обращаться к внешним системам без явного разрешения пользователя.

LangGraph подходит для такой роли, поскольку предоставляет низкоуровневые примитивы для управляемых одноагентных, многоагентных и иерархических workflow, поддержку human-in-the-loop, памяти и потоковой выдачи событий [1]. Graphiti предназначен для временных context-графов, где сохраняются сущности, факты, эпизоды и их происхождение, а поиск сочетает семантический, ключевой и графовый контекст [2]. Serena следует использовать как MCP/LSP-слой семантического поиска, рефакторинга и навигации на уровне символов [3].

Критерии готовности MVP:

| Область | Критерий приемки |
|---|---|
| Оркестрация | Граф выполняет цикл `intake → plan → execute → review → finalize` и умеет повторить исполнение после замечаний reviewer. |
| LLM | OmniRoute выбирает одну из бесплатных моделей по сложности задачи, обрабатывает timeout, rate limit и fallback. |
| API | REST принимает задачу, WebSocket отдаёт события `run.started`, `plan.created`, `tool.called`, `run.completed` и `run.failed`. |
| Память | Краткосрочная история доступна через Redis, долговременные факты и эпизоды — через Graphiti/Neo4j; отключение одной подсистемы не ломает базовый чат. |
| Инструменты | Shell и файловые операции ограничены workspace, имеют allowlist, timeout, размер вывода и аудит. |
| Интерфейс | React dashboard показывает активный run, ленту событий, шаги плана и граф зависимостей через React Flow. |
| Эксплуатация | Docker-образ собирается воспроизводимо, health/readiness endpoints работают, Railway может запускать сервис из Dockerfile [4]. |
| Безопасность | Секреты только через environment variables/secret manager; API key из входных требований не зашивается в Git и подлежит ротации. |

## 2. Архитектура системы

### 2.1. Логическая схема

```text
                              ┌──────────────────────────┐
                              │       Пользователь       │
                              │ Web / voice / API client │
                              └─────────────┬────────────┘
                                            │ HTTPS + WSS
                         ┌──────────────────▼──────────────────┐
                         │ React Dashboard                     │
                         │ chat, run status, React Flow graph  │
                         │ LiveKit/TEN voice client            │
                         └──────────────────┬──────────────────┘
                                            │ REST / WebSocket
                         ┌──────────────────▼──────────────────┐
                         │ FastAPI API                         │
                         │ auth, validation, sessions, events  │
                         └──────────┬───────────┬───────────────┘
                                    │           │
                         ┌──────────▼───┐   ┌───▼──────────────┐
                         │ Run service  │   │ Voice gateway     │
                         │ queue/stream │   │ LiveKit/TEN       │
                         └──────┬───────┘   └────────┬─────────┘
                                │                    │ audio/events
                 ┌──────────────▼────────────────────▼─────────────┐
                 │ LangGraph Orchestrator                           │
                 │ intake → planner → context → executor → review  │
                 │ checkpointing, retry, HITL, cancellation          │
                 └───────┬──────────────┬──────────────┬─────────────┘
                         │              │              │
              ┌──────────▼──────┐ ┌─────▼────────┐ ┌──▼─────────────┐
              │ OmniRoute       │ │ Memory       │ │ Tool gateway    │
              │ policy + router │ │ assembler    │ │ policy + audit  │
              └──────────┬──────┘ └──┬───────────┘ └──┬─────────────┘
                         │           │               │
              ┌──────────▼──────┐ ┌──▼───────────┐ ┌─▼───────────────┐
              │ OpenRouter API  │ │ Graphiti     │ │ Serena MCP/LSP   │
              │ free models     │ │ Neo4j        │ │ shell/files      │
              └─────────────────┘ └──────────────┘ └─────────────────┘
                                    │
                         ┌──────────▼───────────┐
                         │ PostgreSQL + Redis   │
                         │ runs, users, audit,  │
                         │ queue, short memory  │
                         └──────────────────────┘
```

### 2.2. Поток выполнения задачи

1. Клиент отправляет `POST /v1/runs` или сообщение через WebSocket. FastAPI валидирует payload, создаёт `run_id`, проверяет права и публикует событие.
2. LangGraph формирует типизированное состояние `AgentState`, фиксирует checkpoint и вызывает intake-классификатор. Если задача требует опасного действия, граф переходит в interrupt/HITL.
3. Planner через OmniRoute строит JSON-план: цель, шаги, зависимости, ожидаемые артефакты, риски и критерии проверки. Headroom до вызова модели уменьшает историю и сохраняет приоритетные фрагменты.
4. Context node запрашивает Redis для текущего диалога и Graphiti для релевантных фактов, ограничений и предыдущих решений.
5. Executor выбирает только разрешённые tools. Для программного кода он сначала вызывает Serena для символов/ссылок, затем использует безопасные операции файлов и shell. Каждый вызов публикуется в event stream и журнал аудита.
6. Reviewer сравнивает результат с acceptance criteria, запускает проверки и возвращает `approved`, `needs_revision` или `blocked`. При `needs_revision` граф возвращается к planner/executor с лимитом итераций.
7. Finalizer формирует ответ, сохраняет эпизод и важные факты в Graphiti, обновляет PostgreSQL status и завершает stream.

## 3. Компоненты и технологический стек

| Компонент | Назначение | Рекомендуемый стек MVP | Производственный вариант |
|---|---|---|---|
| LangGraph orchestrator | Stateful workflow, retries, checkpoints, HITL | Python 3.11, LangGraph, Pydantic | Отдельные worker-процессы, durable checkpointer, LangSmith/OpenTelemetry |
| OmniRoute | Единая маршрутизация к LLM | `httpx`, OpenRouter Chat Completions, registry free models | Policy engine с бюджетом, latency/cost metrics, circuit breaker, model health |
| Graphiti | Эпизодическая и временная память | `graphiti-core`, Neo4j driver, Pydantic schemas | Отдельный memory service, индексы, retention и tenant isolation |
| Neo4j | Знания, связи, временные факты | Neo4j 5.x, Bolt/neo4j URI | Managed Neo4j, read replicas/cluster при подтверждённой нагрузке |
| Serena | Semantic code navigation через MCP/LSP | Serena server в tool container | Изолированный per-workspace MCP process, language servers, quotas |
| Headroom | Сжатие контекста и токенов | Headroom middleware/адаптер перед каждым LLM call | Policy по важности, token telemetry, offline quality benchmarks |
| FastAPI backend | REST, WebSocket, auth, lifecycle | FastAPI, Uvicorn, WebSocket, SQLAlchemy/asyncpg | Несколько API pods, Redis pub/sub, queue workers, rate limits |
| PostgreSQL | Users, runs, plans, events metadata, audit | PostgreSQL 16, SQLAlchemy, Alembic | Managed PostgreSQL, PITR, read replicas, partitioned event tables |
| Redis | Short-term memory, locks, stream/pubsub, rate limiting | Redis 7, `redis.asyncio` | Managed Redis, Sentinel/cluster, eviction policy and persistence |
| React dashboard | Chat, run control, live event stream | React + TypeScript + Vite, React Flow, Zustand/Query | CDN, code splitting, Sentry, feature flags |
| Voice | Real-time audio and transcripts | LiveKit client/server or TEN Framework adapter | Dedicated voice worker, TURN, VAD, TTS/STT provider abstraction |
| Deployment | Reproducible service packaging | Docker, docker-compose, Railway TOML | Separate services: API, worker, voice, Postgres, Redis, Neo4j |

Free OpenRouter models should be treated as an experimental pool: availability, latency, context window and rate limits can change. The registry must therefore be configuration-driven and the planner must degrade gracefully to a deterministic clarification response when no model is available.

## 4. Внутренние контракты компонентов

### 4.1. Canonical run object

```json
{
  "run_id": "uuid",
  "user_id": "uuid",
  "session_id": "uuid",
  "task": "string",
  "status": "queued|running|waiting_human|completed|failed|cancelled",
  "workspace_id": "string",
  "max_iterations": 3,
  "created_at": "RFC3339",
  "metadata": {"client": "web", "locale": "ru-RU"}
}
```

### 4.2. LangGraph state

```python
class AgentState(TypedDict):
    run_id: str
    user_id: str
    task: str
    messages: list[dict]
    plan: dict | None
    current_step: int
    context: list[dict]
    tool_results: list[dict]
    review: dict | None
    events: list[dict]
    status: str
    iteration: int
    error: str | None
```

State updates must be append-safe for events and replace-safe for canonical fields. PII and credentials are not allowed in persisted state; redact before checkpointing.

### 4.3. REST API

| Method | Endpoint | Request | Response |
|---|---|---|---|
| `GET` | `/healthz` | none | `{"status":"ok"}` |
| `GET` | `/readyz` | none | dependency status; HTTP 503 if critical dependency unavailable |
| `POST` | `/v1/runs` | `CreateRunRequest` | `202 Accepted`, `RunResponse` |
| `GET` | `/v1/runs/{run_id}` | path + auth | current run, plan, review and timestamps |
| `POST` | `/v1/runs/{run_id}/cancel` | none | cancellation acknowledgement |
| `POST` | `/v1/runs/{run_id}/approve` | `{decision, comment}` | HITL decision acknowledgement |
| `GET` | `/v1/runs/{run_id}/events` | `after_seq` optional | paginated event list |
| `WS` | `/v1/ws/runs/{run_id}` | auth handshake | bidirectional event stream and control messages |

Error format:

```json
{
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "Run does not exist",
    "request_id": "uuid",
    "retryable": false
  }
}
```

### 4.4. WebSocket protocol

Server events use `{type, run_id, seq, timestamp, payload}`. Required event types are `run.started`, `plan.created`, `memory.retrieved`, `tool.called`, `tool.result`, `review.updated`, `human.required`, `run.completed`, `run.failed` and `run.cancelled`. Client commands are `subscribe`, `cancel`, `approve`, `pause` and `resume`. The server sends a heartbeat every 20–30 seconds and closes idle or unauthenticated connections with a documented code.

### 4.5. OmniRoute contract

```python
class ChatRequest(BaseModel):
    messages: list[dict]
    complexity: Literal["low", "medium", "high"]
    structured_schema: dict | None = None
    max_tokens: int = 1024
    temperature: float = 0.2
    request_id: str

class ChatResponse(BaseModel):
    model: str
    content: str
    usage: dict
    latency_ms: int
    fallback_used: bool
```

The router assigns low complexity to the cheapest/fastest free model, medium complexity to the strongest available free model, and high complexity to a sequential strategy: attempt the strongest model, then fallback to another model with a reduced context. Every request has timeout, retry budget, idempotency key and response validation. The API key is read only from `OPENROUTER_API_KEY`; the exposed key in the supplied requirements must be revoked and replaced before any deployment.

### 4.6. Tool contract

```json
{
  "tool": "shell.exec",
  "input": {"command": "pytest -q", "cwd": "/workspace/repo", "timeout_s": 30},
  "policy": {"approval_required": false, "network": false},
  "result": {"exit_code": 0, "stdout": "...", "stderr": "...", "truncated": false},
  "audit_id": "uuid"
}
```

Tool execution is never allowed to receive raw model-generated paths without normalization and policy checks. Tools return bounded output and machine-readable errors.

## 5. Схемы данных

### 5.1. PostgreSQL

PostgreSQL хранит транзакционные данные и не заменяет Graphiti. Suggested tables:

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE runs (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
  task TEXT NOT NULL,
  status TEXT NOT NULL,
  workspace_id TEXT,
  graph_state JSONB,
  iteration INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_code TEXT
);

CREATE TABLE run_events (
  id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, seq)
);

CREATE TABLE tool_audit (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES runs(id),
  user_id UUID NOT NULL REFERENCES users(id),
  tool_name TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  approval_state TEXT NOT NULL,
  exit_status TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Индексы: `runs(user_id, created_at DESC)`, `runs(status)`, `run_events(run_id, seq)`, `tool_audit(user_id, created_at DESC)`. При большом объёме `run_events` партиционировать по месяцу или по hash `run_id`.

### 5.2. Neo4j/Graphiti

Graphiti-specific implementation should follow the installed library version; the conceptual model is:

```text
(:User {id, tenant_id})
(:Session {id, user_id})
(:Episode {id, session_id, content, source, occurred_at, ingested_at})
(:Entity {id, tenant_id, type, name, summary})
(:Fact {id, predicate, valid_at, invalid_at, confidence, source_episode_id})
(:ToolObservation {id, tool, result_hash, created_at})

(User)-[:OWNS]->(Session)
(Session)-[:HAS_EPISODE]->(Episode)
(Episode)-[:MENTIONS]->(Entity)
(Entity)-[:HAS_FACT]->(Fact)
(Fact)-[:ABOUT]->(Entity)
(Episode)-[:PRODUCED]->(Fact)
(Session)-[:OBSERVED]->(ToolObservation)
```

Обязательные свойства — `tenant_id`, `source_episode_id`, `valid_at`, `invalid_at`, `confidence`, `created_at`. Устаревший факт не удаляется: его validity window закрывается, чтобы сохранялась история. Уникальные constraints следует создать для `User.id`, `Session.id`, `Episode.id` и `Entity(tenant_id, id)`. Все запросы должны фильтровать tenant/user scope.

### 5.3. Redis

| Key pattern | Значение | TTL/политика |
|---|---|---|
| `session:{id}:messages` | List/JSON последних сообщений | 24–72 часа; длинная история архивируется |
| `run:{id}:events` | Redis Stream или pub/sub channel | До завершения + retention 24 часа |
| `run:{id}:lock` | Distributed lock token | 30–60 секунд с heartbeat |
| `ratelimit:{user}:{window}` | Счётчик запросов | окно 1 минута |
| `approval:{run_id}` | HITL decision | До завершения run |
| `cache:model:{model}:{hash}` | Короткоживущий кэш безопасных ответов | Только для idempotent запросов |

Redis не является источником истины для финального статуса: события и итог run должны быть записаны в PostgreSQL.

## 6. Headroom и контекстная политика

Перед каждым LLM-вызовом Context Builder объединяет задачу, текущий шаг, релевантные Graphiti facts, последние сообщения и результаты инструментов. Headroom получает лимит токенов модели и выполняет сжатие по приоритетам: системные ограничения и acceptance criteria сохраняются полностью, затем текущий план, ошибки/результаты последнего шага, релевантные факты и только после этого старые сообщения. Сжатие должно быть детерминируемо логируемым: хранить `tokens_before`, `tokens_after`, `dropped_sections` и `compression_ratio`.

Для снижения риска потери смысла нужны golden-тесты: задача и ожидаемый набор фактов проходят через compression pipeline, после чего evaluator проверяет сохранение ограничений, имён файлов, чисел и критериев. При структурированном JSON нельзя сжимать имена полей и значения, влияющие на безопасность.

## 7. Голосовой интерфейс

На клиенте LiveKit WebRTC должен отвечать за низкую задержку аудио, комнаты и reconnect; TEN Framework можно использовать как агентный runtime/адаптер для VAD, STT, LLM и TTS. Сервер не должен передавать аудио через обычный REST. Голосовой канал публикует события `voice.transcript.partial`, `voice.transcript.final`, `voice.agent.started`, `voice.agent.audio` и `voice.agent.finished`, а текстовый task stream остаётся тем же источником истины для dashboard.

Голосовой worker получает короткоживущий room token, не получает долгоживущие секреты браузеру, применяет VAD и interruption/barge-in. Для каждого tenant устанавливаются лимиты длительности комнаты, размера аудио и числа concurrent sessions. При недоступности voice provider пользователь должен автоматически получить text fallback.

## 8. React dashboard и визуализация

Frontend состоит из четырёх зон: чат и голосовой control bar; timeline событий; plan/step panel; React Flow canvas. Узлы графа соответствуют шагам плана, tool calls, артефактам и зависимостям. Цвет узла отражает `queued/running/blocked/completed/failed`, а edge хранит `depends_on` и `produced_by`. React Flow обновляется по WebSocket-событиям, но при reconnect восстанавливается через `GET /v1/runs/{id}/events?after_seq=N`.

Состояние UI разделяется на server state (runs/events, React Query) и ephemeral state (selected node, zoom, draft message, Zustand). Никаких LLM secrets в bundle. Ошибки, reconnect и backpressure должны быть видимыми, но не раскрывать внутренние prompt или токены.

## 9. План реализации и сроки

Оценка рассчитана на одного опытного full-stack/AI инженера при работе 35–40 часов в неделю. Для команды из 2–3 человек календарное время может быть сокращено, но интеграционные зависимости останутся.

| Фаза | Срок | Результат |
|---|---:|---|
| 0. ADR и bootstrap | 2–3 дня | Репозиторий, Python/Node toolchain, Docker Compose, `.env.example`, ADR по tenant model и tool policy. |
| 1. OmniRoute и базовый FastAPI | 4–5 дней | Registry free models, routing/fallback, health, REST chat, structured logging. |
| 2. LangGraph core | 5–7 дней | Typed state, planner/executor/reviewer, retries, cancellation, checkpoints, event sink. |
| 3. PostgreSQL/Redis | 3–4 дня | Alembic schema, run/event persistence, locks, pub/sub/streams, rate limit. |
| 4. Tools и Serena adapter | 5–7 дней | Workspace sandbox, shell/files, MCP process lifecycle, LSP smoke tests, audit. |
| 5. Graphiti/Neo4j memory | 4–6 дней | Episode ingestion, temporal facts, hybrid retrieval, privacy/retention jobs. |
| 6. Headroom/context quality | 3–5 дней | Compression pipeline, token telemetry, golden fixtures, fallback when context is too large. |
| 7. React dashboard | 6–8 дней | Auth shell, chat, live stream, plan timeline, React Flow dependency graph. |
| 8. Voice | 5–8 дней | LiveKit/TEN proof of concept, transcript/audio events, interruption, text fallback. |
| 9. Production hardening | 5–7 дней | Observability, security tests, load tests, migrations, backups, CI/CD, Railway staging. |
| 10. Pilot | 1–2 недели | 5–10 real workflows, acceptance review, model policy tuning, runbook and rollback. |

Итого для MVP: примерно **8–10 календарных недель** одному инженеру или **4–6 недель** небольшой команде при наличии готовых credentials и workspace policy.

## 10. Deployment strategy на Railway

Для MVP используется один Docker service с FastAPI и worker mode, но в конфигурации следует сохранить возможность разделить процессы. Railway поддерживает deployment FastAPI из GitHub, CLI, шаблона или Dockerfile, а `railway.toml`/`railway.json` позволяет хранить deployment configuration as code [4].

```text
Railway project
├── api service       : FastAPI/Uvicorn, REST + WebSocket
├── worker service    : LangGraph runs, tool execution, memory jobs
├── postgres service  : transactional data
├── redis service     : stream, locks, rate limits
├── neo4j external   : managed Neo4j/secured private endpoint
├── voice service     : LiveKit/TEN worker when enabled
└── frontend service  : static React build or CDN
```

На staging допустим docker-compose с локальными PostgreSQL, Redis и Neo4j. На production базы должны быть managed или иметь регулярные backup snapshots; Neo4j connection string и credentials задаются через Railway variables. Docker image запускается non-root пользователем, имеет multi-stage build, минимальный runtime, `HEALTHCHECK` и команду с `$PORT`. Для WebSocket нужно проверить keepalive, graceful shutdown и публичный Railway domain. Autoscaling API и отдельное масштабирование worker безопаснее, чем масштабирование процесса с in-memory state.

CI/CD должен выполнять lint, type check, unit/integration/e2e tests, build и vulnerability scan; deploy в staging запускается автоматически после merge, production — после ручного approval. Rollback — на предыдущий image digest; database migrations — backward-compatible, с отдельным migration job.

## 11. Тестирование

| Уровень | Что проверяется | Инструменты/метрики |
|---|---|---|
| Unit | Router policy, schema validation, redaction, path policy, graph transitions | pytest, pytest-asyncio, Hypothesis |
| Contract | REST/WS event envelopes, idempotency, error codes | OpenAPI snapshots, JSON Schema, websocket client tests |
| Integration | OpenRouter mock, Redis, PostgreSQL, Neo4j/Graphiti, Serena stub | Testcontainers или docker-compose CI |
| Workflow | Planner→executor→reviewer, retry, HITL, cancellation | deterministic fake LLM, LangGraph state assertions |
| Security | traversal, command injection, secret leakage, authz, tenant isolation | Semgrep, Bandit, dependency scan, OWASP cases |
| Load | concurrent runs, WS fanout, queue latency, memory growth | Locust/k6; p95 latency and saturation thresholds |
| Quality/evals | plan correctness, tool selection, memory precision, compression recall | curated task set, rubric evaluator, regression gates |
| E2E | Browser chat, live events, graph updates, reconnect, voice fallback | Playwright, mocked LiveKit/TTS/STT |

Минимальные release gates: 80% line coverage для критического backend-кода, 100% покрытие policy/security functions, отсутствие P0/P1 уязвимостей, успешный smoke run в staging и p95 для обычного text request в пределах согласованного SLO. Реальный LLM не должен использоваться в unit tests: применяются fixtures и deterministic fake responses.

## 12. Безопасность и управление рисками

**Секреты.** Ключ OpenRouter, Neo4j, Redis, PostgreSQL и LiveKit никогда не помещаются в исходники, README, frontend или Docker image. Используются Railway Variables/secret storage и локальный `.env`, исключённый из Git. Ключ из предоставленного задания уже считается скомпрометированным: его следует немедленно отозвать в OpenRouter и выпустить новый с минимальными правами.

**Изоляция выполнения.** Shell запускается в отдельном контейнере/worker с non-root UID, read-only base image, workspace volume, CPU/memory/PID limits, timeout, seccomp/AppArmor по возможностям платформы, отключённой сетью по умолчанию и allowlist команд. Для production не следует выполнять model-generated shell на том же хосте, где находятся credentials или база.

**Авторизация и multi-tenancy.** Каждый запрос несёт user/tenant claims; все `run_id`, Graphiti query, SQL query, WebSocket subscription и tool audit проходят ownership check. Администраторские операции выделяются отдельными scopes. Ввод валидируется Pydantic, output экранируется, CORS ограничен известными origins, cookies имеют `HttpOnly`, `Secure`, `SameSite`.

**Prompt injection и data exfiltration.** Внешние документы и код считаются недоверенными данными, а не инструкциями. System policy отделяется от retrieved context. Агент не может сам расширить tool permissions; опасные действия требуют HITL. В журнале хранятся хэши и метаданные, а не секреты и полные чувствительные prompts. PII имеет retention policy и процедуру удаления.

**Доступность и злоупотребления.** Rate limits на user/tenant/IP, максимальный размер задачи/файла/вывода, лимиты concurrency и budget per run защищают бесплатные модели от исчерпания квот. Circuit breaker прекращает запросы к деградировавшему provider. WebSocket использует heartbeat, reconnect и backpressure.

## 13. Наблюдаемость и SLO

Каждый run и tool call получает correlation ID. OpenTelemetry traces связывают HTTP request, LangGraph node, LLM call, database query и tool execution. Metrics: `run_duration_seconds`, `llm_latency_ms`, `llm_errors_total`, `fallback_total`, `tokens_in/out`, `compression_ratio`, `tool_failures_total`, `ws_connections`, `queue_depth`, `memory_retrieval_latency_ms`. Logs структурированы JSON и редактируются перед отправкой.

Предварительные SLO после стабилизации: API availability 99.5%, WebSocket reconnect без потери событий при повторной загрузке по sequence number, p95 `POST /runs` ACK < 500 ms, p95 event delivery < 1 s при нормальной нагрузке, успешное восстановление run после worker restart > 99%. Для LLM latency нужно отдельно публиковать provider-dependent target, поскольку бесплатные модели имеют непредсказуемые очереди.

## 14. Масштабирование

На первом уровне масштабируется API горизонтально, потому что состояние run хранится в PostgreSQL/Redis, а WebSocket subscriptions используют Redis pub/sub. Worker масштабируется по длине очереди и ограничивается semaphore по provider/model. Voice workers масштабируются по комнатам и CPU, а Serena — по workspace с quotas.

На втором уровне вводятся отдельные сервисы: `orchestrator`, `tool-executor`, `memory-writer`, `memory-retriever`, `voice-gateway`. Длинные tasks переводятся в durable queue; retries делаются с exponential backoff и dead-letter queue. PostgreSQL partitioning и retention уменьшают размер event log, Redis Cluster обслуживает streams, Neo4j получает индексы и read replicas только после измерения.

На третьем уровне добавляются model health scoring, per-tenant budgets, priority queues, caching только для детерминированных запросов, batch ingestion memory и workspace snapshots. Не следует преждевременно делать multi-agent swarm: сначала измерить качество единого graph и failure modes.

| Риск | Вероятность | Влияние | Митигирование |
|---|---:|---:|---|
| Бесплатная модель недоступна | Высокая | Высокое | Router fallback, health checks, понятный degraded mode, возможность платного provider позже. |
| LLM создаёт неверный план | Средняя | Высокое | Structured output, reviewer, max iterations, HITL для риска. |
| Утечка через shell/tool | Средняя | Критическое | Изолированный runner, deny-by-default, audit, network off. |
| Потеря WebSocket события | Средняя | Среднее | Sequence IDs, Redis stream, PostgreSQL replay endpoint. |
| Graphiti/Neo4j latency | Средняя | Среднее | Async ingestion, cached context, circuit breaker, graceful memory degradation. |
| Token compression удаляет ограничение | Средняя | Высокое | Priority policy, golden tests, no-compress safety fields. |
| Railway resource saturation | Средняя | Высокое | Separate workers, quotas, metrics, external managed databases. |
| Prompt injection из репозитория | Средняя | Высокое | Treat repository as untrusted data; tool policy outside model context. |

## 15. Порядок запуска и операционный runbook

Локально запускать нужно в следующем порядке: скопировать `.env.example` в `.env`, заполнить только локальные credentials, поднять PostgreSQL/Redis/Neo4j через compose, применить migrations, запустить API и выполнить health smoke test. Затем отправить тестовую задачу с fake или реальным OpenRouter key, проверить события и закрыть run.

В production сначала создать managed data services и секреты, затем выполнить миграции, задеплоить worker, затем API, после чего подключить frontend и voice. Перед rollout проверить `readyz`, queue consumption, WebSocket reconnect, audit records и rollback. При деградации OpenRouter отключить high-complexity jobs, оставить low-risk text mode и сообщить пользователю, что task находится в degraded state. При подозрении на утечку ключа немедленно revoke/rotate, invalidate sessions, inspect audit trail и redeploy image.

## 16. Источники

[1]: https://www.langchain.com/langgraph "LangGraph — официальный обзор и возможности"

[2]: https://github.com/getzep/graphiti "Graphiti — open-source temporal context graphs for AI agents"

[3]: https://oraios.github.io/serena/01-about/000_intro.html "Serena — официальное описание semantic code tools и MCP"

[4]: https://docs.railway.com/guides/fastapi "Railway — Deploy a FastAPI App"

[5]: https://fastapi.tiangolo.com/advanced/websockets/ "FastAPI — официальная документация WebSockets"

[6]: https://reactflow.dev/ "React Flow — официальная документация"

[7]: https://docs.livekit.io/ "LiveKit — официальная документация"

[8]: https://openrouter.ai/docs "OpenRouter — официальная документация API"

---

**Примечание по реализации:** план сознательно разделяет MVP и production hardening. В рабочем прототипе допустимы stubs для Graphiti и Serena, но границы интерфейсов должны совпадать с описанными контрактами, чтобы заменить stub реальным сервисом без переделки LangGraph и FastAPI.
