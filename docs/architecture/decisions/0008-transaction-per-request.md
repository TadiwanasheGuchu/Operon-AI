# 0008 — One database transaction per request

**Status:** Accepted (2026-11-13)

**Context.** Multi-step operations (create an organisation with roles, owner membership and audit
events) must apply completely or not at all. Row-level-security context is set with `SET LOCAL`,
which only lives for one transaction.

**Decision.** The request's database session opens one transaction, committed after the handler
returns and **before** the response is sent (`Depends(..., scope="function")`); any exception rolls
it back. Services flush but never commit. Audit records for failures and denials, which must
survive that rollback, are written by `audit.record_independent` in their own transaction.

**Consequences.** Handlers can't half-apply changes, and a failed commit produces an error
response, not a false success. Long-running or external work must move to background workflows
(Temporal, Phase 3) rather than hold a request transaction open.
