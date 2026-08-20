# ADR 008: Approval-bound cloud-to-device semantic job relay

**Status:** Accepted  
**Date:** 2026-08-20

## Context

The cloud control plane can authorize a user to inspect a project, but Serena and Graphiti operate on a paired PC where the checked-out Git workspace and local graph database exist. A cloud request must never gain a generic local shell, filesystem handle, MCP endpoint, Graphiti credential, or persistent inbound connection to the PC. The PC can be offline, and cloud state remains authoritative during that time.

The existing local runtime already maintains an outbound, device-token-scoped HTTPS sync loop, a durable local SQLite outbox, project RBAC, one-time pairing, a project event log, and a read-only Serena tool allow-list. Those primitives are sufficient for a secure relay without opening an inbound listener.

## Decision

The cloud stores typed `device_jobs` in SQLite. The only initial job types are `find_symbol`, `find_references`, `index_workspace`, and `retrieve_project_memory`. Every job is bound to one project, one registered device, a creator, a narrow validated input payload, an expiry time, and an explicit approval decision. Job creation is not execution: a browser operator with the required project role must approve a pending job before it becomes deliverable.

An approved job is delivered only as part of the existing device-authenticated sync response. Delivery creates a short lease. A runtime can execute only a job whose project and device match its local configuration, whose type is in its compiled allow-list, whose lease is valid, and whose payload passes local validation. The runtime has no generic command field. It uses only the hardened read-only Serena boundary or the local Graphiti retrieval adapter.

The runtime returns structured, bounded results with a job ID and lease ID in the next outbound sync request. The cloud records result status and a truncated structured result projection for authorized visibility. Results are never accepted after job expiry, from another device, or under a different project credential. A timed-out lease is returned to the queued state only while the job itself remains unexpired. Device credentials, Graphiti connection values and local filesystem contents are never included in the browser-facing job model.

## Consequences

An offline device receives no job; cloud work remains available and the UI can show the request as queued. When the device reconnects, its normal sync cycle claims eligible jobs. This is a deliberate pull relay, not a remote-desktop connection.

The first increment handles only read-only semantic retrieval and indexing. It does not permit edits, shell commands, Git actions, arbitrary URLs, arbitrary MCP calls, or Graphiti mutation from cloud jobs. The stored result is evidence for an authorized workflow, not a replacement for Git or Graphiti provenance. Graphiti remains a derived memory system and never controls authorization, RBAC, approval or job dispatch.

## Security invariants

| Surface | Invariant |
|---|---|
| Cloud creation | Project RBAC plus a separate explicit approval transition before dispatch |
| Device delivery | Project ID, device ID, device credential, job expiry and lease binding are all checked |
| Local execution | Compiled allow-list; no shell strings; no filesystem write capability; no inbound service |
| Serena | Loopback-only endpoint and `get_symbols_overview`, `find_symbol`, `find_referencing_symbols` only |
| Graphiti | Retrieval only; provider and database credentials stay local |
| Results | Structured and output-size bounded; accepted once under matching active lease |
| Offline state | Queue/lease/expiry are durable cloud state; no assumption that a PC is online |

## Rejected alternatives

A cloud-initiated HTTP callback to the PC was rejected because it would expose an inbound listener and require NAT, firewall or public endpoint handling. Generic remote shell and generic MCP forwarding were rejected because neither preserves the approval and scope boundary. Polling a separate public job queue was rejected because the existing authenticated sync channel already provides device identity, retry behavior and a durable cursor.

## External implementation references

The MCP Streamable HTTP specification requires local servers to validate origins, bind to localhost when running locally, and use JSON-RPC request/response semantics; the relay therefore keeps Serena loopback-only and never forwards its endpoint to cloud clients. [1]

VS Code’s current agent security guidance similarly recommends workspace-limited access, explicit edit review, session-scoped approvals, protection for secret paths, and deterministic controls rather than broad auto-approval. These principles inform the subsequent full local workspace increment. [2]

[1] [Model Context Protocol — Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)

[2] [VS Code — AI security](https://code.visualstudio.com/docs/agents/run/security)
