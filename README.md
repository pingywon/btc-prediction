# BTC Prediction

A 15-minute BTC "above or below $X" game that mirrors Robinhood's real "BTC 15 min" prediction market exactly — because it *is* that market. The strike price and the settlement result both come straight from Kalshi's public API (`KXBTC15M` series, the exchange that actually powers Robinhood's contract), not an independent calculation. No login, no API key, no Robinhood credentials anywhere in this app.

A live cosmetic price ticker (Coinbase, Kraken fallback) drives a "live lean" indicator between rounds — purely a vibe read of the instant price, never the settlement rule. The 24h scoreboard renders as a real baccarat Big Road (streaks stack into columns) rather than a flat grid.

## Pages

Four versions of the same dashboard, all reading the same backend and cross-linked
via the "Switch" button in each header:

- `GET /` — **Classic**, the original 2-column dashboard.
- `GET /fluid` — **Fluid**, a genuine flex-wrap layout with fully unconstrained
  module reordering (no fixed columns).
- `GET /ticket` — **The Ticket**, a from-scratch visual redesign (paper/ink exchange
  ticket look) on the same modular system.
- `GET /algo` — **ALGO Desk**, an AI making its own YES/NO call every round, tracked
  against your own picks.

Every module on every page can be reordered, collapsed, and hidden from its own
header controls, and the price chart can browse the last 12 settled rounds via the
Prev/Live/Next controls above it (not just the live one).

## Run

```
python3 app.py
```

Env vars: `PORT` (default 8160), `BIND` (default 0.0.0.0), `BP_DB` (SQLite path, default `./data.db`).

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

- `GET /`, `/fluid`, `/ticket`, `/algo` — the 4 pages
- `GET /api/state` — current round, live price, lean, Kalshi market odds, last settled round
- `GET /api/history?hours=24` — settled rounds + tallies (accepts any window: 1, 2, 3, 6, 24, 168, 720, 8760)
- `GET /api/ticks?since=<ts>[&until=<ts>]` — raw price ticks for a round's chart; `until` bounds a historical round's fetch to its own 15-minute window
- `GET /health`

## Data sources

- Kalshi public API (`api.elections.kalshi.com`) — authoritative strike + settlement. No auth.
- Coinbase / Kraken public tickers — cosmetic live price only.
