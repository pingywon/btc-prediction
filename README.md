# BTC Prediction

A 15-minute BTC "above or below $X" game that mirrors Robinhood's real "BTC 15 min" prediction market exactly — because it *is* that market. The strike price and the settlement result both come straight from Kalshi's public API (`KXBTC15M` series, the exchange that actually powers Robinhood's contract), not an independent calculation. No login, no API key, no Robinhood credentials anywhere in this app.

A live cosmetic price ticker (Coinbase, Kraken fallback) drives a "live lean" indicator between rounds — purely a vibe read of the instant price, never the settlement rule. The 24h scoreboard renders as a real baccarat Big Road (streaks stack into columns) rather than a flat grid.

## Run

```
python3 app.py
```

Env vars: `PORT` (default 8160), `BIND` (default 0.0.0.0), `BP_DB` (SQLite path, default `./data.db`).

## Endpoints

- `GET /` — the app
- `GET /api/state` — current round, live price, lean, last settled round
- `POST /api/vote {"choice":"yes"|"no"}` — cast a vote (one per anonymous cookie per round)
- `GET /api/history?hours=24` — settled rounds + tallies
- `GET /health`

## Data sources

- Kalshi public API (`api.elections.kalshi.com`) — authoritative strike + settlement. No auth.
- Coinbase / Kraken public tickers — cosmetic live price only.
