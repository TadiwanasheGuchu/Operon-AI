# Operon AI — Frontend Design Direction

> **Document:** Frontend visual identity, UI/UX standards and implementation brief  
> **Product:** Operon AI — Autonomous Enterprise Operations Platform  
> **Audience:** Claude Code, product designers and frontend engineers  
> **Status:** Design direction for the first production-quality interface  
> **Primary instruction:** Build a distinctive, premium enterprise product. Do not produce a generic AI SaaS dashboard.

---

## 1. Design vision

Operon AI should feel like a serious operational instrument used by executives, operations managers and enterprise teams—not a chatbot wrapped in an admin template.

The visual identity should combine:

- The warmth and material richness of coffee, espresso, roasted cacao and parchment.
- The precision and clarity of modern enterprise software.
- Editorial typography and considered composition.
- Information-dense dashboards that remain calm and easy to scan.
- Subtle, purposeful motion and interaction feedback.
- A recognisable visual language that can scale across dashboards, reports, workflows and marketing pages.

### Brand attributes

**Grounded · Intelligent · Assured · Precise · Warm · Operational · Human**

The design should communicate trust and competence. It must not feel playful, gimmicky, futuristic for its own sake, or like a template generated from a prompt.

### Design principle

> Warmth in the brand. Precision in the interface. Intelligence in the details.

Use the coffee palette as a recognisable brand signature, not as a reason to make every screen brown. Large working surfaces should remain light and neutral so that dense information is readable for long periods.

---

## 2. Visual references and design research

Use these references to study craft, hierarchy, composition and interaction. They are references for design principles—not layouts to copy.

### Dribbble references

1. **Enterprise SaaS Dashboard UI/UX Design**  
   https://dribbble.com/shots/27137769-Enterprise-SaaS-Dashboard-UI-UX-Design  
   Study: modular data layout, restrained colour, risk indicators and dashboard scalability.

2. **Modern SaaS Analytics Dashboard**  
   https://dribbble.com/shots/27145597-Modern-SaaS-Analytics-Dashboard-Website-UI-Design  
   Study: editorial typography, warm neutral tones, whitespace and a strong product-storytelling hierarchy.

3. **Minimal SaaS Dashboard — Clean UI and Visual Hierarchy**  
   https://dribbble.com/shots/26989557-Minimal-SaaS-Dashboard-Clean-UI-Visual-Hierarchy  
   Study: spacing, component rhythm, readable data density and restrained card treatments.

4. **Enterprise Dashboard for Business Metrics**  
   https://dribbble.com/shots/25999987-Enterprise-Dashboard-UI-for-Business-Metrics-Conversions  
   Study: neutral surfaces, green operational accents and clear metric hierarchy.

5. **B2B SaaS Dashboard UI**  
   https://dribbble.com/shots/26892648-B2B-SaaS-Dashboard-UI  
   Study: modular widgets, muted colour and scalable interface patterns.

6. **Dribbble Enterprise Dashboard collection**  
   https://dribbble.com/tags/enterprise-dashboard  
   Use for ongoing visual research. Filter for real enterprise workflows, not just attractive concept shots.

### Awwwards and digital craft references

1. **Terminal Industries**  
   Website: https://terminal-industries.com/  
   Studio case study: https://www.rejouice.com/work/terminal-industries  
   Study: how a complex B2B logistics product can have a distinctive brand, confident typography, real operational imagery and a clear product narrative. Notice how the product is explained through actual operational situations rather than generic technology graphics.

2. **Awwwards**  
   https://www.awwwards.com/  
   Study: art direction, typography, interaction craft, transitions and responsive execution. Borrow the quality of execution, not excessive motion.

3. **SaaS web design award archive**  
   https://www.webdesignawards.io/categories/saas  
   Study: clarity of product proposition, originality, content hierarchy, responsive experience and technical quality.

4. **Enterprise software website examples**  
   https://uidiscovery.com/websites/enterprise-software  
   Study: enterprise positioning, navigation, feature explanation and product proof.

### How to use references

- Extract design principles, not screenshots.
- Never reproduce another designer's exact layout or branding.
- A dashboard concept shot is not proof that its interaction model works.
- Prioritise real product usability over portfolio-shot decoration.
- Every visual decision must support a user task, brand recognition or comprehension.

---

## 3. Colour system — Coffee, parchment and mineral neutrals

The colour system should be recognisable and consistent. Coffee brown is the primary brand colour. Use parchment and warm stone as the main canvas, with muted green, amber and red reserved for operational meaning.

### Core brand palette

| Token | Hex | Usage |
|---|---|---|
| Espresso | `#2B1D18` | Primary brand, strongest text, selected navigation |
| Dark Roast | `#3A2922` | Sidebar, dark brand surfaces, strong buttons |
| Coffee Bean | `#51382D` | Primary interactive brown |
| Mocha | `#765744` | Secondary emphasis, charts, hover details |
| Caramel | `#A9784F` | Small brand accent, highlights |
| Bronze | `#B58A62` | Decorative or data accent used sparingly |
| Latte | `#D7C2A8` | Soft emphasis, selected backgrounds |
| Oat Milk | `#E9DDCE` | Subtle panels and dividers |
| Parchment | `#F6F1E9` | Main application background |
| Warm White | `#FCFAF6` | Primary content surfaces |
| Stone | `#E7E1D8` | Borders and separators |
| Muted Taupe | `#94877B` | Secondary text and quiet icons |

### Functional palette

These colours communicate status and must remain distinguishable from the brand palette.

| Token | Hex | Meaning |
|---|---|---|
| Operational Green | `#39745B` | Healthy, completed, available |
| Green Tint | `#EAF2EC` | Positive status background |
| Warning Amber | `#A96F24` | Needs attention, approaching threshold |
| Amber Tint | `#F8F0E2` | Warning background |
| Critical Red | `#B64D43` | Failure, urgent, critical |
| Red Tint | `#F8EAE7` | Critical background |
| Information Blue | `#55758A` | Informational state, neutral system notice |
| Blue Tint | `#EAF0F3` | Informational background |

### Colour usage rules

- Use Espresso and Dark Roast for brand identity and high-contrast navigation.
- Use Parchment or Warm White for the majority of the working interface.
- Use Coffee Bean for primary actions; do not make every button brown.
- Use Caramel and Bronze as small accents, never as large blocks behind body text.
- Use functional colours consistently for status, not decoration.
- Do not use gradients as a default background treatment.
- Do not use low-contrast beige text on parchment.
- Never communicate status using colour alone; include labels, icons or shape.
- Charts should use a restrained, accessible palette and clearly distinguish series.
- Provide a dark theme only as a deliberate future theme, not as the default design direction.

### CSS variables

Implement the palette as central design tokens. Do not scatter raw hex values throughout components.

```css
:root {
  --color-espresso: #2B1D18;
  --color-dark-roast: #3A2922;
  --color-coffee-bean: #51382D;
  --color-mocha: #765744;
  --color-caramel: #A9784F;
  --color-bronze: #B58A62;
  --color-latte: #D7C2A8;
  --color-oat-milk: #E9DDCE;
  --color-parchment: #F6F1E9;
  --color-warm-white: #FCFAF6;
  --color-stone: #E7E1D8;
  --color-muted-taupe: #94877B;

  --color-success: #39745B;
  --color-success-bg: #EAF2EC;
  --color-warning: #A96F24;
  --color-warning-bg: #F8F0E2;
  --color-danger: #B64D43;
  --color-danger-bg: #F8EAE7;
  --color-info: #55758A;
  --color-info-bg: #EAF0F3;
}
```

---

## 4. Typography

Typography must give Operon AI its own character. Avoid relying on the default look of a starter template.

### Recommended type system

- **Primary UI font:** `DM Sans` or `Manrope` — use one consistently for navigation, controls, body copy and tables.
- **Editorial/display font:** `Newsreader` — use sparingly for selected marketing headlines, section statements or report covers.
- **Monospaced font:** `IBM Plex Mono` — use for IDs, timestamps, event codes, technical metadata and compact numeric labels.

Suggested starting point: DM Sans + Newsreader + IBM Plex Mono.

### Typography rules

- Use a clear type scale and consistent line heights.
- Use sentence case for most interface labels.
- Use uppercase only for small metadata labels where it improves scanning.
- Avoid oversized headings inside dense application pages.
- Use tabular numerals for financial values, counts and time-series data.
- Use monospaced typography for technical metadata only, not whole paragraphs.
- Do not use several unrelated font families.
- Do not use thin font weights for important data or small text.

### Suggested scale

| Role | Size |
|---|---|
| Marketing hero | 56–72px desktop, responsive down |
| Page title | 28–34px |
| Section heading | 18–22px |
| Card heading | 14–16px |
| Body | 14–16px |
| Table | 13–14px |
| Metadata | 11–12px |

---

## 5. Iconography

Use **Lucide icons** consistently. Use the `lucide-react` package and a central icon mapping where practical.

### Icon style

- Outline icons, consistent stroke width.
- Default stroke width around 1.75–2.
- Standard sizes: 16px for compact controls, 18px for navigation, 20px for standard actions, 24px for prominent empty states.
- Use filled icons only for selected states or where the icon family requires it.
- Align icons optically with labels.
- Use tooltips for icon-only actions.
- Never mix Lucide, Font Awesome, emoji and random SVG packs in the same interface.

### Suggested icon mapping

| Area | Lucide icon |
|---|---|
| Overview | `layout-dashboard` |
| Intelligence | `scan-search` |
| Workflows | `workflow` |
| AI Agents | `bot` |
| Incidents | `siren` |
| Integrations | `plug` |
| Knowledge Centre | `library` |
| Reports | `chart-no-axes-combined` |
| Organisation | `building-2` |
| Users | `users` |
| Security | `shield-check` |
| Audit trail | `scroll-text` |
| Notifications | `bell` |
| Search | `search` |
| Settings | `settings-2` |
| Approvals | `clipboard-check` |
| Finance | `wallet` |
| Procurement | `shopping-basket` |
| Inventory | `boxes` |
| Logistics | `truck` |
| Healthy system | `activity` |
| Warning | `triangle-alert` |
| Failure | `circle-x` |
| Success | `circle-check` |
| External link | `external-link` |
| More actions | `ellipsis` |

Do not use an icon if its meaning is unclear. Pair less familiar icons with labels.

---

## 6. Layout and application shell

### Overall direction

Use a structured, editorial enterprise workspace. The layout should feel deliberately composed, not like a collection of floating cards.

### Desktop shell

- Left navigation rail/sidebar: approximately 248–264px expanded.
- Collapsed sidebar: approximately 72px.
- Main workspace: flexible, with a sensible maximum content width for reading-heavy pages.
- Top header: compact, approximately 64–72px.
- Main content padding: 28–36px desktop, 20–24px tablet, 16px mobile.
- Use a consistent 4px spacing foundation.

### Sidebar

Use Dark Roast or Espresso as the primary navigation surface, with warm off-white text.

Include:

- Operon wordmark and a distinctive, simple brand mark.
- Organisation switcher.
- Main navigation grouped by purpose.
- Clear active state using a subtle Latte or Caramel treatment.
- A restrained help/support area.
- User profile and account controls.

Avoid making every navigation item a large rounded pill. Active navigation should be obvious but quiet.

### Header

Include:

- Breadcrumb or current workspace context.
- Global search / command launcher.
- Time range or organisation context where relevant.
- Notification centre.
- Help access.
- User avatar and menu.

Do not fill the header with redundant buttons.

### Main content

Each page should have:

1. Clear page title.
2. One-sentence context where useful.
3. Primary action in a consistent position.
4. Useful filters and time range controls.
5. Main information arranged by task priority.
6. Supporting information below or in a secondary panel.

Avoid identical card grids on every page. Choose layouts based on the information and task.

---

## 7. Dashboard design

The command centre should feel like a real operational control room translated into a refined, usable interface.

### Recommended dashboard composition

**Top area**
- Greeting or workspace title.
- Current organisation and selected reporting period.
- Last updated timestamp and data freshness indicator.
- Primary action, such as `Create workflow` or `Review exceptions`.

**Operational summary**
- Operational health.
- Active incidents.
- Pending approvals.
- Workflows in progress.
- Integration health.

Use a restrained metric strip or a few well-composed panels. Do not turn every metric into a giant rounded card.

**Main analysis**
- Operational performance trend.
- Department or process performance.
- Incident severity distribution.
- Workflow execution status.

**Action area**
- Priority exceptions.
- Pending approvals.
- Recent operational events.
- AI insights with evidence and a clear recommended next step.

### Data visualisation rules

- Use charts only when they help compare, understand change or identify anomalies.
- Label axes, units and time periods.
- Show the underlying value on hover and provide an accessible textual summary.
- Avoid 3D charts, decorative donut charts and meaningless gauges.
- Use direct labels where possible.
- Provide empty, loading and error states.
- Do not invent a health score without a documented calculation.
- Show data freshness and source when data is external.
- Distinguish demo, simulated, stale and live data clearly.

---

## 8. AI-specific interface: make intelligence useful, not theatrical

Operon AI can be an AI-powered product without looking like a generic AI product.

### Do not use

- Purple-to-blue gradients as the main identity.
- Glowing orbs, neural network backgrounds or floating particles.
- Robot mascots.
- Random sparkle icons everywhere.
- Chat bubbles as the default presentation for every AI capability.
- "Ask AI anything" as the centre of every page.
- Fake typing animations that delay useful information.
- AI-generated summaries with no source evidence.
- Unexplained confidence percentages.
- Large empty AI chat panels that dominate operational pages.

### Use instead

- Evidence-led insight panels.
- Clear explanation of the detected condition.
- Source records and affected systems.
- Severity and business impact.
- Recommended action and expected outcome.
- Approval controls for consequential actions.
- Transparent execution history.
- Clear distinction between AI suggestion and completed action.

### AI insight example

**Supplier delivery risk detected**

- Severity: High
- Source: Procurement system
- Affected purchase orders: 4
- Expected delay: 2–3 business days
- Evidence: Supplier delivery performance and current order status
- Recommendation: Review alternative approved supplier
- Actions: `View evidence` · `Create review task` · `Dismiss`

AI should be visually represented as a capability embedded into real operational work—not as decoration.

---

## 9. Component design language

Create a coherent component library before implementing many pages.

### Surfaces

- Prefer flat, clean surfaces with subtle borders.
- Use shadows sparingly and consistently.
- Use layered elevation only when it clarifies hierarchy, such as popovers and dialogs.
- Avoid excessive rounded cards.
- Standard card radius: 10–14px.
- Inputs and buttons: 8–10px.
- Large dialogs: 14–18px.
- Avoid pill-shaped controls everywhere.

### Buttons

Define clear variants:

- Primary: Coffee Bean background, Warm White text.
- Secondary: Warm White background, Espresso text, Stone border.
- Tertiary: transparent, text-first.
- Destructive: Critical Red.
- Quiet icon button: transparent with clear hover and focus states.

Buttons need hover, active, disabled, loading and focus-visible states.

### Tables

Tables are central to enterprise operations.

Include:

- Clear column headers.
- Numeric alignment.
- Sorting.
- Filtering.
- Search.
- Pagination or virtualisation when needed.
- Row selection where useful.
- Bulk actions.
- Status labels.
- Row-level action menu.
- Empty and loading states.
- Responsive behaviour.

Do not turn every table into a collection of cards on desktop. Dense information should remain easy to scan.

### Status badges

Use small, consistent badges for:

- Healthy
- In progress
- Pending
- Needs attention
- Failed
- Resolved
- Paused

Use status colour plus text. Avoid oversized colourful badges.

### Forms

- Use visible labels, not placeholder-only labels.
- Group related fields.
- Explain important business consequences.
- Validate inline.
- Show field-level errors.
- Preserve user input after recoverable errors.
- Use confirmation steps for destructive or high-impact actions.

### Dialogs and drawers

Use dialogs for focused decisions. Use side drawers for contextual detail that should preserve the current page.

Do not use modals for every small interaction.

### Feedback

Design toast, inline alert, confirmation and progress patterns. Feedback must explain what happened and what the user can do next.

---

## 10. Motion and interaction

Use motion to communicate state, hierarchy and cause/effect.

### Motion principles

- Short, purposeful transitions.
- Most interface transitions: 140–220ms.
- Larger panel transitions: 200–300ms.
- Use subtle easing.
- Animate opacity and small positional changes rather than large movement.
- Respect `prefers-reduced-motion`.
- Avoid parallax in the core dashboard.
- Avoid scroll-jacking.
- Avoid custom cursors in the application.
- Do not animate every card on page load.

### Useful interactions

- Sidebar collapse with a smooth width transition.
- Table row hover and selection feedback.
- Chart range changes with subtle transitions.
- Workflow nodes highlight as execution progresses.
- Incident timeline reveals events clearly.
- Insight panel expands to show evidence.
- Command launcher opens quickly with keyboard shortcut.
- Optimistic updates only where rollback and error handling are reliable.

Every interaction must have a functional purpose and keyboard-accessible equivalent.

---

## 11. Landing page direction

The public marketing site and the logged-in application should share one brand system but serve different purposes.

### Hero

Use a strong editorial headline and a real product interface preview.

Suggested headline:

**Understand your operations. Act with confidence.**

Supporting copy:

Operon AI connects operational data, identifies the issues that matter and helps teams coordinate the next action—with control at every step.

Primary CTA: `Request a demo`  
Secondary CTA: `Explore the platform`

### Landing page sections

1. Hero with distinctive product screenshot or carefully art-directed operational scene.
2. Trust / customer proof area (only real logos and testimonials).
3. Operational problem explained clearly.
4. Product capability overview.
5. Real workflow walkthrough.
6. Example operational insight with evidence.
7. Integrations ecosystem.
8. Security and governance.
9. Industry use cases.
10. Closing CTA.
11. Detailed footer.

### Visual storytelling

Use real-world operational imagery where it adds context: warehouses, distribution centres, manufacturing lines, logistics operations and people coordinating work.

Avoid generic stock imagery of people pointing at transparent screens. Avoid AI-generated abstract glowing brains, robot heads and fake dashboards.

The product interface should be the primary proof of the platform.

---

## 12. Responsive behaviour

The product must be designed for desktop first because it is an enterprise operations platform, but it must remain genuinely usable on tablets and phones.

### Desktop

- Full sidebar.
- Multi-column analysis layouts.
- Dense tables.
- Side-by-side evidence and action panels.

### Tablet

- Collapsible navigation.
- Reduced dashboard columns.
- Tables with priority columns and horizontal overflow where appropriate.
- Drawers instead of narrow side-by-side panels.

### Mobile

- Compact navigation or drawer.
- Single-column content.
- Prioritised metrics.
- Stacked filters.
- Tables transformed carefully into focused list rows only where necessary.
- Touch-friendly actions.
- No hover-only functionality.

Do not simply shrink the desktop layout.

---

## 13. Accessibility and usability standards

Target WCAG 2.2 AA.

Requirements:

- Keyboard navigation throughout.
- Visible focus indicators.
- Semantic HTML.
- Correct accessible names for icon-only controls.
- Sufficient text and non-text contrast.
- Proper heading hierarchy.
- Form labels and helpful validation.
- Accessible chart summaries.
- Reduced-motion support.
- Screen-reader announcements for important status changes.
- Do not rely on colour alone.
- Minimum practical touch target around 44×44px for important mobile controls.

Accessibility is part of product quality, not a later polish task.

---

## 14. Technical frontend standards

Recommended frontend stack:

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui as a component foundation, customised to the Operon design system
- Lucide React icons
- TanStack Query for server state where appropriate
- React Hook Form and Zod for forms
- A suitable chart library such as Recharts or Visx, selected based on actual chart needs

### Implementation rules

- Create central design tokens for colour, spacing, radius, typography and elevation.
- Build reusable primitives and domain-specific components.
- Keep page components focused.
- Separate API logic from presentation.
- Use typed API contracts.
- Avoid `any` unless there is a documented reason.
- Do not hardcode fake business data into production components.
- Clearly label seeded demo data.
- Build loading, empty, error and permission-denied states.
- Ensure components work with real backend data.
- Avoid installing multiple libraries that solve the same problem.
- Do not introduce a large animation library for trivial transitions.
- Keep the application fast and avoid unnecessary client-side JavaScript.

### Suggested frontend structure

```text
apps/web/
├── app/
│   ├── (marketing)/
│   ├── (auth)/
│   └── (workspace)/
├── components/
│   ├── ui/
│   ├── layout/
│   ├── navigation/
│   ├── data-display/
│   ├── feedback/
│   └── domain/
│       ├── dashboard/
│       ├── intelligence/
│       ├── workflows/
│       ├── incidents/
│       ├── integrations/
│       └── knowledge/
├── features/
├── hooks/
├── lib/
├── styles/
│   ├── tokens.css
│   └── globals.css
└── types/
```

Adapt to the existing repository rather than blindly replacing its structure.

---

## 15. Brand mark and visual identity

Create a simple, ownable Operon mark.

Potential creative directions to explore:

- Interlocking operational paths.
- A continuous loop representing connected systems.
- A modular geometric symbol representing coordinated operations.
- A restrained monogram based on the letter O.

The symbol should work at 16px, in the sidebar, on a favicon and in a monochrome setting.

Do not use a generic robot head, brain, sparkle or circuit-board logo.

The wordmark should be typographically confident and work independently of the symbol.

---

## 16. Content and microcopy

Use precise, human language.

Preferred terms:

- Operational health
- Active incidents
- Pending approvals
- Workflow execution
- Integration status
- Recommended action
- Evidence
- Last synchronised
- Requires attention

Avoid vague AI marketing language:

- Unlock the power of AI
- Supercharge your business
- Revolutionary intelligence
- Magic automation
- Your AI copilot for everything

Use specific language that explains what the product does and what the user can do next.

---

## 17. Anti-generic design checklist

Reject the implementation if it contains several of these patterns without a strong product reason:

- Purple/blue AI gradients.
- Glowing orbs and particle backgrounds.
- Robot illustrations.
- Sparkle icons scattered through the UI.
- Excessive glassmorphism.
- Identical rounded metric cards on every page.
- Giant empty chat interface as the primary dashboard.
- Excessive shadows.
- Too many pills and badges.
- Random gradients in charts.
- Decorative charts with no operational meaning.
- Generic stock photos of people pointing at screens.
- Inconsistent icon families.
- Over-animated page transitions.
- Placeholder content presented as real functionality.
- A dashboard that looks like an unmodified shadcn starter.

The product should look recognisable even if the logo is removed.

---

## 18. Required design deliverables before full implementation

Claude Code should first produce:

1. `docs/design/visual-direction.md` — final visual direction and rationale.
2. `docs/design/design-tokens.md` — colour, typography, spacing, radius, elevation and motion tokens.
3. `docs/design/component-inventory.md` — reusable components and states.
4. `docs/design/page-layouts.md` — layouts for dashboard and core modules.
5. A working application shell with sidebar, header and responsive behaviour.
6. A high-fidelity Operations Command Centre page using clearly labelled sample data.
7. A component state demonstration covering loading, empty, error, success, disabled and permission-denied states.

Do not implement every application module before the design system and shell have been reviewed.

---

## 19. Acceptance criteria

The frontend design foundation is accepted only when:

- The coffee and parchment palette is implemented through tokens.
- Typography is consistent and distinctive.
- Lucide icon usage is consistent.
- Sidebar and header work at supported screen sizes.
- The dashboard has a clear visual hierarchy.
- Operational data is readable and accurately labelled.
- Tables and charts are genuinely useful.
- AI insights display evidence and recommended actions.
- Loading, empty, error and permission states exist.
- Keyboard navigation and focus states work.
- The interface does not rely on generic AI visual tropes.
- The visual system is reusable across all modules.
- The application remains responsive and performant.

---

## 20. Instructions to Claude Code

You are the lead product designer and senior frontend engineer for Operon AI.

Before implementing:

1. Inspect the current repository and existing frontend.
2. Read the main `CLAUDE.md` and relevant architecture documentation.
3. Review the references linked in this document.
4. Identify reusable existing components and avoid unnecessary rewrites.
5. Propose the visual system and page structure.
6. Implement the design tokens and application shell first.
7. Build the Operations Command Centre as the first high-fidelity page.
8. Run the application and inspect it at desktop, tablet and mobile widths.
9. Fix visual inconsistencies, overflow, accessibility issues and broken interactions.
10. Document the design decisions.

Do not stop at a static mockup. The result must be a functioning frontend connected to the project's actual API contracts where available.

If backend endpoints are not ready, use a clearly separated typed mock-data adapter and label the environment as a demo. Do not mix demo data into production API logic.

**Final instruction:** Make Operon AI feel like a distinctive, premium enterprise operations product. Coffee-inspired warmth should establish the brand; disciplined typography, excellent information architecture, real functionality and precise interaction design should establish its credibility.
