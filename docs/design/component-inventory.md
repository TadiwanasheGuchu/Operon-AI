# Component inventory

Live reference: `/system/components` (visible in demo and development builds only).
Every component consumes semantic tokens; none hard-code brand hex values (the destructive
button's hover/active shades are the documented exception, pending tokens).

## Primitives — `src/components/ui`

| Component | States | Notes |
|---|---|---|
| `Button` | primary · secondary · tertiary · destructive · quiet; sm · md · icon; hover · active · focus-visible · disabled · loading (`aria-busy`) | `asChild` renders links with button styling |
| `Badge`, `StatusBadge`, `SeverityBadge` | healthy · in progress · pending · needs attention · failed · resolved · paused · disconnected; critical · high · medium · low | Always icon + text |
| `Panel`, `PanelHeader`, `PanelBody` | — | Default section container |
| `Tooltip` | delayed open, keyboard focus opens | For icon-only controls; never the only way to read a value |
| `DropdownMenu*` | highlighted · disabled | Radix: arrow keys, typeahead, Esc |
| `Dialog`, `DrawerContent` | open/close with focus trap and return | Drawer for mobile navigation and contextual detail |
| `Skeleton` | pulse (disabled under reduced motion) | Mirrors final layout |
| `Kbd` | — | Keyboard hints |

## Feedback — `src/components/feedback`

| Component | Role | Use |
|---|---|---|
| `InlineAlert` (info · success · warning · danger) | `status` / `alert` | Explains what happened and what to do next |
| `EmptyState` | `status` | Says why it's empty and how data will arrive |
| `ErrorState` | `alert` | Retry action + request ID for support |
| `PermissionDenied` | `status` | Names the missing permission (e.g. `workflows.approve`) |
| `ToastProvider` / `useToast` (success · danger · info) | `status` / foreground for errors | Confirmation after an action; never the only record of an error that needs fixing |
| `ConfirmDialog` | `alertdialog` | Destructive or high-impact actions; states the consequence; busy state blocks double submit |

## Forms — `src/components/ui/form.tsx`

| Component | Notes |
|---|---|
| `Field` | Visible label, hint and error wired with `aria-describedby` / `aria-invalid` (render prop) |
| `Input`, `Select` | 40px, `border-line-control` (3:1), danger border when invalid |
| `Switch` | `role="switch"`, labelled by the setting's title, described by its consequence |

Forms use React Hook Form + Zod; schemas live in `features/*/schemas.ts` and mirror the API's
Pydantic validation, which stays authoritative.

## Data display — `src/components/data-display`

| Component | Notes |
|---|---|
| `Table`, `Th`, `Td`, `Tr`, `TableScroll` | 36px header, 44px rows, hairline rows, numeric alignment, horizontal scroll inside the panel on small screens |
| `ProvenanceBadge` | live · demo · stale · unavailable, with screen-reader hint |
| `Delta` | Arrow + signed number + "vs previous N days"; colour only reinforces |

Planned: sortable/filterable data table with row actions and bulk selection (first needed by
Intelligence and Incidents, Phase 4).

## Layout — `src/components/layout`

| Component | Behaviour |
|---|---|
| `AppShell` | Skip link, fixed sidebar ≥1024px, drawer below, demo banner, global shortcuts (⌘K, /, ⌘\\) |
| `SidebarContent` | Wordmark, organisation switcher, grouped navigation from the module registry, live platform status, collapse control |
| `Header` | Menu button (<1024px), breadcrumb, search launcher, notifications, help, account |
| `CommandLauncher` | Combobox + listbox pattern, arrow keys, Enter, only real destinations |
| `PlatformStatus` | Live `GET /api/v1/health/ready`, `aria-live` |

## Domain — `src/components/domain/dashboard`

`IndicatorStrip` (unavailable values render as a muted dash with the reason, never 0),
`InsightsPanel` (evidence disclosure), `ApprovalsPanel`, `IncidentSeverity`, `FillRateChart`
(chart ↔ table toggle, screen-reader summary), `InventoryRisk` (directly labelled bars),
`WorkflowsTable`, `IntegrationsStatus`, `ActivityFeed`, `GettingStarted`, `TeamPanel`,
`NotAvailable` (one compact list instead of many empty panels), `LayoutControl`, `PeriodControl`.
Every section panel shows a `ProvenanceBadge` in its header.

`features/dashboard/arrange.ts` decides what renders: ready sections in layout order (wide = 8
columns, narrow = 4, dense packing), unavailable ones folded into `NotAvailable`, restricted ones
omitted, a finished setup checklist hidden.

## Navigation registry

`src/components/navigation/registry.ts` lists every module with its roadmap phase and an
`implemented` flag. Only implemented modules render, in the sidebar or the command launcher, so
there are no dead links. Unimplemented routes return 404.
