# Operon AI

Operational intelligence for enterprise operations teams: observe, understand, detect, recommend
and execute, with a human in control of every consequential action.

**Status:** Phases 0–7 complete:

- A secure multi-tenant foundation.
- An operations overview that labels where every figure comes from.
- Integrations: Odoo and Shopify connectors and CSV import.
- Intelligence: stockout-risk and overdue-PO detectors with traceable evidence, explanations that are
  validated (template fallback), and incidents with time-based escalation.
- Workflows: purchase requests from stockout insights, with multi-stage approvals, separation of
  duties and versioned policy. Approved requests become draft POs in Odoo, without duplicates.

- Assistant and agent: typed, permission-capped tools; every write becomes an approval request.
- Enterprise readiness: OIDC single sign-on, retention and export, OpenTelemetry, verified
  backups, and a one-command deploy with automatic rollback.

Not yet verified live: the Odoo and Shopify connectors, the Temporal path, the AI providers and
agent evaluations, a staging deploy, and a managed-database PITR drill. They need sandboxes, keys
and a hosting decision.

```bash
docker compose up --build        # or: make setup db-init migrate, then make api / make web
```

| | |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Product brief and engineering rules |
| [`docs/development.md`](docs/development.md) | Setup, checks, conventions |
| [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md) | System architecture |
| [`docs/architecture/decisions/`](docs/architecture/decisions/) | Architecture decision records |
| [`docs/product/mvp-implementation-plan.md`](docs/product/mvp-implementation-plan.md) | MVP phases, entities, endpoints, acceptance criteria |
| [`docs/design/`](docs/design/) | Design direction, tokens, components, layouts |
| [`docs/guides/`](docs/guides/) | Onboarding (connect Odoo, first insights) and administration |
| [`docs/operations/`](docs/operations/) | Deployment, backup and recovery, observability, load testing |
| [`docs/security/`](docs/security/) | Authentication, tenancy and the threat model |
| [`docs/security/authentication-and-tenancy.md`](docs/security/authentication-and-tenancy.md) | Security controls and the tests that prove them |

```
apps/api      FastAPI modular monolith (Python 3.13, SQLAlchemy 2, Alembic)
apps/web      Next.js 16 app (React 19, Tailwind 4, Radix, TanStack Query, Recharts)
infrastructure/database/init   Postgres roles and databases
.github/workflows/ci.yml       Lint, type check, tests, build, audits, secret scan
```
