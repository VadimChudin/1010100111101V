# Changelog

## 0.2.0 — Durable Workspace MVP

This release turns the original chat prototype into a durable, event-driven agent platform foundation. It is deployed as a FastAPI service on Railway with a React client on Vercel.

| Area | Delivered capability |
|---|---|
| **Chat contract** | Typed `AgentPlan` and public chat response model; fenced JSON plan parsing; frontend normalization for object-shaped plans. |
| **Safety** | Raw shell remains disabled by default. The public Tool Gateway exposes only typed workspace operations and enforces deterministic policy decisions. |
| **Durable runs** | SQLite WAL persists runs, sequenced events, terminal answers, plans, approvals, and cursor replay. |
| **Realtime** | `POST /v1/runs` creates queued runs; `GET /v1/runs/{run_id}/stream` supplies resumable SSE timeline events. |
| **Approvals** | `plan`, `confirm_each`, `allow_workspace_edits`, `smart_development`, and `all_approvals_for_run` modes are represented in the client and policy layer. Hard denials still apply. |
| **Typed tools** | Read-only file/search/git tools and bounded `create_file`/`replace_text` workspace edits; no free-form commands are accepted. |
| **Workspace** | Default project registry, persisted modules, notes, tasks, task status, generated marker badges, React Flow canvas, and Context Inspector. |
| **Observability** | Request correlation IDs, latency/count metrics at `/v1/metrics`, terminal run outcome metrics, and optional Sentry bootstrap through `SENTRY_DSN`. |
| **Serena** | Read-only provider contract and readiness endpoint at `/v1/serena/status`; semantic transport is intentionally feature-gated until the Serena connector is explicitly enabled and isolated worker wiring is supplied. |

### Validation

The release has backend regression coverage for chat contracts, SQLite storage, SSE replay, queue worker behavior, policy/approval flows, workspace APIs, observability, and the Serena provider contract. Frontend TypeScript checks and Vitest tests pass.

### Operating notes

The MVP intentionally uses a single-service delivery fallback in addition to Redis queue hand-off. It is suitable for the current free-tier deployment but does not yet offer stale-run leases or recovery after a worker dies post-claim. See [ADR 003](adr/003-queue-worker-fallback.md).

Serena remains **read-only by design** and is unavailable until its connector is enabled with explicit confirmation. Its staged integration is documented in [ADR 004](adr/004-serena-read-only-provider.md).


## 0.2.0-beta — Production Hardening

| Area | Delivered capability |
|---|---|
| **Worker reliability** | Execution leases, heartbeats, bounded retries, periodic stale-run recovery, limited model fallback and absolute agent run deadline. |
| **Approvals** | Durable pending-approval polling with scope-aware approve/reject cards in the frontend. |
| **Run-to-context** | Completed runs can be saved to workspace notes or follow-up tasks with `source_run_id` provenance. |
| **Security** | `X-Content-Type-Options`, anti-framing, referrer and permissions policies; `/v1/metrics` now requires authentication. |
| **CI** | GitHub Actions validates backend tests, frontend typecheck and Vitest on pushes and pull requests. |

See [`BETA_ACCEPTANCE.md`](BETA_ACCEPTANCE.md) for the operator acceptance matrix, known beta boundaries and rollback procedure.
