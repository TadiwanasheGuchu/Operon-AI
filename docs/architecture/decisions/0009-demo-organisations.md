# 0009 — Demo organisations replace the frontend demo mode

**Status:** Accepted (2026-11-13). Supersedes the `NEXT_PUBLIC_OPERON_DATA_SOURCE=demo` mode.

**Context.** Until Phase 2 the web app could render a signed-out preview from a fixture bundled
in the frontend. With a real dashboard API, that meant two copies of the demo data and a second,
unauthenticated code path. Sales and design reviews still need a realistic, populated overview
before customers connect systems (Phases 3–5).

**Decision.**
- A demo is an ordinary organisation with `organisations.is_demo = true`, created only by
  `python -m operon.cli seed-demo --owner-email …` (`make seed-demo`). It uses real sign-in,
  members, roles and audit.
- The flag is enforced by the database: the application role has no INSERT/UPDATE privilege on
  `is_demo`, so no API path, bug or request body can turn a real organisation into a demo or
  back. The seed command connects as the schema owner.
- The dashboard service returns sample data from `modules/dashboard/demo.py` **only** when the
  organisation row says `is_demo`. Every such section and indicator carries provenance `demo`; the
  web app shows a persistent "Demo organisation" banner and "Demo data" badges.
- Real data stays real inside a demo organisation (team, members, audit, notifications).
- The frontend demo fixture, data-source switch and `/system/sample-overview` are removed.

**Consequences.** One source of demo data, behind auth, impossible to confuse with a customer's
organisation. Demos need a running backend. When real modules ship, `demo.py` must keep producing
the same contract (the shared fixtures and contract tests catch drift).
