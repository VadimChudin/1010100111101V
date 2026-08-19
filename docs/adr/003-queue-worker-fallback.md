# ADR 003: Redis queue with immediate delivery fallback

**Status:** Accepted

## Context

The initial queued-run implementation used a Redis-backed queue and a worker started from the FastAPI application lifecycle. Production verification showed that a submitted run could remain in `queued` state when no consumer claim was observed promptly. For the free-tier, single-service Railway MVP, leaving a user-visible run pending indefinitely is worse than accepting a short-lived in-process execution path.

## Decision

A queued run is written durably to SQLite first and is then published to the Redis queue. The API additionally starts a bounded in-process delivery attempt using the same `RunWorker`. Both paths call an atomic `claim_run` transition from `queued` to `running`; only one can execute the run. The non-winning delivery attempt exits without side effects.

Redis remains the cross-process hand-off mechanism, while SQLite remains the authoritative source for run state and timeline events. This design preserves the asynchronous REST/SSE contract and avoids raw background execution that has not passed the policy layer.

## Consequences

The MVP gains reliable prompt execution in the current single-service deployment and still retains a queue hand-off path for a future dedicated worker. It does not yet provide full at-least-once recovery for a process that dies after claiming a run. A future production-hardening phase should add leases, heartbeats, stale-run recovery, and a separately deployed worker service.
