# 0004 — Tenant selection via request header

**Status:** Accepted (2026-11-13)

**Decision.** Tenant-scoped requests carry `X-Operon-Organisation: <org_id>`. The backend verifies
active membership for the session user and builds a `TenantContext`; unknown or foreign
organisations return 404. URLs in the web app use the organisation slug. Organisation IDs in
bodies or query strings are never used for data access. PostgreSQL RLS (`app.current_org_id`,
forced) is the backstop.

**Consequences.** API paths stay as in CLAUDE.md §12 (`/api/v1/incidents/…`). Every tenant route is
covered by the cross-tenant test suite.

## Implementation note (Phase 1)

Implemented as described, with one deferral: web URLs don't carry the organisation slug yet.
The active organisation is a per-browser preference (localStorage) that the web app sends as the
header. Tampering with it is harmless: the API re-checks membership on every request, and the web
app falls back to a real membership when the stored value is unknown (verified end to end).
Slug URLs remain the target once deep links to organisation records exist (Phase 4).
