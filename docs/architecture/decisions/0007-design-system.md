# 0007 — Coffee-and-parchment design system replaces the navy palette

**Status:** Accepted (2026-11-13). Supersedes the colour and typography in CLAUDE.md §11.

**Decision.** Adopt `docs/design/frontend-design-direction.md` with four contrast corrections
(warning, danger and info text colours; a new AA muted-text token) and the rule that Bronze and
Stone are decorative only. DM Sans, Newsreader (page titles only) and IBM Plex Mono. Tokens live in
`apps/web/src/styles/tokens.css`; Tailwind's default palette is disabled.

**Consequences.** Every component uses semantic tokens. A validated categorical chart palette is
still required before the first multi-series chart.
