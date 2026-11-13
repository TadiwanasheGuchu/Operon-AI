# 0002 — Initial integrations: Odoo and Shopify

**Status:** Accepted (2026-11-13), subject to confirmation against pilot customers' systems.

**Context.** The MVP needs two real connections that cover the stockout scenario end to end,
including writing a purchase request back.

**Decision.** Odoo (inventory, sales, purchasing; supports write-back; open source, so it runs
locally against real APIs) and Shopify (orders and inventory levels; real development stores),
plus a generic CSV/REST ingestion path.

**Consequences.** Support one Odoo version initially (17/18 Community). If pilot customers run
other systems, this ADR is superseded before Phase 3 starts.
