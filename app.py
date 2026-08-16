#!/usr/bin/env python3
"""
BTC Prediction — 15-min Yes/No round game mirroring Robinhood's "BTC 15 min"
prediction market (Kalshi KXBTC15M series) exactly: same strike, same result.

No pip installs. Python 3.7+.
"""
import calendar
import json
import os
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
import uuid
import http.client
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BP_DB", os.path.join(HERE, "data.db"))
PORT = int(os.environ.get("PORT", "8160"))
BIND = os.environ.get("BIND", "0.0.0.0")

KALSHI_HOST = "api.elections.kalshi.com"  # trading-api.kalshi.com is the dead old host
KALSHI_SERIES = "KXBTC15M"
COINBASE_HOST = "api.exchange.coinbase.com"
KRAKEN_HOST = "api.kraken.com"

LOCK_BUFFER_S = 60          # betting closes this long before close_time
ACTIVE_WINDOW_S = 45        # a client seen within this long ago counts as "active"
ACTIVE_ROUND_POLL_S = 15
ACTIVE_PRICE_POLL_S = 4
IDLE_CHECK_S = 5            # idle-mode cosmetic-poller cadence (no network call, just re-checks activity)
SETTLE_RETRY_S = 3
BACKFILL_LOOKBACK_S = 26 * 3600  # slightly over 24h so the scoreboard window is never short a round
LEAN_FULL_TILT_USD = 300.0
TICK_RETENTION_S = 3 * 3600


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
    markets = data.get("markets") or []
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
            self.conn.execute("""CREATE TABLE IF NOT EXISTS votes (
                round_id INTEGER NOT NULL, voter_id TEXT NOT NULL, choice TEXT NOT NULL,
                ts REAL NOT NULL, UNIQUE(round_id, voter_id))""")

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
    for _ in range(50):  # hard cap on pages so a bug can't loop forever
        data = kalshi_markets("settled", cursor=cursor, limit=100)
        markets = data.get("markets") or []
        if not markets:
            break
        stop = False
        for m in markets:
            close_t = parse_kalshi_ts(m["close_time"])
            if close_t < cutoff:
                stop = True
                break
            existing = db.query_one("SELECT result FROM rounds WHERE kalshi_ticker=?", (m["ticker"],))
            if existing and existing["result"] is not None:
                continue  # already correctly settled locally
            db.upsert_round(to_round_row(m))
            inserted += 1
        cursor = data.get("cursor")
        if stop or not cursor:
            break
    return inserted


def round_engine():
    try:
        n = backfill()
        print("[round_engine] backfilled %d rounds" % n, file=sys.stderr)
    except Exception as e:  # noqa
        print("[round_engine] backfill failed: %s" % e, file=sys.stderr)
    with STATE_LOCK:
        STATE["catching_up"] = False

    while True:
        current = None
        try:
            m = fetch_open_round()
            if m:
                row = to_round_row(m)
                db.upsert_round(row)
                with STATE_LOCK:
                    STATE["current_ticker"] = row["kalshi_ticker"]
                current = row
        except Exception as e:  # noqa
            print("[round_engine] open-round fetch failed: %s" % e, file=sys.stderr)

        # Scan for anything past close_time still unsettled, rather than trusting
        # "current" to still be the round that just closed -- Kalshi opens the next
        # round immediately, so a slow idle-mode wakeup can find the open-round query
        # already pointing at the NEW round, silently skipping the one that just ended.
        pending = db.query("SELECT kalshi_ticker FROM rounds WHERE result IS NULL AND close_time <= ?",
                            (time.time(),))
        for p in pending:
            settle_round(p["kalshi_ticker"])

        sleep_s = ACTIVE_ROUND_POLL_S
        if not is_active():
            if current and current["close_time"]:
                sleep_s = max(5, (current["close_time"] + LOCK_BUFFER_S + 5) - time.time())
            else:
                sleep_s = 60
        time.sleep(min(sleep_s, 20 * 60))


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


def my_vote_for(round_id, voter_id):
    if not round_id or not voter_id:
        return None
    row = db.query_one("SELECT choice FROM votes WHERE round_id=? AND voter_id=?", (round_id, voter_id))
    return row["choice"] if row else None


def vote_counts(round_id):
    rows = db.query("SELECT choice, COUNT(*) c FROM votes WHERE round_id=? GROUP BY choice", (round_id,))
    counts = {"yes": 0, "no": 0}
    for r in rows:
        counts[r["choice"]] = r["c"]
    return counts


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

    def _voter_id(self):
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        if "bp_vid" in cookies:
            return cookies["bp_vid"].value, {}
        vid = uuid.uuid4().hex
        return vid, {"Set-Cookie": "bp_vid=%s; Path=/; Max-Age=157680000; HttpOnly; SameSite=Lax" % vid}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            return self._serve_page()
        if path == "/health":
            return self._send(200, json.dumps({"ok": True, "catching_up": STATE["catching_up"]}).encode())
        if path == "/api/state":
            return self._api_state()
        if path == "/api/history":
            return self._api_history(urllib.parse.parse_qs(parsed.query))
        self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/vote":
            return self._api_vote()
        self._send(404, b'{"error":"not found"}')

    def _serve_page(self):
        try:
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        except Exception as e:  # noqa
            self._send(500, json.dumps({"error": str(e)}).encode())

    def _api_state(self):
        touch_client()
        voter_id, set_cookie = self._voter_id()
        cur = current_round_row()
        payload = {"now": time.time(), "catching_up": STATE["catching_up"], "current_round": None,
                   "last_settled": None, "live_price": STATE["live_price"],
                   "live_price_source": STATE["live_price_source"], "lean": None,
                   "ticks": STATE["recent_ticks"][-120:]}
        if cur:
            counts = vote_counts(cur["id"])
            payload["current_round"] = {
                "ticker": cur["kalshi_ticker"], "floor_strike": cur["floor_strike"],
                "open_time": cur["open_time"], "close_time": cur["close_time"], "lock_ts": cur["lock_ts"],
                "locked": time.time() >= cur["lock_ts"],
                "yes_votes": counts["yes"], "no_votes": counts["no"],
                "my_vote": my_vote_for(cur["id"], voter_id),
                "kalshi_yes_price": cur["kalshi_yes_price"], "kalshi_no_price": cur["kalshi_no_price"],
            }
            payload["lean"] = compute_lean(STATE["live_price"], cur["floor_strike"])
        last = last_settled_row()
        if last:
            my_vote = my_vote_for(last["id"], voter_id)
            payload["last_settled"] = {
                "ticker": last["kalshi_ticker"], "result": last["result"],
                "floor_strike": last["floor_strike"], "settlement_value": last["settlement_value"],
                "close_time": last["close_time"], "my_vote": my_vote,
                "my_outcome": ("won" if my_vote == last["result"] else "lost") if my_vote else None,
            }
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        headers.update(set_cookie)
        self._send(200, body, extra_headers=headers)

    def _api_history(self, qs):
        hours = float((qs.get("hours") or ["24"])[0])
        cutoff = time.time() - hours * 3600
        rows = db.query("""SELECT kalshi_ticker, close_time, floor_strike, settlement_value, result
                            FROM rounds WHERE result IS NOT NULL AND close_time >= ?
                            ORDER BY close_time ASC""", (cutoff,))
        tallies = {"yes": sum(1 for r in rows if r["result"] == "yes"),
                   "no": sum(1 for r in rows if r["result"] == "no")}
        self._send(200, json.dumps({"rounds": rows, "tallies": tallies}).encode())

    def _api_vote(self):
        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:  # noqa
            return self._send(400, b'{"error":"bad json"}')
        choice = data.get("choice")
        if choice not in ("yes", "no"):
            return self._send(400, b'{"error":"choice must be yes or no"}')
        cur = current_round_row()
        if not cur:
            return self._send(409, b'{"error":"no open round"}')
        if time.time() >= cur["lock_ts"]:
            return self._send(409, b'{"error":"round is locked"}')
        voter_id, set_cookie = self._voter_id()
        try:
            db.execute("INSERT INTO votes (round_id, voter_id, choice, ts) VALUES (?,?,?,?)",
                       (cur["id"], voter_id, choice, time.time()))
        except sqlite3.IntegrityError:
            pass  # already voted this round; fall through and report current tally
        counts = vote_counts(cur["id"])
        body = json.dumps({"ok": True, "my_vote": my_vote_for(cur["id"], voter_id),
                            "yes_votes": counts["yes"], "no_votes": counts["no"]}).encode()
        headers = {"Content-Type": "application/json"}
        headers.update(set_cookie)
        self._send(200, body, extra_headers=headers)

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
