# Agent Room Desktop — Test Channel

Agent Room Desktop is a minimal local companion for the existing Agent Room web product. Its onboarding flow is intentionally simple: install the application, choose **Continue with GitHub**, approve in the default browser, select a local Git workspace, and choose **Install and pair this computer**. The application then opens the same deployed Agent Room chat and control surface that is available in the browser.

## What the desktop application owns

| Concern | Desktop behavior |
|---|---|
| GitHub sign-in | Opens the existing GitHub OAuth authorization in the user’s default browser with PKCE. The browser confirms the desktop request; it does not send its cookie to the application. |
| Desktop session | Claims a one-time opaque server session after browser approval and stores it using the operating system’s encrypted credential facility. The web workspace runs in an isolated Electron browser session with an HTTP-only backend cookie. |
| Local runtime | Downloads the verified `runtime-latest` wheel, checks SHA-256, creates a dedicated user-local Python environment, registers the PC with a one-time cloud pairing token, then starts durable auto-sync. |
| Serena | Installs the supported `serena-agent` package through the runtime toolchain, initializes it, and starts an MCP endpoint only on `127.0.0.1:9121`. Cloud-exposed usage remains limited to Agent Room’s approved read-only semantic tool boundary. |
| Graphiti | If Docker is running, starts the existing local Neo4j profile with loopback-only ports. If Docker is unavailable, setup succeeds for runtime and Serena; provenance envelopes remain durable and synchronizable until the local graph profile is enabled. |

## Test artifacts

The GitHub Actions desktop release workflow publishes per-platform artifacts to the `desktop-latest` prerelease channel:

- Windows: `Agent-Room-Setup-<version>.exe` via an NSIS one-click installer.
- Linux: `Agent-Room-<version>.AppImage` and `.deb`.

The test channel is intentionally unsigned. Windows SmartScreen, Gatekeeper, and enterprise endpoint protection may warn about an unsigned test artifact. Production signing, notarization, native auto-update, a bundled Python sidecar, and an embedded Graphiti provider configuration are explicitly not asserted by this test channel.

## Local development

```bash
cd desktop
pnpm install
pnpm test
pnpm exec electron .
```

The local development flow can target a staging backend and frontend without changing source code:

```bash
AGENT_ROOM_API_URL=https://staging.example AGENT_ROOM_FRONTEND_URL=https://staging-ui.example pnpm exec electron .
```

## Security boundaries

The renderer uses `contextIsolation`, sandboxing, and `nodeIntegration: false`. It only receives a narrow preload API for setup actions. It cannot run arbitrary shell commands, read the selected workspace directly, retrieve the device credential, retrieve the browser authorization secret, or read the local Graphiti password. The desktop app invokes only fixed, allow-listed runtime commands and never opens an inbound runtime API.

See [ADR 007](../docs/adr/007-desktop-paired-runtime.md) for the complete architecture decision.
