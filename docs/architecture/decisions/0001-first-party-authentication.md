# 0001 — First-party authentication for the MVP

**Status:** Accepted (2026-11-13)

**Context.** Operon must own authorisation (organisations, memberships, roles, permissions) whatever
identity provider is used. Keycloak adds a JVM service, realm configuration and organisation-sync
work before Phase 1 can deliver; managed providers add per-user cost and data-residency questions.

**Decision.** Build email/password authentication, verification, reset, opaque server-side sessions
(HttpOnly cookie, hashed tokens) and TOTP MFA in the `identity` module, behind an
`IdentityProvider` boundary. Add OIDC/SAML SSO in Phase 7 through that boundary.

**Consequences.** We own security-sensitive code: use Argon2id and established libraries, focused
tests, rate limiting, and an external review in Phase 7. Swapping in Keycloak or a managed
provider later changes only `identity`.
