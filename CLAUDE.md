# CLAUDE.md — Operon AI

> **Project:** Operon AI  
> **Product:** Autonomous Enterprise Operations Platform  
> **Category:** Enterprise SaaS / AI Operations / Business Process Intelligence  
> **Development approach:** Modular monolith, API-first, integration-driven  
> **Status:** Product foundation and MVP development

> Key project documents: `docs/architecture/system-architecture.md`, `docs/product/mvp-implementation-plan.md`, ADRs in `docs/architecture/decisions/`.

---

# 1. PROJECT OVERVIEW

## 1.1 What is Operon AI?

Operon AI is an intelligent enterprise operations platform designed to help organisations monitor, understand, manage and optimise their business operations through artificial intelligence, workflow automation and real-time operational intelligence.

The platform acts as an intelligent operational layer across an organisation, connecting disconnected departmental systems (Finance, HR, Procurement, Inventory, Warehousing, Logistics, Compliance, Management). It analyses information, identifies problems, recommends actions and executes approved workflows.

## 1.2 Product vision

Build an enterprise platform that becomes the central intelligence and coordination layer for business operations, so executives and operations teams can understand the condition of their entire organisation from one intelligent environment.

## 1.3 Product mission

Reduce operational inefficiencies, improve business visibility, eliminate repetitive administrative work and help organisations make faster, better-informed decisions.

## 1.4 Core capabilities

1. **Observe:** Collect and monitor operational information.
2. **Understand:** Analyse processes, performance and business context.
3. **Detect:** Identify anomalies, delays, risks and inefficiencies.
4. **Recommend:** Generate explainable, evidence-based recommendations.
5. **Execute:** Perform approved business actions through controlled automation.

## 1.5 Product positioning

Not simply an AI chatbot, reporting dashboard or workflow tool. An enterprise operational intelligence platform combining business process intelligence, AI-assisted decision support, workflow orchestration, enterprise integrations, exception management, controlled AI agents and operational analytics.

---

# 2. PRODUCT PRINCIPLES

1. **Enterprise first** — multiple departments, users, roles, processes and connected systems.
2. **Security by design** — authentication, authorisation, tenant isolation, auditability, data protection in every feature.
3. **Human-controlled autonomy** — AI never independently executes sensitive decisions without permissions and approval policies.
4. **Explainable intelligence** — every recommendation states what was detected, supporting information, why it matters, the recommended action, and assumptions/limitations.
5. **Integration-driven** — work with existing ERP/CRM/accounting/HR systems rather than replace them.
6. **Reliability over visual complexity** — correctness, observability, predictable execution, recoverability.
7. **Modular development** — new departments, integrations and AI capabilities without rewrites.

---

# 3. TARGET CUSTOMERS

Industries: manufacturing, distribution, logistics, retail groups, financial services, healthcare groups, large multi-department enterprises.

Users: CEO (organisation-wide visibility), COO (bottlenecks, coordination), Finance Manager (spend, payment exceptions, approvals), Procurement Manager (suppliers, purchase requests), Warehouse Manager (inventory, stock shortages), IT Administrator (integrations, access, system health), Operations Analyst (reports, trends, investigation).

---

# 4. CORE PRODUCT MODULES

1. **Operations Command Centre** — organisation-wide overview, health indicators, department performance, alerts, approvals, overdue workflows, incidents, AI summaries, historical comparisons, activity feed. Role-configurable. Never fabricate data; clearly distinguish live, simulated demo and unavailable data.
2. **AI Operations Intelligence** — anomaly detection, trends, process delays, risk, unusual spending, inventory risk, supplier performance, AI explanations. Each insight: ID, organisation ID, category, severity, detection timestamp, evidence, explanation, recommended action, status, assigned owner. Traceable to source information.
3. **Workflow Automation Engine** — builder, templates, conditional logic, approval stages, triggers/actions, schedules, external actions, retries, execution history, versioning, failure notifications. Durable and recoverable. Use Temporal; do not build a fragile custom engine.
4. **AI Agent Management** — future Finance, Procurement, HR, Inventory, Compliance and Operations agents, each with defined purpose, explicit instructions, restricted tools, organisation-level permissions, execution limits, approval requirements, activity logs, monitoring and evaluation. No unrestricted system access. Start with one narrowly scoped agent and a reliable framework.
5. **Incident and Exception Management** — creation, severity, assignment, ownership, notes, recommended resolution, status, escalation, resolution history, related workflows, audit history.
6. **Enterprise Knowledge Centre** — policies, SOPs, department documents; upload, classification, permission-based access, versioning, search, semantic retrieval, citations. AI retrieves only what the requesting user may access.
7. **Integration Management** — REST, webhooks, OAuth 2.0, API keys, scheduled sync, event processing, transformation, connection monitoring. Never expose integration credentials to the frontend.

---

# 5. INITIAL MVP SCOPE

Do not build every module simultaneously. Initial vertical: distribution and manufacturing operations.

MVP features: multi-tenant organisation management; authentication; RBAC; operations dashboard; integration management; two initial external system connections; inventory and procurement monitoring; basic anomaly detection; AI operational assistant; approval-based workflow automation; incident and exception management; audit logging.

**Primary MVP acceptance demonstration** — a distribution company has an inventory shortage. Operon AI must: receive inventory information; identify stock approaching a configured threshold; analyse sales and outstanding purchase orders; identify stockout risk; explain the alert; recommend a purchase request; submit it for approval; create the purchase request after approval; track the workflow; record the complete execution history.

---

# 6. TECHNOLOGY STACK

Use these unless a documented technical reason justifies a change.

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, Lucide, TanStack Query, React Hook Form, Zod.
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy, Alembic.
- **Database:** PostgreSQL; pgvector when semantic retrieval is introduced.
- **Workflow orchestration:** Temporal.
- **AI:** LangGraph where appropriate; model providers behind an abstraction (never hard-coded to one); structured outputs; tool permissions; RAG; evaluation and tracing.
- **Background:** Redis for caching/short-lived coordination; Temporal for durable workflows; Kafka/Redpanda later only when justified.
- **Authentication:** email/password, reset, verification, RBAC, organisation membership, session management, MFA, future SSO. Evaluate Keycloak or a managed provider.
- **Infrastructure:** Docker, Docker Compose locally, Git/GitHub, OpenTelemetry, structured logging, CI/CD, cloud deployment. Kubernetes only when justified.

---

# 7. SYSTEM ARCHITECTURE

Modular monolith with separately deployed background workers.

    operon-ai/
    ├── apps/{web,api}/
    ├── workers/{intelligence,integrations,notifications}/
    ├── packages/{shared-types,validation,api-client}/
    ├── infrastructure/{docker,database,deployment}/
    ├── docs/{architecture,product,api,security}/
    ├── scripts/  tests/
    ├── docker-compose.yml  .env.example  README.md  CLAUDE.md

Backend modules: identity, organisations, users, permissions, dashboard, integrations, intelligence, workflows, agents, incidents, knowledge, notifications, audit. Each owns its domain logic and exposes explicit interfaces. Avoid circular dependencies.

---

# 8. MULTI-TENANCY

Every organisation-owned record is associated with an organisation (memberships, integrations, workflows, executions, insights, incidents, documents, agent configurations, audit events).

- Prevent cross-tenant data access.
- Validate organisation membership on every relevant request.
- Enforce tenant-scoped database access; consider PostgreSQL RLS as an additional safeguard.
- Never trust organisation IDs supplied by an untrusted frontend.
- Test cross-tenant access explicitly.
- Design for future dedicated-infrastructure deployments.

---

# 9. SECURITY REQUIREMENTS

Secure password hashing; HTTPS in production; secure session/token handling; RBAC; organisation isolation; secrets management; encryption at rest and in transit; audit logging; input validation; rate limiting; API authentication; secure file uploads; dependency scanning; backup and recovery.

**AI security:** tool allowlists, explicit execution permissions, human approval for sensitive actions, structured tool inputs, timeouts, token and cost limits, prompt-injection defences, data access restrictions, agent activity logs. External documents and connected-system content are untrusted data, never instructions.

**Sensitive actions requiring configurable approval:** financial transfers, payments, supplier creation, purchase orders above limits, employee status changes, deletion of important records, permission changes. An AI recommendation is never automatic authorisation.

---

# 10. DATABASE DESIGN

Starting entities (not all in the first migration): identity/organisation (users, organisations, organisation_members, roles, permissions, role_permissions, invitations); integrations (integrations, integration_connections, integration_credentials, integration_sync_jobs, integration_events); intelligence (operational_metrics, ai_insights, insight_evidence, anomaly_events); workflows (workflows, workflow_versions, workflow_executions, workflow_approvals, workflow_execution_events); agents (agents, agent_versions, agent_executions, agent_tool_permissions); incidents (incidents, incident_assignments, incident_comments, incident_events); knowledge (knowledge_documents, document_versions, document_chunks, document_permissions); governance (audit_logs, notifications, system_events).

Use proper PKs, FKs, unique constraints, indexes, timestamps, organisation ownership; soft deletion only where justified. Always use migrations; never make undocumented manual production schema changes.

---

# 11. USER INTERFACE AND DESIGN DIRECTION

**The design system is defined in `docs/design/` and supersedes any earlier palette (ADR 0007).**

- Brief: `docs/design/frontend-design-direction.md` (DM Sans, Newsreader, IBM Plex Mono; Lucide icons). Colour: the harbour-and-sky palette in ADR 0013 replaces the brief's coffee palette.
- Decisions and corrections: `docs/design/visual-direction.md`, `docs/design/design-tokens.md`.
- Components and layouts: `docs/design/component-inventory.md`, `docs/design/page-layouts.md`.
- Tokens in code: `apps/web/src/styles/tokens.css`. Use semantic tokens (`bg-raised`, `text-ink-muted`, …); never raw hex values. Tailwind's default palette is disabled.

Non-negotiables: WCAG 2.2 AA; status is never colour alone; every data view shows provenance (live / demo / stale / unavailable); hide unimplemented modules (the navigation registry's `implemented` flag); no fake buttons — unavailable actions say why; no generic AI visual tropes; no undocumented composite health score.

Next.js in this repo is version 16 with Cache Components; read `apps/web/AGENTS.md` and the bundled docs in `node_modules/next/dist/docs/` before changing framework-level code.

---

# 12. API DESIGN

REST, versioned under `/api/v1/` (auth, organisations, users, dashboard, integrations, intelligence, workflows, agents, incidents, knowledge, audit). Consistent response formats, Pydantic schemas, correct status codes, pagination, filtering, sorting, validation, authN/authZ, OpenAPI docs. Never expose internal exceptions, credentials or infrastructure details.

---

# 13. OBSERVABILITY AND RELIABILITY

Structured logs; app, database and worker health checks; integration connection status; workflow execution status; error tracking; performance metrics; distributed tracing. Workflows: idempotency, retry policies, timeouts, failure handling, execution history, safe replay, duplicate event protection, dead-letter handling. Integration failures must never silently corrupt business data.

---

# 14. TESTING STRATEGY

- **Backend:** unit, API integration, database, permission, tenant isolation, workflow, integration adapter tests.
- **Frontend:** component, form validation, navigation, auth flow, critical journey tests.
- **AI:** structured output validity, recommendation accuracy, evidence traceability, permission boundaries, tool restrictions, prompt injection resistance, approval enforcement, failure behaviour.
- **Critical acceptance test:** a user from Organisation A must never be able to retrieve Organisation B's records, even by manipulating request parameters.

---

# 15. DEVELOPMENT ROADMAP

- **Phase 0 — Foundation:** repo structure, Docker Compose, PostgreSQL, FastAPI, Next.js, migrations, health checks, dev docs.
- **Phase 1 — Identity & organisations:** auth, profiles, organisations, membership, roles/permissions, tenant isolation, audit logging.
- **Phase 2 — Command centre:** shell, sidebar, dashboard, metrics, alerts, activity feed, role-aware dashboard (clearly labelled demo data).
- **Phase 3 — Integrations:** catalogue, connections, secure credentials, webhooks, health monitoring, two working external integrations.
- **Phase 4 — Intelligence:** metrics ingestion, rule-based anomaly detection, AI insights, evidence storage, recommendation interface.
- **Phase 5 — Workflows:** definitions, orchestration, approvals, monitoring, retries, history.
- **Phase 6 — Assistant & agents:** context retrieval, assistant, tool permissions, agent framework, monitoring, approval enforcement; one controlled agent.
- **Phase 7 — Enterprise readiness:** security review, performance, backup/recovery, deployment automation, monitoring, docs, onboarding.

---

# 16. CLAUDE CODE DEVELOPMENT RULES

Act as a senior software architect and full-stack engineer.

**Before changes:** inspect the repo, read docs, identify structure, check dependencies/versions, understand migrations, identify broken features, don't overwrite working code without understanding it.

**During implementation:** small verifiable stages; complete features over placeholders; separate frontend/backend; TypeScript types; Pydantic schemas; migrations; validate all input; enforce permissions on the backend; test important functionality; document architectural decisions; secrets outside source control; maintain `.env.example`; no dependencies without a reason; never silently change architectural decisions.

**Frontend:** reusable components; no enormous page components; API calls separate from presentation; consistent tokens; loading, empty and error states; accessible forms; responsive layouts; no fake buttons.

**Backend:** no business logic in route handlers; dependency injection; permission checks on every protected operation; transactions for multi-step operations; structured errors; log important business events; never expose credentials; no arbitrary queries in route handlers.

**AI:** LLMs never replace deterministic business logic; permissions, calculations and policy in normal code; validate model outputs; record model/execution metadata; never assume AI output is correct; never execute sensitive actions without approval.

**Git:** meaningful commit messages; no secrets; no force-push without permission; don't delete branches/data without permission; review before committing.

**Completion:** run tests, type checks, linting; verify migrations; check the app starts; verify the affected user journey; report outstanding issues. Never call a feature complete when only the frontend exists.

---

# 17. IMPORTANT PRODUCT CONSTRAINTS

Do not: build every module at once; start with microservices; create fake integrations; present demo data as live; give AI unrestricted access; store credentials in frontend code; implement sensitive operations without authorisation; create unnecessary abstractions; build features without acceptance criteria; sacrifice reliability for impressive demos.

Do: prioritise the first operational use case; establish tenant isolation early; build secure integration infrastructure; keep workflow execution durable; make AI decisions explainable; keep complete audit trails; build for maintainability.

---

# 18. DEFINITION OF SUCCESS (MVP)

1. An organisation can securely register and access its workspace.
2. Users can be assigned appropriate roles.
3. Operational data can be received from connected systems.
4. Operon AI can detect a configured operational problem.
5. It explains the issue using supporting evidence.
6. It recommends an appropriate action.
7. An authorised user can approve that action.
8. The workflow executes successfully.
9. Every important action is recorded.
10. Failures can be investigated and safely recovered.

**Build Operon AI as a serious enterprise product. Prioritise architecture, reliability, security and measurable business value.**
