# Layouts

Single-page app — there is no separate shared shell/nav/sidebar component (no other pages exist to share one with). The "layout" is the one page's own outer structure in `index.html`.

## Page shell (`index.html` lines 178-235)

```html
<div class="wrap">
  <header>
    <h1>♠ BTC 15 ♦ ABOVE OR BELOW ♣</h1>
    <div class="sub">mirrors Robinhood's live BTC 15-min market, straight from the exchange</div>
  </header>

  <div class="panel status-bar">
    <div>
      <div class="plain-sentence" id="plainSentence">Loading the table…</div>
      <div class="rail-track" id="railTrack"><div class="rail-fill" id="railFill"></div></div>
    </div>
    <div class="status-row">
      <div class="status-zone zone-price">
        <div class="price-compare">
          <div class="pc-item"><div class="pc-label">Now</div><div class="pc-value now" id="livePrice">—</div></div>
          <div class="pc-vs">vs</div>
          <div class="pc-item"><div class="pc-label">Target</div><div class="pc-value target" id="strikeValue">—</div></div>
        </div>
        <div class="pc-delta" id="liveDelta"></div>
      </div>
      <div class="status-zone zone-lean lean-block">
        <div class="lean-track"><div class="lean-chip" id="leanChip"></div></div>
        <div class="lean-label" id="leanLabel">reading the table…</div>
      </div>
      <div class="status-zone zone-link">
        <a class="rh-link" id="rhLink" href="#" target="_blank" rel="noopener">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 17L17 7M17 7H8M17 7V16"/></svg>
          View current round on Robinhood
        </a>
      </div>
    </div>
  </div>

  <div class="panel stats-strip" id="statsStrip">
    <div class="stat-tile"><div class="num yes" id="statYes">0</div><div class="label">Yes wins</div></div>
    <div class="stat-tile"><div class="num no" id="statNo">0</div><div class="label">No wins</div></div>
    <div class="stat-tile"><div class="num" id="statStreak">—</div><div class="label">Current streak</div></div>
    <div class="stat-tile"><div class="num" id="statLongest">—</div><div class="label">Longest streak</div></div>
    <div class="stat-tile"><div class="num" id="statChop">—</div><div class="label">Chop rate</div></div>
  </div>

  <div class="panel last-settled" id="lastSettled"></div>

  <div class="panel">
    <div class="bigroad-head">
      <h2>Big Road</h2>
      <div class="timeframe-select" id="timeframeSelect">
        <button class="tf-btn active" data-hours="24">24H</button>
        <button class="tf-btn" data-hours="168">7D</button>
        <button class="tf-btn" data-hours="720">30D</button>
        <button class="tf-btn" data-hours="8760">1Y</button>
      </div>
    </div>
    <div class="bigroad-scroll" id="bigroadScroll"><div class="bigroad-grid" id="bigroadGrid"></div></div>
  </div>

  <footer>live lean is instant-price only, not the settlement rule · settlement = Kalshi's own 60s-average result</footer>
</div>
```

Renders, top to bottom: title/subtitle header → status panel (plain-English sentence + countdown rail, then a row of price-compare / live-lean gauge / Robinhood link) → stats-strip (5 KPI tiles) → last-settled one-liner → Big Road panel (heading + timeframe filter + horizontally-scrolling bead grid) → footer disclaimer.

`.wrap` is `max-width: 640px` on mobile, widening at two breakpoints (900px, 1200px) via `@media` queries — see `theme.md` for the exact values. No sidebar, no top nav — this is the entire visible surface of the app.
