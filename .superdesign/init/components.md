# Components

No component library, no framework — these are repeated CSS class + HTML patterns within the single `index.html` file, not separate files. Full source (CSS from `theme.md`, HTML inline below) for each reusable pattern.

## Panel
The base card used for every section on the page.
```html
<div class="panel"> ... </div>
```
```css
.panel {
  background: var(--panel); border: 1px solid var(--panel-border); border-radius: var(--radius);
  padding: clamp(0.8rem, 3vw, 1.2rem);
  box-shadow: 0 0 0 1px rgba(0,0,0,0.3) inset, 0 8px 30px rgba(0,0,0,0.35);
}
```

## Stat tile
Used 5× in the stats strip (Yes wins / No wins / Current streak / Longest streak / Chop rate).
```html
<div class="stat-tile"><div class="num yes" id="statYes">0</div><div class="label">Yes wins</div></div>
```
```css
.stat-tile {
  flex: 1 1 110px; text-align: center; padding: 0.7rem 0.4rem; border-radius: 10px;
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06);
}
.stat-tile .num { font-size: clamp(1.2rem, 4.2vw, 1.7rem); font-weight: bold; }
.stat-tile .num.yes { color: var(--yes); }
.stat-tile .num.no { color: var(--no); }
.stat-tile .label { font-size: 0.62rem; color: var(--dim); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.15rem; }
```
Props that vary per instance: the number value, the `.yes`/`.no`/(none) color class, the label text.

## Timeframe filter button
4 instances in a row (`24H`/`7D`/`30D`/`1Y`), one carries `.active`.
```html
<button class="tf-btn active" data-hours="24">24H</button>
```
```css
.tf-btn {
  font-family: var(--mono); font-size: 0.72rem; padding: 0.35rem 0.65rem; border-radius: 7px;
  border: 1px solid var(--panel-border); background: transparent; color: var(--dim); cursor: pointer;
}
.tf-btn.active { color: var(--gold); background: rgba(232,196,104,0.12); border-color: var(--gold); }
```

## External link button (Robinhood link)
```html
<a class="rh-link" href="..." target="_blank" rel="noopener">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 17L17 7M17 7H8M17 7V16"/></svg>
  View current round on Robinhood
</a>
```
```css
.rh-link {
  display: inline-flex; align-items: center; gap: 0.4rem; justify-content: center;
  width: 100%; padding: 0.6rem 0.9rem; border-radius: 10px;
  border: 1px solid var(--panel-border); color: var(--gold); text-decoration: none;
  font-size: 0.8rem; font-weight: bold; letter-spacing: 0.02em;
  background: rgba(232,196,104,0.08); transition: background 0.15s;
}
.rh-link:active { background: rgba(232,196,104,0.18); }
```

## Big Road bead (the settled-round history cell)
A 3D card-flip cell: back face = diamond-pattern "card back", front face = Y/N result. Rendered dynamically in JS (`renderBigRoad()`), one per settled round, grouped into streak-columns (max 6 per column).
```html
<div class="bead">
  <div class="bead-inner flip">
    <div class="bead-face back"></div>
    <div class="bead-face front yes">Y</div>
  </div>
</div>
```
```css
.bead { width: var(--bead); height: var(--bead); border-radius: 6px; perspective: 200px; }
.bead-inner { position: relative; width: 100%; height: 100%; transform-style: preserve-3d; transition: transform 0.5s ease; border-radius: 6px; }
.bead.flip .bead-inner { transform: rotateY(180deg); }
.bead-face { position: absolute; inset: 0; border-radius: 6px; backface-visibility: hidden; display: flex; align-items: center; justify-content: center; font-size: calc(var(--bead) * 0.42); font-weight: bold; }
.bead-face.back { background: repeating-linear-gradient(45deg, #1a3327, #1a3327 3px, #133024 3px, #133024 6px); border: 1px solid var(--panel-border); }
.bead-face.front { transform: rotateY(180deg); color: #04140c; }
.bead-face.front.yes { background: var(--yes); }
.bead-face.front.no { background: var(--no); }
```

## Price comparison pair (Now vs Target)
```html
<div class="price-compare">
  <div class="pc-item"><div class="pc-label">Now</div><div class="pc-value now">$63,747.89</div></div>
  <div class="pc-vs">vs</div>
  <div class="pc-item"><div class="pc-label">Target</div><div class="pc-value target">$63,558.83</div></div>
</div>
```
```css
.price-compare { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.6rem; justify-content: center; }
.pc-item { text-align: center; }
.pc-label { font-size: 0.65rem; color: var(--dim); letter-spacing: 0.1em; text-transform: uppercase; }
.pc-value { font-size: clamp(1.2rem, 4.2vw, 1.6rem); font-weight: bold; white-space: nowrap; }
.pc-value.now { color: var(--ink); }
.pc-value.target { color: var(--gold); }
```
This is the exact element the user wants improved (see Step 2 requirements gathering) — currently both values are the same size/weight and only distinguished by label + color (ink vs gold), with a separate small `.pc-delta` line below showing the signed difference. No highlight/badge on the delta itself yet beyond a color class (`.up`/`.down`).

## Lean gauge (live sentiment chip)
```html
<div class="lean-track"><div class="lean-chip yes"></div></div>
```
```css
.lean-track { position: relative; height: 16px; border-radius: 10px; background: linear-gradient(90deg, var(--no-dim), rgba(255,255,255,0.08), var(--yes-dim)); }
.lean-chip { position: absolute; top: 50%; left: 50%; width: 30px; height: 30px; border-radius: 50%; background: var(--gold); border: 3px solid #2a2110; transform: translate(-50%, -50%); transition: left 0.6s ease-out, background 0.3s; box-shadow: 0 0 14px rgba(232,196,104,0.75); }
.lean-chip.yes { background: var(--yes); box-shadow: 0 0 14px rgba(51,255,158,0.8); }
.lean-chip.no { background: var(--no); box-shadow: 0 0 14px rgba(255,77,122,0.8); }
```
`left` position is set inline via JS (50% ± up to 45%, proportional to lean strength).
