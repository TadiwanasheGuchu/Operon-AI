# Page layouts

## Application shell

```
┌──────────────┬──────────────────────────────────────────────────────────────┐
│ ◯ Operon  ⇤  │ Demo workspace banner (demo only)                            │
│ [HV] Org  ⇅  ├──────────────────────────────────────────────────────────────┤
│              │ Org / Page title          [Search ⌘K]   🔔  ?  (AO)          │ 64px
│ OPERATE      ├──────────────────────────────────────────────────────────────┤
│ ▌Overview    │                                                              │
│              │   page content (max 1440px, gutters 36/24/16)                │
│ …            │                                                              │
│ ● Platform   │                                                              │
└──────────────┴──────────────────────────────────────────────────────────────┘
  256px / 72px collapsed (≥1024px)   ·   drawer below 1024px
```

## Operations Command Centre (`/overview`)

Sections and their order come from the viewer's layout (Executive, Operations, Finance,
Warehouse; default from role, saved per user). The diagram below is the Operations layout in a
demo organisation; in a real organisation without connected systems, unavailable sections fold
into a single "Not available yet" panel and the setup checklist leads.


Ordered by what an operations manager does first: see the state, act on exceptions, then
understand trends.

```
Org name
Good morning, Amara                          [7 d | 30 d | 90 d] [Review exceptions ↓]
[Demo data] Last synchronised 4 min ago · Refreshed just now ⟳

┌ Open insights │ Active incidents │ Pending approvals │ Workflows │ Integrations ┐  summary strip
└───────────────┴──────────────────┴───────────────────┴───────────┴──────────────┘

┌ Priority exceptions (8/12) ───────────────┐ ┌ Pending approvals (4/12) ┐
│ severity · ref · detected                 │ │ oldest first             │
│ title / summary                           │ └──────────────────────────┘
│ [Recommended action]                      │ ┌ Active incidents ────────┐
│ View evidence ▾ → why · evidence table ·  │ │ segmented bar + counts   │
│   assumptions · limitations · provenance  │ └──────────────────────────┘
└───────────────────────────────────────────┘

┌ Order fill rate (8/12) ───────────────────┐ ┌ Stock at/below ROP (4/12)┐
│ latest · average · target; line + target  │ │ labelled bars by location│
│ [View as table]                           │ └──────────────────────────┘
└───────────────────────────────────────────┘

┌ Workflow execution (8/12) ────────────────┐ ┌ Recent operational events┐
├ Integration status ───────────────────────┤ │ timeline (4/12)          │
└───────────────────────────────────────────┘ └──────────────────────────┘
```

| Width | Behaviour |
|---|---|
| ≥1280px | As above, 12-column grid |
| 1024–1279px | Sidebar visible; exceptions and approvals stack; chart 7/12 + risk 5/12 |
| 640–1023px | Drawer navigation; summary strip 3 columns; panels single column |
| <640px | Summary strip 2 columns; search becomes an icon; tables scroll inside their panel; period control and primary action wrap |

Verified at 1440 × 1000, 834 × 1112 and 390 × 844 with no horizontal page overflow.

## Component states (`/system/components`)

Two-column grid of panels (buttons · badges · feedback · loading · empty · error · permission ·
table), single column on small screens.

## Planned module layouts (not built)

| Module | Layout pattern |
|---|---|
| Intelligence | Filterable table of insights → detail drawer (evidence, history, actions) so the list keeps its place |
| Incidents | Table + detail page with timeline (left 8) and ownership/related records (right 4) |
| Workflows | Template list → execution list → execution detail with a step timeline that highlights the current step |
| Integrations | Catalogue grid (the one place cards are justified: each is a product) → connection detail with sync history table |
| Administration | Settings layout: section nav (left) + forms with grouped fields and consequence text |

## Sign-in screens (`/login`, `/register`, `/verify-email`, `/forgot-password`, `/reset-password`, `/invite`)

Split layout at ≥1024px: Dark Roast brand panel (5/12) with the Newsreader statement, form column
(7/12) with a 400px form. Below 1024px the brand panel is replaced by the wordmark above the form.

## Administration (`/admin/members`, `/roles`, `/audit`, `/organisation`) and account (`/account/profile`, `/security`)

Page header (Newsreader title, one-sentence purpose, primary action right) over panels. Tables
for lists (members, invitations, audit, role matrix); 880px reading width for settings forms.
Pages a role can't use are hidden from navigation and show the permission-denied state if opened
directly.
