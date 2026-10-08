#!/usr/bin/env python3
"""Snapshot the numbers the page prints into tools/data.json.

    BTC15_URL=http://<host> python3 tools/refresh_data.py [prices.json]

Reads only (GET). prices.json is the output of tools/price_check.py, which has to
run next to the database:  docker exec -i btc-prediction python3 - < tools/price_check.py
"""
import json
import os
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = os.environ.get("BTC15_URL", "").rstrip("/")
if not BASE:
    sys.exit("set BTC15_URL to the running app, e.g. BTC15_URL=http://localhost")


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=90) as r:
        return json.load(r)


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


health = get("/health")
summary = get("/api/series?days=0&bucket=day")["summary"]
records = get("/api/calls")["records"]
rounds = sorted((r for r in get("/api/history?hours=87600")["rounds"] if r.get("result") in ("yes", "no")),
                key=lambda r: r["close_time"])
results = [r["result"] for r in rounds]

# After a streak of k or more, how often did the next round match it?
streaks = []
for k in (2, 3, 4, 5):
    n = same = 0
    for i in range(k, len(results)):
        if len(set(results[i - k:i])) == 1:
            n += 1
            same += results[i] == results[i - 1]
    streaks.append({"k": k, "n": n, "same": same, "pct": pct(same, n)})

CALLERS = [("algo12", "ALGO, 12 min left"), ("algo10", "ALGO, 10 min left"),
           ("algoearly", "ALGO, 5 min left"), ("algo", "ALGO, final call")]
prices = {}
calls_since = None
if len(sys.argv) > 1:
    check = json.loads(pathlib.Path(sys.argv[1]).read_text())
    prices = check["agg"]
    first_call = min(ts for src, ts, n in check["first_call"] if src.startswith("algo"))
    calls_since = time.strftime("%b %-d, %Y", time.gmtime(first_call - 4 * 3600))

algo = []
for key, label in CALLERS:
    rec = records[key]
    row = {"key": key, "label": label, "wins": rec["wins"], "losses": rec["losses"],
           "scored": rec["scored"], "pct": pct(rec["wins"], rec["scored"])}
    p = prices.get(key)
    if p and p["priced"]:
        row["price_pct"] = round(100.0 * p["price_sum"] / p["priced"], 1)
        row["priced"] = p["priced"]
        row["priced_win_pct"] = pct(p["wins"], p["priced"])
    algo.append(row)

# Every priced ALGO call pooled, grouped by what the market charged for that side.
bands = []
if prices:
    pooled = {}
    for key, _ in CALLERS:
        for b, (n, w, ps) in prices[key]["buckets"].items():
            t = pooled.setdefault(int(b), [0, 0, 0.0])
            t[0] += n
            t[1] += w
            t[2] += ps
    for b in sorted(pooled):
        n, w, ps = pooled[b]
        if b < 5:
            continue  # calls made against the market: too few to say anything
        bands.append({"lo": b * 10, "hi": b * 10 + 10, "n": n, "price_pct": round(100.0 * ps / n, 1), "win_pct": pct(w, n)})

first = time.gmtime(summary["first_ts"] - 4 * 3600)  # market day is US Eastern
last = time.gmtime(summary["last_ts"] - 4 * 3600)
hist = records["histcall"]
you = records["you"]
data = {
    "as_of": time.strftime("%b %-d, %Y", last),
    "first_round": time.strftime("%b %-d, %Y", first),
    "app_version": health["version"],
    "rounds": summary["rounds"], "yes": summary["yes"], "no": summary["no"],
    "yes_pct": pct(summary["yes"], summary["rounds"]),
    "days": round(summary["span_days"]),
    "flips": summary["flips"], "pairs": summary["pairs"], "flip_pct": pct(summary["flips"], summary["pairs"]),
    "longest_streak": summary["longest_streak"],
    "streaks": streaks,
    "histcall": {"wins": hist["wins"], "losses": hist["losses"], "scored": hist["scored"], "pct": pct(hist["wins"], hist["scored"])},
    "you": {"wins": you["wins"], "losses": you["losses"], "scored": you["scored"]},
    "calls_total": sum(r["scored"] for r in records.values()),
    "calls_since": calls_since,
    "algo": algo,
    "bands": bands,
}
out = ROOT / "tools" / "data.json"
out.write_text(json.dumps(data, indent=1) + "\n")
print(f"wrote {out}  {data['rounds']} rounds  as of {data['as_of']}")
