# 0003 — Introduce Temporal in Phase 3

**Status:** Accepted (2026-11-13). Deviates from CLAUDE.md §15, which places it in Phase 5.

**Context.** Integration syncs need schedules, retries, timeouts and history, the same guarantees
as business workflows.

**Decision.** Add Temporal (server + workers) in Phase 3 and use it for integration syncs, detection
runs and, from Phase 5, approval workflows. Redis is not used as a job queue.

**Consequences.** One durable execution model instead of two. Local stack gains a Temporal service
in Phase 3.
