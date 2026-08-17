# Extractable Components

Single-page app with no separate layout components (no nav/sidebar/header shared across pages — there's only one page). Nothing here is a strong candidate for extraction under the skill's own guidance ("skip basic UI primitives... too simple to warrant extraction, better as inline HTML in drafts") — every pattern below is simple, appears only within this one page, and is naturally regenerated inline by the design draft rather than needing a shared `<sd-component>`.

Listed for completeness / in case a future page is added and would want to reuse these:

#### Basic Components
## StatTile
- Source: `index.html` (inline pattern, not a separate file) — see `components.md`
- Category: basic
- Description: KPI number + label tile, used 5× in a row for the 24h/timeframe stats strip
- Extractable props: value (string/number), label (string), colorClass (string, optional: "yes"|"no")
- Hardcoded: layout, border, background

## TimeframeButton
- Source: `index.html` (inline pattern) — see `components.md`
- Category: basic
- Description: pill-style filter button, 4 shown together (24H/7D/30D/1Y in current build; more will be added per this round's request)
- Extractable props: label (string), hours (number), active (boolean)
- Hardcoded: shape, colors

## BigRoadBead
- Source: `index.html` (inline pattern, generated dynamically in JS) — see `components.md`
- Category: basic
- Description: single settled-round result cell with a card-flip reveal animation
- Extractable props: result ("yes"|"no"), tooltip text
- Hardcoded: flip animation, card-back pattern, colors

**Recommendation for this design task**: skip Step 2.5 component extraction. There's no NavBar/Sidebar/Header/Footer worth extracting (this is genuinely one page, no shared shell), and the patterns above are simple enough that the skill's own "skip basic UI primitives" rule applies directly.
