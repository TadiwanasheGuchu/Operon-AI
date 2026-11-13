# 0013 — Harbour-and-sky palette and a lighter structure

**Status:** Accepted (2026-11-13). Supersedes the colour section of ADR 0007.

**Context.** The product owner found the coffee palette too brown, and the interface generic. The
genericness came mostly from structure: a heavy dark sidebar and identical bordered cards everywhere,
both of which the design brief warns against.

**Decision.**

- **Palette ("harbour and sky"), tokens in `apps/web/src/styles/tokens.css`:**
  - Deep Sea `#0D2638`: text and the sign-in brand panel.
  - Ocean `#1667A0`: primary actions and links; 6.0:1 with white text.
  - Sky `#3FA2E0`: decorative accent only, such as the logo node.
  - Mist `#DDEFFB`: selected rows and the active navigation item.
  - Foam `#EDF6FC`: hover and sunken surfaces.
  - Cloud `#F4F8FB`: the app background.
  - Haze `#DCE5EC`: lines.
  - Steel `#7F92A1`: icons and control borders.
  - Status colours stay green, amber and red. "Info" is teal so it never reads as the brand blue.
  - Every text pair meets WCAG 2.2 AA.
  - No gradients, and no purple: the brief's list of generic-AI visuals still applies.
- **Light sidebar.** White with a hairline border; the active item uses Mist with Ocean text and a
  marker. Deep Sea appears only on the sign-in panel.
- **Fewer cards.**
  - `Panel flat` renders an open section divided by a rule, aligned to the page edge. It's used for
    primary reading content on the insight, incident and purchase-request pages.
  - Compact cards remain for side summaries and the dashboard.
  - Panel radius drops from 12px to 10px.

**Consequences.**

- Components keep using semantic tokens. Only the brand names changed (espresso, coffee-bean,
  latte, … became deep-sea, ocean, shallows, …), and no raw hex values remain in components.
- `docs/design/frontend-design-direction.md` still describes the coffee palette. For colour, this
  ADR takes precedence; the brief's other guidance (type, density, provenance, accessibility) is
  unchanged.
