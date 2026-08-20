# Agent Room Local Runtime

`agent-room-runtime` connects a registered PC workspace to the cloud Agent Room control plane. It keeps a durable SQLite outbox on the PC, reports only Git inventory by default, and does **not** expose an inbound control port.

The runtime is intentionally separate from the browser integration. A browser can manage the project while the PC is offline; on reconnect, the runtime pushes its pending typed events and pulls all cloud events since its acknowledged cursor.

## What runs locally

| Component | Purpose | Data boundary |
|---|---|---|
| Local runtime | Pairing, Git inventory, encrypted device credential, durable outbox and sync | Sends typed events, not a filesystem mount. |
| Serena | Read-only symbol navigation against the registered workspace | Bound to `127.0.0.1`; only outline, symbol lookup and references are exposed through the runtime contract. |
| Graphiti | Optional temporal project-memory store | Lives in a local persistent volume; immutable episodes are replayed by provenance ID. |

## Install and pair

Create a pairing token in the browser dashboard after the device panel is available. Pairing tokens are one-time and expire by default after ten minutes.

```bash
cd local-runtime
python3 -m venv .venv
. .venv/bin/activate
pip install -e .

agent-room-runtime init \
  --cloud-url https://app-production-cc16.up.railway.app \
  --project-id default \
  --workspace-root /absolute/path/to/project \
  --state-dir ~/.agent-room/default \
  --device-name "Development PC"

agent-room-runtime register \
  --config ~/.agent-room/default/runtime.json \
  --pairing-token "<one-time-token>"

agent-room-runtime sync-once --config ~/.agent-room/default/runtime.json
```

A background supervisor on the PC may call `sync-once` with reconnect/backoff. It must not use a public inbound listener. The first release deliberately keeps synchronization pull-based over HTTPS so it works through normal outbound firewall rules.

## Serena

Install Serena on the PC using its official installation process. The runtime prints a hardened, local-only command:

```bash
agent-room-runtime serena-command --config ~/.agent-room/default/runtime.json
```

The generated command binds Serena's streamable HTTP transport to `127.0.0.1`, selects the registered Git workspace and disables the Serena web dashboard. Do **not** change it to a public address. The cloud never connects to this port directly; a later runtime relay will invoke only allowlisted read-only operations.

## State and conflict model

* Git is the authority for code. Dirty files are reported but never silently copied to the cloud.
* Cloud SQLite is the authority for users, RBAC, approvals, runs, tasks and common project event history.
* A local event carries an `event_id`, entity revision precondition and payload. The cloud accepts it idempotently or returns a typed conflict.
* Cloud events created while the PC is off are replayed in server-cursor order after reconnection.
* Graphiti episodes are immutable, provenance-tagged envelopes. The graph itself is not last-write-wins replicated.

## Security boundaries

The local runtime never enables raw shell execution. Serena edit tools, memory tools and generic shell tools are rejected by the allowlist. Device credentials are stored locally and their hash only is stored in cloud SQLite. Revoke a device by invalidating its credential in a future dashboard action; do not share a device token.

## Local Graphiti profile

Graphiti is optional at initial pairing, but it is the local temporal-memory layer once enabled. Start the local graph database on the PC only:

```bash
cd local-runtime
printf 'NEO4J_PASSWORD=<choose-a-long-local-password>\n' > .env
docker compose -f compose.graphiti.yml up -d
```

Both Neo4j ports bind to `127.0.0.1`; they must not be published to the Internet. Install the optional runtime dependency with `pip install -e '.[graphiti]'` and configure a compatible Graphiti client using the local Bolt endpoint. The local memory bridge creates immutable episode envelopes containing a project group ID, source run, source commit and occurrence time. Those envelopes enter the same durable outbox as notes and tasks.

When the PC reconnects, the cloud accepts each episode ID once and sends any cloud-originated episode envelopes that the PC missed. The graph database remains a local derived index: it can be rebuilt by replaying authorized envelopes, while cloud SQLite remains the authority for identity, permissions and synchronization cursors.
