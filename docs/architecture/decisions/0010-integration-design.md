# 0010 — Integration design: connectors, sync engine, webhooks, CSV import

**Status:** Accepted (2026-11-13)

**Context.** Phase 3 connects external systems. Customers run different versions of the same
product, webhooks can be forged or replayed, URLs are user-supplied, and an integration failure
must never silently corrupt data (CLAUDE.md §13).

**Decisions.**
1. **Connector contract.** Each system implements `check()` and `fetch(entity)`, returning
   canonical records. Sync code never sees vendor payloads.
2. **Odoo**: both external APIs, auto-detected — JSON-2 (Odoo 19+, API key as bearer token) and
   JSON-RPC (Odoo 17/18). Purchase requests are written back as draft RFQs, idempotent via
   `partner_ref` (used by Phase 5).
3. **Shopify**: GraphQL Admin API with the merchant's custom-app access token, not a public
   OAuth app. A public app needs Operon registered with Shopify (client id/secret, app review);
   that can be added later behind the same connector.
4. **Webhooks only trigger syncs.** A verified delivery is stored once (unique per connection and
   source event id) and starts an incremental sync; payloads are never written directly, so a
   partial or out-of-order event can't corrupt data. Unsigned or forged deliveries are rejected
   and audited.
5. **Write rules per entity**: catalogue entities upsert on (connection, external id); stock is a
   snapshot replaced as a whole; sales replace the synced window (90 days initially, then the
   last 3 days); purchase-order lines are replaced per order. Each entity is one transaction and
   its cursor advances in that same transaction.
6. **Failure states**: credential or configuration problems → `action_required` (a person must
   act); transient problems → `degraded` (retried). Managers are notified on the transition only.
   Upstream error text goes to logs, never to users or the database.
7. **Durable execution**: Temporal workflow per sync (one per connection at a time), schedules per
   connection with overlap skipped. An `inline` dispatcher runs the same `run_sync` in-process for
   development and tests and is refused in staging/production.
8. **SSRF protection**: user-supplied URLs must be https and resolve to public addresses
   (private, loopback, link-local, metadata ranges refused), checked at connect and before each
   sync. Shopify domains must match `*.myshopify.com`.
9. **CSV import** is a first-class connection type for systems without a connector: strict,
   all-or-nothing validation with row-level errors.
10. **Credentials** are AES-256-GCM encrypted per connection (associated data binds ciphertext to
    the connection id). KMS-wrapped data keys remain a Phase 7 item.

**Consequences.** Connectors are testable against protocol-level test servers; live verification
against real Odoo and Shopify instances needs sandbox credentials and network access (see the
Phase 3 notes in the plan). Real-time accuracy depends on webhooks or the sync interval.
