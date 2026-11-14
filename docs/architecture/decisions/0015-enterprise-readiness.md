# 0015 — Enterprise readiness: SSO, governance, telemetry, recovery and deployment

**Status:** Accepted (2026-11-14)

**Context.** Phase 7 makes Operon operable by an enterprise customer. That means single
sign-on, data retention and export, observability, a tested recovery path, and repeatable
deployments. The hosting target is still open (ADR index), so nothing here may depend on one cloud.

**Decision.**

- **SSO is OpenID Connect behind the identity boundary (ADR 0001).**
  - Each organisation has at most one connection (`sso_connections`). Its client secret is
    encrypted with the application key, bound to the connection id.
  - Email domains (`sso_domains`) are globally unique. A domain is used only after its DNS TXT
    record (`_operon-verification.<domain>`) has been verified. Public email domains are refused.
  - Sign-in uses the authorisation code flow with PKCE (S256), `state` and `nonce`. State is
    single-use, kept in Redis for 10 minutes.
  - The ID token is checked against the provider's JWKS for issuer, audience, expiry and nonce,
    and must contain `email_verified`. The email must belong to a verified domain of that
    organisation.
  - Just-in-time provisioning is optional and uses a default role. Owner and administrator are
    not offered, so SSO can't grant administration.
  - "Require SSO" turns off password sign-in for members at verified domains. Owners keep
    password sign-in as a break-glass in case the identity provider is down.
  - SCIM and SAML are deferred until a customer needs them.
- **Retention is per organisation, with bounds enforced in code and in the database.**
  - Audit log: 365–3650 days. Conversations: 7–3650 days. Run logs: 30–3650 days. Sync history:
    7–3650 days.
  - Audit and conversation purges go through `SECURITY DEFINER` functions. These refuse anything
    newer than the minimum, so a bug can't empty the audit log.
  - Business records (insights, incidents, purchase requests and their histories) never age out.
  - Purging runs in the maintenance loop (inline) or the `housekeeping` activity (Temporal), and
    is audited as `retention.applied`.
- **Export is a ZIP of JSON Lines, one file per table, plus a manifest.**
  - Rows are read under the requester's tenant context, so RLS applies.
  - Credentials, password hashes, MFA secrets, tokens, the SSO secret, IP addresses and
    members' private conversations are excluded.
  - Limited to 5 a day per organisation, and audited.
- **Telemetry is OpenTelemetry over OTLP/HTTP, off by default (`OPERON_OTEL_ENABLED`).**
  - Traces come from FastAPI, SQLAlchemy and httpx. Business counters cover syncs, insights,
    workflow transitions, agent runs and model tokens.
  - Trace and span ids are added to every structured log line.
  - Any OTLP backend works (Grafana, Honeycomb, Datadog, a managed collector).
- **Recovery has two layers.**
  1. Managed point-in-time recovery (WAL archiving) is the primary mechanism.
  2. Logical, checksummed, verified dumps (`infrastructure/backup/`) are the portable second
     copy and the basis of the restore drill.
- **Deployment uses immutable images and a single host-agnostic command.**
  - Images are published to GHCR, tagged by commit.
  - `compose.production.yml` (API, worker, web, Caddy for TLS) is deployed by `deploy.sh` over
    `DOCKER_HOST`: pull → migrate → roll out → health gate → automatic rollback.
  - Migrations are additive (expand/contract), so the previous version still runs after a
    rollback.
  - Cloud-specific infrastructure as code waits for the hosting decision.
- **Outbound HTTP pins the resolved address at connect time.** `GuardedTransport` closes the DNS
  rebinding gap left by URL validation alone.
- **Expensive actions have their own rate limits**, separate from authentication limits:
  assistant, agent runs, detection, explanations, purchase requests and exports.
- **Request bodies are capped at 1 MB**, with uploads at the configured upload maximum.

**Consequences.**

- There's no external IdP dependency for password users. SSO customers bring any OIDC provider
  (Entra ID, Okta, Google Workspace, Keycloak).
- Retention can't go below its minimums, even through a misconfiguration or a code defect.
- One compose file and one script cover staging and production on any Docker host. Moving to
  Kubernetes or a PaaS later reuses the same images and health checks.
- Still open:
  - KMS-wrapped data keys;
  - Temporal Cloud versus self-hosted;
  - managed Postgres. All three wait on the hosting decision.
