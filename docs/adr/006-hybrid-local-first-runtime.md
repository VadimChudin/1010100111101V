# ADR 006: Hybrid local-first runtime with cloud-authoritative project state

**Status:** Accepted

**Date:** 2026-08-20

## Context

The platform must support work that moves between a browser-hosted cloud control plane and a developer PC. The PC may be switched off while users continue work in the cloud. Serena should orient the agent in the real local repository, while Graphiti should retain temporal project memory. The existing MVP uses FastAPI, GitHub OAuth, SQLite WAL, strict project RBAC and Git-derived code maps.

Replicating the entire SQLite database to each PC would create unsafe multi-writer behavior for approvals, leases, run state and RBAC. Syncing the working directory with a generic filesystem tool would conflict with Git and would not preserve project-scoped authorization or workflow provenance.

## Decision

Cloud SQLite is the authoritative store for identities, opaque sessions, RBAC, approvals, run state, workspace records and a new append-only `project_events` log. Every local runtime owns a durable SQLite outbox and a `server_cursor`. The cloud accepts typed events idempotently by `(project_id, event_id)`, validates an entity revision precondition, updates workflow projections transactionally, and returns the full missing central event stream after the runtime cursor.

A local runtime is paired through a short-lived one-time token and receives an opaque device credential. The cloud stores only the credential hash. Device sync is HTTPS device-token scoped and carries inventory plus a bounded event batch. The runtime never exposes a public inbound service or raw shell interface.

Git remains the code authority. Serena runs locally against an approved Git workspace and only exposes outline, symbol lookup and references through the read-only capability contract. Its semantic index is rebuildable and is not synchronized as primary state.

Graphiti runs locally against a persistent local graph database. It emits immutable, provenance-tagged episode envelopes through the common event protocol. Cloud stores those envelopes for authorized replay and visibility; Graphiti facts remain a derived memory layer, never an authorization or workflow authority.

## Consequences

When a PC is offline, cloud workflows continue normally and append events to the central log. On reconnect, the runtime pushes unsent local events, receives accepted/conflict results, then replays missing cloud events in cursor order. Conflicts are explicit rather than silently last-write-wins. A dirty local Git working tree is reported but never automatically copied to cloud; an explicit future WIP checkpoint policy is required for cloud execution against uncommitted code.

The first release intentionally does not use CRDT/database replication for protected workflow entities. A future collaborative rich-text editor may use Yjs only for free-form note bodies. ElectricSQL, CRDT SQLite and Turso remain future options, not control-plane sources of truth.
