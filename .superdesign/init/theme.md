# Theme

No Tailwind, no CSS-in-JS, no design-token build step — plain CSS custom properties in a single `<style>` block inside `index.html`. No dark/light mode (single dark theme only).

## Part 1 — Compact token summary

**Palette** (`:root`, `index.html:8-24`):
| Token | Value | Use |
|---|---|---|
| `--felt-1` | `#04140c` | Page background gradient, darkest |
| `--felt-2` | `#071f14` | Page background gradient, lighter |
| `--ink` | `#d9f5e8` | Primary text |
| `--dim` | `#7fa694` | Secondary/label text |
| `--yes` | `#33ff9e` | YES / positive accent (bright green) |
| `--yes-dim` | `#14603f` | YES darker variant (borders, gradients) |
| `--no` | `#ff4d7a` | NO / negative accent (pink-red) |
| `--no-dim` | `#6b1a34` | NO darker variant |
| `--gold` | `#e8c468` | Brand/highlight accent (title, target price, links) |
| `--panel` | `rgba(6, 28, 19, 0.72)` | Card/panel background (translucent) |
| `--panel-border` | `rgba(232, 196, 104, 0.35)` | Card/panel border (translucent gold) |

**Layout tokens:**
| Token | Value |
|---|---|
| `--radius` | `14px` (panel corner radius) |
| `--mono` | `ui-monospace, 'SFMono-Regular', Menlo, Consolas, 'Courier New', monospace` — the ONLY font family used anywhere on the page |
| `--bead` | `34px` mobile / `40px` ≥900px / `46px` ≥1200px — Big Road cell size |
| `--bead-gap` | `5px` mobile / `6px` ≥900px / `7px` ≥1200px |

**Breakpoints:** `@media (min-width: 900px)`, `@media (min-width: 1200px)` — only two, both widen `.wrap` and bump `--bead`/`--bead-gap`. No `max-width` (desktop-down) queries; the base styles ARE mobile.

**Type scale:** all via `clamp(min, preferred-vw, max)`, no fixed breakpoint jumps for font-size except the two above. Roughly: labels/footer ~0.62-0.72rem, body/sentence ~0.85-1rem, stat numbers ~1.2-1.7rem, price compare values ~1.2-1.6rem, h1 ~1.1-1.6rem.

**Shadows:** panels use a double shadow — `0 0 0 1px rgba(0,0,0,0.3) inset, 0 8px 30px rgba(0,0,0,0.35)`. Glow effects (`box-shadow` with color + blur, no spread) on the gold title text, the lean chip, and the locked/urgent countdown rail pulse.

**Background texture:** `body::before` is a fixed, full-viewport `repeating-linear-gradient` scanline overlay at 3px pitch, `mix-blend-mode: overlay`, very low opacity (`rgba(255,255,255,0.015)`) — a subtle CRT/terminal texture, not decorative noise.

## Part 2 — Raw source (full `<style>` block, `index.html:7-175`)

```css
:root {
  --felt-1: #04140c;
  --felt-2: #071f14;
  --ink: #d9f5e8;
  --dim: #7fa694;
  --yes: #33ff9e;
  --yes-dim: #14603f;
  --no: #ff4d7a;
  --no-dim: #6b1a34;
  --gold: #e8c468;
  --panel: rgba(6, 28, 19, 0.72);
  --panel-border: rgba(232, 196, 104, 0.35);
  --radius: 14px;
  --mono: ui-monospace, 'SFMono-Regular', Menlo, Consolas, 'Courier New', monospace;
  --bead: 34px;
  --bead-gap: 5px;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0; min-height: 100%;
  background: radial-gradient(ellipse at 50% -10%, var(--felt-2), var(--felt-1) 70%);
  color: var(--ink);
  font-family: var(--mono);
  -webkit-font-smoothing: antialiased;
}
body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background: repeating-linear-gradient(0deg, rgba(255,255,255,0.015) 0px, rgba(255,255,255,0.015) 1px, transparent 1px, transparent 3px);
  mix-blend-mode: overlay;
}
.wrap {
  position: relative; z-index: 1;
  max-width: 640px; margin: 0 auto;
  padding: clamp(0.75rem, 3vw, 1.5rem);
  display: flex; flex-direction: column; gap: clamp(0.75rem, 2.5vw, 1.1rem);
}
@media (min-width: 900px) { .wrap { max-width: 920px; } :root { --bead: 40px; --bead-gap: 6px; } }
@media (min-width: 1200px) { .wrap { max-width: 1150px; } :root { --bead: 46px; --bead-gap: 7px; } }

header { text-align: center; padding-top: 0.25rem; }
header h1 {
  margin: 0; font-size: clamp(1.1rem, 4.5vw, 1.6rem); letter-spacing: 0.06em;
  color: var(--gold); text-shadow: 0 0 14px rgba(232,196,104,0.45);
}
header .sub { color: var(--dim); font-size: clamp(0.7rem, 2.6vw, 0.82rem); margin-top: 0.15rem; }

.panel {
  background: var(--panel); border: 1px solid var(--panel-border); border-radius: var(--radius);
  padding: clamp(0.8rem, 3vw, 1.2rem);
  box-shadow: 0 0 0 1px rgba(0,0,0,0.3) inset, 0 8px 30px rgba(0,0,0,0.35);
}

.status-bar { display: flex; flex-direction: column; gap: clamp(0.9rem, 3vw, 1.3rem); }
.status-row { display: flex; flex-wrap: wrap; align-items: center; gap: clamp(0.9rem, 3vw, 1.6rem); }
.status-zone { min-width: 0; }
.zone-price { flex: 1.4 1 320px; }
.zone-lean { flex: 1 1 220px; }
.zone-link { flex: 1 1 220px; }

.price-compare { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.6rem; justify-content: center; }
.pc-item { text-align: center; }
.pc-label { font-size: 0.65rem; color: var(--dim); letter-spacing: 0.1em; text-transform: uppercase; }
.pc-value { font-size: clamp(1.2rem, 4.2vw, 1.6rem); font-weight: bold; white-space: nowrap; }
.pc-value.now { color: var(--ink); }
.pc-value.target { color: var(--gold); }
.pc-vs { color: var(--dim); font-size: 0.9rem; padding: 0 0.1rem; }
.pc-delta { text-align: center; font-size: 0.75rem; margin-top: 0.2rem; color: var(--dim); }
.pc-delta.up { color: var(--yes); }
.pc-delta.down { color: var(--no); }

.plain-sentence { font-size: clamp(0.85rem, 3.4vw, 1rem); line-height: 1.4; text-align: center; }
.plain-sentence b { color: var(--gold); }
.plain-sentence .locked-tag { color: var(--no); font-weight: bold; }

.rail-track {
  position: relative; height: 14px; border-radius: 8px; overflow: hidden;
  background: rgba(255,255,255,0.06); margin-top: 0.6rem;
}
.rail-fill {
  position: absolute; inset: 0 0 0 auto; width: 100%; height: 100%;
  background: linear-gradient(90deg, var(--yes-dim), var(--gold));
  transition: width 0.9s linear;
}
.rail-track.urgent .rail-fill { background: linear-gradient(90deg, var(--no-dim), var(--no)); }
.rail-track.urgent { animation: railpulse 1s ease-in-out infinite; }
@keyframes railpulse { 0%,100% { box-shadow: 0 0 0 rgba(255,77,122,0); } 50% { box-shadow: 0 0 16px rgba(255,77,122,0.65); } }

.lean-block { text-align: center; }
.lean-track {
  position: relative; height: 16px; border-radius: 10px;
  background: linear-gradient(90deg, var(--no-dim), rgba(255,255,255,0.08), var(--yes-dim));
}
.lean-chip {
  position: absolute; top: 50%; left: 50%; width: 30px; height: 30px; border-radius: 50%;
  background: var(--gold); border: 3px solid #2a2110;
  transform: translate(-50%, -50%); transition: left 0.6s ease-out, background 0.3s;
  box-shadow: 0 0 14px rgba(232,196,104,0.75);
}
.lean-chip.yes { background: var(--yes); box-shadow: 0 0 14px rgba(51,255,158,0.8); }
.lean-chip.no { background: var(--no); box-shadow: 0 0 14px rgba(255,77,122,0.8); }
.lean-label { font-size: 0.72rem; color: var(--dim); margin-top: 0.45rem; }

.rh-link {
  display: inline-flex; align-items: center; gap: 0.4rem; justify-content: center;
  width: 100%; padding: 0.6rem 0.9rem; border-radius: 10px;
  border: 1px solid var(--panel-border); color: var(--gold); text-decoration: none;
  font-size: 0.8rem; font-weight: bold; letter-spacing: 0.02em;
  background: rgba(232,196,104,0.08); transition: background 0.15s;
}
.rh-link:active { background: rgba(232,196,104,0.18); }
.rh-link svg { width: 13px; height: 13px; }

.stats-strip { display: flex; flex-wrap: wrap; gap: 0.6rem; }
.stat-tile {
  flex: 1 1 110px; text-align: center; padding: 0.7rem 0.4rem; border-radius: 10px;
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06);
}
.stat-tile .num { font-size: clamp(1.2rem, 4.2vw, 1.7rem); font-weight: bold; }
.stat-tile .num.yes { color: var(--yes); }
.stat-tile .num.no { color: var(--no); }
.stat-tile .label { font-size: 0.62rem; color: var(--dim); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.15rem; }

.last-settled { text-align: center; font-size: 0.82rem; color: var(--dim); padding: 0.7rem clamp(0.8rem, 3vw, 1.2rem); }
.last-settled b.yes { color: var(--yes); }
.last-settled b.no { color: var(--no); }

.bigroad-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.7rem; flex-wrap: wrap; gap: 0.5rem; }
.bigroad-head h2 { margin: 0; font-size: 0.9rem; letter-spacing: 0.1em; color: var(--gold); text-transform: uppercase; }
.timeframe-select { display: flex; gap: 0.3rem; }
.tf-btn {
  font-family: var(--mono); font-size: 0.72rem; padding: 0.35rem 0.65rem; border-radius: 7px;
  border: 1px solid var(--panel-border); background: transparent; color: var(--dim); cursor: pointer;
}
.tf-btn.active { color: var(--gold); background: rgba(232,196,104,0.12); border-color: var(--gold); }

.bigroad-scroll {
  overflow-x: auto; padding-bottom: 0.4rem; min-height: calc(var(--bead) * 6 + var(--bead-gap) * 5 + 4px);
  -webkit-overflow-scrolling: touch;
}
.bigroad-grid { display: flex; gap: var(--bead-gap); width: max-content; }
.bigroad-col { display: flex; flex-direction: column; gap: var(--bead-gap); }
.bead { width: var(--bead); height: var(--bead); border-radius: 6px; perspective: 200px; cursor: default; }
.bead-inner {
  position: relative; width: 100%; height: 100%; transform-style: preserve-3d;
  transition: transform 0.5s ease; border-radius: 6px;
}
.bead.flip .bead-inner { transform: rotateY(180deg); }
.bead-face {
  position: absolute; inset: 0; border-radius: 6px; backface-visibility: hidden;
  display: flex; align-items: center; justify-content: center;
  font-size: calc(var(--bead) * 0.42); font-weight: bold;
}
.bead-face.back {
  background: repeating-linear-gradient(45deg, #1a3327, #1a3327 3px, #133024 3px, #133024 6px);
  border: 1px solid var(--panel-border);
}
.bead-face.front { transform: rotateY(180deg); color: #04140c; }
.bead-face.front.yes { background: var(--yes); }
.bead-face.front.no { background: var(--no); }

footer { text-align: center; font-size: 0.65rem; color: var(--dim); padding: 0.5rem 0 1.2rem; }
```
