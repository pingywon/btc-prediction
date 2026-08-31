# BTC Prediction

Current release: **v4.13.0** (the running version is shown at the bottom of every page
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
- `GET /algo` — **ALGO Desk**, an AI making its own YES/NO call every round, tracked
  against your own picks. Kept as its own page because it is a distinct feature, not a
  skin.
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
  metrics are a dropdown. Layout persists to `localStorage` and the whole board can be
  exported and re-imported as JSON.

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

  **Your call is shared across every page.** The Studio reads and writes the same
  `btc15_picks` / `btc15_record` / `btc15_resolved` keys the fixed pages use, so a YES/NO
  made on The Board shows up here and counts toward the same record. Light/dark is shared
  through `btc15_theme` too. Still browser-local, still never sent to the server.

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

The current skin and board are still remembered on their own (`btc_studio_skin`,
`btc_studio_dashboard_v2`, browser-local) — a save slot is for keeping more than one.

### The toolbar gets out of the way

Outside edit mode the Studio's toolbar folds to a slim strip: the status chip (price,
history depth, running version), **Edit**, and a chevron that brings the full bar back
(Mode, Range, Bucket, Design). Pressing Edit always expands it; Done returns it to
whatever you last chose, and that choice is remembered (`btc_studio_topbar_open`).

Dropping a panel mostly on top of another **swaps** them (a dashed outline marks the
target while you drag); a glancing overlap still pushes the other panel down.

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
- `GET /health`

## Data sources

- Kalshi public API (`api.elections.kalshi.com`) — authoritative strike + settlement. No auth.
- Coinbase / Kraken public tickers — cosmetic live price only.
