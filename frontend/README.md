# Agent Room

**Agent Room** — тёмная real-time консоль для наблюдения за AI-агентом. В левой панели оператор отправляет задачу, читает ответ и видит ленту событий. В правой панели план агента отображается как интерактивный граф React Flow: узлы появляются из ответа API и подсвечиваются по мере выполнения.

## Стек

| Слой | Технология |
| --- | --- |
| UI | React 18/19, TypeScript, Vite |
| Стили | Tailwind CSS, CSS design tokens |
| Граф | `@xyflow/react` |
| Реалтайм | Native WebSocket API |
| API | Railway REST + WebSocket |

## Запуск локально

```bash
pnpm install
pnpm dev
```

Порт по умолчанию — `3000`. Перед запуском скопируйте `.env.example` в `.env.local` и при необходимости измените адрес API:

```bash
VITE_API_URL=https://app-production-cc16.up.railway.app
```

Если переменная не задана, приложение использует этот Railway URL как fallback.

## API-контракт

Приложение вызывает `GET /v1/healthz` для ручной проверки доступности, `POST /v1/chat` с телом `{ "message": "text" }` для запуска задачи и подключается к `WS /v1/ws` для получения событий выполнения. Ответ `/v1/chat` поддерживает `run_id`, `status`, `answer`, `plan` и `events`; план допускает как массив строк, так и массив объектов с `id`, `title`, `description`, `status` и `tool`.

## Проверки

```bash
pnpm check
pnpm build
```

## Деплой на Vercel

Проект содержит `vercel.json` с командой сборки `pnpm build`, директорией `dist/public` и rewrite для SPA. В настройках Vercel добавьте переменную `VITE_API_URL`, если backend отличается от значения по умолчанию. WebSocket должен быть доступен по `wss://` через тот же домен backend; приложение автоматически преобразует `https://` в `wss://`.

## Структура

```text
client/src/
  components/Chat.tsx
  components/MessageBubble.tsx
  components/TaskGraph.tsx
  hooks/useChat.ts
  hooks/useWebSocket.ts
  types.ts
  App.tsx
  main.tsx
  index.css
```

## Дизайн-система

Визуальное направление — **Dark Mission Control**: графитовый фон, Signal Ice `#9DE8FF` для активного интеллекта, amber для процесса, mint для подтверждённого завершения, Space Grotesk для интерфейса и IBM Plex Mono для телеметрии. Анимации ограничены короткими переходами и отключаются при `prefers-reduced-motion`.
