# ADR 007: Desktop Paired Runtime and Browser Authorization

**Status:** Accepted for the test channel  
**Date:** 2026-08-20  
**Decision owners:** Agent Room maintainers

## Context

Agent Room must be usable as a local application without asking a user to manually install Python packages, copy pairing tokens, or configure an MCP client. The application must preserve the existing model: Git is the code authority; the cloud SQLite store is authoritative for authentication, RBAC, workspace state and the append-only project event log; Serena is local semantic navigation; and Graphiti is local temporal memory.

The desktop application must not expose a filesystem API, an arbitrary shell API, local Serena endpoint, device credential, or Graphiti provider credentials to the cloud or to renderer JavaScript. A login initiated by the desktop shell must use the existing GitHub OAuth application and browser session rather than embedding a GitHub password page in the application.

## Decision

A new `desktop/` package implements a thin Electron test client. It has two surfaces. The native onboarding surface is a minimal local page that shows installation and runtime status. Once setup is complete, the desktop window loads the existing deployed Agent Room frontend, so its chat and project dashboard stay identical to the browser product.

The desktop client starts authentication by creating a short-lived desktop authorization request at the cloud API. The API returns a GitHub authorization URL. The client opens it in the user’s default browser. When GitHub OAuth succeeds, the cloud callback creates a normal opaque session and atomically completes the matching authorization request. The desktop client polls only with a one-time secret created on the same device. On completion it receives the session token once, stores it using the operating-system protected desktop store, and sets an HTTP-only cookie in Electron’s isolated session for the backend origin. The renderer never receives either the session token or a device token.

After authorization, the Electron main process requests a one-time project pairing token and invokes only allow-listed local runtime commands. The bootstrap creates runtime configuration, registers the device, then starts the runtime with verified auto-update. The initial test profile uses supported Serena installation commands through `uv`; it always launches Serena on `127.0.0.1` and exposes only the existing read-only tool allow-list. Graphiti is brought up only through the existing local Neo4j compose profile; it binds locally and remains optional until Docker is available. A missing Docker installation is reported clearly rather than substituted by an insecure remote database or hidden privileged installer.

## Consequences

The test client gives the desired one-click product journey where platform prerequisites are already available: install the desktop app, click **Continue with GitHub**, approve in the browser, select a workspace, and the local runtime registers and synchronizes. The desktop UI then opens the same chat and project dashboard as the web application.

A Windows native installer will be built on GitHub Actions using a Windows runner. The Linux pipeline builds a portable test artifact. Native code signing and macOS notarization are intentionally outside this test-channel ADR; unsigned test installers must clearly be treated as test artifacts. Tauri was evaluated, but Electron is selected for the first test channel because its Node main process can package and coordinate the existing Python-oriented local runtime with less cross-language conversion. A later production client may migrate to Tauri after the runtime is compiled into stable per-platform sidecars.

The current Graphiti bridge preserves and syncs durable provenance envelopes even when its optional graph client is unavailable. This ADR does not claim that Graphiti has fully initialized a local provider until a supported local provider configuration is supplied. Nor does it add cloud-to-device job relay; that remains a later typed, approval-bound increment.

## Security invariants

| Boundary | Required invariant |
|---|---|
| OAuth | PKCE state, browser-based GitHub authorization, one-time 10-minute desktop delivery request |
| Desktop delivery | Only a hash of the desktop request secret is persisted; the session token is delivered once and deleted atomically |
| Renderer | No Node integration, no raw shell commands, no filesystem privileges and no access to credentials |
| Local runtime | Outbound cloud sync only; no inbound listener and no raw shell API |
| Serena | Loopback-only MCP endpoint and the existing read-only semantic tool allow-list |
| Graphiti | Local-only Neo4j compose profile; not an authority for authentication, RBAC or approvals |
| Release integrity | Runtime and desktop build artifacts are release-channel assets with SHA-256 verification |

## References

[1] [Tauri deep link documentation](https://v2.tauri.app/plugin/deep-linking/)  
[2] [Tauri external sidecar documentation](https://v2.tauri.app/develop/sidecar/)  
[3] [Serena installation documentation](https://oraios.github.io/serena/02-usage/010_installation.html)
