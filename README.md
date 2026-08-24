# BTC Prediction

A 15-minute BTC "above or below $X" game that mirrors Robinhood's real "BTC 15 min" prediction market exactly — because it *is* that market. The strike price and the settlement result both come straight from Kalshi's public API (`KXBTC15M` series, the exchange that actually powers Robinhood's contract), not an independent calculation. No login, no API key, no Robinhood credentials anywhere in this app.

A live cosmetic price ticker (Coinbase, Kraken fallback) drives a "live lean" indicator between rounds — purely a vibe read of the instant price, never the settlement rule. The 24h scoreboard renders as a real baccarat Big Road (streaks stack into columns) rather than a flat grid.

## Pages

Twelve pages, all reading the same backend and cross-linked via the "Switch" button in
each header. Eleven are fixed-layout versions of the same dashboard; the twelfth builds
its own:

- `GET /` — **Classic**, the original 2-column dashboard.
- `GET /fluid` — **Fluid**, a genuine flex-wrap layout with fully unconstrained
  module reordering (no fixed columns).
- `GET /ticket` — **The Ticket**, a from-scratch visual redesign (paper/ink exchange
  ticket look) on the same modular system.
- `GET /board` — **The Board**, a real pegboard: drag tiles by the header, resize
  from the corner grip, on a 12-column grid with collision push-down and upward
  compaction. Executive-glassmorphism skin.
- `GET /gauge` — **The Gauge**, the confidence readout as the entire page — a 16-cell
  segmented meter with a needle, on a dark-brutalist card whose atmospheric glow
  changes colour with how certain the round is.
- `GET /algo` — **ALGO Desk**, an AI making its own YES/NO call every round, tracked
  against your own picks.
- `GET /terminal` — **Terminal**, a retro green-phosphor CRT trading terminal —
  monochrome monospace, scanline overlay, ASCII corner brackets on every card.
- `GET /tape` — **The Tape**, a dense Bloomberg-style order-book read: a real YES/NO
  depth ladder off Kalshi's live prices, a scrolling ticker tape of settled rounds
  across the top, steel-blue accent.
- `GET /blueprint` — **Blueprint**, the round as an engineering drawing: a gridded
  sheet inside a ruled drawing frame, modules as drafting frames with corner ticks,
  captions set like drafting callouts. Cyan on blueprint navy, ink-blue on white paper.
- `GET /arcade` — **Arcade**, a coin-op attract screen: zero blur anywhere, hard offset
  shadows and 3px keylines, square corners, saturated cabinet palette.
- `GET /pit` — **The Pit**, the baccarat table this scoreboard's Big Road came from:
  felt and gold rules, chip-round controls and a serif face.
- `GET /studio` — **The Studio**, a build-your-own board. A 24-column drag-and-drop grid
  in the style of Grafana: add a panel, pick one of 18 visualizations (gauge, bar gauge,
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

- `GET /`, `/fluid`, `/ticket`, `/board`, `/gauge`, `/algo`, `/terminal`, `/tape`,
  `/blueprint`, `/arcade`, `/pit`, `/studio` — the 12 pages
- `GET /fonts/<name>.woff2` — self-hosted webfonts (whitelisted names only)
- `GET /api/state` — current round, live price, lean, Kalshi market odds, last settled round
- `GET /api/history?hours=24[&limit=N]` — settled rounds + tallies (accepts any window: 1, 2, 3, 6, 24, 168, 720, 8760). `limit` returns only the newest N rounds, which is how the bead/table panels stay cheap over a multi-month window.
- `GET /api/series?days=0&bucket=day` — history bucketed for charting: per-bucket round count, YES/NO split, YES rate, settlement OHLC, average and largest move, plus a summary block (streaks, chop rate, YES rate by hour-of-day and weekday). `days=0` means every round held. The full ~68-day history is ~15KB this way instead of ~1MB of raw rows.
- `GET /api/ticks?since=<ts>[&until=<ts>]` — raw price ticks for a round's chart; `until` bounds a historical round's fetch to its own 15-minute window
- `GET /health`

## Data sources

- Kalshi public API (`api.elections.kalshi.com`) — authoritative strike + settlement. No auth.
- Coinbase / Kraken public tickers — cosmetic live price only.
