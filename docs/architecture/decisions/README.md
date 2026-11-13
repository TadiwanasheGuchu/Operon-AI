# Architecture Decision Records

One file per decision: **Context**, **Decision**, **Consequences**, **Status**
(Proposed / Accepted / Superseded by NNNN).

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-first-party-authentication.md) | First-party authentication for the MVP | Accepted |
| [0002](0002-initial-integrations.md) | Odoo + Shopify as first integrations | Accepted (confirm with pilots) |
| [0003](0003-temporal-from-phase-3.md) | Temporal from Phase 3 | Accepted |
| [0004](0004-tenant-selection-header.md) | Tenant selection via header + membership check | Accepted (slug URLs deferred) |
| [0005](0005-monorepo-layout.md) | Single repo, pnpm + uv workspaces | Accepted |
| [0006](0006-llm-provider-abstraction.md) | LLM provider abstraction, two providers | Accepted |
| [0007](0007-design-system.md) | Coffee-and-parchment design system | Colour superseded by 0013 |
| [0008](0008-transaction-per-request.md) | One database transaction per request | Accepted |
| [0009](0009-demo-organisations.md) | Demo organisations replace the frontend demo mode | Accepted |
| [0010](0010-integration-design.md) | Integration design: connectors, sync, webhooks, CSV | Accepted |
| [0011](0011-intelligence-and-explanations.md) | Deterministic detectors, validated explanations, incidents | Accepted |
| [0012](0012-approval-workflows.md) | Approval workflows: idempotent state machine on Temporal | Accepted |
| [0013](0013-sky-palette.md) | Harbour-and-sky palette, light sidebar, fewer cards | Accepted |
| [0014](0014-assistant-and-agents.md) | Assistant and agents: typed tools, code-enforced limits, human approval | Accepted |

Open: hosting target (affects KMS, managed Postgres, Temporal Cloud vs self-hosted).
