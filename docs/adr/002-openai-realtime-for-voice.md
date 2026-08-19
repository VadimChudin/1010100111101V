# ADR 002: OpenAI Realtime как основной голосовой provider

**Статус:** принято  
**Дата:** 20 августа 2026 г.

## Контекст

Платформа развивается в сторону voice-first interactive workspace. Пользователь должен вести естественный разговор об архитектуре проекта, прерывать агента, видеть partial transcript и быстро создавать привязанные к модулям notes/tasks. Голосовой слой не должен дублировать либо обходить общий run/event/approval contract.

## Решение

Для speech-to-speech взаимодействия выбираем **OpenAI Realtime API** как основной provider. Он будет подключаться через WebRTC и предоставлять голосовой диалог, VAD, audio/text streaming events и interruption handling. LiveKit остаётся рекомендуемым transport/room layer для web-клиента и отдельного voice worker: он обеспечивает управляемые комнаты, token-based access, transport abstractions и provider-agnostic path на будущее.

```text
React client microphone
  → LiveKit WebRTC room
  → Voice worker / adapter
  → OpenAI Realtime session
  → final transcript + typed intent
  → FastAPI domain API → PostgreSQL events, notes, tasks, approvals
```

## Последствия

Финальные transcript segments обязательно сохраняются в доменной модели независимо от voice provider. Это нужно для notes, tasks, module markers и audit history. OpenAI Realtime не получает прямого доступа к секретам, GitHub, Railway или tool execution; доступ к коду и внешним действиям остаётся за FastAPI/Tool Gateway и policy engine.

Первая голосовая версия будет push-to-talk. Затем добавляются VAD, естественное turn detection и barge-in. При прерывании TTS отменяется сразу; отдельно определяется, продолжать ли фоновый agent run или остановить его. Raw audio recording по умолчанию отключена; для MVP хранятся final transcripts и производные проектные артефакты.

## Отклоненные альтернативы

Не используем передачу аудио через обычный FastAPI WebSocket: для voice-first UX это создает лишнюю сложность с media transport, jitter, reconnect и двусторонним аудио. Не привязываем продуктовый data model только к OpenAI session: provider может меняться, тогда как Project/Module/Discussion/Task/Note/Event/Approval остаются стабильными.

## References

- https://developers.openai.com/api/docs/guides/realtime-conversations
- https://docs.livekit.io/agents/
- https://docs.livekit.io/agents/logic/turns/
