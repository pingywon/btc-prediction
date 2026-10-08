# BTC 15 page

The site at https://pingywon.github.io/btc-prediction/. The app itself is on the `master` branch.

## Update it

```
python3 tools/build.py        # src/index.src.html + tools/data.json + VERSION -> index.html
node tools/check.cjs          # renders the page and checks it
```

Bump `VERSION` on every change. The footer prints it.

## Refresh the numbers

```
docker exec -i btc-prediction python3 - < tools/price_check.py > tools/prices.json
BTC15_URL=http://<host> python3 tools/refresh_data.py tools/prices.json
BTC15_URL=http://<host> node tools/shots.cjs    # new screenshots
node tools/og.cjs                               # new link-preview card
```

Everything here only reads. `shots.cjs` blocks every write request.
