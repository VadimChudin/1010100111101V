# 1010100111101V

**1010100111101V** — стартовая платформа AI-агента на Python для выполнения многошаговых задач. LangGraph отвечает за состояние и переходы графа, OmniRoute выбирает модель через OpenRouter, Graphiti хранит эпизодическую память в Neo4j, Redis используется для краткосрочного контекста, а FastAPI предоставляет REST и WebSocket API.

## Архитектура

| Компонент | Назначение |
|---|---|
| LangGraph | Граф `planner → executor → reviewer` с условным повтором и checkpointing |
| OmniRoute | Классификация сложности задачи и выбор модели OpenRouter |
| Graphiti / Neo4j | Долговременная эпизодическая память в виде графа знаний |
| Redis | Краткосрочная память с TTL |
| Serena | Адаптер для MCP/LSP-навигации по коду; endpoint задаётся переменной окружения |
| FastAPI | HTTP API, health-check и WebSocket для потокового диалога |
| Railway | Рекомендуемый production-хостинг с native service linking |

> Локальный `docker-compose.yml` предназначен для разработки. Railway обычно разворачивает каждый сервис как отдельный Service; PostgreSQL, Redis и Neo4j следует подключить как Railway Plugins или отдельные сервисы с переменными-ссылками.

## Быстрый запуск локально

1. Скопируйте `.env.example` в `.env` и задайте `OPENROUTER_API_KEY`.
2. Запустите `docker compose up --build`.
3. Откройте `http://localhost:8000/docs`.
4. Проверка состояния: `curl http://localhost:8000/health`.
5. Отправка задачи: `curl -X POST http://localhost:8000/api/v1/agent/run -H 'Content-Type: application/json' -d '{"message":"Составь краткий план релиза"}'`.

Для запуска без Docker:

```bash
bash scripts/setup.sh
source .venv/bin/activate
bash scripts/run_dev.sh
```

## Развёртывание в Railway

Создайте проект Railway и добавьте PostgreSQL и Redis через Plugins. Neo4j можно запустить отдельным сервисом из Docker image `neo4j:5.26-community` либо использовать внешний Neo4j Aura. Для приложения выберите репозиторий GitHub и оставьте Nixpacks или Dockerfile согласно конфигурации репозитория.

В сервисе приложения задайте переменные из `.env.example`. Railway автоматически предоставляет `PORT`; приложение слушает `0.0.0.0:${PORT}`. Для native linking используйте ссылки вида `${{Postgres.DATABASE_URL}}`, `${{Redis.REDIS_URL}}`, а для Neo4j — адрес и учётные данные сервиса Neo4j. `DATABASE_URL` PostgreSQL предусмотрен для будущих прикладных таблиц и health-интеграций; память Graphiti использует Neo4j.

Файлы `railway.toml`, `Procfile` и `nixpacks.toml` уже добавлены. `docker-compose.yml` не является способом оркестрации нескольких Railway-сервисов, поэтому в Railway рекомендуется native service linking, а Compose использовать локально.

## API

`GET /health` возвращает состояние приложения и внешних зависимостей. `POST /api/v1/agent/run` принимает JSON с полями `message`, `thread_id` и необязательным `metadata`. WebSocket `GET ws://localhost:8000/ws/chat/{thread_id}` принимает текстовые сообщения и возвращает JSON-события узлов графа.

## Переменные окружения

Полный список находится в `.env.example`. Минимально необходимы `OPENROUTER_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` и `REDIS_URL`. Секреты не должны попадать в Git.

## Тесты и качество

```bash
pytest -q
python -m compileall src
```

Тест оркестратора работает без внешних сервисов: он подменяет вызовы LLM детерминированным mock-клиентом.

## Лицензия

Шаблон предназначен для дальнейшей адаптации командой проекта. Перед production-развёртыванием добавьте аутентификацию, ограничения команд shell, аудит, rate limiting и политики хранения персональных данных.
