# BTC 15

A coin flip, every 15 minutes.

**Just for fun. No bets, no money, no advice.**

**[See the page](https://pingywon.github.io/btc-prediction/)**

[![BTC 15 main screen](https://pingywon.github.io/btc-prediction/img/shot-classic.webp)](https://pingywon.github.io/btc-prediction/)

## The game

1. Every 15 minutes a real market asks: will Bitcoin close above the target price?
2. Call YES or NO.
3. The exchange settles it. The app keeps score.

The market is Kalshi's 15-minute Bitcoin contract, the one behind Robinhood's "BTC 15 min". The app reads its public feed. No account, no key.

![The Big Road scoreboard](https://pingywon.github.io/btc-prediction/img/shot-road.webp)

## It is 50/50

| 10,672 rounds, as of Oct 8, 2026 | |
|---|---|
| Closed YES | 49.9% |
| Flipped from the round before | 50.9% |
| Right, calling by pattern | 51.0% |

ALGO is right 85% of the time because it backs the favourite late, when that side costs about 86 cents to win a dollar. That is break-even. The [page](https://pingywon.github.io/btc-prediction/#numbers) has the chart.

## Run it

```
docker build -t btc-prediction .
docker run -d -p 80:80 -v btc-prediction-data:/data btc-prediction
```

One container, one Python file, one SQLite database. It settles every round and logs every call around the clock, browser open or not. Keep the `/data` volume and the history survives restarts.

Without Docker: `python3 app.py`. Set `PORT`, `BIND` or `BP_DB` to change the defaults.

## Screens

| Page | What it is |
|---|---|
| `/` | Classic, the main screen |
| `/studio` | The Studio: drag-and-drop board, 38 panel types, 10 skins |
| `/algo` | ALGO Desk: its record next to yours |

![The Studio](https://pingywon.github.io/btc-prediction/img/shot-studio.webp)

<details>
<summary>API</summary>

| Route | Returns |
|---|---|
| `GET /api/state` | Current round, live price, market odds, last result |
| `GET /api/history?hours=24` | Settled rounds with every caller's pick |
| `GET /api/series?days=0&bucket=day` | History in buckets, plus streak and YES-rate totals |
| `GET /api/calls` | Each caller's record and recent calls |
| `GET /api/ticks?since=<ts>` | Raw price ticks |
| `POST /api/picks` | Your call for the open round |
| `GET` `POST /api/board`, `/api/layouts`, `/api/prefs` | Saved Studio boards and page settings |
| `GET /health` | Version |

</details>

---

Current release: **v5.4.0**, shown at the bottom of every page. MIT licence. Not affiliated with Kalshi or Robinhood.
