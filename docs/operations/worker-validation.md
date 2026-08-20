# Worker Reliability Validation

An authenticated production smoke run was submitted through the Vercel UI after the lease/recovery deployment.

| Field | Value |
|---|---|
| Run ID | `ad135fdc-1e34-4ba8…` (UI-visible prefix) |
| Submission path | Authenticated Vercel Chat UI → Railway queue → durable SQLite run store |
| Initial observed state | `queued`, with the live SSE timeline connected |

The terminal state and worker metric outcome are recorded after completion. The first UI observation remained in the active state, so the run is being diagnosed before treating the smoke test as successful.

The durable record confirmed that attempt 1 started, planner and executor events persisted, and the lease heartbeat continued to advance `updated_at`. The run did not reach reviewer completion, indicating an upstream model-call latency problem rather than a lost queue job or expired worker lease. The record is not counted as a successful smoke test.
