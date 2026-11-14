# Threat model and security review (Phase 7)

Scope: the API (`apps/api`), web app (`apps/web`), workers, the database, and integrations with
Odoo, Shopify, CSV, OIDC identity providers and model providers. The method is STRIDE over the
trust boundaries below, together with the controls and tests in
[`authentication-and-tenancy.md`](authentication-and-tenancy.md).

> This is an internal review against the code at the end of Phase 7. It does **not** replace an
> independent penetration test, which should run against staging before the first customer
> goes live.

## Assets

- Each tenant's operational data: stock, sales, purchase orders and suppliers.
- Insights, incidents, approvals and purchase requests.
- Integration credentials: Odoo and Shopify keys, webhook secrets.
- The SSO client secret.
- Sessions, password hashes, TOTP secrets.
- Audit logs.
- AI budgets: model spend is money.

## Trust boundaries

| # | Boundary | Main threats |
|---|---|---|
| B1 | Browser → web/API | Session theft, CSRF, XSS, clickjacking, brute force, oversized requests |
| B2 | Member of org A → data of org B | Tenant isolation bypass through ids, headers or joins |
| B3 | API → connected systems (Odoo, Shopify, IdP, model providers) | SSRF, DNS rebinding, credential leakage, poisoned responses |
| B4 | Connected-system content → models | Prompt injection that turns data into instructions |
| B5 | Inbound webhooks / CSV uploads | Forged events, replay, oversized or malformed files |
| B6 | Identity provider → Operon (SSO) | Forged tokens, login CSRF, domain takeover, account linking abuse |
| B7 | Operators → infrastructure | Leaked secrets, unverified backups, unsafe deploys |

## STRIDE summary

| Threat | Key controls |
|---|---|
| **Spoofing** | Argon2id passwords. Opaque, hashed session tokens. TOTP MFA with an organisation policy. OIDC with PKCE, `state`, `nonce` and JWKS signature checks. `email_verified` required. Domains proven by DNS TXT. Webhook HMAC. |
| **Tampering** | CSRF double-submit on unsafe methods. Pydantic validation (`extra="forbid"`). Same-organisation composite foreign keys. Append-only histories (workflow events, run steps, audit). Idempotency keys on external writes. |
| **Repudiation** | Audit log of every consequential action, with actor, request id and outcome. Workflow and agent histories are reconstructable. Trace ids appear in every log line. |
| **Information disclosure** | PostgreSQL RLS on every tenant table, plus service-level checks. The route-enumerating isolation suite. Credentials encrypted and never returned. Errors carry no internals. Private assistant conversations (restrictive RLS). Export excludes secrets. |
| **Denial of service** | Rate limits on authentication and on costly actions. 1 MB body cap. Upload limits. Model step, token and time limits, plus a monthly budget. Outbound timeouts. |
| **Elevation of privilege** | Server-side RBAC on every route. Role assignment capped at your own role. Agent permissions capped by the member it acts for and by `AGENT_CEILING`. Writes become approval requests. Separation of duties. SSO can't grant owner or administrator. |

## Findings of this review

Severity uses CVSS-style judgement: impact × reachability.

| ID | Finding | Severity | Status |
|---|---|---|---|
| P7-01 | Outbound URL checks resolved DNS once, but the HTTP client resolved again, so a rebinding DNS server could reach private addresses (SSRF via integration URLs) | High | **Fixed:** `GuardedTransport` checks and connects to the same resolved address (`core/net.py`, `test_net_guard.py`) |
| P7-02 | SSO state wasn't bound to the browser that started it. An attacker could get a victim signed into the attacker's account (login CSRF) | Medium | **Fixed:** an HttpOnly binding cookie is required at the callback (`test_a_sign_in_cannot_be_completed_in_another_browser`) |
| P7-03 | Costly endpoints (assistant, agent runs, detection, explanations, exports) had no per-action limits, so a member could exhaust the AI budget or the database | Medium | **Fixed:** `core/usage_limits.py`, applied in the agents, intelligence, workflows and governance APIs |
| P7-04 | No request body size limit outside uploads | Medium | **Fixed:** `BodyLimitMiddleware` (413 `payload_too_large`) |
| P7-05 | No Content-Security-Policy or HSTS | Medium | **Fixed:** CSP and HSTS in `next.config.ts`, plus HSTS at Caddy. See the residual risk R1. |
| P7-06 | An agent run interrupted by a crash stayed "running" for ever and blocked new runs | Low | **Fixed:** `fail_stale_runs` in maintenance |
| P7-07 | No retention policy: logs and conversations were kept for ever | Low | **Fixed:** per-organisation retention with database-enforced minimums |
| P7-08 | Dependencies | — | `pip-audit` and `pnpm audit` are clean. Both run in CI. |

**Open high or critical findings: none.**

## Residual risks (accepted, tracked)

| ID | Risk | Why accepted / plan |
|---|---|---|
| R1 | CSP allows `'unsafe-inline'` scripts. Next.js inlines hydration scripts, and nonces would force every page to render dynamically, which defeats Cache Components. | Other directives still block third-party scripts, framing, `<base>` and form hijacking. React escapes output, and the only `dangerouslySetInnerHTML` is a QR SVG generated by the server. Revisit if Next.js supports hashes for static pages. |
| R2 | Integration and SSO secrets are encrypted with an application key ring (rotatable), not KMS-wrapped per-record keys. | Waits on the hosting decision. The `SecretBox` interface already allows a KMS-backed implementation. |
| R3 | No breached-password check, no passkeys. | Planned. MFA policy and SSO mitigate. |
| R4 | Fixed-window rate limits allow short bursts at window edges. | Low impact. Limits are conservative. |
| R5 | Model providers see the tool outputs sent to them. | Disclosed to organisations, which opt in. No credentials or personal data beyond member names are sent. |
| R6 | No external penetration test yet. | Required before the first production tenant. Scope it with this document. |

## Review checklist for new features

- Every new tenant table has RLS, is in `TENANT_TABLES`, and its routes are in the isolation
  suite.
- Every new consequential action is audited and has a permission.
- Outbound HTTP goes through the integration HTTP factory (`GuardedTransport`).
- Costly actions get a usage limit.
- Content from connected systems is passed to models as data, never as instructions.
