# Serena, Graphiti and Production Headroom Assessment

**Assessment date:** 2026-08-20

## Observed platform state

| Area | Verified state |
|---|---|
| Backend deployment | Railway service `1baa9e9c-f93f-4bd0-b56c-80dce5cc2dd8`; current release is healthy. |
| Service limit | Railway reports 2 CPU and 1,000,000,000 bytes memory for the backend service instance. |
| Last 24 hours | CPU was approximately 0.39%–0.75% in sampled intervals. Steady memory was around 80–100 MB, with deployment-related transients up to approximately 1.11 GB. Disk telemetry reported 0–0.038 GB ephemeral use; persistent SQLite data lives on the attached volume. |
| Serena connector | Enabled in the task configuration, UID `f7f15fe8-15cf-4fb9-a546-720f16dcf5e6`. The application production transport remains intentionally unavailable; the UI shows Gated. |
| Graphiti connector | No configured Graphiti connector. No active Neo4j or Graphiti runtime is part of the production service. |

## Technical findings

Serena is an MCP-based semantic code intelligence service. It can run as a client-launched process or as an HTTP-mode MCP server, and supports symbol-level retrieval through language servers. In the product, it must remain a read-only provider until a separate approval-gated writing pathway exists.

Graphiti is an open-source temporal context graph engine. Its core model stores episodes, entities and time-bounded facts. It requires a graph backend such as Neo4j 5.26+, FalkorDB, or Neptune, plus reliable structured-output LLM and embedding providers. It is not a replacement for authentication, execution state or source control.

## Design guardrails

1. Git remains the code source of truth; Serena reads the Git workspace but never owns it.
2. SQLite WAL continues to hold users, opaque sessions, RBAC, runs, approvals and workspace notes/tasks.
3. Graphiti is limited to derived, project-scoped semantic memory and provenance-rich episodes. It cannot become an authorization source.
4. A Graphiti database and its ingestion worker must not run inside the existing 1 GB API service. Deployment memory transients already exceed the nominal service ceiling.
5. Graphiti ingestion must be asynchronous, bounded and idempotent; retrieval can be request-scoped with strict project and user authorization checks.

## Sources

1. Railway Metrics: https://docs.railway.com/observability/metrics
2. Railway Public API: https://docs.railway.com/integrations/api
3. Serena documentation: https://oraios.github.io/serena/01-about/000_intro.html
4. Graphiti repository: https://github.com/getzep/graphiti
5. Graphiti overview: https://www.getzep.com/platform/graphiti/

## Recommended rollout

| Release | Scope | Runtime boundary | Exit criterion |
|---|---|---|---|
| Serena S1 | Deploy isolated Serena HTTP/MCP sidecar or worker against the read-only Git checkout. Expose only outline, symbol lookup and references through the existing typed `SerenaClient`. | Separate process or service; API communicates through a narrow read-only client. | Project-scoped semantic queries return results; no write or shell MCP tool is exposed. |
| Serena S2 | Add tool policy mapping and approval-aware mutation design, but keep symbolic editing disabled until the project write protocol is independently reviewed. | Typed gateway and policy engine remain the enforcement point. | Explicit deny tests prove raw shell and direct Serena mutations remain inaccessible. |
| Graphiti S1 | Provision a separate graph database service, use Neo4j-compatible Graphiti driver, and add an asynchronous ingestion worker with one project namespace/group per workspace project. | Separate database and worker; not the existing API process. | A completed agent run can ingest a bounded, provenance-tagged episode idempotently. |
| Graphiti S2 | Add retrieval before planning/review: project- and user-authorized temporal facts, decisions, unresolved questions and task context. | API gateway applies RBAC before graph lookup; only retrieval snippets enter the LLM context. | Cross-project memory leakage tests and deletion/retention tests pass. |

### Resource policy

The existing Railway backend is suitable for the control plane, SQLite state, Git index, normal tool dispatch, and low-volume Serena request proxying. It is **not** an acceptable host for a Graphiti database or concurrent Graphiti extraction workload. Its steady-state memory headroom is approximately 900 MB (90%), but the observed deployment-window metric peaked approximately 10.93% above the reported 1 GB limit. Treat this as a deployment stability warning, not spare capacity.

For the first Graphiti release, provision a dedicated graph database and worker with independent memory allocation. Keep ingestion concurrency at one or two until its model-rate limits, episode latency, and database memory footprint are measured. Do not combine Graphiti batch ingestion with the API worker or the existing run worker.

### Data ownership target

| Data class | Authoritative store |
|---|---|
| Source code, commit history, dependency manifests | GitHub/Git checkout |
| Users, OAuth state, opaque sessions, RBAC | SQLite WAL |
| Runs, events, approvals, leases, notes, tasks | SQLite WAL |
| Code symbols and references | Serena language-server index; disposable and rebuildable from Git |
| Derived temporal facts and their episode provenance | Graphiti graph database |


# Hybrid Local-First Extension

## Decision assessment

The proposed architecture is feasible and is preferable for the current stage. The browser application remains the cloud control plane and uses the existing GitHub OAuth, opaque session, RBAC, SQLite durable state, run queue and SSE timeline. A local runtime installed on the user's PC owns access to local repositories, Serena language-server state, and a local Graphiti graph database. It opens an outbound, authenticated TLS control connection to the cloud; the cloud does not connect to a port on the PC.

This supports two execution locations per project without changing its user-facing identity:

| Project runtime | Code and semantic location | Persistent context location | Use case |
|---|---|---|---|
| `cloud` | Git checkout in the hosted workspace | Existing SQLite; future cloud Graphiti | GitHub-visible work and fully hosted operation |
| `local:<device_id>` | Registered PC workspace through local runtime | Central SQLite plus local Graphiti/Neo4j or FalkorDB | Working-tree context, uncommitted changes, fast semantic inspection |
| `hybrid` | Local runtime is primary; Git revision is a synchronisation anchor | Central SQLite, local Graphiti, optional episode replication | Browser control from any device while code stays on PC |

## Local runtime responsibilities

The future `agent-room-runtime` is a separately installed daemon or Docker Compose bundle. It has the following components:

1. A device agent that owns registered local workspace roots and emits a signed inventory: repository identifier, branch, commit, dirty status, tracked tree summary and available capabilities.
2. A Serena service configured only with approved workspace roots. Version one exposes outline, find-symbol and references; direct edit, generic shell and Serena's own memory tools are disabled.
3. A Graphiti service backed by a local persistent graph database volume. It ingests bounded episodes derived from approved local work, run completions and workspace decisions; it has no authority over authentication or project membership.
4. An encrypted local outbox. When offline, it queues inventory deltas, events and bounded graph-derived summaries; when online, it syncs them to the cloud control plane idempotently.

## Connection and trust model

The local runtime must make an outbound `wss://` connection to the cloud runtime gateway. During device pairing, the signed-in browser receives a short-lived one-time code and the PC runtime exchanges it for a device credential. The cloud stores only a hash/public key and device metadata, never the PC filesystem path as a globally trusted capability. Every job carries `project_id`, `device_id`, actor identity, allowed operation and expiry. The runtime verifies that the project root is registered locally before serving it.

The dashboard can therefore render an online/offline device state and project inventory from any browser. It receives source metadata and semantic query results by default, not a full raw local file mirror. Viewing or returning file content remains a separately policy-gated operation. This prevents the local runtime from becoming an unauthenticated reverse shell or an exposed LAN service.

## Migration path

A future cloud upgrade does not change the control-plane contract. The project runtime can be switched from `local:<device_id>` to `cloud`, and Graphiti can replay retained, provenance-tagged episodes into a cloud graph store. Git remains the immutable code anchor; SQLite remains the source for users, sessions, RBAC, runs, approvals, notes and tasks.

## Target control-plane contracts

| Contract | Direction | Minimal payload | Security boundary |
|---|---|---|---|
| Device pairing | Browser → cloud → PC runtime | one-time pairing code, user session, device public key | Code expires; cloud stores credential hash/public key only. |
| Device heartbeat | PC runtime → cloud | device ID, runtime version, capabilities, encrypted workspace identifiers | Outbound TLS only; no inbound PC listener. |
| Workspace inventory | PC runtime → cloud | project ID, Git remote/branch/HEAD, dirty status, source-tree summary | Runtime validates a locally registered root; payload is idempotent. |
| Semantic query | Cloud → PC runtime → cloud | project ID, allowed read-only Serena operation, relative path or symbol, expiry | Cloud checks RBAC and policy; runtime checks device/project binding. |
| Graph episode sync | PC runtime → cloud | project ID, episode ID, type, provenance, digest and optional bounded summary | At-least-once delivery with idempotency key; raw local content excluded unless explicitly approved. |
| Local execution request | Cloud → PC runtime | run ID, approved tool request, scope, expiry | Cannot execute generic shell; only typed local capabilities exist. |

The cloud must treat the local runtime as an untrusted but authenticated execution peer, not as a mounted filesystem. The local runtime must treat the cloud as an authorized job broker, not as authority to access arbitrary paths. This allows the same contracts to route a project to a future cloud runtime without changing the dashboard, role model or durable SQL state.

## Local-first roadmap

| Sprint | Deliverable | Does not change |
|---|---|---|
| H0 — hybrid foundation | Device registry, pairing flow, device heartbeat, project-to-device binding, read-only inventory endpoint and dashboard online/offline state. | SQLite auth/RBAC remains authoritative; no local execution yet. |
| H1 — local Serena | `agent-room-runtime` package/Compose profile, registered workspace roots, local Serena with read-only semantic operations, typed runtime gateway and policy tests. | No Serena write tools, no raw shell, no full local file replication. |
| H2 — local Graphiti | Local Graphiti + graph backend profile, project namespace, encrypted outbox, idempotent episode ingestion and authorized context retrieval. | SQLite still owns notes/tasks/runs; Graphiti only derives memory. |
| H3 — hybrid agent routing | Run capability planner chooses `cloud` or `local:<device>` according to the project setting; approvals bind to device, project, scope and expiry. | Existing cloud Git dashboard continues to work when PC is offline. |
| H4 — cloud parity | Deploy separate cloud Graphiti database/worker; support replay/migration of retained local episodes and choose local/cloud/hybrid project mode. | Browser UI and API contracts stay stable. |
| Voice sprint | OpenAI Realtime/LiveKit consumes the same project/runtime context broker after H0–H3 prove stable. | Voice does not receive direct filesystem or graph database credentials. |

The recommended implementation starts with H0 and H1. They produce immediate value for browsing PC repositories and using Serena safely while creating the permanent execution contract that Graphiti and future cloud workers share.

# GitHub Audit: Offline Common Project State

## Audit scope

The requirement is not generic file synchronization. The platform needs a common state that survives a PC shutdown, accepts cloud-side progress during that period, and converges automatically when the local runtime returns. The audit distinguishes:

1. **Code state** — Git working tree, branch, commit and uncommitted changes.
2. **Durable control state** — identities, RBAC, runs, approvals, notes, tasks and device registrations.
3. **Collaborative drafts** — concurrently edited note bodies or planning documents.
4. **Derived semantic memory** — Serena index and Graphiti episodes/facts.

## Verified candidates

| Project | Stars observed | Evidence of maintenance | Fit | Decision direction |
|---|---:|---|---|---|
| `yjs/yjs` | 22,474 | Pushed 2026-08-06; updated 2026-08-20 | JavaScript CRDTs, browser collaboration and provider ecosystem | Strong candidate only for collaborative drafts and future shared rich-text notes. |
| `yjs/y-indexeddb` | 279 | Pushed 2025-02-12; updated 2026-08-06 | Local browser persistence for Yjs docs | Companion to Yjs, not system-wide state sync. |
| `yjs/y-websocket` | 712 | Pushed 2026-08-06; updated 2026-08-13 | WebSocket provider for Yjs docs | Optional future component; does not replace project event protocol. |
| `automerge/automerge` | 6,519 | Pushed 2026-08-19 | General JSON-like CRDT with automatic merge | Good technical alternative, but not selected for v1 because current app needs event semantics more than free-form document CRDTs. |
| `automerge/automerge-repo` | 704 | Pushed 2026-08-20 | Network/persistence layer for Automerge | Promising but less mature than the core and adds a second state model. |
| `electric-sql/electric` | 10,327 | Pushed 2026-08-14; updated 2026-08-20 | Local-first database synchronization | Strong later candidate if the durable backend moves from SQLite to PostgreSQL; mismatched with the current SQLite-first MVP. |
| `vlcn-io/cr-sqlite` | 3,768 | Pushed 2026-08-10 | Multi-writer convergent replicated SQLite | Technically relevant but not a drop-in replacement for existing Python SQLite WAL persistence; extension and operational complexity are not justified in v1. |
| `apache/pouchdb` | 17,600 | Pushed 2026-07-27 | Document database replication | Mature but introduces CouchDB-style data and operational model that conflicts with existing typed SQL schema. |
| `rocicorp/replicache` | 1,172 | Last push 2022-05-07 | Client-side realtime sync pattern | Architecture reference only; apparent code activity is too old for the platform core. |
| `syncthing/syncthing` | Not collected in command output | Pushed 2026-08-20 | Continuous file synchronization | Explicitly reject as project-state transport: it can race with Git working tree and cannot enforce RBAC or semantic memory rules. |
| `cloudflare/cloudflared` | 15,309 | Pushed 2026-08-14 | Outbound-only private connectivity | Optional transport hardening; not a state synchronizer. |
| `tursodatabase/libsql` | 17,149 | Pushed 2026-08-11 | SQLite-compatible embedded replicas | Future migration candidate, but retains SQLite single-writer limitation. |
| `tursodatabase/turso` | 23,942 | Pushed 2026-08-20 | SQLite-compatible concurrent and bidirectional offline sync | Promising future platform option; upstream README currently labels bidirectional offline support as beta, so not the v1 control-plane authority. |

## Preliminary conclusion

No candidate should replace the current cloud SQLite authority in the first hybrid release. The reliable v1 design is an append-only, idempotent **project event log** implemented inside the existing FastAPI + SQLite service, together with a per-device local SQLite outbox and checkpoint cursor. It uses the data model already protected by GitHub OAuth/RBAC and avoids forcing database-level multi-master replication onto runs and approvals, which require ordered, auditable state transitions.

Use CRDTs selectively. Yjs is the preferred future layer for free-form simultaneous editing of note or planning text. It must not own approvals, task status, run leases, RBAC or code state. Git remains the merge and conflict authority for code; Graphiti replays provenance-tagged episodes and is never the authority for workflow state.

## Compatibility and security comparison

| Candidate | FastAPI + SQLite compatibility | Offline reconciliation | Auditability for approvals/runs | Operational impact | Result |
|---|---|---|---|---|---|
| Existing SQLite + application event log | Native | Explicit cursor/outbox replay | Strong: server applies ordered, idempotent domain events | Low | **Select for v1 common state** |
| Yjs + IndexedDB/WebSocket | Strong in React; no Python CRDT processing needed if server relays/persists updates | Strong for document updates | Weak for ordered workflow transitions; correct only for document bodies | Medium | **Selective use for drafts** |
| Automerge / Automerge Repo | Strong in TypeScript; extra bridge needed for Python services | Strong CRDT convergence | Weak/ambiguous for leases and approvals | Medium | Defer; evaluate if local-first documents expand beyond notes |
| ElectricSQL | Requires PostgreSQL and Electric deployment | Strong | Potentially strong after data-model migration | High | Future cloud-scale candidate, not current MVP |
| cr-sqlite | Requires replacing/embedding SQLite extension semantics | Strong but database-level | Difficult to preserve domain invariants across multi-writer replicas | High | Reject for v1 |
| PouchDB / CouchDB | Requires document-store path alongside SQL | Strong | Requires separate authorization/conflict policies | High | Reject |
| libSQL embedded replicas | Close to SQLite but changes runtime/database topology | Primarily replicated reads | Single-writer constraint unsuitable for multi-device authority | Medium | Defer |
| Turso offline bidirectional sync | Promising but feature is beta upstream | Intended support | Insufficient beta confidence for auth/run authority | High | Watchlist only |
| Syncthing | Files only | Files only | No project-RBAC or workflow semantics | Medium and unsafe around Git | Reject as state transport |
| cloudflared | Transport only | N/A | N/A | Optional | Use only if direct outbound WSS becomes insufficient |

### Security decision

The cloud service remains the sole sequencer for protected state transitions: project membership, role changes, run creation, run lease changes, approval decisions, task lifecycle and marker creation. A PC may create or update a local intent event, but the cloud validates user session/device credential, project membership, optimistic concurrency revision, idempotency key and policy before appending it to the shared log.

The local runtime cannot merge or overwrite central authorization records. Conversely, the cloud does not mount the PC filesystem or write directly into local Graphiti/Serena stores. Sync is a constrained protocol of typed events, checkpoints and signed/hashed payloads.

## Recommended common-state and reconciliation architecture

### State ownership

| State category | Authority | Local behavior while PC is offline | Reconciliation rule |
|---|---|---|---|
| Auth, sessions, RBAC, approvals, run lifecycle, leases | Cloud SQLite event log and projections | Local runtime may read cached capability grants but cannot finalize protected state offline | Cloud-only; stale grants expire. |
| Notes, tasks, markers, decisions | Cloud event log and projections | Local runtime creates immutable intent events in local outbox | Server appends idempotently; field conflicts use revision/precondition policy. |
| Collaborative draft body | Yjs document, if/when collaborative editor is introduced | Browser/PC persists CRDT updates locally | CRDT updates merge automatically; materialized snapshot is stored centrally. |
| Git code | Git repository | PC owns local working tree, including dirty changes | Git commit/merge remains authority; runtime reports status but does not sync raw working tree through the state protocol. |
| Serena index | Local runtime cache | Unavailable while device is off | Rebuild from workspace after device returns. |
| Graphiti facts and episodes | Local Graphiti first; cloud stores provenance cursor and optional shared episode envelope | Local graph receives no new PC-derived episodes while off; cloud work produces cloud-originated episodes | Both sides exchange immutable episodes by ID; derived facts are recomputed/retrieved per graph namespace, never last-write-wins copied. |

### Event protocol

Each mutable shared entity gets a cloud revision number. The local runtime maintains a SQLite outbox with `(event_id, project_id, device_id, entity_type, entity_id, operation, base_revision, payload_hash, payload, occurred_at, retry_state)`. Event IDs are UUIDv7 or similarly sortable unique IDs. The cloud event log enforces a unique `(project_id, event_id)` constraint, yielding at-least-once transport with exactly-once observable application.

The cloud synchronisation response contains two cursors: `accepted_through` for the device's outbox and `server_cursor` for all project events. A returning device follows this deterministic sequence:

1. It authenticates the device and sends its last acknowledged server cursor plus a bounded batch of unsent outbox events.
2. The cloud validates project membership, device binding, expiry, payload schema, idempotency key and each event's `base_revision`.
3. Accepted events append to the central project event log and update SQLite projections transactionally.
4. Rejected or conflicted events return a typed conflict record; they are not silently overwritten.
5. The cloud streams every missing central event since the local `server_cursor`, including the work performed in cloud while the PC was off.
6. The PC applies those events locally in cursor order, advances its checkpoint, then retries only events whose preconditions are still valid.
7. The PC rebuilds Serena if the Git workspace changed and imports/replays only missing Graphiti episodes by provenance ID.

### Conflict policy

Do not apply a single last-write-wins rule to every data type. A task status transition requires an expected revision. An approval can only be issued or revoked by the cloud policy engine. A note title/body may use a conflict copy in v1 or CRDT in a later collaborative editor. A marker is append-only. A Git change is never copied into a state merge; Git itself resolves it.

This means an offline PC cannot destroy cloud progress. Cloud activity becomes normal events in the same log, and when the PC returns it pulls that log before it resumes local execution.

