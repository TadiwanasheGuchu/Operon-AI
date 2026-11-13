# 0005 — Single repository with pnpm and uv workspaces

**Status:** Accepted (2026-11-13)

**Decision.** One repository: `apps/web` (pnpm workspace), `apps/api` (uv project), shared
`packages/` (the generated TypeScript API client arrives with the first real API contract),
`infrastructure/`, `docs/`. Root Makefile and CI run both.

**Consequences.** API and UI changes land in one pull request; CI runs both pipelines on every
change.
