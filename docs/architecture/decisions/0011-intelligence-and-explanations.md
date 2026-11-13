# 0011 — Deterministic detectors, validated explanations, incidents

**Status:** Accepted (2026-11-13)

**Context.** Phase 4 adds detection and AI explanations. CLAUDE.md requires every insight to be explainable and
traceable, and forbids AI from replacing deterministic business logic.

**Decision.**

- **Detectors are versioned code** (`modules/intelligence/detectors/`). Each has a rule id, a version and a
  Pydantic parameter model. Organisations can switch detectors on or off and tune their parameters
  (`detector_configs`). Detectors read canonical tables, compute in `Decimal` and return findings with
  evidence. They never write and never call a model. A changed calculation needs a new version.
- **The engine reconciles findings with insights** (`engine.py`):
  - There is one active insight per (organisation, rule, subject), enforced by a partial unique index.
  - Re-detection updates that insight and records the change in `insight_events`.
  - A condition that clears resolves its insight automatically.
  - A dismissal suppresses the subject for 7 days unless the severity rises.
  - Each detector runs in its own transaction.
- **Evidence is stored per insight** (`insight_evidence`): display value, numeric value, source type, the Operon
  record id, the source system's reference, and the formula for computed values. An API endpoint resolves any
  synced evidence item to its current record.
- **Explanations:**
  - Every finding carries a template explanation built from its own evidence.
  - If an organisation turns AI on, has budget left, and a provider key is configured on the deployment, the
    evidence (title, labels, values, recommendation, assumptions, limitations — nothing else) goes to the
    provider with a strict structured-output schema.
  - The validator rejects output that contains any number absent from the evidence, any link, or an empty
    field. Rejected, refused and failed attempts are recorded in `ai_generations` and the template stays.
  - Model text is applied only if the insight's numbers didn't change during the call.
  - Recommendations (quantities, prices, suppliers) and severity are always computed in code.
- **Providers:**
  - `LLMProvider` with two adapters, each in its own module using the vendor's official SDK.
  - Anthropic uses the default model `claude-opus-5-5` with structured outputs and effort `low`. Server-side
    refusal fallbacks (`fallbacks="default"`) are enabled, and the model that actually served the call is
    recorded.
  - OpenAI uses the Responses API with structured outputs; its model must be configured explicitly.
  - Keys come from the server environment only. Organisations cannot supply their own keys yet.
- **Incidents:**
  - Incidents have their own lifecycle (open → investigating → resolved, which can be reopened) and per-severity
    response targets: critical 1 h, high 4 h, medium 24 h, low 72 h.
  - Comments, assignments and status changes live in one append-only `incident_events` timeline. This replaces
    the separate assignments and comments tables in the plan.
  - An incident still `open` after its target escalates to managers, up to 3 times. The sweep runs from a
    Temporal schedule (`Maintenance` workflow, every 5 minutes), or from an in-process loop when using the
    inline backend. It finds due incidents across tenants through a SECURITY DEFINER function that returns ids
    only, then acts under each organisation's RLS context.
- **When detection runs:** after each successful sync (an inline hook, or a Temporal activity after the sync
  activity), after each accepted CSV upload, and on demand.

**Consequences.**

- Detection is reproducible and testable: there are golden tests against an independent float implementation.
- Explanations can't introduce facts; the cost is blander wording than an unconstrained model would produce.
- History tables are append-only for the application role.
- Detection after an upload runs in the API process, not on Temporal. It is idempotent, and the next sync
  re-runs it.
- `operational_metrics` and `anomaly_events` from the original plan are deferred. `detection_runs` and
  `insight_events` cover run history; derived daily metrics arrive when a detector needs them.
