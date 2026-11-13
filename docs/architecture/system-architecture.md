# Operon AI — System Architecture

| | |
|---|---|
| Status | **Accepted** (decisions D1–D6 recorded as ADRs 0001–0006) |
| Date | 2026-11-13 |
| Scope | MVP (Phases 0–7 of `CLAUDE.md` §15) |
| Related | `docs/product/mvp-implementation-plan.md`, `docs/architecture/decisions/` |

This document describes how Operon AI is built for the MVP: what the components are, which component owns what, and where the security boundaries sit. Decisions that need product-owner sign-off are collected in [§13 Decisions requiring review](#13-decisions-requiring-review).

---

## 1. Architectural style

**Modular monolith + separately deployed workers.**

- One FastAPI application (`apps/api`) holds all domain modules. Modules talk to each other through explicit service interfaces, not through each other's tables.
- One Next.js application (`apps/web`) is the only user interface.
- Background and long-running work runs in **Temporal workers** (`workers/*`). They share the domain code with the API (they are a separate *process*, not a separate *codebase*).
- One PostgreSQL database is the system of record.

Why not microservices: one team, one release train, and the main risk is getting tenancy, permissions and workflow durability right. A monolith with enforced module boundaries keeps those guarantees in one place. Modules can be split out later if they need to scale independently, because they already communicate through interfaces.

---

## 2. Component architecture

```
                         ┌──────────────────────────────────────────┐
  Browser ──HTTPS──▶     │ apps/web  (Next.js, App Router)          │
                         │  • UI, routing, forms, client caching    │
                         │  • /api/* proxied same-origin to API     │
                         └───────────────┬──────────────────────────┘
                                         │ HTTPS (cookie session)
  External systems ──webhooks──▶ ┌───────▼──────────────────────────────────────────┐
  (Odoo, Shopify, …)             │ apps/api  (FastAPI modular monolith)             │
                                 │                                                  │
                                 │  identity · organisations · permissions · audit  │
                                 │  dashboard · integrations · intelligence         │
                                 │  workflows · incidents · agents · knowledge      │
                                 │  notifications                                   │
                                 └──┬──────────────┬───────────────┬────────────────┘
                                    │ SQL          │ gRPC          │ cache / rate limits
                              ┌─────▼─────┐  ┌─────▼──────┐  ┌─────▼─────┐
                              │PostgreSQL │  │ Temporal   │  │  Redis    │
                              │ (+RLS,    │  │ server     │  └───────────┘
                              │  pgvector │  └─────▲──────┘
                              │  later)   │        │ task queues
                              └─────▲─────┘  ┌─────┴───────────────────────────────┐
                                    │        │ workers/                            │
                                    └────────│  integrations  (sync, webhooks)     │
                                             │  intelligence  (detection, AI)      │
                                             │  workflows     (approval processes) │
                                             │  notifications (email, in-app)      │
                                             └──────────┬──────────────────────────┘
                                                        │ HTTPS (outbound only)
                                              External APIs · LLM providers · SMTP
```

| Component | Technology | Responsibility | Deployed as |
|---|---|---|---|
| Web app | Next.js 15, React, TypeScript, Tailwind, shadcn/ui, TanStack Query, RHF + Zod | All user interface | Container (Node) |
| API | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic | Authentication, authorisation, domain logic, REST API, webhook intake | Container (uvicorn) |
| Workers | Temporal Python SDK, same domain packages as the API | Durable background work: syncs, detection runs, approval workflows, notifications | Containers, one per task queue |
| Database | PostgreSQL 16 | System of record; tenant isolation backstop (RLS); later pgvector | Managed Postgres in production |
| Orchestrator | Temporal | Durable execution, retries, timers, schedules, history | Temporal Cloud or self-hosted |
| Cache | Redis 7 | Rate limiting, short-lived caches, login throttling. **Never** the only copy of business state. | Managed Redis |
| Object storage | S3-compatible (MinIO locally) | Uploaded documents (Phase 6+) | Managed |

---

## 3. Frontend / backend responsibilities

The rule: **the backend is the only place where a decision is made; the frontend only presents and collects.**

| Concern | Frontend (`apps/web`) | Backend (`apps/api`) |
|---|---|---|
| Authentication | Login/registration forms, MFA prompt | Password hashing, session issue/revoke, MFA verification, lockout |
| Authorisation | Hides actions the user can't take (UX only) | **Enforces** every permission on every request |
| Tenant context | Sends the selected organisation | Verifies membership, builds tenant context, scopes every query |
| Validation | Zod schemas for instant feedback | Pydantic schemas are authoritative |
| Business rules | None | Thresholds, calculations, approval policies, anomaly rules |
| AI | Renders insights, evidence, citations | Calls models, validates output, stores provenance |
| Integration credentials | Write-only form fields; never displayed or returned | Encrypts, stores, uses |
| Data shape | Generated TypeScript client from OpenAPI (`packages/api-client`) | Pydantic → OpenAPI is the single contract |

### Frontend structure

```
apps/web/src/
  app/                     # routes only: layout, loading, error, page files
    (auth)/login, register, verify, reset
    (app)/[orgSlug]/overview, intelligence, workflows, incidents, integrations, admin
  components/ui/           # shadcn primitives (owned, themed with tokens)
  components/<domain>/     # presentational components per domain
  features/<domain>/       # hooks (TanStack Query), form schemas, mappers
  lib/api/                 # generated client + fetch wrapper (cookies, CSRF, errors)
  styles/tokens.css        # design tokens from CLAUDE.md §11
```

- Pages compose feature hooks and presentational components; components never call `fetch` directly.
- Navigation entries are generated from a module registry gated by (a) the module being implemented and (b) the user's permissions. Unimplemented modules don't appear.
- Every data view has explicit loading, empty, error and **data-provenance** states (`Live`, `Demo`, `Stale since …`, `Unavailable`).

### API request path

Browser → Next.js same-origin `/api/*` rewrite → FastAPI. One origin means cookies stay `SameSite=Lax`/`HttpOnly` and no CORS surface in production. Server components forward the session cookie when fetching on the server.

---

## 4. Backend module structure

```
apps/api/src/operon/
  main.py                  # app factory, middleware, router registration
  core/                    # config, db session, logging, telemetry, errors, security primitives
  tenancy/                 # TenantContext, dependency, RLS session hook
  modules/
    identity/              # users, credentials, sessions, MFA, verification, reset
    organisations/         # organisations, memberships, invitations
    permissions/           # roles, permissions, policy checks
    audit/                 # append-only audit log
    dashboard/             # read models / aggregates for the command centre
    integrations/          # catalogue, connections, credentials, sync, webhooks, adapters/
    intelligence/          # metrics, detectors, insights, evidence, AI explanations
    incidents/             # incidents, assignments, comments, events
    workflows/             # definitions, versions, executions, approvals (Temporal client)
    agents/                # agent definitions, tool registry, executions (Phase 6)
    knowledge/             # documents, chunks, retrieval (post-MVP core)
    notifications/
  workers/                 # Temporal worker entrypoints, one per task queue
```

Each module has the same internal layout:

```
<module>/
  api.py         # FastAPI router: parse → call service → map response. No queries, no rules.
  schemas.py     # Pydantic request/response models
  service.py     # business logic, transactions, permission checks, audit events
  repository.py  # SQLAlchemy queries; every method takes a TenantContext
  models.py      # SQLAlchemy ORM models
  events.py      # domain events this module publishes
  public.py      # the ONLY things other modules may import
```

**Boundary enforcement:** `import-linter` contracts in CI forbid importing another module's `models`, `repository` or `service` directly — only its `public` interface. This keeps the monolith splittable and avoids circular dependencies.

**Cross-module side effects** (e.g. "insight created → notify owner → write audit") go through a **transactional outbox**: the domain change and an `outbox_events` row commit in the same transaction; a relay dispatches them to handlers/Temporal. No event is lost if a process crashes between commit and dispatch.

---

## 5. Database strategy

- **PostgreSQL 16**, one database, one schema (`public`) for the MVP; `pgvector` extension enabled when the Knowledge Centre arrives.
- **SQLAlchemy 2.0** (async, `asyncpg`) for the API; **Alembic** for every schema change. Migrations run as a separate deploy step, never on app start in production. Each migration must be reversible or document why not.
- **Keys:** UUIDv7 primary keys (time-ordered → good index locality, safe to expose, no enumeration).
- **Timestamps:** `created_at`, `updated_at` as `timestamptz`, UTC everywhere.
- **Tenant ownership:** every tenant-owned table has `organisation_id uuid not null` with an index leading on it. Child tables reference parents through **composite foreign keys** `(organisation_id, parent_id)` so a row can never point at another tenant's parent.
- **Money and quantities:** `numeric` with explicit scale — never floats.
- **Soft delete:** only where history matters (users, integrations, workflows). Audit and execution history are append-only and never deleted by the application.
- **Database roles:**
  - `operon_owner` — owns the schema, runs migrations.
  - `operon_app` — used by API and workers; DML only; **no `BYPASSRLS`**; no `UPDATE`/`DELETE` on `audit_logs`.
  - `operon_readonly` — reporting/support, also subject to RLS.
- **Operational data model** (inventory/procurement) is normalised into Operon's own canonical tables (`products`, `stock_levels`, `sales_daily`, `purchase_orders`, `suppliers`) with `source_integration_id` + `external_id` (unique per tenant) so syncs are idempotent upserts and every value is traceable to its source.

---

## 6. Authentication approach

### Recommendation (requires sign-off — see §13, D1)

**First-party authentication in the `identity` module for the MVP, built behind an `IdentityProvider` boundary so enterprise OIDC/SAML (Keycloak, Entra ID, Okta, or a broker such as WorkOS) can be added in Phase 7 without touching authorisation code.**

Reasoning:

- Operon must own **authorisation** (organisations, memberships, roles, permissions) regardless of IdP, so an external IdP only replaces the credential-checking part.
- Keycloak adds a JVM service, its own database, realm configuration and theming work before Phase 1 can deliver anything, and its organisation model would have to be kept in sync with ours.
- A managed provider (Auth0/Clerk/WorkOS) is a reasonable alternative and moves password/MFA risk off us, at a per-MAU cost and a data-residency question. If you prefer that, only `identity` changes.

### Mechanics

| Feature | Implementation |
|---|---|
| Password hashing | Argon2id (`argon2-cffi`), parameters tuned per environment; breached-password check (k-anonymity HIBP API, optional) and minimum length 12 |
| Sessions | Opaque random 256-bit token in an `HttpOnly; Secure; SameSite=Lax` cookie. Only a SHA-256 hash is stored in `user_sessions`. Idle timeout (e.g. 30 min) + absolute lifetime (e.g. 12 h). Server-side revocation (logout, password change, admin action). |
| CSRF | `SameSite=Lax` + double-submit token header on state-changing requests |
| Email verification / password reset | Single-use, hashed, short-lived tokens; responses never reveal whether an email exists |
| MFA | TOTP (RFC 6238) with recovery codes; WebAuthn later. Organisation policy can require MFA for all members. |
| Brute force | Per-account and per-IP throttling in Redis; progressive delays; audit events for failures |
| API access for machines | Per-organisation API keys (hashed, scoped, expirable) — Phase 3, for inbound integrations |
| Future SSO | OIDC/SAML login method mapping an external subject to a `users` row; JIT membership via verified domain; SCIM later |

Why opaque sessions instead of JWTs: immediate revocation, nothing sensitive in the browser, and no key-rotation story needed for the MVP. Workers authenticate to Temporal with mTLS, not user tokens.

---

## 7. Multi-tenancy strategy

**Model:** shared database, shared schema, `organisation_id` on every tenant-owned row, with three independent layers of enforcement.

### Layer 1 — Request context (application)

1. Session middleware resolves the **user** from the cookie.
2. The client names the organisation it wants (`X-Operon-Organisation: <org_id>` header, set by the web app from the `[orgSlug]` route).
3. The `require_tenant` dependency loads the user's **active membership** in that organisation. No membership → `404` (not `403`, to avoid confirming existence).
4. A frozen `TenantContext(organisation_id, user_id, membership_id, permissions)` is created. **The organisation ID used for data access always comes from this context, never from a request body or query parameter.**

### Layer 2 — Repository (application)

- Every repository method takes `TenantContext` as a required argument and adds `organisation_id = ctx.organisation_id` to every query and insert.
- A test sweep asserts every ORM model with an `organisation_id` column is only accessed through tenant-scoped repositories.

### Layer 3 — Row-level security (database backstop)

- RLS is enabled and **forced** on every tenant-owned table:
  ```sql
  ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
  ALTER TABLE incidents FORCE ROW LEVEL SECURITY;
  CREATE POLICY tenant_isolation ON incidents
    USING (organisation_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (organisation_id = current_setting('app.current_org_id')::uuid);
  ```
- At the start of each tenant-scoped transaction the session runs `SET LOCAL app.current_org_id = '<id>'` (transaction-scoped, so pooled connections cannot leak context).
- If the setting is missing, `current_setting` raises an error → queries **fail closed**.
- Cross-tenant system jobs (e.g. scheduler fan-out) use a separate, explicitly named code path that enumerates organisations and then opens one tenant-scoped transaction per organisation.

### Testing

The critical acceptance test (CLAUDE.md §14) is implemented as a parametrised suite: for **every** tenant-scoped endpoint, a user of Org A attempts read/update/delete of Org B's resource by ID, by manipulated header, and by body fields — all must return `404` and touch nothing. A second suite bypasses the app layer and confirms RLS alone blocks cross-tenant reads.

### Future isolation tiers

Because all access flows through `TenantContext`, a large customer can later be moved to a **dedicated database** (connection routing by organisation) without code changes in modules.

---

## 8. Authorisation (RBAC)

- **Permissions** are fixed strings defined in code (`incidents.read`, `incidents.manage`, `workflows.approve`, `integrations.manage`, `members.manage`, …).
- **Roles** are per-organisation bundles of permissions. System roles seeded on organisation creation: `Owner`, `Administrator`, `Operations Manager`, `Approver`, `Analyst`, `Viewer`. Custom roles post-MVP.
- Checks happen in the **service layer** (`authorise(ctx, "workflows.approve", resource)`), not just route decorators, so workers and agents go through the same checks.
- **Approval policies** are data (e.g. "purchase requests above 10,000 need `Finance Manager` approval"), evaluated by deterministic code.
- **Separation of duties:** the requester of an action cannot approve it, enforced in code.
- Every permission-sensitive decision (grant, deny on sensitive action, role change) writes an audit event.

---

## 9. Background processing

| Kind of work | Mechanism | Examples |
|---|---|---|
| Durable, multi-step, may wait for humans | **Temporal workflow** | Purchase-request approval, replenishment process |
| Scheduled / periodic | **Temporal schedule** → workflow | Integration sync every 15 min, nightly detection run |
| Event-driven from external systems | Webhook endpoint → verify signature → store `integration_events` row (idempotency key) → start/signal Temporal workflow | Odoo stock move, Shopify order |
| Cross-module domain events | Transactional outbox → relay → handler or Temporal | Insight created → notify owner |
| Short-lived coordination | Redis | Rate limits, login throttles, cache |
| High-throughput streams | Kafka/Redpanda — **not in MVP**; introduce when event volume justifies | — |

**Deviation to approve (§13, D3):** `CLAUDE.md` introduces Temporal in Phase 5. This proposal brings it in during **Phase 3** for integration syncs, because syncs need retries, schedules and history too. The alternative is a second, hand-built job system that would be thrown away in Phase 5.

### Reliability rules for all background work

- Activities are **idempotent** (natural keys / idempotency keys; upserts by `(organisation_id, source_integration_id, external_id)`).
- Every activity has an explicit start-to-close timeout and retry policy; non-retryable errors (validation, auth revoked) are classified.
- Workflow inputs carry `organisation_id`; activities open a tenant-scoped DB transaction from it (RLS applies to workers too).
- Execution state is mirrored into `workflow_executions` / `workflow_execution_events` for UI and audit; Temporal history remains the source of truth for replay.
- Failed syncs mark the connection `degraded`, raise a notification and **never** partially overwrite canonical data (each sync batch is committed atomically per entity page).

---

## 10. AI architecture

### Principle: deterministic core, AI on the edge

```
Canonical data ─▶ Detectors (deterministic code) ─▶ Finding + Evidence ─▶ Explanation (LLM, optional) ─▶ Insight
                                                         │                       │
                                                         │                       └─ validated structured output,
                                                         │                          provenance stored
                                                         └─ calculations, thresholds, recommended quantity
                                                            are computed in code, never by the model
```

- **Detection** is rule-based and statistical code (e.g. projected stockout). Results are reproducible and testable.
- **Evidence** is a structured bundle saved with the insight: source records (with integration + external ID), the calculation inputs and outputs, the rule version.
- **Explanation** — the LLM receives *only* the evidence bundle and returns a structured object: `{summary, why_it_matters, recommended_action, assumptions, limitations, evidence_refs[]}`. Output is validated with Pydantic; every `evidence_ref` must exist in the bundle, and numbers quoted must match evidence values. Invalid → retry once → fall back to a deterministic template explanation, flagged as such.
- **Recommendation** is produced by code (e.g. reorder quantity); the model may phrase it, not change it.

### Provider abstraction

```python
class LLMProvider(Protocol):
    async def generate_structured(self, *, task: str, messages: list[Message],
                                  schema: type[BaseModel], limits: CallLimits) -> LLMResult: ...
```

- Adapters: OpenAI first (per `CLAUDE.md`), a second provider (e.g. Anthropic) to prove the abstraction. Selection by configuration per task; organisations may disable AI entirely.
- Every call records an `ai_generations` row: provider, model, prompt template version, input hash, token counts, cost estimate, latency, validation result, and the insight/agent run it belongs to.
- Per-organisation token and cost budgets enforced before calls.
- Tracing via OpenTelemetry spans (GenAI semantic conventions).

### Assistant and agents (Phase 6)

- **One agent first:** an *Inventory Replenishment Agent* scoped to the MVP scenario.
- Agents run as Temporal workflows (durable, time-limited, auditable). LangGraph is adopted only if the agent's control flow becomes graph-shaped enough to justify it.
- **Tools** are typed Python functions registered in a tool registry with: required permission, `read`/`write` classification, `requires_approval` flag, rate limit. An agent's allowlist is stored in `agent_tool_permissions`.
- An agent acts **as a service principal bound to the organisation, with permissions no wider than the human who invoked it** (intersection of agent allowlist and user permissions).
- Write tools never execute directly; they create an **approval request** that a human with the right permission must approve. Approval is enforced in the workflow engine, not the prompt.
- **Prompt-injection defence:** all data from integrations and documents is placed in clearly delimited data sections and treated as untrusted; system policy is not overridable by content; tools validate arguments against schemas and tenant context regardless of what the model asks for; the model never sees credentials.
- **Knowledge retrieval** (RAG, pgvector) filters chunks by `organisation_id` **and** document permissions *before* similarity ranking, and answers cite source chunks.

---

## 11. Integration architecture

### Building blocks

| Piece | Purpose |
|---|---|
| **Connector catalogue** (code) | Each connector is a Python package implementing a `Connector` interface: `capabilities`, `auth_type`, `test_connection()`, `sync(entity, cursor)`, `handle_webhook()`, and optional `actions` (e.g. `create_purchase_request`). |
| `integrations` / `integration_connections` | A tenant's configured instance of a connector, status (`pending`, `active`, `degraded`, `disconnected`), last successful sync, health. |
| `integration_credentials` | Encrypted secrets (see below). Never returned by any API. |
| `integration_sync_jobs` | One row per sync run: entity, cursor before/after, counts, errors. Mirrors the Temporal workflow. |
| `integration_events` | Inbound webhook events, stored raw with an idempotency key (unique per connection) before processing. |
| Transformers | Map external payloads → canonical models via Pydantic, with validation errors recorded, not swallowed. |

### Credential security

- **Envelope encryption**: each secret is encrypted with AES-256-GCM using a per-record data key; data keys are wrapped by a key-encryption key from a KMS (AWS KMS / GCP KMS / Vault Transit) in production, or from an environment variable locally. Key version stored to allow rotation.
- Decryption happens only inside the worker activity that needs it; plaintext never logged, never sent to the frontend or to an LLM.
- OAuth 2.0 tokens: authorisation-code flow handled server-side with `state` + PKCE; refresh handled by workers.

### Inbound webhooks

`POST /api/v1/webhooks/{connection_public_id}` → verify HMAC signature/timestamp (connector-specific) → reject replays → insert `integration_events` (unique idempotency key) → `202 Accepted` → process asynchronously. The endpoint does no business processing inline.

### Initial connectors (requires sign-off — §13, D2)

Proposal: **Odoo** (inventory, sales, purchasing — covers the whole demo scenario, including writing back a purchase request; open source, so it can run locally against real APIs) and **Shopify** (sales/order signals and inventory levels). Both have real sandboxes, so nothing is faked. A generic **CSV upload / REST push** ingestion path is also provided for customers whose systems have no connector yet.

---

## 12. Security boundaries

```
 ┌─────────────── Untrusted ───────────────┐
 │ Browser · webhook senders · external API│
 │ responses · uploaded documents · LLM    │
 │ outputs                                 │
 └───────────────────┬─────────────────────┘
          (B1) TLS, auth, CSRF, rate limits, schema validation, signature checks
 ┌───────────────────▼─────────────────────┐
 │ API process                             │
 │  (B2) TenantContext + permission checks │
 │  (B3) Approval policy for sensitive ops │
 └───────────────────┬─────────────────────┘
          (B4) DB role without BYPASSRLS + RLS policies
 ┌───────────────────▼─────────────────────┐
 │ PostgreSQL                              │
 └─────────────────────────────────────────┘
          (B5) Secrets: KMS-wrapped keys, decrypted only in worker activities
          (B6) LLM boundary: evidence-only context, structured output validation,
               tool allowlists, no credentials, no direct write access
```

| Boundary | Threats addressed | Controls |
|---|---|---|
| B1 Edge | Credential stuffing, CSRF, injection, forged webhooks, abuse | HTTPS/HSTS, secure cookies, CSRF tokens, Pydantic validation, HMAC verification, Redis rate limits, request size limits, security headers/CSP |
| B2 Tenant & permission | Cross-tenant access, privilege escalation, IDOR | Membership-derived TenantContext, service-layer authorisation, 404 on foreign IDs, composite FKs |
| B3 Sensitive actions | AI or users executing high-impact actions without control | Configurable approval policies, separation of duties, approvals enforced in Temporal workflows |
| B4 Database | Application bug leaking data | RLS (forced), least-privilege roles, append-only audit table |
| B5 Secrets | Credential leakage | Envelope encryption, write-only APIs, secret scanning in CI, `.env` never committed |
| B6 AI | Prompt injection, hallucinated facts, unbounded cost | Untrusted-data framing, output validation against evidence, tool allowlists, approval gates, token/cost budgets, full generation logging |

### Audit

`audit_logs` is append-only (application role has `INSERT`/`SELECT` only): actor (user / agent / system), organisation, action, target, before/after summary (no secrets), request ID, IP, user agent, timestamp. Written in the same transaction as the change it describes.

### Observability

- Structured JSON logs (`structlog`) with `request_id`, `organisation_id`, `user_id`, `workflow_id`; secrets redacted by a log processor.
- OpenTelemetry traces across web → API → DB → Temporal → external calls; metrics for latency, error rate, sync freshness, workflow outcomes, LLM cost.
- Health endpoints: `/health/live` (process up), `/health/ready` (DB, Redis, Temporal reachable). Workers expose equivalent readiness.

---

## 13. Decisions requiring review

| ID | Decision | Proposal | Alternatives |
|---|---|---|---|
| **D1** | Identity provider | First-party auth in `identity` (Argon2id, opaque sessions, TOTP MFA) behind an IdP boundary; OIDC/SAML SSO in Phase 7 | Keycloak from day one; managed (WorkOS, Auth0, Clerk) |
| **D2** | First two integrations | Odoo + Shopify (+ generic CSV/REST ingestion) | Customer-driven choice, e.g. NetSuite, SAP Business One, QuickBooks, Sage, Dynamics 365 BC |
| **D3** | When Temporal arrives | Phase 3 (integration syncs) rather than Phase 5 | Phase 5, with a temporary job table in Phase 3 |
| **D4** | Tenant selection on requests | `X-Operon-Organisation` header, validated against membership; org slug in UI URLs | Org ID in API path (`/api/v1/organisations/{id}/…`) |
| **D5** | Repository layout | pnpm workspaces (JS) + uv workspace (Python) in one repo, as in `CLAUDE.md` §7 | Separate repos for web and API |
| **D6** | First LLM providers | OpenAI + one second provider behind `LLMProvider` | Single provider initially |

Decisions approved here are recorded as ADRs in `docs/architecture/decisions/`.
