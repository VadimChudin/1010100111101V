# ADR 004: Serena is a staged, read-only provider

**Status:** Accepted

## Context

The workspace needs symbol overview, symbol lookup, and reference lookup without exposing semantic editing to the agent. Serena is available as a disabled MCP connector in the current environment. Enabling or modifying a user connector requires an explicit confirmation, which is intentionally not bypassed.

## Decision

The platform exposes a typed `SerenaClient` read-only provider contract covering `get_symbols_overview`, `find_symbol`, and `find_referencing_symbols`. Its public status endpoint reports availability and never exposes any of Serena's editing, refactoring, memory-writing, or shell tools. The Tool Gateway remains restricted to the P0 typed catalog.

The production runtime does not spawn an MCP CLI process from the API service. A real Serena transport must be injected by a dedicated, isolated MCP-aware worker only after the connector is explicitly enabled. This keeps tool permissions and workspace isolation enforceable at the gateway boundary.

## Consequences

The frontend and API can discover read-only Serena readiness now, while semantic code inspection remains safely unavailable until the connector approval and isolated worker deployment are complete. This is deliberate feature gating rather than a silent fallback to unsafe local execution.
