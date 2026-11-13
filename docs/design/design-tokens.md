# Design tokens

Source of truth: [`apps/web/src/styles/tokens.css`](../../apps/web/src/styles/tokens.css).
Tailwind utilities are generated from the semantic tokens in `globals.css` (`@theme inline`). The
default Tailwind palette is removed (`--color-*: initial`), so raw colours like `bg-blue-500` don't
exist. Components can only use Operon tokens.

## Colour

### Brand: harbour and sky (ADR 0013)

| Token | Hex | Use | Contrast |
|---|---|---|---|
| `--color-deep-sea` | `#0D2638` | Strongest text; sign-in brand panel | 14.6:1 on canvas |
| `--color-harbour` | `#123A55` | Pressed primary, brand panel shapes | — |
| `--color-ocean` | `#1667A0` | Primary action, links, focus ring, chart series | 6.0:1 with white text; 5.1:1 on mist |
| `--color-ocean-deep` | `#0F4F7D` | Primary hover | 8.6:1 with white text |
| `--color-slate` | `#3D5568` | Secondary text, navigation text | 7.3:1 on canvas |
| `--color-sky` | `#3FA2E0` | Decorative accent only (logo node, inverse focus ring) | 2.8:1: never text |
| `--color-shallows` | `#CDE5F4` | Disabled fills, avatar tiles | — |
| `--color-mist` | `#DDEFFB` | Selected rows, active navigation item, skeletons | — |
| `--color-foam` | `#EDF6FC` | Hover and sunken surfaces | — |
| `--color-cloud` | `#F4F8FB` | Application canvas | — |
| `--color-white` | `#FFFFFF` | Panels, inputs, sidebar | — |
| `--color-haze` | `#DCE5EC` | Dividers and panel borders | decorative |
| `--color-steel` | `#7F92A1` | Icons, input borders (non-text) | 3.2:1 on white |
| `--color-steel-strong` | `#5B6F7E` | Muted text | 4.9:1 on canvas |

### Functional

| Token | Hex | Text on its tint |
|---|---|---|
| `--color-success` | `#2E7350` on `#E7F3EC` | 5.0:1 |
| `--color-warning` | `#8F5B12` on `#FBF1DF` | 5.1:1 |
| `--color-danger` | `#B13A30` on `#FBE9E6` | 5.1:1 |
| `--color-info` | `#0E6E7E` on `#E3F4F6` (teal, distinct from the brand blue) | 5.2:1 |

### Semantic (what components use)

| Token | Maps to | Tailwind |
|---|---|---|
| `--surface-canvas` / `-raised` / `-sunken` / `-selected` | cloud / white / foam / mist | `bg-canvas`, `bg-raised`, `bg-sunken`, `bg-selected` |
| `--surface-nav` / `-hover` / `-active` | dark roast / `#46332A` / `#524035` | `bg-nav`, … |
| `--text-primary` / `-secondary` / `-muted` | deep sea / slate / steel-strong | `text-ink`, `text-ink-secondary`, `text-ink-muted` |
| `--text-nav` / `-nav-muted` / `-nav-active` | slate / steel-strong / ocean | `text-ink-nav`, `text-ink-nav-muted` |
| `--border-subtle` / `-control` | stone / muted taupe | `border-line`, `border-line-control` |
| `--focus-ring` / `-inverse` | ocean / sky | applied globally via `:focus-visible` |
| `--chart-series` / `-reference` / `-grid` | mocha / taupe-strong / stone | used inline in charts |

### Charts

Single-series charts use Mocha (5.8:1 against the canvas). The brand browns **failed** the
categorical palette validator (lightness band and chroma floor), so they must not be used as a
multi-series palette. A validated categorical palette is required before the first multi-series
chart is built. Severity series use the status colours, always with labels.

## Typography

| Role | Family | Size / line height | Weight |
|---|---|---|---|
| Page title | Newsreader | 30/36 mobile, 34/40 desktop | 500 |
| Section heading (panel) | DM Sans | 15/24 | 600 |
| Body | DM Sans | 14/21 (body), 13/20 (dense) | 400 |
| Table | DM Sans | 13 | 400, numbers right-aligned `tabular-nums` |
| Indicator value | DM Sans | 28/36 | 600, proportional figures |
| Metadata label | DM Sans | 11, uppercase, 0.06em tracking | 500 |
| Machine facts | IBM Plex Mono | 11 | 400 |

Fonts are self-hosted at build time by `next/font` (no runtime requests to Google).

## Spacing, radius, elevation, layout

- 4px base grid. Panel padding 20px; page gutters 16 / 24 / 36px (mobile / tablet / desktop).
- Radius: controls 8px (`rounded-control`), panels 12px (`rounded-panel`), dialogs 16px, badges 6px.
- Elevation: `--shadow-popover` (menus, tooltips), `--shadow-dialog` (dialogs, drawers). Panels have none.
- Sidebar 256px / collapsed 72px; header 64px; content max width 1440px (1200px for reading pages).

## Motion

| Token | Value | Use |
|---|---|---|
| `--duration-fast` | 140ms | Hover, colour changes |
| `--duration-base` | 200ms | Dialogs, menus, disclosure |
| `--duration-panel` | 260ms | Sidebar width, drawers |
| `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | Everything |

Under `prefers-reduced-motion: reduce`, all durations become 0 and animations are suppressed. No
page-load animation; charts render without entry animation.
