# ADR 009: Paired local workspace control without bulk source synchronization

**Status:** Accepted  
**Date:** 2026-08-20

## Context

A developer may keep a 200 GB project on a paired PC and still need to analyze, modify, test, commit and push it while away from that machine. The browser dashboard must offer an intentional source choice between a paired local workspace and a GitHub repository. Copying a large local checkout to cloud is impractical, risks leaking source and conflicts with Git as the code authority.

The existing architecture already provides a browser control plane, GitHub OAuth/RBAC, a durable cloud SQLite database, a paired PC runtime with outbound HTTPS sync, a project event log, policy approval modes, a verified release channel, and approval-bound read-only semantic jobs. It deliberately does not expose a remote shell or inbound PC listener.

## Decision

The product adds a **paired local workspace mode**. A desktop user explicitly registers a project-relative workspace manifest from a selected local Git root. Cloud stores only a bounded, Git-derived index and status projection: stable workspace ID, device binding, remote URL, branch, commit, dirty state, tracked-file and dependency summaries, language/module map, incremental index revision, and selected small result snippets. The source tree, untracked data, virtual environments, build artifacts, Graphiti credentials and actual large file contents remain on the PC.

The browser selects either:

| Source | Execution location | Code authority |
|---|---|---|
| `paired_local` | The selected paired PC, through its outbound runtime sync loop | The local Git checkout |
| `github_repository` | A GitHub-derived cloud project index and future isolated Git workspace | The selected Git repository/ref |

The paired runtime receives only typed workspace operations through the same lease-based pull relay. There is no raw shell, arbitrary command, arbitrary filesystem path, public MCP endpoint, or direct cloud-to-PC connection. Each operation is bound to project, device, workspace ID, index revision, lease and expiry.

### Typed local operations

| Operation | Risk | Local boundary | Approval rule |
|---|---|---|---|
| `refresh_index`, `list_files`, `search_text`, `read_file_range`, Serena semantic queries, Graphiti retrieval | R0 read-only | Registered workspace root; secret paths and binary/oversized content excluded | Allowed in the selected workspace mode |
| `apply_unified_patch` | R1 reversible local edit | Validated unified diff; registered workspace root; protected path deny-list; diff captured | Confirm each by default; workspace/run grant may permit it |
| `run_test_profile` | R2 controlled execution | Only named commands declared in `agent-room.yml`; fixed workdir, timeout and output cap | Explicit approval unless a bounded development mode grants it |
| `git_status`, `git_diff` | R0 read-only | Registered Git root | Allowed |
| `git_commit`, `git_push` | R3 persistent external action | Fixed Git subcommands; configured remote/branch; reviewable diff and commit message | Always explicit approval; never auto-granted by all-approvals mode |

A workspace trust file may declare test profiles and project-specific safe paths, but it can never permit secret access, arbitrary shell, package installation, destructive Git operations, credential reads, arbitrary external URLs or edits outside the registered root. The cloud policy engine remains deterministic and authoritative; local validation enforces the same scope again immediately before execution.

### 200 GB indexing model

Indexing is incremental and on-demand. The runtime derives a paginated Git file map from `git ls-files`, applies ignored and size limits, computes metadata hashes, and sends only changed index records in bounded batches. Large/binary files are represented by path and metadata, not content. File body access returns a capped line range only after a read request is approved by the scoped policy. Content is never bulk-uploaded as a prerequisite for opening the local project in the dashboard.

### Offline behavior

If the PC is off, the cloud displays the last signed index/status and queues only unexpired approved operations. It cannot read, modify or test the project until the PC comes back online. The runtime receives jobs through its existing outbound poll/sync, executes locally, stores a durable structured result and acknowledges it on a subsequent sync. Browser clients may disconnect without interrupting a leased PC task.

## Consequences

The dashboard can be a real project map for both local and GitHub-backed work without treating the cloud as a remote disk. Full developer workflows are possible on the PC while keeping the high-risk action boundary visible and reviewable. The next implementation increment requires a local workspace registry, project-source contracts, typed operation queue/executor, declared test profiles, result audit stream and a dashboard source chooser.

The system intentionally postpones arbitrary interactive terminals, SSH/VPN tunnels, raw desktop control, fully automatic Git pushes, unrestricted Docker commands and syncing actual source trees. Those features would weaken the project/device/approval boundary and are not required to support controlled coding workflows.

## References

The design follows current agent security guidance to constrain filesystem scope, protect sensitive paths, require review of changes and use deterministic controls rather than broad auto-approval. [1] A dedicated agent host may run next to a workspace so the UI can be remote while edits and commands stay close to source; the paired runtime provides that role without opening an inbound server. [2]

[1] [VS Code — AI security](https://code.visualstudio.com/docs/agents/run/security)

[2] [VS Code — Agent Host architecture](https://code.visualstudio.com/docs/agents/concepts/agent-host)
