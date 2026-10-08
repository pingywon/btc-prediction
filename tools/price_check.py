import sqlite3, json, re
c = sqlite3.connect("file:/data/data.db?mode=ro", uri=True)
out = {}
out["tables"] = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
out["calls_cols"] = [r[1] for r in c.execute("pragma table_info(calls)")]
out["rounds_cols"] = [r[1] for r in c.execute("pragma table_info(rounds)")]
out["first_call"] = c.execute("select source, min(ts), count(*) from calls group by source").fetchall()
rx = re.compile(r"(\d+)% YES / (\d+)% NO")
rows = c.execute(
    "select c.source, c.choice, c.reason, r.result from calls c join rounds r on r.kalshi_ticker = c.kalshi_ticker "
    "where r.result in ('yes','no') and c.source in ('algo12','algo10','algoearly','algo')").fetchall()
agg = {}
for src, choice, reason, result in rows:
    m = rx.search(reason or "")
    a = agg.setdefault(src, {"n": 0, "priced": 0, "wins": 0, "price_sum": 0.0, "followed_market": 0, "buckets": {}})
    a["n"] += 1
    if not m:
        continue
    y, n = int(m.group(1)), int(m.group(2))
    tot = (y + n) or 1
    p = (y if choice == "yes" else n) / tot
    win = 1 if choice == result else 0
    a["priced"] += 1
    a["wins"] += win
    a["price_sum"] += p
    a["followed_market"] += 1 if p >= 0.5 else 0
    b = min(int(p * 10), 9)
    k = a["buckets"].setdefault(str(b), [0, 0, 0.0])
    k[0] += 1
    k[1] += win
    k[2] += p
out["agg"] = agg
print(json.dumps(out))
