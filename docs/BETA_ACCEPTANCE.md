# Beta Acceptance Checklist

**Release baseline:** `b551c1c` at the start of beta documentation.  
**Scope:** durable runs, GitHub OAuth, RBAC, workspace context, approvals, CI, and production security controls. Voice and Git-centric repository import are deliberately outside this beta baseline.

## Acceptance matrix

| Capability | Acceptance criterion | Evidence | Status |
|---|---|---|---|
| Authentication | Unauthenticated production API requests are rejected; owner can authenticate through GitHub OAuth. | `docs/operations/github-oauth-setup.md` | Verified |
| CORS | Only the Vercel production origin is permitted with credentials. | Production validation record | Verified |
| Durable state | SQLite WAL runs, events, approvals, workspace artifacts and sessions survive redeploy on mounted `/data`. | `docs/operations/storage-validation.md` | Verified |
| Worker reliability | Leases, bounded retries, stale-run recovery and absolute run deadline are enabled. | `docs/operations/worker-validation.md` | Verified with latency follow-up |
| Live timeline | Authenticated run timeline is delivered over resumable SSE. | Production UI validation | Verified |
| Approvals | Pending approval polling and scoped approve/reject cards operate against durable approval records. | API regression tests and deployed UI | Verified |
| Workspace context | A completed run can be saved as a note or follow-up task with `source_run_id` provenance. | Backend regression tests and deployed UI | Verified |
| Security | Strict CORS, session-bound RBAC, no raw shell, baseline response headers and authenticated metrics. | Backend tests and Railway response inspection | Verified |
| CI | Backend tests, frontend typecheck and frontend tests run for pushes and pull requests. | GitHub Actions CI | Verified |

## Beta operator checks

1. Sign in with the approved GitHub account at the production frontend.
2. Confirm that the dashboard loads a project workspace and can select a module.
3. Submit a short chat run and observe the SSE timeline until terminal state.
4. Where a policy-gated tool call exists, verify that the card describes the action, offers scope choices, and does not execute before approval.
5. Capture a terminal run as a note and as a follow-up task; confirm the selected module displays the abbreviated run provenance.
6. Confirm GitHub Actions is green for the deployed commit, Railway health is successful, and Vercel points to the production alias.

## Known beta boundaries

The current canvas is a workspace module map, not yet a direct import of the repository's full file tree or dependency graph. The next dashboard phase makes Git the source of truth and replaces the seeded module registry with an indexed repository model. Serena is intentionally read-only and gated in production until an isolated transport is wired. Voice interaction remains scheduled for the final sprint.

## Rollback

Railway and Vercel are both deployed from `main`. To roll back, revert the relevant commit on `main`, allow CI to pass, and verify the resulting Railway and Vercel production deployments. SQLite data is durable on `/data`; schema migrations must remain backward compatible.
