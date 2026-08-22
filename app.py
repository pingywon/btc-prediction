#!/usr/bin/env python3
"""
BTC Prediction — 15-min Yes/No round game mirroring Robinhood's "BTC 15 min"
prediction market (Kalshi KXBTC15M series) exactly: same strike, same result.

No pip installs. Python 3.7+.
"""
import calendar
import json
import os
import re
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
import http.client
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BP_DB", os.path.join(HERE, "data.db"))
PORT = int(os.environ.get("PORT", "8160"))
BIND = os.environ.get("BIND", "0.0.0.0")

FONT_DIR = os.path.join(HERE, "fonts")
FONT_NAME_RE = re.compile(r"^[a-z0-9-]+\.woff2$")  # no dots or slashes -> no traversal

KALSHI_HOST = "api.elections.kalshi.com"  # trading-api.kalshi.com is the dead old host
KALSHI_SERIES = "KXBTC15M"
COINBASE_HOST = "api.exchange.coinbase.com"
KRAKEN_HOST = "api.kraken.com"

LOCK_BUFFER_S = 60          # betting closes this long before close_time
ACTIVE_WINDOW_S = 12 * 3600  # a visit keeps the app "active" (full-speed polling) for this long
ACTIVE_ROUND_POLL_S = 10
ACTIVE_PRICE_POLL_S = 2
IDLE_CHECK_S = 5             # how often threads re-check activity state (cheap, no network call)
IDLE_ROUND_RESYNC_S = 12 * 3600  # when idle, only re-sync with Kalshi this often (bulk backfill, not per-round)
GAP_BACKFILL_THRESHOLD_S = 20 * 60  # rounds are 15 min; >20 min since the newest row means a hole, not just "the current round hasn't closed yet"
SETTLE_RETRY_S = 3
ROUND_RETENTION_S = 30 * 24 * 3600  # rolling window -- owner doesn't need anything older
BACKFILL_LOOKBACK_S = ROUND_RETENTION_S
LEAN_FULL_TILT_USD = 300.0
TICK_RETENTION_S = 3 * 3600
MONTH_ABBR = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:  # noqa
        return "127.0.0.1"
    finally:
        s.close()


def parse_kalshi_ts(s):
    if not s:
        return None
    if "." in s:
        s = s.split(".")[0] + "Z"
    return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))


def http_get_json(host, path, timeout=10):
    conn = http.client.HTTPSConnection(host, timeout=timeout)
    try:
        conn.request("GET", path, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        resp = conn.getresponse()
        body = resp.read()
        if resp.status != 200:
            raise RuntimeError("%s %s -> HTTP %d" % (host, path, resp.status))
        return json.loads(body)
    finally:
        conn.close()


def kalshi_markets(status, cursor=None, limit=100):
    q = {"series_ticker": KALSHI_SERIES, "status": status, "limit": limit}
    if cursor:
        q["cursor"] = cursor
    return http_get_json(KALSHI_HOST, "/trade-api/v2/markets?" + urllib.parse.urlencode(q))


def fetch_open_round():
    data = kalshi_markets("open", limit=5)
    all_markets = data.get("markets") or []
    # Kalshi briefly creates a market shell before assigning its strike -- treat one
    # missing floor_strike as "not ready yet" rather than letting it KeyError and
    # abort the whole poll (which froze current_round for up to ~1min per rollover).
    markets = [m for m in all_markets if m.get("floor_strike") not in (None, "")]
    if not markets:
        return None
    now = time.time()
    markets.sort(key=lambda m: parse_kalshi_ts(m["open_time"]) or 0, reverse=True)
    for m in markets:
        if (parse_kalshi_ts(m["open_time"]) or 0) <= now:
            return m
    return markets[0]


def to_round_row(m):
    open_t = parse_kalshi_ts(m["open_time"])
    close_t = parse_kalshi_ts(m["close_time"])
    result = (m.get("result") or "").lower() or None
    settled = m.get("status") in ("finalized", "settled") or result in ("yes", "no")
    return {
        "kalshi_ticker": m["ticker"],
        "open_time": open_t,
        "close_time": close_t,
        "lock_ts": close_t - LOCK_BUFFER_S,
        "floor_strike": float(m["floor_strike"]),
        "result": result if settled else None,
        "settlement_value": float(m["expiration_value"]) if settled and m.get("expiration_value") not in (None, "") else None,
        "kalshi_yes_price": float(m.get("yes_bid_dollars") or m.get("last_price_dollars") or 0) or None,
        "kalshi_no_price": float(m.get("no_bid_dollars") or 0) or None,
    }


def robinhood_url(floor_strike, open_time):
    # Reverse-engineered from real Robinhood pages (not an official API) -- slug is
    # {thousands}-{cents-of-remainder, zero-padded to 5 digits}, e.g. $65,086.84 -> "65-08684".
    thousands = int(floor_strike // 1000)
    remainder_cents = round((floor_strike - thousands * 1000) * 100)
    slug = "%d-%05d" % (thousands, remainder_cents)
    dt = datetime.fromtimestamp(open_time, tz=ZoneInfo("America/New_York"))
    date_part = "%s-%02d-%d" % (MONTH_ABBR[dt.month - 1], dt.day, dt.year)
    return "https://robinhood.com/us/en/prediction-markets/crypto/events/btc-15-min-%s-target-%s/" % (slug, date_part)


class DB:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self.lock, self.conn:
            self.conn.execute("""CREATE TABLE IF NOT EXISTS ticks (
                ts REAL NOT NULL, price REAL NOT NULL, source TEXT NOT NULL)""")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_ts ON ticks(ts)")
            self.conn.execute("""CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kalshi_ticker TEXT NOT NULL UNIQUE,
                open_time REAL NOT NULL, close_time REAL NOT NULL, lock_ts REAL NOT NULL,
                floor_strike REAL NOT NULL, result TEXT, settlement_value REAL,
                kalshi_yes_price REAL, kalshi_no_price REAL, created_at REAL NOT NULL)""")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_rounds_close ON rounds(close_time)")
            self.conn.execute("DROP TABLE IF EXISTS votes")

    def execute(self, sql, params=()):
        with self.lock, self.conn:
            return self.conn.execute(sql, params)

    def query(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def query_one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def upsert_round(self, r):
        with self.lock, self.conn:
            self.conn.execute("""
                INSERT INTO rounds (kalshi_ticker, open_time, close_time, lock_ts, floor_strike,
                    result, settlement_value, kalshi_yes_price, kalshi_no_price, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(kalshi_ticker) DO UPDATE SET
                    result=excluded.result, settlement_value=excluded.settlement_value,
                    kalshi_yes_price=excluded.kalshi_yes_price, kalshi_no_price=excluded.kalshi_no_price
            """, (r["kalshi_ticker"], r["open_time"], r["close_time"], r["lock_ts"], r["floor_strike"],
                  r["result"], r["settlement_value"], r["kalshi_yes_price"], r["kalshi_no_price"], time.time()))


db = DB(DB_PATH)

STATE = {
    "catching_up": True,
    "current_ticker": None,
    "last_client_seen": 0.0,
    "live_price": None,
    "live_price_source": None,
    "recent_ticks": [],  # in-memory ring for the sparkline; DB is the durable copy
}
STATE_LOCK = threading.Lock()


def is_active():
    return (time.time() - STATE["last_client_seen"]) < ACTIVE_WINDOW_S


def touch_client():
    with STATE_LOCK:
        STATE["last_client_seen"] = time.time()


def backfill():
    cutoff = time.time() - BACKFILL_LOOKBACK_S
    cursor = None
    inserted = 0
    skipped = 0
    # 1 year of 15-min rounds is ~35k; cap well above that so a bug can't loop forever
    # but a full year's worth of pages can still complete.
    for _ in range(500):
        data = kalshi_markets("settled", cursor=cursor, limit=100)
        markets = data.get("markets") or []
        if not markets:
            break
        stop = False
        for m in markets:
            close_t = parse_kalshi_ts(m.get("close_time"))
            if close_t is None or close_t < cutoff:
                stop = True
                break
            existing = db.query_one("SELECT result FROM rounds WHERE kalshi_ticker=?", (m["ticker"],))
            if existing and existing["result"] is not None:
                continue  # already correctly settled locally
            try:
                db.upsert_round(to_round_row(m))
                inserted += 1
            except (KeyError, TypeError, ValueError) as e:
                # Older Kalshi records occasionally don't match the current market
                # shape (e.g. missing floor_strike) -- skip that one round rather
                # than aborting the whole sweep; log so a real regression is visible.
                skipped += 1
                print("[backfill] skipped %s: %s" % (m.get("ticker", "?"), e), file=sys.stderr)
        cursor = data.get("cursor")
        if stop or not cursor:
            break
    if skipped:
        print("[backfill] skipped %d malformed record(s)" % skipped, file=sys.stderr)
    return inserted


def prune_old_rounds():
    cutoff = time.time() - ROUND_RETENTION_S
    cur = db.execute("DELETE FROM rounds WHERE close_time < ?", (cutoff,))
    return cur.rowcount if cur else 0


def newest_settled_close_time():
    # Deliberately excludes the still-open round: refresh_open_round() runs right
    # before this is checked and always upserts whatever Kalshi currently reports as
    # open, so MAX(close_time) over ALL rows would almost always land on that live
    # round's (near-future) close_time and mask an arbitrarily large hole sitting
    # right behind it. Anchoring on the newest SETTLED row instead measures the thing
    # that actually broke in production: "how long since we last durably recorded a
    # finished round," independent of whether the open-round pointer is fresh.
    row = db.query_one("SELECT MAX(close_time) AS m FROM rounds WHERE result IS NOT NULL")
    return row["m"] if row and row["m"] is not None else 0.0


def refresh_open_round():
    try:
        m = fetch_open_round()
        if m:
            row = to_round_row(m)
            db.upsert_round(row)
            with STATE_LOCK:
                STATE["current_ticker"] = row["kalshi_ticker"]
    except Exception as e:  # noqa
        print("[round_engine] open-round fetch failed: %s" % e, file=sys.stderr)


def round_engine():
    try:
        n = backfill()
        print("[round_engine] backfilled %d rounds" % n, file=sys.stderr)
    except Exception as e:  # noqa
        print("[round_engine] backfill failed: %s" % e, file=sys.stderr)
    try:
        prune_old_rounds()
    except Exception as e:  # noqa
        print("[round_engine] prune failed: %s" % e, file=sys.stderr)
    with STATE_LOCK:
        STATE["catching_up"] = False

    refresh_open_round()
    last_prune = time.time()

    # The IDLE_CHECK_S loop below always runs so activity changes are noticed within
    # a few seconds; actual Kalshi calls only fire when "due", at ACTIVE_ROUND_POLL_S
    # while someone's watching or IDLE_ROUND_RESYNC_S (12h) while nobody is -- so a
    # long quiet stretch costs ~2 Kalshi calls/day instead of one every 15 minutes.
    # Seeded to "now" (not 0) since the current round was just fetched above -- the
    # loop's first iteration shouldn't immediately treat itself as overdue and re-run
    # the just-finished startup backfill a second time.
    last_check = time.time()
    while True:
        active = is_active()
        interval = ACTIVE_ROUND_POLL_S if active else IDLE_ROUND_RESYNC_S
        if time.time() - last_check >= interval:
            last_check = time.time()
            refresh_open_round()

            # Detect any hole in recent history and self-heal it immediately, rather
            # than only during the scheduled 12h idle resync. A hole can open for lots
            # of reasons beyond "nobody was watching" -- a slow wakeup from sleep, a
            # Kalshi hiccup, or simply the idle->active transition itself (someone
            # opens the page after a long gap: `active` flips true THIS tick, so the
            # interval shrinks to ACTIVE_ROUND_POLL_S and this check fires within
            # seconds instead of waiting up to 12h). Re-running the startup sweep is
            # cheap when there's nothing new (every existing row just gets skipped),
            # so gating it on "is there actually a gap" rather than "are we idle"
            # covers both cases with one mechanism instead of two.
            if time.time() - newest_settled_close_time() > GAP_BACKFILL_THRESHOLD_S:
                try:
                    n = backfill()
                    if n:
                        print("[round_engine] gap catch-up backfilled %d rounds" % n, file=sys.stderr)
                except Exception as e:  # noqa
                    print("[round_engine] gap catch-up failed: %s" % e, file=sys.stderr)

            if time.time() - last_prune > 3600:
                last_prune = time.time()
                try:
                    prune_old_rounds()
                except Exception as e:  # noqa
                    print("[round_engine] prune failed: %s" % e, file=sys.stderr)

            if active:
                # Scan for anything past close_time still unsettled, rather than trusting
                # "current" to still be the round that just closed -- Kalshi opens the next
                # round immediately, so a slow wakeup can find the open-round query already
                # pointing at the NEW round, silently skipping the one that just ended.
                pending = db.query("SELECT kalshi_ticker FROM rounds WHERE result IS NULL AND close_time <= ?",
                                    (time.time(),))
                for p in pending:
                    settle_round(p["kalshi_ticker"])

        time.sleep(IDLE_CHECK_S)


def settle_round(ticker):
    for _ in range(20):
        try:
            data = kalshi_markets("settled", limit=25)
            for m in data.get("markets") or []:
                if m["ticker"] == ticker and (m.get("result") or ""):
                    db.upsert_round(to_round_row(m))
                    return True
        except Exception as e:  # noqa
            print("[settle_round] %s" % e, file=sys.stderr)
        time.sleep(SETTLE_RETRY_S)
    return False


def fetch_cosmetic_price():
    try:
        d = http_get_json(COINBASE_HOST, "/products/BTC-USD/ticker")
        return float(d["price"]), "coinbase"
    except Exception:  # noqa
        pass
    d = http_get_json(KRAKEN_HOST, "/0/public/Ticker?pair=XBTUSD")
    pair = next(iter(d["result"].values()))
    return float(pair["c"][0]), "kraken"


def price_poller():
    last_prune = 0.0
    while True:
        if is_active():
            try:
                price, source = fetch_cosmetic_price()
                now = time.time()
                with STATE_LOCK:
                    STATE["live_price"] = price
                    STATE["live_price_source"] = source
                    STATE["recent_ticks"].append((now, price))
                    STATE["recent_ticks"] = STATE["recent_ticks"][-300:]
                db.execute("INSERT INTO ticks (ts, price, source) VALUES (?,?,?)", (now, price, source))
                if now - last_prune > 300:
                    db.execute("DELETE FROM ticks WHERE ts < ?", (now - TICK_RETENTION_S,))
                    last_prune = now
            except Exception as e:  # noqa
                print("[price_poller] %s" % e, file=sys.stderr)
            time.sleep(ACTIVE_PRICE_POLL_S)
        else:
            time.sleep(IDLE_CHECK_S)


def current_round_row():
    with STATE_LOCK:
        ticker = STATE["current_ticker"]
    if not ticker:
        return None
    return db.query_one("SELECT * FROM rounds WHERE kalshi_ticker=?", (ticker,))


def last_settled_row():
    return db.query_one("SELECT * FROM rounds WHERE result IS NOT NULL ORDER BY close_time DESC LIMIT 1")


def compute_road_stats(rows):
    results = [r["result"] for r in rows]  # already chronological (close_time ASC)
    if not results:
        return {"current_streak": None, "longest_streak": None, "chop_rate": None, "flips": None, "pairs": None}

    cur_result = results[-1]
    cur_len = 1
    for r in reversed(results[:-1]):
        if r != cur_result:
            break
        cur_len += 1

    longest_result, longest_len = results[0], 1
    run_result, run_len = results[0], 1
    for r in results[1:]:
        run_len = run_len + 1 if r == run_result else 1
        run_result = r
        if run_len > longest_len:
            longest_len, longest_result = run_len, run_result

    flips = sum(1 for a, b in zip(results, results[1:]) if a != b)
    pairs = len(results) - 1
    chop_rate = round(100.0 * flips / pairs, 1) if pairs else None

    return {
        "current_streak": {"result": cur_result, "length": cur_len},
        "longest_streak": {"result": longest_result, "length": longest_len},
        "chop_rate": chop_rate,
        "flips": flips,
        "pairs": pairs,
    }


def compute_lean(price, strike):
    if price is None or strike is None:
        return None
    delta = price - strike
    strength = max(0.0, min(1.0, abs(delta) / LEAN_FULL_TILT_USD))
    return {"direction": "yes" if delta >= 0 else "no", "strength": round(strength, 3), "delta": round(delta, 2)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json", extra_headers=None):
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            for k, v in (extra_headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionError):
            pass

    def do_GET(self):
        # Any unhandled exception below this point previously propagated straight out
        # of do_GET with no response ever sent -- the client just saw the connection
        # drop ("empty reply"), which looks exactly like a dead button/silent no-op.
        # Catch broadly here so a bug in one endpoint always yields a real JSON error
        # instead of a vanished connection.
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path in ("/", "/index.html"):
                return self._serve_page("index.html")
            if path in ("/algo", "/algo.html"):
                return self._serve_page("algo.html")
            if path in ("/fluid", "/fluid.html"):
                return self._serve_page("fluid.html")
            if path in ("/ticket", "/ticket.html"):
                return self._serve_page("ticket.html")
            if path in ("/board", "/board.html"):
                return self._serve_page("board.html")
            if path in ("/gauge", "/gauge.html"):
                return self._serve_page("gauge.html")
            if path in ("/terminal", "/terminal.html"):
                return self._serve_page("terminal.html")
            if path in ("/tape", "/tape.html"):
                return self._serve_page("tape.html")
            if path.startswith("/fonts/"):
                return self._serve_font(path[len("/fonts/"):])
            if path == "/health":
                return self._send(200, json.dumps({"ok": True, "catching_up": STATE["catching_up"]}).encode())
            if path == "/api/state":
                return self._api_state()
            if path == "/api/history":
                return self._api_history(urllib.parse.parse_qs(parsed.query))
            if path == "/api/ticks":
                return self._api_ticks(urllib.parse.parse_qs(parsed.query))
            self._send(404, b'{"error":"not found"}')
        except Exception as e:  # noqa
            print("[http] GET %s failed: %s" % (self.path, e), file=sys.stderr)
            try:
                self._send(500, json.dumps({"error": "internal error"}).encode())
            except Exception:  # noqa
                pass

    def do_POST(self):
        self._send(404, b'{"error":"not found"}')

    def _serve_page(self, filename):
        try:
            with open(os.path.join(HERE, filename), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        except Exception as e:  # noqa
            self._send(500, json.dumps({"error": str(e)}).encode())

    def _serve_font(self, name):
        # Self-hosted webfonts (see fonts/LICENSE.md) -- the pages are zero-CDN, and the
        # v3 skins need a real weight 200 that no system font stack provides.
        #
        # This is the only place in the app where a request path reaches the filesystem,
        # so the name is checked twice: a strict character whitelist (no dots, no slashes,
        # so "..", absolute paths and encoded traversal can't survive it), and then a
        # realpath containment check in case the first one is ever loosened.
        if not FONT_NAME_RE.match(name or ""):
            return self._send(404, b'{"error":"not found"}')
        path = os.path.realpath(os.path.join(FONT_DIR, name))
        if os.path.commonpath([path, os.path.realpath(FONT_DIR)]) != os.path.realpath(FONT_DIR):
            return self._send(404, b'{"error":"not found"}')
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            return self._send(404, b'{"error":"not found"}')
        # Font files are immutable once shipped; let the browser keep them for a year so
        # this is one download shared across all six pages rather than per-page.
        self._send(200, body, "font/woff2", {"Cache-Control": "public, max-age=31536000, immutable"})

    def _api_state(self):
        touch_client()
        cur = current_round_row()
        payload = {"now": time.time(), "catching_up": STATE["catching_up"], "current_round": None,
                   "last_settled": None, "live_price": STATE["live_price"],
                   "live_price_source": STATE["live_price_source"], "lean": None,
                   "ticks": STATE["recent_ticks"][-120:]}
        if cur:
            payload["current_round"] = {
                "ticker": cur["kalshi_ticker"], "floor_strike": cur["floor_strike"],
                "open_time": cur["open_time"], "close_time": cur["close_time"], "lock_ts": cur["lock_ts"],
                "locked": time.time() >= cur["lock_ts"],
                "kalshi_yes_price": cur["kalshi_yes_price"], "kalshi_no_price": cur["kalshi_no_price"],
                "robinhood_url": robinhood_url(cur["floor_strike"], cur["open_time"]),
            }
            payload["lean"] = compute_lean(STATE["live_price"], cur["floor_strike"])
        last = last_settled_row()
        if last:
            payload["last_settled"] = {
                "ticker": last["kalshi_ticker"], "result": last["result"],
                "floor_strike": last["floor_strike"], "settlement_value": last["settlement_value"],
                "close_time": last["close_time"],
            }
        self._send(200, json.dumps(payload).encode())

    def _api_history(self, qs):
        hours = float((qs.get("hours") or ["24"])[0])
        cutoff = time.time() - hours * 3600
        rows = db.query("""SELECT kalshi_ticker, close_time, floor_strike, settlement_value, result
                            FROM rounds WHERE result IS NOT NULL AND close_time >= ?
                            ORDER BY close_time ASC""", (cutoff,))
        # floor_strike(N) == settlement_value(N-1) (Kalshi chains rounds), so this delta is both
        # "price change since the previous round" and the exact number that decided yes/no.
        # A handful of older Kalshi records are settled (result set) but never got an
        # expiration_value (see to_round_row) -- settlement_value is None for those, so
        # delta must stay None too instead of crashing the whole request (this previously
        # took down any timeframe whose window reached back far enough to include one,
        # e.g. "1Y", with the connection just dropping and the button looking dead).
        for r in rows:
            r["delta"] = round(r["settlement_value"] - r["floor_strike"], 2) if r["settlement_value"] is not None else None
        tallies = {"yes": sum(1 for r in rows if r["result"] == "yes"),
                   "no": sum(1 for r in rows if r["result"] == "no")}
        tallies.update(compute_road_stats(rows))
        self._send(200, json.dumps({"rounds": rows, "tallies": tallies}).encode())

    def _api_ticks(self, qs):
        # The in-memory ring buffer (STATE["recent_ticks"]) only holds ~10 minutes and
        # resets on restart -- not enough to chart a full 15-minute round. Ticks are
        # also durably written to the DB (3h retention), so read from there instead;
        # a single round's window is always comfortably inside that retention.
        since = float((qs.get("since") or ["0"])[0])
        until = qs.get("until")
        if until:
            rows = db.query("SELECT ts, price FROM ticks WHERE ts >= ? AND ts < ? ORDER BY ts ASC",
                             (since, float(until[0])))
        else:
            rows = db.query("SELECT ts, price FROM ticks WHERE ts >= ? ORDER BY ts ASC", (since,))
        self._send(200, json.dumps({"ticks": [[r["ts"], r["price"]] for r in rows]}).encode())

    def log_message(self, *a):
        pass


def main():
    threading.Thread(target=round_engine, daemon=True).start()
    threading.Thread(target=price_poller, daemon=True).start()
    print("\n  BTC Prediction")
    print("  --------------")
    print("  Bind:  %s:%d" % (BIND, PORT))
    print("  Local: http://localhost:%d/" % PORT)
    print("  LAN:   http://%s:%d/" % (lan_ip(), PORT))
    print("  Press Ctrl+C to stop.\n")
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
