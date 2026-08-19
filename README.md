# AI Agent Platform

Минимальный рабочий backend AI-агента на Python с LangGraph, OmniRoute/OpenRouter, FastAPI REST/WebSocket и адаптерами памяти и инструментов.

## Безопасность ключа

Не вставляйте OpenRouter key в исходники. Установите его через `.env` или secret variables Railway. Ключ, который был передан в исходном задании, следует считать раскрытым и отозвать/заменить перед использованием.

## Локальный запуск

```bash
cp .env.example .env
# отредактируйте .env и задайте OPENROUTER_API_KEY
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m src.main
```

Проверка:

```bash
curl http://localhost:8000/v1/healthz
curl -X POST http://localhost:8000/v1/runs \
  -H 'content-type: application/json' \
  -d '{"message":"Составь короткий план проверки проекта","approval_mode":"confirm_each"}'
# затем откройте GET /v1/runs/{run_id}/stream для SSE timeline
curl http://localhost:8000/v1/projects
curl http://localhost:8000/v1/metrics
```

Для локальных баз:

```bash
docker compose up --build
```

WebSocket endpoint: `ws://localhost:8000/v1/ws`. После подключения отправьте JSON `{"message":"Привет"}`.

## Архитектура

LangGraph управляет planner/executor/reviewer. SQLite WAL является durable source of truth для runs, events, approvals и project workspace; Redis используется для очереди и delivery wake-up. `POST /v1/runs` создаёт queued run, а `GET /v1/runs/{run_id}/stream` выдаёт возобновляемый SSE timeline по sequence cursor.

Tool Gateway принимает только типизированные операции. Policy engine применяет `deny → grant → mode default`, а `.env`, credentials, raw shell, deploy и privileged actions не могут быть обойдены режимом approvals. В P0 доступны read-only workspace tools и обратимые bounded edits через API approval card.

Project workspace хранит modules, notes, tasks и markers; React Flow canvas показывает их как устойчивую карту проекта. SerenaClient — read-only provider contract; реальный MCP transport включается только после отдельного подтверждённого подключения и isolated worker wiring. Подробности релиза: [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

## Railway

Проект собирается через `Dockerfile` и использует `railway.toml`. В Railway задайте `OPENROUTER_API_KEY`, `REDIS_URL`, `STATE_DATABASE_PATH` (по умолчанию `./data/agent-state.db`) и при необходимости `SENTRY_DSN` как secret variables. Для persistent SQLite WAL необходим mounted volume; без него данные сохраняются только до следующего redeploy. Публичный домен, SSE и WebSocket следует проверять в staging перед production.
# Deployed on Railway
