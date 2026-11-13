# Development guide

## Prerequisites

Python 3.13 + [uv](https://docs.astral.sh/uv/), Node 22 + pnpm 10, and either Docker or local
PostgreSQL 16 and Redis 7.

## Option A: Docker (full stack)

```bash
cp .env.example .env
docker compose up --build
```

Web: http://localhost:3000 · API docs: http://localhost:8000/api/v1/docs · Mail: http://localhost:8025.
`migrate` runs `alembic upgrade head` before the API starts. Every email (confirmation,
invitations, password resets) lands in Mailpit.

## Option B: local services

```bash
make setup        # uv sync + pnpm install
make db-init      # roles operon_owner / operon_app, databases operon + operon_test
make migrate
make api          # :8000, auto-reload
make web          # :3000, proxies /api/* to :8000
```

## First sign-in

1. Open http://localhost:3000 and choose **Create an organisation**.
2. Open the confirmation email: in Mailpit (Docker), or in the API log when
   `OPERON_EMAIL_BACKEND=console` (look for `email_console`).
3. Sign in. You're the owner of the new organisation. Invite colleagues from **Members**; their
   invitation emails arrive the same way.

## Checks (what CI runs)

```bash
make check        # ruff, ruff format, mypy --strict, import-linter, eslint, tsc, pytest, vitest
```

API tests use the real `operon_test` database (migrated down and up per session) and Redis db 15.
Override with `OPERON_TEST_DATABASE_URL`, `OPERON_TEST_MIGRATIONS_DATABASE_URL`, `OPERON_TEST_REDIS_URL`.

## Database roles

| Role | Used by | Rights |
|---|---|---|
| `operon_owner` | Alembic only | Owns the schema |
| `operon_app` | API and workers | DML only; no DDL, no `BYPASSRLS` (tested) |

New migration: `cd apps/api && uv run alembic revision --autogenerate -m "…"`, then review it.
`tests/test_database.py` fails if models and migrations drift.

## Integrations (ADR 0010)

- **CSV import** works everywhere: Integrations → Set up CSV import → download a template per
  file type → import locations first, then products, supplier terms, stock, sales, purchase orders.
- **Odoo / Shopify** need a reachable instance. For a local Odoo on your machine set
  `OPERON_ALLOW_PRIVATE_INTEGRATION_HOSTS=true` (development only).
- **Syncs.** With `OPERON_WORKFLOW_BACKEND=inline` (default outside Docker) a sync runs inside the
  API request and there are no schedules: use "Sync now". With Docker Compose the backend is
  `temporal`: the `worker` service runs syncs, schedules follow each connection's interval, and
  the Temporal UI at http://localhost:8233 shows every run.
- **Tests** use protocol-level Odoo and Shopify servers (`apps/api/tests/fakes/`); connector code
  runs unmodified against them.

## Demo organisations (ADR 0009)

To show a populated overview before any system is connected:

```bash
make seed-demo EMAIL=you@example.com
```

The account must already exist and be verified. You'll find "Harbour & Vale Distribution (demo)"
in your organisation switcher. Its operational figures are fictional and labelled "Demo data"
everywhere; its members, settings and audit log are real. Only this command can create a demo
organisation: the application's database role can't set the flag.

## Dashboard contract fixtures

`apps/web/src/test/fixtures/dashboard-*.json` are real API responses (live, viewer-restricted and
demo organisations). Frontend contract tests parse them, so changes to
`modules/dashboard/schemas.py` must be reflected in `features/dashboard/contract.ts`. After
changing the API contract, regenerate them (this wipes the **test** database):

```bash
cd apps/api && uv run python scripts/capture_dashboard_fixtures.py ../web/src/test/fixtures
```

## Tenancy in code

- Tenant routes depend on `require_permission(Perm.X)` (or `TenantDep`); never read an organisation
  ID from a body or query string.
- Every new tenant-owned table needs `organisation_id`, an RLS policy in its migration, and
  composite foreign keys to tenant-owned parents. `tests/test_tenant_isolation.py` fails until a
  new route is classified, then attacks it automatically.
- Services flush, never commit (ADR 0008). Use `audit.record` for changes and
  `audit.record_independent` for failures that must survive a rollback.

See `docs/security/authentication-and-tenancy.md` for every control and the test that proves it.

## Conventions

- API: routers parse and delegate; logic in `service.py`; errors via `ApiError` → `{"error": {code, message, details, request_id}}`.
- Every response carries `x-request-id`; logs are structured JSON with sensitive keys redacted.
- `operon.core` must not import from `operon.modules` (import-linter contract).
- Web: pages compose feature hooks + presentational components; components never call `fetch`.
