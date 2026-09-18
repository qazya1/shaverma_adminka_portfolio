# Shaverma Admin — Master Design System

This file is the visual source of truth for the frontend. It is based on the
`ui-ux-pro-max` dashboard, dark-mode contrast, restaurant palette, typography,
accessibility, and responsive-layout guidance, refined to match the product
requirements and the backend's actual capabilities.

## Product and data boundaries

- Product: operational control plane for restaurant service instances.
- Primary user: one of two equal infrastructure administrators.
- Real dashboard entities: managed services, stored activity state, on-demand
  systemd state, environment files, and provisioning readiness.
- Do not present orders, client turnover, average cheque, guests, sales trends,
  or restaurant performance on an API-backed screen: the current backend
  exposes none of those values.
- Derived metrics may aggregate fields already returned by `GET /api/v1/services`.
- Local demo data must implement the same response shapes as the real API.

## Visual direction

- Premium, restrained dark SaaS interface; operational rather than decorative.
- Deep charcoal canvas, never pure black.
- Layered opaque surfaces with precise 1px borders; no glassmorphism.
- Warm amber is the only brand/action accent.
- Green and red are reserved for semantic operational states.
- Dashboard-only tonal surface variation and low-opacity radial warmth are
  permitted to separate the operational canvas; they must never compromise
  contrast or become decorative atmosphere.
- A small controlled glow may support the active navigation item, primary CTA,
  active status dot, or a KPI's semantic top edge. No neon fields, animated
  background, oversized radii, floating decorative blobs, or marketing-page
  composition.
- Information-dense but visually calm: grouping comes from spacing, alignment,
  borders, and type hierarchy.

## Color tokens

| Token | Value | Usage |
|---|---:|---|
| `--bg-canvas` | `#0d0e0f` | App background |
| `--bg-sidebar` | `#101113` | Persistent navigation |
| `--surface-1` | `#131517` | Primary panels |
| `--surface-2` | `#181a1d` | Inputs, nested rows, hover surfaces |
| `--surface-3` | `#1e2124` | Menus, elevated controls |
| `--border-subtle` | `#25282c` | Default 1px borders |
| `--border-strong` | `#34383e` | Selected/focused boundaries |
| `--text-primary` | `#f3f1ec` | Headings and primary content |
| `--text-secondary` | `#aaa8a1` | Supporting content |
| `--text-muted` | `#77766f` | Metadata and quiet labels |
| `--accent` | `#f2a33b` | Primary action and active navigation |
| `--accent-hover` | `#ffb454` | Hovered accent |
| `--accent-pressed` | `#d98a25` | Pressed accent |
| `--accent-soft` | `rgba(242, 163, 59, 0.12)` | Selected/quiet accent surface |
| `--on-accent` | `#1a1208` | Text/icons on accent |
| `--success` | `#4fbd82` | Running/healthy only |
| `--success-soft` | `rgba(79, 189, 130, 0.12)` | Success chip surface |
| `--danger` | `#e56b6b` | Failed/stopped destructive actions |
| `--danger-soft` | `rgba(229, 107, 107, 0.12)` | Error chip surface |
| `--warning` | `#d9a441` | Unknown/pending attention |
| `--warning-soft` | `rgba(217, 164, 65, 0.12)` | Warning chip surface |
| `--focus` | `#f6b85f` | 2px focus indicator |

Normal text must maintain at least 4.5:1 contrast. Meaningful component
boundaries and icons target at least 3:1 against adjacent surfaces.

## Typography

- Family: `Inter`, `SF Pro Text`, `Segoe UI`, system sans-serif fallback.
- Numeric metrics and technical identifiers use tabular figures.
- Page title: 32–40/1.08, weight 650, tracking -0.045em.
- Section title: 19/24, weight 640.
- Metric value: 38–46/1.1, weight 660, tabular figures.
- Body: 15/23, weight 400; dense table content may use 12–14px.
- Label: 11–12/16, weight 650, optional uppercase with 0.06em tracking.
- Technical values: 12/18, ui-monospace.
- Avoid display fonts and excessive bold weights.

## Spacing and layout

- Base rhythm: 4px. Common steps: 4, 8, 12, 16, 20, 24, 32, 40, 48.
- Desktop sidebar: 264px; compact desktop/tablet sidebar: 76px.
- Header: minimum 82px; content gutters: 40px at 1440, 32px at 1024,
  20px at 768.
- Dashboard max width: 1600px; content remains fluid below it.
- Panel padding: 24px. KPI cards: 24px with a 180px minimum height. Table
  cells: 12px vertical, 20px horizontal, with 82px rows.
- Radii: 6px controls, 10px panels, 12px modal maximum.
- Avoid cards nested more than one level deep.

## Elevation and borders

- Default panels use `1px solid var(--border-subtle)`.
- Hovered interactive rows use `var(--surface-2)`, a 3px amber inset edge,
  and keep dimensions stable.
- Subtle panel depth is permitted: `0 12px 30px rgba(0,0,0,.16)`; menus and
  dialogs use `0 18px 48px rgba(0,0,0,.42)`.
- No glow, blur, translucent cards, or gradient borders.

## Application shell

- Sidebar owns product identity, primary navigation, environment label, and
  account/logout at the bottom.
- Only real destinations are enabled. Future destinations appear as disabled
  roadmap items with a clear `Скоро` label rather than fake screens.
- Header owns breadcrumb/context, page title, concise description, and the
  page's single primary action.
- At 1024px the sidebar becomes icon-led and compact.
- At 768px and below it becomes an off-canvas drawer controlled by a labelled
  menu button; content never sits beneath it.
- At 560px and below the dashboard becomes one column: KPI cards stack,
  filters are full width, controls are 48px high, and the supporting header
  description remains visible. Below 680px the service table is replaced by a
  card list, rather than horizontally compressing desktop columns.

## Components

### Buttons

- Height 44px across the primary desktop dashboard and touch layouts.
- Primary: amber fill, dark text; one primary action per screen.
- Secondary: surface fill with border.
- Ghost: transparent, for low-priority toolbar actions.
- Danger: quiet red surface by default; stronger red only on confirmation.
- Include visible labels with SVG icons; icon-only controls require aria-label.
- Disabled state is both semantic and visual; preserve text contrast.

### Inputs and selects

- Persistent visible label; helper/error text below the control.
- 42px height desktop, 44px at narrow breakpoints.
- Background `surface-2`, subtle border, 2px amber focus ring with 2px offset.
- Validation happens after interaction, not on every keystroke.

### Status chips

- Compact 28px height, 999px radius permitted only for chips.
- Dot/icon plus text: status cannot be communicated through color alone.
- Active/running = green; inactive/stopped = neutral; failed = red;
  unchecked/pending = amber.

### Metric cards

- One flat panel level; label, value, concise definition, optional restrained
  semantic icon.
- Values are aggregates of currently loaded API data, not invented history.
- Loading uses a fixed-size skeleton; empty/error states keep layout stable.

### Tables

- Sticky header where useful, clear row hover, no zebra striping.
- Technical identifiers use monospace and allow safe wrapping.
- Actions remain grouped and keyboard reachable.
- On narrow screens the table may scroll horizontally; the page itself must not.
- At phone widths, each service card exposes name, text-labelled status,
  `system_name`, systemd unit, `.env`, and the available start/stop action.
  Secondary live-state data and status refresh live inside a native `details`
  disclosure. Do not squeeze labels into unreadable columns or require a
  horizontal table scroll.
- Empty state explains why it is empty and offers the relevant real action.

### Dialogs and dropdowns

- Use for confirmation or secondary actions, never for primary navigation.
- Visible title, reason, close/cancel path, focus containment and Escape support.
- Destructive confirmation names the affected service.

## Dashboard composition

1. Header: `Обзор заведений`, current operational context, `Новое заведение`.
2. Four derived metrics: total, active, stopped, status not checked.
3. Operational distribution panel based on the same service collection.
4. Managed services table with stored/live state and existing actions.
5. No sales chart or activity feed until matching backend endpoints exist.

## Business analytics (local mock only)

- `business.html` is a separate frontend-only prototype for the future
  restaurant analytics contract. It must not call or extend the current backend
  API until an analytics endpoint is actually provided.
- The screen treats the figures as client monitoring, never Shaverma P&L:
  orders, client turnover, active orders, average check, order-flow statuses,
  active tasks, cancelled orders, and open points. Points are ranked by client
  turnover and show their client context.
- Delivery is a separate operational channel: show delivery figures only for
  client points where delivery is enabled, including delivery orders and their
  client turnover.
- Period and point filters update the same local data model. Mock data is kept
  in `frontend/js/business-demo.js`, isolated from the service-management mock
  routes, so a future API adapter can replace only the source layer.
- The page reuses the premium charcoal/amber visual system; green is reserved
  for live/open status, amber for attention/primary data, and red for cancelled
  order attention. To distinguish the local client-monitoring workspace from
  service administration, it may use one restrained desaturated cyan data tone
  for telemetry, comparisons, and non-interactive data surfaces — never for
  danger/success semantics, CTA treatment, or an AI-style gradient. On mobile,
  cards and point rows reflow without horizontal scrolling. At 360–430px the
  four summary cards may remain in a readable 2×2 grid; at 320px they become
  one column. Period controls are full width and at least 44px high, while the
  technical background grid is removed to preserve contrast.

## New-service wizard

- The new-service flow is a four-step onboarding wizard: basic data, channels,
  optional integration keys, and review/create. It sends the unchanged
  `POST /api/v1/services` payload only on the final step.
- Desktop composition is two-thirds working area and one-third sticky live
  preview. The preview mirrors name, domain, `system_name`, human-readable
  channel states, and activation state while the user types.
- Controls use field-level surfaces with a label, plain-language explanation,
  and 48px input. Technical identifiers use monospace only in the value.
- Boolean backend fields remain native checkboxes in code but render as labelled
  toggle switches; raw field names such as `is_active` are not user-facing.
- Optional entry keys belong inside a collapsed `details` disclosure.
- After creation, do not imply automatic provisioning. Render the actual
  endpoint-backed sequence: record, directories, uploaded backend, generated
  environment, built frontend, nginx, and systemd. Status labels come only from
  `GET /api/v1/services/{id}/provision/status`.
- When every real provisioning status is done, replace the action timeline with
  a success state and real navigation actions. On phones the live preview is an
  inline disclosure and all wizard/provision controls occupy a single column.

## States and motion

- Hover/focus transitions: 140–180ms.
- Panel/content entrance: opacity + translateY(6px), 220ms maximum.
- Phone status chips, the active navigation item, and the primary CTA may use
  a restrained, low-opacity semantic glow to support scanning. It is never a
  decorative ambient effect and does not replace visible text or borders.
- Never animate width, height, table layout, or continuously moving decoration.
- `prefers-reduced-motion: reduce` disables non-essential transforms and smooth
  scrolling; final readable state is always present.
- Loading: skeleton for structured data, spinner only for a button action.
- Error: specific message plus retry action.
- Empty: plain explanation plus one valid next step.

## Accessibility and responsive QA

- Semantic landmarks, skip link, sequential headings, visible focus.
- Native buttons/links/inputs; no clickable generic divs.
- All SVG icons are decorative beside text (`aria-hidden="true"`) or receive an
  accessible name when standalone.
- Password managers and paste remain enabled.
- Verify 1440, 1024, and 768 widths, plus 375px for safe degradation.
- No horizontal scrolling at page level; only explicit table wrappers may scroll.
- Phone layouts account for `safe-area-inset-*`; inputs use 16px text to avoid
  browser zoom and adjacent touch controls keep at least an 8px gap.
- Keyboard operation must cover navigation, filters, service actions, dialogs,
  and logout.
