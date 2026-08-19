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
curl -X POST http://localhost:8000/v1/chat \
  -H 'content-type: application/json' \
  -d '{"message":"Составь короткий план проверки проекта"}'
```

Для локальных баз:

```bash
docker compose up --build
```

WebSocket endpoint: `ws://localhost:8000/v1/ws`. После подключения отправьте JSON `{"message":"Привет"}`.

## Архитектура

LangGraph управляет planner/executor/reviewer. OmniRoute выбирает бесплатные модели OpenRouter и выполняет fallback. GraphitiMemory и SerenaClient являются version-agnostic adapters: их можно подключить через реальные клиенты без изменения API оркестратора. Shell tool в этом прототипе предназначен только для доверенного локального workspace; production требует отдельного sandbox runner, deny-by-default policy и approval для опасных действий.

## Railway

Проект собирается через `Dockerfile` и использует `railway.toml`. В Railway задайте `OPENROUTER_API_KEY`, `REDIS_URL`, `DATABASE_URL`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` как secret variables. Публичный домен и WebSocket следует проверять в staging перед production.
