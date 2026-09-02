# BTC Prediction

Current release: **v5.0.0** (the running version is shown at the bottom of every page
and in the Studio's status chip; it comes from `VERSION` in `app.py`, the single source
of truth — the git tag, Dockerfile LABEL and this line must match it).

A 15-minute BTC "above or below $X" game that mirrors Robinhood's real "BTC 15 min" prediction market exactly — because it *is* that market. The strike price and the settlement result both come straight from Kalshi's public API (`KXBTC15M` series, the exchange that actually powers Robinhood's contract), not an independent calculation. No login, no API key, no Robinhood credentials anywhere in this app.

A live cosmetic price ticker (Coinbase, Kraken fallback) drives a "live lean" indicator between rounds — purely a vibe read of the instant price, never the settlement rule. The 24h scoreboard renders as a real baccarat Big Road (streaks stack into columns) rather than a flat grid.

## Pages

**Two views**, cross-linked via the "Mode" button in each header, plus the ALGO Desk.
Classic is deliberately fixed; everything else is one modular board that can wear any
skin:

- `GET /` — **Classic**, the original 2-column dashboard. **Not movable, on purpose** —
  this is the fixed reference layout. Modules can still be collapsed or hidden, but
  nothing reorders.
- `GET /algo` — **ALGO Desk**, an AI making its own YES/NO call every round — **on the
  server, 24/7, whether or not any browser is open** (v4.15.0) — tracked against your
  own picks. Kept as its own page because it is a distinct feature, not a skin.
- `GET /studio` — **The Studio**, the modular view and the home of every skin.
  A build-your-own board. A 24-column drag-and-drop grid
  in the style of Grafana: add a panel, pick one of 25 visualizations (the seven Classic
  modules, plus gauge, bar gauge,
  stat, time series, bar chart, candlestick, heatmap, histogram, donut, state timeline,
  Big Road, table, countdown, note, plus the live ones — **price vs target**, drawing
  this round's tick track green above the strike and red below it with a dashed line at
  the target and Prev/Live/Next to page back through settled rounds; **lean bar**, a
  green/red bar measuring distance from the target; **round card**, the live price,
  countdown, round window, target and round-over-round delta in one block; and **your
  call**, the YES/NO pick and running record), pick the metric it reads, then drag the header to move it and
  the corner to resize it. Per-panel unit, min/max, decimals, colour mode and threshold
  steps. There is only one data source, so — as in Netdata — there is no query language:
  metrics are a dropdown. The working board lives **on the server** (localStorage is
  only an offline cache), and the whole board can be exported and re-imported as JSON.

  **The default board is Classic, module for module.** Live Price & Pick, Round
  Confidence, Current Spread and Market Gauges stacked in the 14/24-wide left column,
  Results Sidebar in the 10/24 right column, Big Road History and Round-to-Round Spread
  full-width beneath — the same `7fr 5fr` split `/` uses, and the same calculations
  (the confidence engine, Kalshi odds normalisation, streak/chop tallies, the tile Big
  Road with its Dragon Tail ring, pick badges and Big Eye Boy) ported line for line. The
  Big Road's timeframe selector drives the Results and Spread windows together, as on
  Classic. So "modular Classic" is literally Classic, just movable and resizable. The
  earlier analytics layout is still there as a preset in the JSON dialog.

  It also carries a **skin picker**: the same board renders in any of the ten looks —
  Classic, Fluid, The Ticket, The Board, The Gauge, Terminal, The Tape, Blueprint, Arcade
  and The Pit. Each skin's palette is lifted from that page's own token block; shape, type
  and texture are set alongside it (Arcade goes square with hard offset shadows, The Pit
  goes felt-and-gold with a serif face and chip-round buttons, Terminal goes green
  phosphor and monospace, Blueprint gets its drawing grid). The fixed pages are untouched
  — `/` is still exactly the Classic dashboard it always was.

  **Your call is shared across every page — and every device.** Since v4.15.0 a pick is
  a `POST /api/picks`; the record is derived on the server from settled rounds, so the
  same numbers appear in any browser that opens the site. Light/dark stays a per-device
  preference (`btc15_theme`).

Every module on every page can be reordered, collapsed, and hidden from its own
header controls, and the price chart can browse the last 12 settled rounds via the
Prev/Live/Next controls above it (not just the live one).


### Design sheet: skin, arrangement, saves, panels

Everything that changes how the Studio *looks* lives in one place — the **Design**
button opens a drawer on the right (the board stays visible, so skins preview live):

- **Skin** — the ten looks (Classic, The Ticket, The Board, The Gauge, Terminal, The
  Tape, Blueprint, Arcade, The Pit, Solari) plus the light/dark toggle. They are looks
  applied to the one modular board, not separate pages any more. **Fluid was removed.**
- **Arrangement** — eight ready-made boards (Classic, Player, Analyst, Tape Room, Wall,
  Minimal, Solari desk, Analytics). Picking one replaces the layout and leaves the skin
  alone, except the Solari desk which brings its own.
- **Saves** — **five named slots** for boards of your own: layout, sizes, per-panel
  colours, range/bucket and the skin. They are kept **on the server** (`layouts` table
  in the SQLite DB, `GET`/`POST /api/layouts`), so a board saved in one browser is there
  in every other browser and device on the LAN. The light/dark theme is deliberately
  not part of a save — it is shared with Classic and the ALGO Desk.
- **Panels** — **Reset to Classic** (every module back exactly where the fixed page has
  it) and the JSON export/import dialog. *Add panel* lives in the toolbar while editing.

The current skin and board auto-save to the server as you work (debounced; other open
tabs pull the newer board within ~10s when they are not mid-edit) — a save slot is for
keeping more than one. The drawer reads in the order you use it: **1 · Pick a design,
2 · Pick a skin, 3 · Save it to a slot**, with Panels last.

### The toolbar gets out of the way

Outside edit mode the Studio's toolbar folds to a slim strip: the status chip (price,
history depth, running version), **Edit**, and a chevron that brings the full bar back
(Mode, Range, Bucket, Design). Pressing Edit always expands it; Done returns it to
whatever you last chose, and that choice is remembered (`btc_studio_topbar_open`).

**Calm drag** (v4.15.0): while you drag, nothing else moves — the tile floats, a ghost
shows where it will land, and a dashed outline marks a swap target. Collisions, the swap
and compaction settle exactly once, on the drop: mostly-on-top **swaps**, a glancing
overlap pushes the other panel down.

**No module ever scrolls.** A panel shows the newest rows or columns that fit its box
and drops the rest — resize the panel (or widen its window) to see more. The same goes
for the spread list on Classic and the ALGO Desk.

## Full memory (v4.15.0)

Everything that used to live in the browser now lives in the server's SQLite, so it
follows the owner to any browser or device:

- **Three callers, logged every round** in the `calls` table: **you** (`POST
  /api/picks`), **ALGO** (a third daemon thread ports the page's exact heuristic and
  fires in the two minutes before lock — Kalshi's own odds, with the live-lean fallback
  inside the ±4-point coin-flip band), and **History Call** (the static order-3 table).
  The same thread also settles rounds around the clock, so records score with no tab
  open. Records are **derived** by joining calls against settled results — never stored
  counters, so they cannot drift.
- **The Accuracy module** (Studio → Add panel → Accuracy; it also sits on the default
  board) shows all three records with win percentages at a glance. Expect everything to
  hover near 50% — the 105-hypothesis history study found no real edge, and this module
  is the live test of that.
- **The Call Log module** (v5.0.0; Studio → Add panel → Call Log, also on the default
  board) is the round-by-round view of the same data: the picks standing for the round in
  play across the top, then one row per settled round — result, and what each caller said
  with a ✓ or ✗ against it. The footer tallies the window and matches Accuracy exactly.
  Rounds before v4.15.0 carry no calls, so by default only rounds with a logged call are
  listed; the panel editor can show every round, drop your own calls from the view, and
  change the window.
- **The working Studio board + skin** (`kv` key `board`), the five save slots, and the
  Classic/ALGO module preferences (`classic_modules` / `algo_modules`) are all
  server-side. A one-time migration imports a browser's old local picks on first visit.

## Getting around the Studio (v5.0.0)

The Studio grew faster than its chrome did. v5.0.0 is a pass over the parts you touch
rather than look at:

- **Range and Bucket stay on screen.** They are viewing controls, not editing controls,
  but the slim strip used to hide them until you entered Edit mode. They now live in the
  strip permanently, and the bare chevron that held everything else is labelled **More**.
- **Every ready-made board shows a mini-map** of its own panel rectangles in the Design
  drawer, so you can see the shape before you commit to it instead of reading a sentence
  about it. The board you are on is marked **current**, and its button reads *Reset*.
- **Blank** is a new board: nothing on it. Picking it lands you on an **empty-state**
  prompt with *Add your first panel* and *Open Design*, because a blank canvas with no
  visible way forward is a trap — in view mode the Add panel button is not even rendered.
- **The panel picker filters as you type.** Thirty-odd panels is more than anyone can
  scan; the search box takes focus when the sheet opens, and group headings disappear
  when nothing under them matches.
- **Panels are named after the panel.** Adding a module with no metric — Accuracy, Call
  Log, History Call — used to title it after a metric it does not use, so picking
  "Call Log" gave you a panel called "Live BTC price". Fixed.
- **The Accuracy module trims instead of clipping.** With four callers its footer ran off
  the bottom of the panel; it now follows the same no-scrollbar rule as everything else.

## Round Confidence

Every page carries an estimate of how the current round is likely to resolve. It
blends two independent reads, both from data already being polled:

1. **Kalshi's own live order book** (weight 0.7) — `kalshi_yes_price` is a 0–1
   traded probability, not an invented score. The two sides are bid-side prices that
   rarely sum to exactly 1, so it normalises over the pair to de-vig.
2. **Position versus time** (weight 0.3) — how far price sits from the strike, judged
   against the observed spread of completed-round moves rather than an assumed
   volatility. A round is exactly 900s, so a move across the remaining fraction `f`
   is about `sqrt(f)` the size of a whole-round move; the required move is scaled up
   to a whole-round equivalent before being compared against history, then halved
   because it also has to go the right way. As time runs out this sharpens and the
   current position takes over.

It skips the second read below 8 settled rounds rather than quoting a percentage off
three samples, and returns nothing at all when neither read is available. **It is an
estimate, not advice** — and there is no betting anywhere in this app; the personal
pick is `localStorage`-only and never leaves the browser.

## Fonts

Inter, Manrope and JetBrains Mono are **self-hosted** (`fonts/`, served at
`/fonts/<name>.woff2`) rather than linked from a CDN — one latin-subset variable file
per family covering the whole weight axis, ~113KB total, shared across all twelve pages.
All three are SIL OFL 1.1; see `fonts/LICENSE.md`.

## Run

```
python3 app.py
```

Env vars: `PORT` (default 80), `BIND` (default 0.0.0.0), `BP_DB` (SQLite path, default `./data.db`).

### Docker

```
docker build -t btc-prediction .
docker run -p 80:80 -v btc-prediction-data:/data btc-prediction
```

Defaults to port 80 inside the container (`ENV PORT=80`) and stores its SQLite DB
at `/data/data.db` (`ENV BP_DB=/data/data.db`) — mount a volume at `/data` (as
above) so round history survives a container recreation; without it, a fresh
container starts with an empty Big Road / spread ledger every time.

## Endpoints

- `GET /`, `/studio`, `/algo` — the three pages. The retired per-skin URLs
  (`/ticket`, `/board`, `/gauge`, `/terminal`, `/tape`, `/blueprint`, `/arcade`,
  `/pit`) 302-redirect to `/studio?skin=<name>`; `/fluid` is gone and redirects
  to `/studio`
- `GET /fonts/<name>.woff2` — self-hosted webfonts (whitelisted names only)
- `GET /api/state` — current round, live price, lean, Kalshi market odds, last settled round
- `GET /api/history?hours=24[&limit=N]` — settled rounds + tallies (accepts any window: 1, 2, 3, 6, 24, 168, 720, 8760). `limit` returns only the newest N rounds, which is how the bead/table panels stay cheap over a multi-month window.
- `GET /api/series?days=0&bucket=day` — history bucketed for charting: per-bucket round count, YES/NO split, YES rate, settlement OHLC, average and largest move, plus a summary block (streaks, chop rate, YES rate by hour-of-day and weekday). `days=0` means every round held. The full ~68-day history is ~15KB this way instead of ~1MB of raw rows.
- `GET /api/ticks?since=<ts>[&until=<ts>]` — raw price ticks for a round's chart; `until` bounds a historical round's fetch to its own 15-minute window
- `GET /api/layouts` — the Studio's five save slots (`{slots:[{slot,name,saved_at,payload}], max:5}`). Kept on the server so a saved board follows you across browsers and devices.
- `POST /api/layouts` — `{"slot":1..5,"name":"…","payload":{…}}` saves or overwrites a slot (payload is a JSON object, ≤200KB; blank names default to "Slot N"); `{"slot":N,"delete":true}` clears one. Responds with the full slot list. No auth — single-owner LAN app.
- `GET /api/calls` — the three call records (you / ALGO / History Call): win-loss derived live from settled rounds, this round's calls, and the last ~50 scored calls.
- `POST /api/picks` — `{"ticker":"…","choice":"yes"|"no"}` records YOUR call for the current round; 409 once the round locks, overwrite allowed before that. Responds with the full `/api/calls` body.
- `GET`/`POST /api/board` — the Studio's working board (`{v,dash,skin}`); POST replies `{"saved_at":…}` and `/api/state` carries `board_saved_at` so open tabs notice newer boards.
- `GET`/`POST /api/prefs` — Classic/ALGO module preferences (`{"key":"classic_modules"|"algo_modules","payload":{…}}`).
- `POST /api/calls/import` — one-time migration of old browser-local picks; only rounds the server holds, never overwriting an existing call.
- `/api/state` also carries `records`, `calls` (this round's) and `board_saved_at`; `/api/history` rows carry a `calls` object (`{you,algo,histcall}` → choice) for the road badges.
- `GET /health`

## Data sources

- Kalshi public API (`api.elections.kalshi.com`) — authoritative strike + settlement. No auth.
- Coinbase / Kraken public tickers — cosmetic live price only.
