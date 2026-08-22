# Design System — BTC 15 (Above or Below)

> Rewritten 2026-08-20 at v2.9.0. The previous version of this file described a navy/amber
> "Ledger Equities Desk" direction from v1.2.0 — that identity was **replaced** at v2.0.0 by the
> arcade-neon skin described below, and the app has since grown from one page to four (six after
> this round). Do not design against the old navy/amber palette; it is history.

## Product context

A spectator dashboard for Kalshi's `KXBTC15M` prediction market (the same market Robinhood surfaces
as "BTC 15 min"). Every 15 minutes a BTC price target is posted; 15 minutes later it resolves YES
(price finished at/above target) or NO. **The strike and settlement are never computed by this app**
— both are read live from Kalshi's public REST API, so the numbers are definitionally the same as
what Robinhood shows.

Kalshi chains rounds: `floor_strike(N) == settlement_value(N-1)` exactly. So a round's
round-over-round price delta *is* the number that decided it. This one fact underpins the Big Road
chips, the spread ledger, and the target-delta line.

**JTBD**: someone watching BTC's 15-minute swings — usually on a second monitor, for hours — wants
to glance over and know: what's the target, where is price relative to it, how much time is left,
and **is this round going to land YES?**

**No betting, no accounts, no crowd voting anywhere.** A "Personal Pick" exists but is
`localStorage`-only, single-browser, never sent to the server. Any predictive readout is framed as
an *estimate of what the market and recent movement suggest* — never advice.

### The objective (owner, this round, verbatim)

> "do not forget our objective, to correctly predict these rounds."

Design decisions get judged against this. Chrome that doesn't help answer *"will this land YES?"*
is decoration. The strongest available signals, in order:

1. **Kalshi's own live market odds** (`kalshi_yes_price` / `kalshi_no_price`) — a real
   order-book-derived probability, not an invented score. This is the anchor.
2. **Distance to strike vs. time remaining** — with the observed distribution of historical
   15-minute moves as the yardstick for whether that distance is still crossable.
3. Pattern history — streak, chop rate, Big Eye Boy.

## Pages

One backend, one database, one set of API endpoints. Each page is a **self-contained single HTML
file** with its own skin; they share data and the module system, not code.

| Route | Name | Identity |
|---|---|---|
| `/` | **Classic** | The main skin, and the owner's favourite. Fixed 2-column desktop grid. Reorder is button-based and stays scoped to two small groups — this fixed shape *is* its identity. |
| `/fluid` | **Fluid** | Same palette as Classic, but a genuine `flex-wrap` tile flow with fully unconstrained reorder. |
| `/ticket` | **The Ticket** | Light paper/ink exchange-ticket look. Serif headlines, monospace figures, flat offset "stamp" shadows, dashed tear-lines. |
| `/algo` | **ALGO Desk** | An AI making its own YES/NO call every round, tracked against the owner's. Cyan accent. |
| `/board` | **The Board** | *(this round)* Pegboard — drag to move, drag to resize. Executive glassmorphism. |
| `/gauge` | **The Gauge** | *(this round)* Dark brutalist. The confidence gauge is the entire page. |

Pages are cross-linked by a "Switch" icon button in every header opening a menu with the current
page dotted. New skins are added, not swapped in — the owner is browsing a gallery and cherry-picking
("keep building until i really find all the parts i like"). Nothing gets retired without being asked.

## The main skin (Classic / Fluid) — arcade neon

- **Palette**: near-black `#05060a` base; layered surfaces `#0d0f16` → `#12151f` → `#171b28` →
  `#232838`. Text: cream `#f5f7fa`, soft `#c7ccd9`, dim `#7d8399`, faint `#4b5066`.
  Accent **amber `#ffd23f`** (deep `#e6ac00`, soft `#ffe28a`).
  Semantic **green `#39ff88` = YES/up**, **red `#ff3d6e` = NO/down**, cyan `#22e6ff` for derived-road
  "repeat".
- **Typography**: system sans stack; **every numeric value carries `font-variant-numeric: tabular-nums`**
  with slight negative tracking so digits align in columns. This is load-bearing, not cosmetic.
- **Cards**: 14px radius, hairline `rgba(255,255,255,0.09)` border, a 160° sheen gradient, soft drop
  shadow. A thin amber gradient hairline along the top edge of the focal card.
- **Deltas** render as rounded-full **pill badges** (10%-opacity green/red background, signed $, a
  direction triangle) — not a quiet coloured number. Making the *difference* pop without mental
  subtraction is an explicit standing requirement.
- **Motion**: functional only — countdown rail drain, lean-chip easing, timer pulse when locked.

## The modular card system (all pages)

Every panel is a module with an always-visible header — this is a **primary interface, not a
settings-panel afterthought**:

```
.module-head   title + info-icon + [move-up] [move-down] [chevron] [eye]
.module-summary   condensed live text, visible only when collapsed
.module-body      the original content
```

- **Reorder** by button + `appendChild`/`insertBefore` — deliberately **not** HTML5 drag-and-drop
  (unreliable iOS Safari touch support). The Board's pegboard uses **Pointer Events** instead, which
  do work uniformly across mouse and touch.
- **Collapse** hides the body and shows the summary, built from data the render functions already
  compute — no extra polling.
- State persists in `localStorage`, one key per page, reconciled against known ids on load so adding
  a module later never silently hides content for someone with a saved layout.

### Tooltips — two tiers, one visual language

- **Hover** (desktop only): a colored CSS-only `[data-tip]::after` bubble containing **date and time
  only**. Disabled under `@media (hover: none)`.
- **Click** (all devices; touch goes straight here): one shared modal per page, opened via a single
  **delegated** listener — Big Road beads and ledger rows are destroyed and rebuilt on every render,
  so per-element listeners would leak. Content is the full structured, colour-coded breakdown.
- Never an inline slide-down.

## Hard constraints

- **Zero CDN. Zero external requests.** No Tailwind CDN, no icon fonts, no Google Fonts links. Icons
  are inline SVG. Web fonts are **self-hosted** and served by `app.py` off `/fonts/`.
- **One self-contained HTML file per page.** No build step, no bundler, no shared `<script src>` —
  the module and tooltip systems are copy-adapted per file. This is a real, accepted maintenance cost.
- Backend is **pure Python stdlib** (no pip dependencies).
- Must look right at **390px (iPhone), 768px / 1024px (iPad), 1440px (desktop)** — verified with
  screenshots, not assumed.
- Never overclaim. Derived roads carry a "good-faith simplification, not verified against a casino
  reference" caveat; the confidence readout carries an equivalent one.

## Owner's new style directions (this round)

Two specs supplied verbatim by the owner, each becoming one new page.

### A. Dark Brutalist Risk Gauge → `/gauge`

Dark glassmorphism + atmospheric glow. **Manrope** for headings/UI (200, 400, 700) and **Inter** for
data (weight **200** for large displays — this needs a real light weight, hence self-hosted fonts).
Base `#050505`.

Colour progression: `#55a630` → `#aacc00` → `#ffb703` → `#ff2d20`.

- 1px borders at `rgba(255,255,255,0.14)`.
- Grainy noise texture (opacity 0.15, `mix-blend-mode: overlay`) over soft radial gradients — a
  physical, dithered light effect.
- Needle motion uses `cubic-bezier(0.34, 1.56, 0.64, 1)` — snappy with a slight overshoot.
- Large portrait card (~760px) with heavily rounded corners (48–64px) and a multi-stop gradient
  border: `linear-gradient(135deg, rgba(170,204,0,0.8) 0%, rgba(255,255,255,0.1) 40%,
  rgba(255,183,3,0.5) 70%, rgba(251,133,0,0.8) 100%)`, 3px inner padding to reveal it, inner
  background `#0a0a0a` at 61px radius.
- **16-cell segmented gauge**: 24px tall cells, 5px radius, 7px gaps, with a 2px × 48px needle above
  carrying a dot and glow. Inactive cell `rgba(255,255,255,0.045)`; active takes the status colour,
  a 12px outer glow and `inset 0 0 8px rgba(255,255,255,0.28)`, 500ms transition.
- Giant value display: 150px, weight 200, vertical gradient `#ffffff → #cccccc`, with a 100px weight-300
  suffix and a tracked sub-label.
- Atmospheric bottom glow: radial ellipse (120% × 350px) using
  `color-mix(in srgb, var(--active-color) 48%, transparent)`, overlaid with an SVG fractal-noise
  filter (`baseFrequency 0.85`) at 0.15 opacity, `mix-blend-mode: overlay`.
- Bottom pill control bar: `rgba(0,0,0,0.5)`, 4px backdrop-blur, rounded-full, 10px bold tracked
  labels; active state takes the risk-level hex.

**Applied to this app**: "Risk Level" becomes **round confidence** — the gauge runs certain-NO on the
left to certain-YES on the right, the needle sits at the blended probability, the 98px status word is
the current call, and the 150px number is the confidence percentage. The band labels become
NO LIKELY / LEANING NO / LEANING YES / YES LIKELY.

### B. JARVIS OS — Executive Glassmorphism → `/board`

"Professional Futurist." Base `#0a0a0c`. Glass panels: `rgba(255,255,255,0.03)` with
`backdrop-filter: blur(24px)` and `1px solid rgba(255,255,255,0.05)`. Radius 24–32px on containers,
12–16px internally. Shadow `0 8px 32px rgba(0,0,0,0.37)`.

Type: **Plus Jakarta Sans** headings/UI (400–800) + **JetBrains Mono** for technical data.
*(Substitution in use: Manrope covers the geometric-humanist heading role and is already being
self-hosted for The Gauge, so The Board uses Manrope rather than adding a fourth font file.)*

Colour: cyan `#22d3ee` primary/active, blue `#0ea5e9` secondary, emerald `#4ade80` positive, caution
yellow, alert red `#ef4444`. Ultra-thin low-opacity borders throughout.
Transitions `cubic-bezier(0.4, 0, 0.2, 1)`, subtle `translateY(-4px)` hovers. Minimalist stroke icons.

Structure: a slim nav rail, a heavy central workspace, a contextual briefing panel, and a **floating
bottom system status bar** (80px, `backdrop-blur-xl`, 1px top border) carrying circular SVG meters —
40px diameter, 2.5px stroke, `stroke-dasharray: 100` with a computed offset, tiny monospace centre
percentage, two-line label stack beside it. Plus an **AI Insight badge**: 128px wide,
`rgba(255,255,255,0.05)`, 12px padding, an 8px black uppercase state-coloured label over 10px
`white/50` clamped body text.

**Applied to this app**: the three circular meters become **Round Progress**, **Lean Strength** and
**Market Confidence** — all three are genuinely 0–100% values. The AI Insight badge becomes the
confidence engine's current call plus its top reason. The 256px sidebar shrinks to a slim icon rail
so the pegboard gets full width, and container radius pulls back to ~16px because 24–32px reads
bubbly once tiles sit adjacent on a grid.

## The Board's pegboard (new capability)

12-column grid, 44px auto-rows, 10px gap; each tile placed by CSS custom properties driving
`grid-column: var(--x) / span var(--w)`. Drag from the module header (1:1 `transform` tracking while a
dashed placeholder snaps to the target cell), resize from a bottom-right grip, both on **Pointer
Events** with `setPointerCapture`. On drop: push overlapping tiles down, then compact upward. A dotted
peg-hole overlay sized to the exact cell pitch appears only while dragging. Below 900px the grid
collapses to a single column and drag/resize no-op behind a `matchMedia` guard — a 12-column pegboard
on a phone is not usable, and stacking is the honest answer.
