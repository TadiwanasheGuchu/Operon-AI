# 0012 — Approval workflows: one idempotent state machine, Temporal for durability

**Status:** Accepted (2026-11-13)

**Context.** Phase 5 turns a stockout recommendation into a purchase order. The process has three
requirements:

- It must survive restarts and wait days for people.
- It must never create a duplicate order.
- It must never send an order without approval (CLAUDE.md §9: an AI recommendation is never
  authorisation).

**Decision.**

- **One state machine, `modules/workflows/engine.advance`.** It is idempotent and holds a row lock.
  It handles approval deadlines (one reminder, then expiry), the move from approved to executing,
  the external write and its retries (exponential backoff, configurable attempts), and completion.
  People's decisions are recorded by `service.decide` in the request transaction; the execution is
  then woken.
- **Durability:**
  - With Temporal, a `PurchaseRequest` workflow per execution calls `advance` as an activity. It
    sleeps on a timer until the next deadline or retry, or until a `wake` signal arrives (decision,
    cancel or retry).
  - With the inline backend (development and tests), `advance` runs after each event, and the
    maintenance loop sweeps executions whose deadline has passed.
  - Both paths run identical logic. Only `advance` is exercised by tests here, because the Temporal
    test server can't be downloaded in this environment.
- **Exactly-once external writes:**
  - The idempotency key `operon-<execution id>` is stored in Odoo's `partner_ref` and searched
    before any create; the order is then read back to confirm it.
  - A per-execution advisory lock stops two runners writing at the same time.
  - A crash between "created in Odoo" and "recorded in Operon" is covered by a test that kills the
    run at that point and restarts it.
- **Policy as versioned parameters:**
  - `workflow_versions.params` hold the policy currency, ordered stages (name, minimum value,
    approver roles), approval timeout and maximum attempts.
  - The first stage must apply to every request. A value that is unknown, or in a different
    currency, requires every stage (fail safe).
  - Each execution pins its version. This replaces the separate `approval_policies` table in the plan.
- **Separation of duties:**
  - The requester can never decide.
  - Nobody can decide two stages of the same request.
  - Deciding needs `approvals.decide` and a role listed for the stage.
  - A rejection needs a reason.
- **What a request contains:**
  - It is created from a stockout insight, server-side. Product, supplier and price come from the
    insight; only the quantity may change, and the change is recorded against the recommendation.
  - One request can be in flight per insight.
- **Where the order goes:**
  - If the product and supplier come from an Odoo connection, an RFQ (draft PO) is created there;
    a person confirms it in Odoo.
  - Otherwise (CSV, or Shopify, which has no purchasing), the approved request is recorded in Operon
    and the UI says plainly that it must be raised in the purchasing system.

**Consequences.**

- Every execution is reconstructable from `workflow_execution_events` (append-only) and the audit
  log.
- Failures notify the requester and workflow managers. Retrying after a failure reuses the
  idempotency key.
- Execution events record the actor's email rather than a display name, the same as the audit log.
- Purchase requests are the only workflow template so far; the tables are generic for later ones.
