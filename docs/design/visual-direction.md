# Visual direction

> **Colour update (ADR 0013):** the palette is now harbour and sky: a light sidebar, Ocean blue for the
> primary action, Mist for selection, and Cloud as the canvas. Where this document mentions coffee,
> parchment or caramel, read the matching role in `design-tokens.md`. The structural principles still apply.

| | |
|---|---|
| Status | Implemented in the shell and Operations Command Centre — awaiting review |
| Brief | [`frontend-design-direction.md`](frontend-design-direction.md) (source brief, unchanged) |
| Tokens | [`design-tokens.md`](design-tokens.md) |

> Warmth in the brand. Precision in the interface. Intelligence in the details.

## The decisions

**1. Coffee is the frame, parchment is the work surface.** The only large brown surface is the
navigation rail (Dark Roast). Everything users read for long periods sits on Parchment and Warm
White. Coffee Bean is reserved for the single primary action per view; Caramel appears only as
small signals: the active-navigation bar, the logo node, unread dots.

**2. Status colours mean status, nothing else.** Green, amber, red and blue never decorate. They
always come with an icon and words (`Needs attention`, `Critical`), so meaning survives
colour-blindness, greyscale printing and forced-colours mode. The brief's status text colours were
darkened slightly to pass WCAG AA (see tokens).

**3. Composed sections, not card confetti.** The operational summary is one strip of five
indicators divided by hairlines, not five floating cards. Panels are flat, 12px radius, 1px Stone
border and no shadow. Shadows exist only on things that float (menus, dialogs).

**4. Editorial type used once per page.** Newsreader sets the page title, the one place that gives
the product its voice. Everything else is DM Sans. IBM Plex Mono marks machine facts: record
references (`INS-2041`), rule IDs, timestamps, calculations. A glance tells you whether text was
written for you or recorded by the system.

**5. AI is shown as evidence, not as a personality.** No sparkles, gradients, orbs or chat bubbles.
An insight is a structured operational record: severity, what was detected, the recommended action
in its own box, and on demand the evidence table, assumptions, limitations, and a line stating how
the explanation was produced (model-written and checked against evidence, or template). Actions
that aren't wired up yet are visibly unavailable, with the reason in plain text.

**6. Provenance is always visible.** Every data view carries `Live`, `Demo data`, `Stale` or
`Unavailable`. The demo workspace adds a persistent banner. There is no composite "health score":
the brief forbids an undocumented one, so the summary shows the underlying indicators instead.

## The mark

An open loop with a single node sitting in its gap: continuous, connected operations, and the one
condition that needs attention. Drawn on a 32px grid with a 4px stroke so it stays legible at 16px
(favicon), and it works in one colour. In the sidebar the node takes Caramel. No robots, brains or
sparkles. The wordmark is DM Sans Semibold with slight negative tracking and stands on its own.

## References: what was taken

The brief's references were used for principles only; no layout was copied.

- **Enterprise dashboard shots** → restrained colour, one accent, metric hierarchy (big number, small
  context, delta in words).
- **Editorial SaaS sites (Terminal Industries)** → confident serif headline paired with a precise
  sans, product explained through real operational situations. That's why the demo is a concrete
  glove stockout at Leeds DC, not abstract KPIs.
- **Minimal dashboards** → whitespace and rhythm on a 4px grid, hairline dividers instead of boxes.

## Anti-generic checklist (§17 of the brief)

| Pattern | Status |
|---|---|
| Purple/blue AI gradients, orbs, particles, robots, sparkles | None |
| Glassmorphism, excessive shadows | Header uses a 95% opaque canvas with light blur for legibility only; no shadows on panels |
| Identical rounded metric cards | Replaced by a single divided strip |
| Chat interface as the dashboard | No chat; AI appears inside insights |
| Decorative charts | Two charts, each answering a question (is fill rate holding? where is stock at risk?) |
| Placeholder content presented as real | Demo banner, provenance badges, unavailable actions labelled |
| Unmodified shadcn look | Primitives are built on Radix with Operon tokens; no default shadcn theme |

## Open for later

- **Dark theme:** deliberately not built (brief §3). Tokens are semantic, so a dark theme is a new
  token set, not a refactor.
- **Marketing site:** deferred until real product screenshots and customer proof exist.
- **Photography:** none yet. When added, real warehouse and distribution imagery only.
