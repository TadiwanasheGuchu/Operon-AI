# Authentication, authorisation and tenant isolation

| | |
|---|---|
| Status | Implemented (Phase 1) |
| Decisions | ADR 0001 (first-party auth), ADR 0004 (tenant selection) |
| Code | `apps/api/src/operon/modules/identity`, `organisations`, `permissions`, `audit`, `access/` |
| Tests | `apps/api/tests/test_auth.py`, `test_mfa.py`, `test_members.py`, `test_tenant_isolation.py`, `test_audit_and_catalogue.py` |

This page lists the controls that exist in code today and the test that proves each one.

## Accounts and credentials

| Control | Implementation | Proven by |
|---|---|---|
| Password hashing | Argon2id (time 3, memory 64 MiB, parallelism 2); transparent rehash on login when parameters change | `test_auth.py` |
| Password policy | 12–256 characters, no composition rules (NIST 800-63B) | `test_short_passwords_are_rejected` |
| No account enumeration | Register, resend-verification and forgot-password always answer 202 with the same message; registering an existing email emails the owner instead; unknown accounts still pay for a hash verification | `test_registration_does_not_reveal_existing_accounts`, `test_wrong_and_unknown_credentials_look_identical`, `test_forgot_password_for_unknown_email_looks_the_same` |
| Email verification | Required before sign-in; revealed only after the correct password | `test_cannot_sign_in_before_verifying`, `test_unverified_state_not_revealed_without_password` |
| Tokens | 256-bit random, stored as SHA-256, single-use, short-lived (verify 24 h, reset 30 min, invitation 7 d); issuing a new one invalidates the previous | `test_password_reset_flow`, `test_expired_reset_link_is_refused` |
| Password reset | Revokes every session and emails a notice | `test_password_reset_flow` |
| Password change | Requires the current password; revokes all other sessions | `test_change_password_keeps_current_session_only` |
| Brute force | Redis fixed windows: login 30/IP and 8/email per 15 min; MFA 5/challenge and 10/user; email actions 10/IP and 3/email; token redemption 20/IP. Fails **closed** if Redis is down | `test_login_is_rate_limited_per_email`, `test_mfa_challenge_is_rate_limited` |

## Sessions and CSRF

| Control | Implementation | Proven by |
|---|---|---|
| Session token | Opaque, HttpOnly, SameSite=Lax, Secure outside dev/test; hashed at rest | `test_session_cookie_is_hardened`, `test_session_tokens_are_stored_hashed` |
| Expiry | 60 min idle (sliding), 12 h absolute; server-side revocation | `test_idle_sessions_expire`, `test_absolute_session_lifetime`, `test_logout_revokes_the_session` |
| Session management | Users list and revoke their own sessions only | `test_list_and_revoke_sessions`, `test_cannot_revoke_someone_elses_session` |
| CSRF | Double-submit cookie: `operon_csrf` must be echoed in `X-CSRF-Token` on every POST/PUT/PATCH/DELETE | `test_state_changes_require_csrf_token` |

## Two-factor authentication

| Control | Implementation | Proven by |
|---|---|---|
| TOTP | RFC 6238, ±30 s drift; secret encrypted at rest with AES-256-GCM, bound to the user ID as associated data, key rotation by key ID | `test_secret_is_encrypted_at_rest` |
| Replay protection | Highest accepted time step is stored; codes at or below it are rejected | `test_totp_codes_cannot_be_replayed` |
| Recovery codes | 10 single-use codes, hashed, shown once | `test_recovery_codes_are_single_use` |
| Login flow | Password step issues a 5-minute challenge (HttpOnly, SameSite=Strict cookie scoped to the login path); no session exists until the second factor passes | `test_login_requires_second_factor`, `test_mfa_step_without_password_step_fails` |
| Disabling | Requires password **and** a current code | `test_disable_mfa_requires_password_and_code` |
| Organisation policy | `mfa_required` blocks members without MFA from every tenant endpoint (account pages stay reachable); an admin can't enable it without MFA themselves | `test_organisation_mfa_policy` |

## Authorisation

- Permissions are a fixed catalogue in code (`permissions/catalogue.py`), seeded by migration; a test fails if code and database disagree.
- Six system roles per organisation: owner, administrator, operations manager, approver, analyst, viewer (matrix: `GET /api/v1/roles`, or the Roles page).
- Every tenant route declares its permission with `require_permission(...)`; denials return 403 and are written to the audit log in their own transaction.
- Role rules, enforced in the service layer: nobody changes their own role; nobody grants or manages a role above their own; only owners grant ownership; the last owner can't be demoted or removed.
- The UI hides what you can't do, but never decides: `test_viewer_cannot_write_and_attempts_are_audited` calls the API directly.

## Tenant isolation (CLAUDE.md §14)

Three independent layers, each tested on its own:

1. **Request context.** `require_tenant` reads `X-Operon-Organisation`, loads the caller's membership and builds `TenantContext`. Malformed, unknown and foreign organisation IDs all return the same 404.
2. **Queries.** Services filter by `ctx.organisation_id`; child rows reference parents through composite keys `(organisation_id, id)`, so a membership can't point at another organisation's role even if the application tries.
3. **Row-level security.** Tenant tables have RLS policies keyed on `app.current_org_id` / `app.current_user_id`, set with `SET LOCAL` per transaction. The runtime role `operon_app` has no `BYPASSRLS`; with no context set, queries return nothing.

`test_tenant_isolation.py` discovers every route from the OpenAPI schema. Every route must be classified, and every tenant route is attacked with a foreign header, bogus headers, foreign resource IDs in the path, and no session. Separate tests query the database directly as the application role to prove RLS alone blocks reads and writes.

The suite was mutation-tested: removing the membership check makes it fail; removing the organisation filter from member queries leaves it passing because RLS still blocks the leak, which is the intended defence in depth.

## Audit trail

- `audit_logs` is append-only for the application role (UPDATE/DELETE/TRUNCATE revoked), tested directly against the database.
- Events are written in the same transaction as the change they describe; failures and denials are written in a separate transaction so the rollback doesn't erase them.
- Account-level events (login, password, MFA) have no organisation, so they are write-only and never appear in any organisation's log.
- Each entry records actor, action, target, outcome, details (never secrets), request ID and IP address.

## Phase 2 additions

| Control | Implementation | Proven by |
|---|---|---|
| Notifications are private to their recipient | RLS: read/update/delete require `user_id = app.current_user_id` as well as the organisation; colleagues get 404 | `test_cannot_read_a_colleagues_notification` |
| Dashboard layouts are per user | RLS on `dashboard_layouts` requires both organisation and user | `test_layout_defaults_by_role_and_can_be_saved` |
| Demo data can't reach a real organisation | The application role has no INSERT/UPDATE privilege on `organisations.is_demo`; only the operator `seed-demo` command (schema owner) can set it; sample data is served only when the flag is set (ADR 0009) | `test_application_role_cannot_create_or_flip_demo_organisations`, `test_demo_organisation_is_labelled_throughout` |
| Dashboard respects permissions | Team and activity sections are `restricted` (no data) without `members.read` / `audit.read`; summary requires `dashboard.read` | `test_sections_follow_permissions` |
| No unlabelled data | Every section and indicator carries provenance; unavailable sections carry no data | `assert_honest` in `test_dashboard.py`, `contract.test.ts` |
| Notification links | Only in-app paths are accepted, so a notification can't become a phishing link | `notifications.service.notify` |

## Phase 3 additions (integrations)

| Control | Implementation | Proven by |
|---|---|---|
| Credentials never leave the server | Write-only API fields; AES-256-GCM at rest, bound to the connection id; tested before saving | `test_credentials_are_encrypted_and_never_returned`, `test_rejected_credentials_are_never_stored` |
| SSRF protection | https only; private, loopback, link-local and metadata addresses refused at connect and before each sync; no redirects followed; Shopify limited to `*.myshopify.com` | `test_private_and_insecure_addresses_are_refused`, `test_shopify_domain_is_validated` |
| Webhook authenticity | HMAC-SHA256 over the raw body, constant-time comparison; unsigned/forged deliveries rejected (401) and audited; 1 MB limit; unguessable URL token | `test_webhooks`, `test_shopify_webhook_verification` |
| Replay / duplicate protection | Unique (connection, source event id); redeliveries acknowledged, not reprocessed | `test_webhooks` |
| Safe failure | Each entity in its own transaction; outages leave existing data untouched; upstream error text kept out of the UI and database | `test_outage_degrades_without_touching_data` |
| No concurrent syncs | Advisory lock per connection (and one Temporal workflow id per connection) | `test_sync_lock_prevents_concurrent_runs` |
| Tenant isolation | RLS on all 12 new tables; composite keys keep synced rows inside their organisation and connection; the isolation suite attacks every integration route | `test_tenant_isolation.py` |
| Upload safety | 5 MB / 50,000-row limits; UTF-8 only; strict columns; all-or-nothing | `test_csv_import.py` |
| Least privilege | Only owners and administrators manage integrations; analysts and operations managers read | `test_permissions` (integrations) |

## Phase 4 additions (intelligence and incidents)

| Control | Proof |
|---|---|
| Nine new tenant tables under RLS, joining the isolation suite's table list | `test_rls_hides_other_tenants_rows`, `test_rls_fails_closed_without_context` |
| Every new route attacked with foreign headers and foreign insight, evidence and incident ids | `test_tenant_isolation.py` (route-enumerating) |
| Owners and assignees must be members of the same organisation (composite foreign key to `organisation_members`, plus a permission check) | `test_owner_must_be_a_member_and_is_notified`, `test_assignee_must_be_a_member_and_can_be_cleared` |
| History is append-only: `insight_events`, `incident_events` and `ai_generations` have UPDATE, DELETE and TRUNCATE revoked | migration 0005 |
| The cross-tenant escalation sweep sees only ids, through a SECURITY DEFINER function; it then acts under each organisation's RLS context | `test_unanswered_incidents_escalate_until_someone_investigates` |
| AI is off by default. Turning it on requires `organisation.manage`, and the settings page states what data is shared | `test_ai_settings_require_a_configured_provider_and_organisation_manage` |
| Connected-system content reaches the model only as data fenced in `<alert>` tags, which it is told never to follow. Output can't add numbers or links (validator) and never sets severity, quantities or actions | `test_ai_explanation_is_validated_and_recorded`, `test_invented_numbers_fall_back_to_template` |
| Provider keys live only in the server environment and are never returned by the API | `AISettingsOut` (no key fields) |

## Phase 5 additions (workflows and approvals)

| Control | Proof |
|---|---|
| Five new tenant tables under RLS; every new route attacked with Org B's execution and approval ids | `test_tenant_isolation.py` |
| A purchase request for another organisation's insight looks like it doesn't exist | `test_cannot_request_purchases_from_another_organisations_insight` |
| Product, supplier and price are taken from the insight on the server; the client may change only the quantity, and the change is recorded | `submit_from_insight`, `test_large_requests_need_two_different_approvers` |
| Separation of duties: the requester can't approve, nobody approves two stages, and a role must be listed for the stage | `test_stockout_to_approved_draft_po_in_odoo`, `test_large_requests_need_two_different_approvers` |
| Nothing is sent to the purchasing system before every stage is approved | `odoo_orders(...) == []` assertions throughout `test_workflows.py` |
| Exactly-once external write (idempotency key plus read-back) | `test_crash_after_external_write_does_not_duplicate` |
| History is append-only: `workflow_execution_events` and `workflow_versions` have UPDATE, DELETE and TRUNCATE revoked | migration 0006 |
| The cross-tenant sweep sees ids only (SECURITY DEFINER), then acts under each organisation's RLS context | `test_undecided_approvals_escalate_then_expire` |

## Phase 6 additions (assistant and agents)

| Control | Proof |
|---|---|
| Seven new tenant tables under RLS; every new route attacked with Org B's conversation and run ids | `test_tenant_isolation.py` |
| Conversations are private to their author: restrictive RLS on `assistant_conversations` and `assistant_messages`, plus service checks | `test_conversations_are_private_at_the_database_level`, `test_assistant_tools_follow_the_askers_permissions` |
| Assistant tools are read-only and filtered by the asker's permissions | `test_assistant_tools_follow_the_askers_permissions` |
| Only allowlisted tools execute; unknown or disallowed calls are denied and logged | `test_injected_instructions_in_synced_data_change_nothing` |
| Tool input is schema-validated before execution | `test_invalid_tool_input_is_rejected_before_running` |
| An agent can never exceed its member's permissions or the fixed ceiling | `test_agent_is_capped_by_the_member_it_acts_for` |
| Writes become approval requests; the member an agent acts for can't approve its drafts | `test_agent_drafts_a_request_that_still_needs_human_approval` |
| Quantity bounds, severity threshold and per-run draft cap are enforced in code | `test_agent_guards_are_enforced_in_code` |
| Step, token and time limits and the monthly budget stop runs | `test_runs_stop_at_their_limits`, `test_assistant_explains_why_it_is_unavailable` |
| Answers citing records or figures not in the tool outputs are flagged to the reader | `test_unsupported_figures_and_references_are_flagged` |
| Run logs are append-only (`agent_execution_steps`, `agent_versions`) | migration 0007 |

## Known gaps (tracked for later phases)

- No breached-password check yet (planned: k-anonymity range lookup).
- No WebAuthn/passkeys; TOTP only.
- No SSO/SCIM (Phase 7, through the identity-provider boundary).
- Email address changes aren't supported yet.
- Audit retention and export policies are not defined.
- Rate limits use fixed windows; a sliding window or token bucket would smooth bursts.
- Outbound URL checks narrow but don't eliminate DNS rebinding; pinning the resolved address per
  request (custom transport) is planned with the security review.
- Integration secrets use an application key; KMS-wrapped per-record data keys are Phase 7.
