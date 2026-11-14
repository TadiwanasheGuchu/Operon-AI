# Operon AI — MVP Implementation Plan

| | |
|---|---|
| Status | **Accepted** (decisions D1–D6 recorded as ADRs 0001–0006) |
| Date | 2026-11-13 |
| Architecture | `docs/architecture/system-architecture.md` |
| Initial vertical | Distribution and light manufacturing |

---

## 1. MVP goal

Deliver one complete, real, end-to-end operational intelligence loop:

> **Inventory shortage → detection → explanation with evidence → recommended purchase request → human approval → purchase request created in the source system → tracked execution → full audit trail.**

Everything in the MVP exists to make that loop secure, multi-tenant, explainable and recoverable. Anything that doesn't serve it is post-MVP.

### In scope

1. Multi-tenant organisation management
2. User authentication (email/password, verification, reset, sessions, TOTP MFA)
3. Role-based access control
4. Operations dashboard (role-aware, with data provenance labels)
5. Integration management (catalogue, connections, encrypted credentials, health)
6. Two real external connectors (proposed: Odoo, Shopify) + CSV/REST ingestion
7. Inventory and procurement data monitoring
8. Rule-based anomaly detection (stockout risk first)
9. AI operational assistant (explanations + Q&A over the tenant's operational data)
10. Approval-based workflow automation (purchase-request workflow)
11. Incident and exception management
12. Audit logging

### Out of scope for the MVP

Visual workflow builder (MVP ships code-defined workflow templates with configurable parameters), Knowledge Centre / document RAG, more than one AI agent, custom roles, SSO/SCIM, Kafka, Kubernetes, reports module, mobile layouts beyond responsive.

---

## 2. Reference scenario — stockout risk

This is the primary acceptance demonstration. The calculation is deterministic and lives in code.

**Inputs (per product × location)** from canonical tables:

| Symbol | Meaning | Source |
|---|---|---|
| `on_hand` | Current stock | `stock_levels` |
| `inbound(t)` | Open PO quantity with expected receipt ≤ t | `purchase_orders`, `purchase_order_lines` |
| `d` | Average daily demand, trailing 28 days (configurable) | `sales_daily` |
| `σ` | Std. deviation of daily demand, same window | `sales_daily` |
| `L` | Supplier lead time in days | `supplier_products` / org default |
| `SS` | Safety stock = `z · σ · √L` (z from service level, default 95% → 1.65), or a configured fixed value | config |
| `ROP` | Reorder point = `d · L + SS` | computed |

**Rule `inventory.stockout_risk.v1`:**

- Projected position at lead time: `P = on_hand + inbound(today + L) − d · L`
- Trigger when `on_hand + inbound(today + L) ≤ ROP + d · review_period` (stock reaches the reorder point before the next review).
- Severity: `critical` if `P ≤ 0` (stockout before replenishment can arrive), `high` if `P < SS` (below the reorder point), `medium` otherwise (at, or within one review period of, the reorder point).
  *Correction (Phase 4):* the original trigger `≤ ROP` made `medium` reachable only when `P = SS` exactly, because `P ≤ SS` whenever the position is at or below ROP. The review-period band gives `medium` a meaning.
- Days of cover: `on_hand / d`; projected stockout date where applicable.
- **Recommended order quantity** (code, not AI): `max(MOQ, ceil_to_pack(ROP + d · review_period − on_hand − inbound(today + L)))`, priced from the last PO cost for the supplier.
- Suppressed (not re-raised) while an open insight or open purchase request already covers the product; re-evaluated on each sync.
- Insufficient history (< 14 days of sales) → insight marked `low confidence` with that limitation stated, never silently dropped.

**Flow:**

1. Odoo/Shopify sync (scheduled Temporal workflow) upserts stock, sales and open POs.
2. Detection workflow runs after each successful sync → creates `ai_insight` + `insight_evidence` rows.
3. Explanation activity calls the LLM with the evidence bundle → validated structured explanation (or template fallback).
4. Insight appears on the dashboard and in Intelligence; owner notified. High/critical insights can be escalated to an incident.
5. User clicks **Create purchase request** → `PurchaseRequestWorkflow` starts with the code-computed quantity (editable by the user, change recorded).
6. Workflow evaluates the approval policy (e.g. > 10,000 needs Finance Manager) and waits for approval (with timeout → escalation).
7. Approver approves (cannot be the requester). Approval and comment are audited.
8. Activity creates the purchase request in Odoo (idempotency key = workflow ID); external ID stored.
9. Workflow records completion; insight moves to `actioned`; next sync confirms the new inbound quantity and the insight resolves.
10. Execution history shows every step, actor, timestamp and external reference; failures are retryable from the UI by authorised users.

---

## Progress

| Phase | Status |
|---|---|
| 0 — Foundation | Done (Compose and CI written; not yet run in Docker/GitHub) |
| 1 — Identity, organisations, permissions, audit | Done: all acceptance criteria below verified by API tests and a browser journey |
| Design track | Shell, Command Centre, component states, auth and admin screens |
| 2 — Operations command centre | Done: dashboard API with per-section provenance, role-aware layouts, notifications, people search, demo organisations (ADR 0009) |
| 3 — Integration infrastructure | Done, with live verification pending (see below) |
| 4 — Intelligence and incidents | Done; Odoo-sourced live data and live AI providers not yet verified (see below) |
| 5 — Workflow automation | Done; live Odoo and the Temporal runtime not yet verified (see below) |
| 6 — AI assistant and first agent | Done with a scripted model; real-model evaluation pending a provider key |
| 7 — Enterprise readiness | Done in code; staging deploy, PITR drill on managed Postgres and an external penetration test need the hosting decision |

Phase 7 notes (ADR 0015):
- Built:
  - **Security review and threat model** (`docs/security/threat-model.md`). Fixed:
    - DNS rebinding SSRF (connect-time address pinning);
    - SSO login CSRF;
    - usage limits on costly actions;
    - a request body cap;
    - CSP and HSTS;
    - stale agent runs.
  - **OIDC single sign-on:** PKCE, nonce, DNS-verified domains, JIT provisioning, "require SSO"
    with an owner break-glass.
  - **Retention** per organisation, with database-enforced minimums, plus a ZIP export.
  - **OpenTelemetry** traces and metrics, and trace ids in logs.
  - **Recovery:** checksummed, verified logical backups and a restore drill.
  - **Load test script;** bulk ingest about 5× faster.
  - **Deployment:** GHCR release, a production compose file with Caddy TLS, `deploy.sh` with a
    health gate and automatic rollback, and a staging pipeline.
  - **Web:** SSO, retention and export settings; "Sign in with SSO".
  - **Guides:** onboarding (`docs/guides/onboarding.md`), administration, and operations runbooks
    (`docs/operations/`).
- Acceptance status:
  - **Documented restore within RPO/RTO:** targets RPO ≤ 5 min (PITR) and RTO ≤ 1 h. Logical
    restore drill passed: 397 MB restored and verified in 10 s. The PITR drill runs on the
    managed database once hosting is chosen.
  - **Zero high/critical findings open:** yes, by internal review (one high fixed). The external
    penetration test is still to do.
  - **Staging deploy is one command or pipeline:** `deploy.sh staging <sha>` and the
    `Deploy staging` workflow. They need a host and secrets; not yet run against a real host.
  - **Onboarding guide to first insights without engineering:** written against the actual
    screens and messages. Live Odoo still unverified (no sandbox).
  - **Load: 50 orgs × 10k SKUs:** measured at 3 × 10k; 50 is extrapolated (see
    `docs/operations/load-testing.md`).
- Deferred: cloud-specific IaC, KMS-wrapped keys, SCIM/SAML, CSP nonces, breached-password
  check.

Phase 6 notes (ADR 0014):
- Built:
  - The provider tool loop (Anthropic and OpenAI) and the controlled runner, enforcing the
    allowlist, input validation, step, tool, token and time limits, and the monthly budget, with
    a full step log.
  - Seven typed tools; only one writes, and it drafts a request for approval.
  - The assistant, with private conversations and answers checked against tool outputs.
  - The inventory replenishment agent: acts for a named member, has a permission ceiling and
    versioned settings, and runs daily or by hand.
  - The real-model evaluation script.
  - Web: the assistant drawer, the agents page (settings and run history) and the run log.
- Acceptance results:
  - Proven by tests with a scripted model: only allowlisted tools run; any write becomes an
    approval request; planted instructions can't widen what a model does, even when it obeys
    them; every run is reconstructable from its log (inputs, tool calls, outputs, model, tokens).
  - "Injected instructions do not change agent behaviour (eval passes)" for a real model needs a
    provider key: run `uv run python evals/run_agent_evals.py`.
- Deferred: LangGraph (not needed for one bounded loop), marking runs interrupted by a crash as
  stale (Phase 7), and per-organisation provider keys.

Phase 5 notes (ADR 0012):
- Built:
  - The workflow tables, with versioned policy parameters instead of an `approval_policies` table.
  - The `advance` state machine: approval deadlines (reminder, then expiry), Odoo draft-PO creation
    with an idempotency key and read-back, retries with backoff, and failure notifications.
  - A Temporal `PurchaseRequest` workflow; an inline runner and sweep for development.
  - The approval API and inbox, with separation of duties; cancel and retry.
  - Live approvals and workflow status on the dashboard.
  - Web pages: purchase requests (list and detail), the approvals inbox, the policy editor (with
    version history), and "Create purchase request" on insights.
- Acceptance results:
  - Verified by tests against the Odoo protocol test server: the full scenario, resuming after a
    crash without a duplicate PO, the requester unable to approve, nothing reaching Odoo unapproved,
    and rejection, expiry, transient and permanent failure, and retry all visible and audited.
  - A two-person browser journey passed on CSV data.
- Not yet verified: a real Odoo instance, and the Temporal worker path (the Temporal server can't
  be downloaded here). The plan's "kill the worker" check is covered at the `advance` level.

Phase 4 notes (ADR 0011):
- Built:
  - The detector framework, with per-organisation settings and versioned rules.
  - `inventory.stockout_risk.v1`, whose medium band was corrected (see §2), and `procurement.po_overdue.v1`.
  - Insights with their evidence, history and lifecycle; a link from each evidence item to its source record.
  - The `LLMProvider` layer with Anthropic and OpenAI adapters, the explanation validator, template fallback,
    monthly token budgets and `ai_generations` records.
  - Incidents with a timeline, assignment and escalation (Temporal schedule, or an in-process loop in dev).
  - A live dashboard: insights, incidents and stock risk.
  - Web pages: Intelligence (list, detail, settings) and Incidents (list, detail).
- Acceptance results:
  - Met: golden numbers, evidence traced to source records, the validator test, the template when AI is off,
    and overdue PO → incident → assignment. All are covered by API tests and a browser journey on CSV-imported
    data.
  - Not yet verified: "with live Odoo data" needs an Odoo instance, and real model calls need a provider key.
    Both adapters are tested with the SDK call replaced.
- Deferred: `operational_metrics` and `anomaly_events` (not needed by these detectors), and per-organisation
  provider keys.

Phase 3 notes:
- Built: connector framework, Odoo (JSON-2 + JSON-RPC) and Shopify (GraphQL) connectors, CSV
  import, canonical operational tables, encrypted credentials, sync engine with per-entity
  transactions and cursors, signed webhooks, Temporal workflow/schedules/worker, integrations UI.
- Verified here: everything except talking to live Odoo/Shopify and running on a Temporal server.
  Connectors are tested against protocol-level test servers; CSV import and the sync engine are
  exercised end to end.
- Pending: (1) live verification — needs an Odoo instance and a Shopify development store, plus
  their hosts allowed in the environment; (2) running the Temporal path — the dev server is in
  Docker Compose; this environment has no Docker and couldn't build the server from source.
- Deviations: catalogue lives in code (no `integrations` table); `purchase_requests` table moves
  to Phase 5 where it's used.

Phase 2 notes: insights, incidents, approvals, workflows, fill rate, stock risk and integrations
are reported as "unavailable" for real organisations until Phases 3–5 supply them; demo
organisations show labelled sample data for them. Notifications are written in the same
transaction as their event (the transactional outbox arrives with Temporal in Phase 3).

Phase 1 deviations: email/reset tokens share one `user_action_tokens` table (purpose column);
custom roles and slug URLs deferred (ADR 0004 note); notifications UI hidden until Phase 2.

## 3. Phases, tasks and acceptance criteria

Each phase ends with a demonstrable, tested increment. Acceptance criteria are the definition of done; all phases additionally require: tests, type checks and lint passing in CI, migrations applied cleanly up *and* down on an empty database, docs updated.

### Phase 0 — Project foundation

| # | Task |
|---|---|
| 0.1 | Monorepo layout (`apps/web`, `apps/api`, `workers/`, `packages/`, `infrastructure/`, `docs/`), pnpm + uv workspaces |
| 0.2 | `docker-compose.yml`: postgres 16, redis 7, api, web (Temporal added in Phase 3) |
| 0.3 | FastAPI app factory, settings (pydantic-settings), structured logging, request IDs, error envelope |
| 0.4 | SQLAlchemy async engine, Alembic configured, initial migration (DB roles, extensions, `system_events` placeholder) |
| 0.5 | Health checks: `/api/v1/health/live`, `/api/v1/health/ready` (DB + Redis) |
| 0.6 | Next.js app with Tailwind, design tokens, shadcn/ui setup, a status page reading API health |
| 0.7 | Tooling: ruff, mypy (strict), pytest + testcontainers/pg; ESLint, Prettier, tsc, Vitest, Playwright skeleton |
| 0.8 | CI pipeline (GitHub Actions): lint, type check, tests, migration up/down check, secret scan, dependency audit |
| 0.9 | `.env.example`, `README.md`, `docs/development.md` |

**Acceptance:** `docker compose up` brings up all services; readiness reports DB and Redis healthy; web shows API status; `make test` passes for both apps; CI green on a PR.

### Phase 1 — Identity, organisations, permissions, audit

| # | Task |
|---|---|
| 1.1 | `users`, `user_credentials`, `user_sessions`, `email_verification_tokens`, `password_reset_tokens`, `mfa_factors`, `recovery_codes` |
| 1.2 | Registration, verification, login, logout, session refresh, password reset, TOTP enrol/verify |
| 1.3 | `organisations`, `organisation_members`, `invitations`; create organisation on sign-up; invite/accept |
| 1.4 | `roles`, `permissions`, `role_permissions`; system role seeding; permission check service |
| 1.5 | `TenantContext` dependency, tenant-scoped repository base, RLS migration helper + policies |
| 1.6 | `audit_logs` (append-only) + audit service used by all modules |
| 1.7 | Rate limiting / lockout (Redis) on auth endpoints |
| 1.8 | Web: auth pages, organisation creation, member management, org switcher |
| 1.9 | Cross-tenant test harness (reusable for every later module) |

**Acceptance:**
- A user can register, verify email, log in, enable MFA, reset password and log out; sessions are revocable.
- An owner can create an organisation, invite a member, assign a role; the invitee accepts and sees only that organisation.
- A Viewer cannot perform any write; attempts return 403 and are audited.
- **Org A user cannot read, list, update or delete any Org B record by ID, header, or body manipulation (returns 404); RLS alone blocks it when application filtering is bypassed in tests.**
- Every auth and membership event appears in the audit log.

### Phase 2 — Operations command centre

| # | Task |
|---|---|
| 2.1 | App shell: sidebar (module registry, permission-gated), org switcher, global search (entities in implemented modules), notification centre, profile |
| 2.2 | Dashboard read API aggregating: health indicators, active insights, open incidents, pending approvals, workflow status, activity feed |
| 2.3 | Data provenance on every widget (`live`, `demo`, `stale`, `unavailable`) |
| 2.4 | Demo organisation seeding command (`is_demo = true` organisations only; banner shown) |
| 2.5 | Role-aware default layouts (Executive, Operations, Finance, Warehouse) |
| 2.6 | `notifications` table and in-app notification centre |

**Acceptance:** dashboard renders real data for a real org (empty states where nothing exists yet) and seeded data for a demo org with a visible "Demo data" label; no widget shows a value without a provenance label; nav shows only implemented modules the user is allowed to see.

### Phase 3 — Integration infrastructure

| # | Task |
|---|---|
| 3.1 | Temporal in compose; worker skeleton; Temporal client in API (decision D3) |
| 3.2 | Connector interface, catalogue, `integrations`, `integration_connections`, `integration_credentials` (envelope encryption), `integration_sync_jobs`, `integration_events` |
| 3.3 | Canonical operational tables: `locations`, `suppliers`, `products`, `supplier_products`, `stock_levels`, `sales_daily`, `purchase_orders`, `purchase_order_lines`, `purchase_requests` |
| 3.4 | Odoo connector: API-key auth, test connection, sync products/stock/sales/POs/suppliers, action `create_purchase_request` |
| 3.5 | Shopify connector: OAuth install flow, sync products/inventory levels/orders, webhooks (orders, inventory) with HMAC verification |
| 3.6 | Webhook intake endpoint, idempotent event store, async processing |
| 3.7 | CSV upload ingestion for stock/sales/POs with validation report |
| 3.8 | Scheduled sync workflows, health status, failure notifications |
| 3.9 | Web: integration catalogue, connect flows, connection detail (health, sync history, errors) |

**Acceptance:** a tenant connects a real Odoo instance and a real Shopify dev store; data appears in canonical tables with source references; re-running a sync produces no duplicates; a revoked credential marks the connection `degraded` and notifies admins without altering existing data; credentials are never present in any API response, log line or frontend bundle (tested); a forged webhook is rejected.

### Phase 4 — Intelligence and incidents

| # | Task |
|---|---|
| 4.1 | `operational_metrics` (derived daily metrics), `ai_insights`, `insight_evidence`, `anomaly_events`, `ai_generations` |
| 4.2 | Detector framework (versioned rules, per-org configuration of thresholds/service levels) |
| 4.3 | `inventory.stockout_risk.v1` detector (§2) + `procurement.po_overdue.v1` (expected receipt passed, not received) |
| 4.4 | `LLMProvider` abstraction, OpenAI adapter, second adapter; explanation activity with validation + template fallback; budgets |
| 4.5 | Insight lifecycle: `open → acknowledged → actioned → resolved / dismissed (with reason)`; owner assignment |
| 4.6 | Incidents: `incidents`, `incident_assignments`, `incident_comments`, `incident_events`; create from insight; severity, escalation rules (time-based via Temporal timer) |
| 4.7 | Web: Intelligence list/detail (evidence table with source links, explanation, assumptions, limitations), Incidents list/detail |

**Acceptance:** with seeded-but-realistic data in a test tenant **and** with live Odoo data, the detector raises the expected insight with correct numbers (golden tests); evidence links resolve to source records; explanation contains no numbers absent from evidence (validator test); with the LLM disabled the insight still appears with a template explanation; an overdue PO creates an insight that can be escalated to an incident and assigned.

### Phase 5 — Workflow automation

| # | Task |
|---|---|
| 5.1 | `workflows`, `workflow_versions`, `workflow_executions`, `workflow_approvals`, `workflow_execution_events`, `approval_policies` |
| 5.2 | `PurchaseRequestWorkflow` (Temporal): policy evaluation, approval wait with timeout + escalation, create in source system, confirm, complete |
| 5.3 | Approval API + inbox; separation of duties; approval comments |
| 5.4 | Execution monitoring: timeline, status, retry/cancel (permissioned), failure notifications |
| 5.5 | Workflow templates with configurable parameters (thresholds, approver roles, timeouts); versioning (running executions keep their version) |
| 5.6 | Web: workflows list, execution detail timeline, approvals inbox |

**Acceptance:** the full §2 scenario runs end-to-end against a real Odoo instance; killing the worker mid-execution and restarting resumes without duplicate purchase requests; the requester cannot approve their own request; an unapproved request never reaches Odoo; rejections, timeouts and external API failures are visible, retryable and audited.

### Phase 6 — AI assistant and first agent

| # | Task |
|---|---|
| 6.1 | Assistant: chat over the tenant's operational data through **read-only typed tools** (query insights, stock, POs, incidents) — no free-form SQL |
| 6.2 | Agent framework: `agents`, `agent_versions`, `agent_executions`, `agent_tool_permissions`; tool registry with permission/approval metadata |
| 6.3 | Inventory Replenishment Agent: reviews open stockout insights, drafts purchase requests (approval-gated), summarises daily |
| 6.4 | Limits: step count, wall time, token/cost budgets; full execution log |
| 6.5 | Evaluation suite: golden scenarios, structured-output validity, prompt-injection fixtures (malicious product names/notes from integrations) |
| 6.6 | Web: assistant panel with cited sources; agent configuration and run history |

**Acceptance:** the agent can only call allowlisted tools; any write produces an approval request rather than an action; injected instructions in synced data do not change agent behaviour (eval passes); every run is reconstructable from logs (inputs, tool calls, outputs, model metadata, cost).

### Phase 7 — Enterprise readiness

Security review and threat model update; penetration-test fixes; load testing (target: 50 orgs × 10k SKUs syncing on schedule); backup + point-in-time recovery drill; deployment automation (IaC, staging/prod); OpenTelemetry dashboards and alerts; SSO (OIDC) via the IdP boundary; admin & onboarding docs; data retention and export.

**Acceptance:** documented restore within agreed RPO/RTO; zero high/critical findings open; staging deploy is one command / pipeline; onboarding guide lets a new tenant connect Odoo and see first insights without engineering help.

---

## 4. Database entities by phase

| Phase | Tables |
|---|---|
| 0 | `system_events`, DB roles, extensions (`pgcrypto`, `citext`) |
| 1 | `users`, `user_credentials`, `user_sessions`, `email_verification_tokens`, `password_reset_tokens`, `mfa_factors`, `recovery_codes`, `organisations`, `organisation_members`, `invitations`, `roles`, `permissions`, `role_permissions`, `audit_logs`, `outbox_events` |
| 2 | `notifications`, `dashboard_layouts` |
| 3 | `integrations`, `integration_connections`, `integration_credentials`, `integration_sync_jobs`, `integration_events`, `api_keys`, `locations`, `suppliers`, `products`, `supplier_products`, `stock_levels`, `sales_daily`, `purchase_orders`, `purchase_order_lines`, `purchase_requests` |
| 4 | `operational_metrics`, `detector_configs`, `ai_insights`, `insight_evidence`, `anomaly_events`, `ai_generations`, `incidents`, `incident_assignments`, `incident_comments`, `incident_events` |
| 5 | `workflows`, `workflow_versions`, `workflow_executions`, `workflow_approvals`, `workflow_execution_events`, `approval_policies` |
| 6 | `agents`, `agent_versions`, `agent_executions`, `agent_tool_permissions`, `assistant_conversations`, `assistant_messages` |
| Post-MVP | `knowledge_documents`, `document_versions`, `document_chunks` (pgvector), `document_permissions` |

Conventions for every table: UUIDv7 PK, `created_at`/`updated_at` timestamptz; tenant-owned tables carry `organisation_id` (indexed, RLS-forced, composite FKs to parents); external records carry `source_integration_id` + `external_id` with a unique constraint per tenant.

Key constraints worth calling out:

- `organisation_members (organisation_id, user_id)` unique.
- `integration_events (connection_id, idempotency_key)` unique.
- `ai_insights` partial unique index on `(organisation_id, rule_id, subject_key) WHERE status IN ('open','acknowledged','actioned')` — prevents duplicate open insights.
- `workflow_approvals`: check constraint `approver_id <> requested_by`.
- `purchase_requests (organisation_id, idempotency_key)` unique.

---

## 5. API endpoints (MVP)

All under `/api/v1`. Tenant-scoped endpoints require a session and `X-Operon-Organisation`. Lists support `?limit&cursor` (cursor pagination), `?sort`, and documented filters. Errors use one envelope: `{ "error": { "code", "message", "details", "request_id" } }`.

**Health**
- `GET /health/live`, `GET /health/ready`

**Auth** (`/auth`)
- `POST /register`, `POST /verify-email`, `POST /login`, `POST /login/mfa`, `POST /logout`
- `POST /password/forgot`, `POST /password/reset`
- `GET /session`, `DELETE /sessions/{id}`, `GET /sessions`
- `POST /mfa/totp/enroll`, `POST /mfa/totp/confirm`, `DELETE /mfa/totp`

**Users** — `GET /users/me`, `PATCH /users/me`

**Organisations & members**
- `POST /organisations`, `GET /organisations` (mine), `GET /organisations/current`, `PATCH /organisations/current`
- `GET /members`, `PATCH /members/{id}` (role), `DELETE /members/{id}`
- `POST /invitations`, `GET /invitations`, `DELETE /invitations/{id}`, `POST /invitations/{token}/accept`
- `GET /roles`, `GET /permissions`

**Audit** — `GET /audit` (filter by actor, action, target, date)

**Dashboard** — `GET /dashboard/summary`, `GET /dashboard/activity`, `GET /dashboard/layout`, `PUT /dashboard/layout`

**Notifications** — `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/read-all`

**Integrations**
- `GET /integrations/catalogue`
- `GET /integrations`, `POST /integrations`, `GET /integrations/{id}`, `PATCH /integrations/{id}`, `DELETE /integrations/{id}`
- `PUT /integrations/{id}/credentials` (write-only), `POST /integrations/{id}/test`
- `GET /integrations/{id}/oauth/start`, `GET /integrations/oauth/callback`
- `POST /integrations/{id}/sync`, `GET /integrations/{id}/sync-jobs`, `GET /integrations/{id}/events`
- `POST /integrations/uploads` (CSV)
- `POST /webhooks/{connection_public_id}` (unauthenticated; signature-verified)

**Operational data (read)** — `GET /inventory/products`, `GET /inventory/products/{id}`, `GET /inventory/stock`, `GET /procurement/purchase-orders`, `GET /procurement/purchase-requests`, `GET /procurement/suppliers`

**Intelligence**
- `GET /intelligence/insights`, `GET /intelligence/insights/{id}` (includes evidence + explanation)
- `POST /intelligence/insights/{id}/acknowledge`, `/dismiss`, `/assign`
- `POST /intelligence/insights/{id}/escalate` (→ incident)
- `GET /intelligence/detectors`, `PATCH /intelligence/detectors/{id}` (thresholds)

**Incidents**
- `GET /incidents`, `POST /incidents`, `GET /incidents/{id}`, `PATCH /incidents/{id}`
- `POST /incidents/{id}/assign`, `POST /incidents/{id}/comments`, `GET /incidents/{id}/events`

**Workflows**
- `GET /workflows` (templates/definitions), `GET /workflows/{id}`, `PATCH /workflows/{id}` (parameters → new version)
- `POST /workflows/{id}/executions` (e.g. start purchase request from insight)
- `GET /workflow-executions`, `GET /workflow-executions/{id}`, `GET /workflow-executions/{id}/events`
- `POST /workflow-executions/{id}/retry`, `POST /workflow-executions/{id}/cancel`
- `GET /approvals` (my inbox), `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject`
- `GET /approval-policies`, `PUT /approval-policies/{id}`

**Assistant & agents** (Phase 6)
- `POST /assistant/conversations`, `POST /assistant/conversations/{id}/messages`, `GET /assistant/conversations/{id}`
- `GET /agents`, `PATCH /agents/{id}`, `POST /agents/{id}/runs`, `GET /agents/{id}/runs`, `GET /agent-runs/{id}`

---

## 6. Testing requirements

| Layer | Tooling | What must be covered |
|---|---|---|
| Backend unit | pytest | Services, permission checks, detectors (golden numeric cases incl. edge cases: zero demand, no history, negative stock, multiple POs), approval policy evaluation, transformers |
| Backend integration | pytest + real Postgres (testcontainers) + httpx | Every endpoint: auth required, permission required, validation errors, happy path |
| **Tenant isolation** | Parametrised suite over all tenant routes + direct-DB RLS suite | Org A → Org B by ID/header/body: always 404, no side effects; RLS blocks with app filter removed |
| Migrations | pytest | Upgrade from empty → head → downgrade → head; model/migration drift check |
| Workflows | Temporal test environment (time-skipping) | Approval path, rejection, timeout escalation, worker crash/replay, idempotent external call, retry exhaustion |
| Integrations | Recorded fixtures (VCR-style) + contract tests against real sandboxes in a nightly job | Pagination, cursors, rate limits, auth failure, malformed payloads, webhook signature verification, duplicate events |
| AI | pytest with fake provider + eval set with real provider (nightly) | Schema validity, evidence-number consistency, fallback behaviour, budget enforcement, prompt-injection fixtures, tool allowlist enforcement, approval enforcement |
| Frontend unit/component | Vitest + Testing Library | Forms (Zod validation, error display), provenance badges, permission-gated UI, empty/loading/error states |
| End-to-end | Playwright | Register → create org → invite; connect integration (stubbed external at E2E level); **full stockout → approval → PR scenario**; cross-tenant URL manipulation |
| Static | ruff, mypy --strict, import-linter, ESLint, tsc --noEmit | Zero errors in CI |
| Security | gitleaks, pip-audit, pnpm audit, Trivy (images) | No secrets, no high/critical vulnerabilities without an exception note |

Coverage target: ≥ 85% lines on `modules/*/service.py`, detectors and workflow code; coverage is a guide, the scenarios above are the requirement.

---

## 7. Dependencies between tasks

```
Phase 0 Foundation
   │
   ▼
Phase 1 Identity ──► 1.5 TenantContext/RLS ──► 1.9 Isolation harness ─────────────┐
   │                        │                                                     │ (every later
   ├──► 1.6 Audit ──────────┼─────────────────────────────────────────┐           │  module plugs in)
   ▼                        ▼                                         │           │
Phase 2 Shell & dashboard   Phase 3 Integrations                      │           │
   │  (empty states until   │  3.1 Temporal ─────────────────┐        │           │
   │   data exists)         │  3.3 Canonical tables          │        │           │
   │                        │  3.4 Odoo ──┐  3.5 Shopify     │        │           │
   │                        ▼             │                  │        │           │
   │                     Phase 4 Intelligence + Incidents    │        │           │
   │                        │  4.3 detectors ◄── 3.3         │        │           │
   │                        │  4.4 LLM layer (parallel)      │        │           │
   │                        ▼             │                  ▼        ▼           ▼
   │                     Phase 5 Workflows ◄── 3.4 Odoo write action, 3.1 Temporal
   │                        │
   └────────────────────────┤ dashboard widgets fill in as 3/4/5 land
                            ▼
                     Phase 6 Assistant + Agent (needs 4 insights, 5 approvals)
                            ▼
                     Phase 7 Enterprise readiness
```

**Can run in parallel:** Phase 2 UI shell alongside Phase 3 backend; LLM provider layer (4.4) alongside connectors (3.4/3.5); Shopify connector alongside Odoo once the connector interface (3.2) is stable.

**Critical path:** 0 → 1.5 → 3.1/3.2/3.3 → 3.4 (Odoo) → 4.3 → 5.2 → MVP demo.

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Tenant data leak | Three enforcement layers + mandatory isolation suite for every new route |
| Connector APIs vary per customer configuration (Odoo modules, versions) | Start with one supported Odoo version (17/18 Community); capability detection in `test_connection` |
| LLM produces wrong or invented facts | Numbers come from code; validator rejects unsupported numbers; template fallback |
| Workflow duplicates external writes | Idempotency key = workflow ID passed to external system; lookup-before-create |
| Scope creep toward all 7 modules | Phase acceptance criteria gate; out-of-scope list above |
| Owning auth code (if D1 accepted) | Well-reviewed libraries, focused tests, external review in Phase 7, IdP boundary allows swap |

---

## 9. Review questions

1. **D1 — Authentication:** first-party auth for MVP (recommended), Keycloak, or a managed provider?
2. **D2 — Integrations:** are Odoo and Shopify right for your first pilot customers, or do they run something else (NetSuite, SAP B1, Dynamics 365 BC, Sage, QuickBooks)?
3. **D3 — Temporal in Phase 3** instead of Phase 5?
4. **Hosting target** for staging/production (AWS / GCP / Azure / other)? This affects KMS, managed Postgres and Temporal Cloud vs self-hosted.
5. **Repository:** where should this code live on GitHub? The current workspace is not connected to a remote, so nothing is persisted beyond this session until it is pushed.
