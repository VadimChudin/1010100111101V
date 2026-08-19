# Release Validation Record — Durable Workspace MVP

**Validated:** 2026-08-19

| Check | Result | Evidence |
|---|---|---|
| Backend tests | Passed | `18 passed` with durable runs, queue/SSE, policy/approvals, workspace, observability, and Serena provider-contract coverage. |
| Frontend checks | Passed | TypeScript `tsc --noEmit` and Vitest `2 tests` passed. |
| Railway health | Passed | `GET /v1/healthz` returned `200` and `{"status":"ok"}`. |
| Durable run | Passed | Production queued run completed; persisted plan and sequence events were returned through the run API. |
| SSE timeline | Passed | Production stream delivered `run.started`, planner, tool/review, and `run.completed` events. |
| Policy gateway | Passed | Production read-only action was allowed; `.env` read produced durable hard-deny policy event. |
| Workspace | Passed | Production default project loaded with five module-registry nodes and workspace snapshot endpoint returned successfully. |
| Serena status | Passed as gated | `GET /v1/serena/status` returns a clear read-only, unavailable state until connector enablement and isolated transport wiring. |
| Frontend visual smoke test | Passed | Production UI loaded the default workspace map with five modules, selected module context, stream state, and approval mode control. |

## Deployed endpoints

- Frontend: <https://frontend-swart-alpha-20.vercel.app>
- Backend: <https://app-production-cc16.up.railway.app>
- Backend health: <https://app-production-cc16.up.railway.app/v1/healthz>
- Workspace projects: <https://app-production-cc16.up.railway.app/v1/projects>
- Metrics: <https://app-production-cc16.up.railway.app/v1/metrics>
