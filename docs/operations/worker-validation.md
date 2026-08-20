# Worker Reliability Validation

An authenticated production smoke run was submitted through the Vercel UI after the lease/recovery deployment.

| Field | Value |
|---|---|
| Run ID | `ad135fdc-1e34-4ba8…` (UI-visible prefix) |
| Submission path | Authenticated Vercel Chat UI → Railway queue → durable SQLite run store |
| Initial observed state | `queued`, with the live SSE timeline connected |

The terminal state and worker metric outcome are recorded after completion. The first UI observation remained in the active state, so the run is being diagnosed before treating the smoke test as successful.

The durable record confirmed that attempt 1 started, planner and executor events persisted, and the lease heartbeat continued to advance `updated_at`. The run initially did not reach reviewer completion, indicating an upstream model-call latency problem rather than a lost queue job or expired worker lease.

## Production smoke outcome

The production run completed successfully on its first attempt. It created planner and executor events at `09:17:46 UTC`, then wrote the reviewer result and terminal `run.completed` event at `09:23:13 UTC`. This confirms durable persistence and completion, but also demonstrates a reviewer latency of roughly 327 seconds under the prior ten-model free-tier fallback policy. Commit `2a6c7e0` reduces the maximum fallback fan-out to three models and applies a 20-second per-attempt timeout; it also adds periodic stale-lease recovery after deployment. A fresh smoke run is required to validate the new latency bound.

The Vercel production UI was subsequently opened as the authenticated owner. It shows the backend as active, the live transport as connected, the configured approval modes, and the input required to submit that fresh smoke run. A fresh minimal run was submitted through that UI under `confirm_each` approval mode: `50e5d1fc-6c37-48b1…`. The UI displayed it as active. A subsequent direct `GET /v1/runs` check returned `405 Method Not Allowed`, because the API intentionally exposes individual run retrieval rather than an unscoped run-list endpoint; no authentication or CORS regression was indicated.
