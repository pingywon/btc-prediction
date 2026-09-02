#!/usr/bin/env python3
"""
BTC Prediction — 15-min Yes/No round game mirroring Robinhood's "BTC 15 min"
prediction market (Kalshi KXBTC15M series) exactly: same strike, same result.

No pip installs. Python 3.7+.
"""
import base64
import calendar
import json
import os
import re
import socket
import sqlite3
import ssl
import struct
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
PORT = int(os.environ.get("PORT", "80"))
BIND = os.environ.get("BIND", "0.0.0.0")

# Single source of truth for the app version. Bump here first on every release;
# the git tag vX.Y.Z, the Dockerfile LABEL and the README line must match.
VERSION = "5.0.0"

FONT_DIR = os.path.join(HERE, "fonts")
# The skins stopped being their own pages; these old URLs redirect into the
# Studio with that skin selected.
SKIN_ROUTES = {}
for _s in ("ticket", "board", "gauge", "terminal", "tape", "blueprint", "arcade", "pit"):
    SKIN_ROUTES["/" + _s] = _s
    SKIN_ROUTES["/" + _s + ".html"] = _s

FONT_NAME_RE = re.compile(r"^[a-z0-9-]+\.woff2$")  # no dots or slashes -> no traversal

KALSHI_HOST = "api.elections.kalshi.com"  # trading-api.kalshi.com is the dead old host
KALSHI_SERIES = "KXBTC15M"
COINBASE_HOST = "api.exchange.coinbase.com"
KRAKEN_HOST = "api.kraken.com"

LOCK_BUFFER_S = 60          # betting closes this long before close_time
ACTIVE_WINDOW_S = 12 * 3600  # a visit keeps the app "active" (full-speed polling) for this long
ACTIVE_ROUND_POLL_S = 10
ROLLOVER_WINDOW_S = 20       # this close to round close (or past it), poll Kalshi fast (BTC-20)
ROLLOVER_POLL_S = 2
ACTIVE_PRICE_POLL_S = 2      # REST price cadence while active (fallback when the stream is up)
IDLE_PRICE_POLL_S = 5        # BTC-17: the price records 24/7 now; idle just polls slower
PRICE_WS_HOST = "ws-feed.exchange.coinbase.com"  # BTC-18: streamed ticks, REST is the fallback
PRICE_WS_IDLE_TIMEOUT_S = 15  # no ticker frame for this long -> reconnect
PRICE_TICK_DB_MIN_S = 1.0    # the stream can fire many times/sec; throttle durable tick rows
IDLE_CHECK_S = 5             # how often threads re-check activity state (cheap, no network call)
IDLE_ROUND_RESYNC_S = 12 * 3600  # when idle, only re-sync with Kalshi this often (bulk backfill, not per-round)
GAP_BACKFILL_THRESHOLD_S = 20 * 60  # rounds are 15 min; >20 min since the newest row means a hole, not just "the current round hasn't closed yet"
STARTUP_BACKFILL_TRIES = 12  # qnet needs ~30s after container start before egress works
ROUND_RETENTION_S = None  # None = never prune; the board charts every round we have ever seen
BACKFILL_LOOKBACK_S = 400 * 24 * 3600  # ask far past Kalshi's real depth (~68d) so it self-limits, not us
LEAN_FULL_TILT_USD = 300.0
TICK_RETENTION_S = 3 * 3600
CALLER_CHECK_S = 5           # caller_loop cadence: round freshness, settlement, auto calls
CALL_WINDOW_S = 120          # algo + histcall calls fire when lock_ts-120 <= now < lock_ts
PRICE_STALE_S = 15           # the price poller sleeps when idle; refetch for the lean if older
SETTLE_SCAN_WINDOW_S = 6 * 3600  # only chase pending rounds this recent (backfill owns older holes)
ALGO_COINFLIP_EPS = 0.04     # odds closer than this are a coin flip; fall back to the live lean
# BTC-25: a SECOND ALGO call made earlier in the round, so there's a read while betting
# is still open. Offset picked from a 7,190-round backtest: T-5:00 scored 85.3% (vs 94% at
# lock) -- see early_call_study.py. Fires within a bounded window so an early call always
# means "~5 min out", never a late call mislabelled early; a missed window is an honest hole.
ALGO_EARLY_OFFSET_S = 300    # fire at close_time - 300 (5:00 before close = 10:00 into the round)
ALGO_EARLY_WINDOW_S = 60     # ...within this window; else that round gets no early call
CALL_SOURCES = ("you", "algo", "algoearly", "histcall")
COVERAGE_WINDOW = 100        # BTC-17: "called n of the last N settled rounds" window
HC_BACKFILL_EVERY_S = 60     # BTC-17: how often to sweep for History Call holes
HC_BACKFILL_BATCH = 200      # holes filled per sweep (deterministic, so catching up is safe)
PICKS_MAX_BYTES = 10_000
KV_MAX_BYTES = 200_000
KV_KEYS = ("board", "classic_modules", "algo_modules")
IMPORT_MAX_BYTES = 2_000_000
IMPORT_MAX_ENTRIES = 20_000  # per source; ~70 days of rounds is ~7k
MONTH_ABBR = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _f(x):
    """Parse an external numeric that may arrive as a thousands-comma STRING.
    Kalshi has been observed returning e.g. expiration_value='77,362.10'; plain
    float() raises on the comma, which (inside settle_pending_once, run every 5s)
    aborted the whole caller tick and silently stopped ALL calls. None/"" -> None."""
    if x is None or x == "":
        return None
    if isinstance(x, str):
        x = x.replace(",", "")
    return float(x)


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


def kalshi_markets(status, cursor=None, limit=1000):
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
        "floor_strike": _f(m["floor_strike"]),
        "result": result if settled else None,
        "settlement_value": _f(m["expiration_value"]) if settled and m.get("expiration_value") not in (None, "") else None,
        "kalshi_yes_price": _f(m.get("yes_bid_dollars") or m.get("last_price_dollars") or 0) or None,
        "kalshi_no_price": _f(m.get("no_bid_dollars") or 0) or None,
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
            # Studio save slots (1..5), server-side so a saved board follows the owner
            # across browsers and devices.
            self.conn.execute("""CREATE TABLE IF NOT EXISTS layouts (
                slot INTEGER PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL,
                saved_at REAL NOT NULL)""")
            # v4.15.0 "full memory": every call, every round, on the server. Sources:
            # 'you' (the owner's pick), 'algo' (the server's own AI, made 24/7 whether or
            # not a browser is open) and 'histcall' (the order-3 History Call). Records
            # are ALWAYS derived by joining against rounds.result -- never stored
            # counters, so they cannot drift.
            self.conn.execute("""CREATE TABLE IF NOT EXISTS calls (
                kalshi_ticker TEXT NOT NULL, source TEXT NOT NULL,
                choice TEXT NOT NULL, reason TEXT, ts REAL NOT NULL,
                PRIMARY KEY (kalshi_ticker, source))""")
            # Small key-value store: the Studio's CURRENT board (key 'board'), and the
            # Classic/ALGO module preferences -- the state that must follow the owner.
            self.conn.execute("""CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY, payload TEXT NOT NULL, saved_at REAL NOT NULL)""")

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

    def list_layouts(self):
        return self.query("SELECT slot, name, payload, saved_at FROM layouts ORDER BY slot")

    def upsert_layout(self, slot, name, payload_text):
        with self.lock, self.conn:
            self.conn.execute("""
                INSERT INTO layouts (slot, name, payload, saved_at) VALUES (?,?,?,?)
                ON CONFLICT(slot) DO UPDATE SET
                    name=excluded.name, payload=excluded.payload, saved_at=excluded.saved_at
            """, (slot, name, payload_text, time.time()))

    def delete_layout(self, slot):
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM layouts WHERE slot=?", (slot,))

    def upsert_call(self, ticker, source, choice, reason, ts):
        # 'you' may overwrite before lock; the endpoint enforces the lock.
        with self.lock, self.conn:
            self.conn.execute("""
                INSERT INTO calls (kalshi_ticker, source, choice, reason, ts) VALUES (?,?,?,?,?)
                ON CONFLICT(kalshi_ticker, source) DO UPDATE SET
                    choice=excluded.choice, reason=excluded.reason, ts=excluded.ts
            """, (ticker, source, choice, reason, ts))

    def insert_call_ignore(self, ticker, source, choice, reason, ts):
        # algo/histcall/import are write-once: the first call for a round stands.
        # Returns whether a row was actually inserted (False = it already existed).
        with self.lock, self.conn:
            cur = self.conn.execute("INSERT OR IGNORE INTO calls (kalshi_ticker, source, choice, reason, ts) "
                                    "VALUES (?,?,?,?,?)", (ticker, source, choice, reason, ts))
            return cur.rowcount > 0

    def delete_calls(self, source):
        # BTC-16: the reset. Only 'you' is ever passed; the endpoint enforces that.
        with self.lock, self.conn:
            cur = self.conn.execute("DELETE FROM calls WHERE source=?", (source,))
            return cur.rowcount

    def delete_call(self, ticker, source):
        with self.lock, self.conn:
            cur = self.conn.execute("DELETE FROM calls WHERE kalshi_ticker=? AND source=?", (ticker, source))
            return cur.rowcount

    def calls_for_round(self, ticker):
        if not ticker:
            return {}
        rows = self.query("SELECT source, choice, reason, ts FROM calls WHERE kalshi_ticker=?", (ticker,))
        return {r["source"]: {"choice": r["choice"], "reason": r["reason"], "ts": r["ts"]} for r in rows}

    def calls_records(self):
        return self.query("""
            SELECT c.source,
                   SUM(c.choice = r.result) AS wins,
                   SUM(c.choice != r.result) AS losses
            FROM calls c JOIN rounds r ON r.kalshi_ticker = c.kalshi_ticker
            WHERE r.result IS NOT NULL GROUP BY c.source""")

    def coverage_counts(self, window):
        # BTC-17: "called n of the last N settled rounds" -- the proof the 24/7
        # recording is actually recording, per source.
        rows = self.query("""
            SELECT c.source, COUNT(*) AS called
            FROM calls c JOIN (SELECT kalshi_ticker FROM rounds WHERE result IS NOT NULL
                               ORDER BY close_time DESC LIMIT ?) w
                 ON w.kalshi_ticker = c.kalshi_ticker
            GROUP BY c.source""", (window,))
        n = self.query_one("SELECT COUNT(*) AS n FROM (SELECT 1 FROM rounds WHERE result IS NOT NULL "
                           "ORDER BY close_time DESC LIMIT ?)", (window,))
        return rows, int(n["n"] if n else 0)

    def recent_scored_calls(self, limit=50):
        return self.query("""
            SELECT c.kalshi_ticker, c.source, c.choice, c.reason, c.ts, r.result, r.close_time
            FROM calls c JOIN rounds r ON r.kalshi_ticker = c.kalshi_ticker
            WHERE r.result IS NOT NULL
            ORDER BY r.close_time DESC, c.source LIMIT ?""", (limit,))

    def kv_get(self, key):
        return self.query_one("SELECT payload, saved_at FROM kv WHERE key=?", (key,))

    def kv_set(self, key, payload_text):
        # Monotonic saved_at: open tabs compare against it to notice newer boards, so two
        # saves inside the same clock tick must still order.
        with self.lock, self.conn:
            row = self.conn.execute("SELECT saved_at FROM kv WHERE key=?", (key,)).fetchone()
            saved_at = max(time.time(), (row["saved_at"] + 0.001) if row else 0.0)
            self.conn.execute("""
                INSERT INTO kv (key, payload, saved_at) VALUES (?,?,?)
                ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, saved_at=excluded.saved_at
            """, (key, payload_text, saved_at))
            return saved_at


db = DB(DB_PATH)

STATE = {
    "catching_up": True,
    "current_ticker": None,
    "last_client_seen": 0.0,
    "live_price": None,
    "live_price_source": None,
    "live_price_ts": 0.0,
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
        data = kalshi_markets("settled", cursor=cursor, limit=1000)
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
    if ROUND_RETENTION_S is None:
        return 0
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
    # The QNAP's qnet VLAN interface is not usable for the first several seconds of a
    # container's life, so the very first Kalshi call reliably dies with "No route to
    # host". A single attempt loses the whole startup backfill, and nothing else re-runs
    # it until a gap is seen or the 12h idle resync -- so retry here instead.
    for attempt in range(STARTUP_BACKFILL_TRIES):
        try:
            n = backfill()
            print("[round_engine] backfilled %d rounds" % n, file=sys.stderr)
            break
        except Exception as e:  # noqa
            print("[round_engine] backfill attempt %d/%d failed: %s"
                  % (attempt + 1, STARTUP_BACKFILL_TRIES, e), file=sys.stderr)
            if attempt + 1 < STARTUP_BACKFILL_TRIES:
                time.sleep(min(20, 3 + attempt * 3))
    try:
        prune_old_rounds()
    except Exception as e:  # noqa
        print("[round_engine] prune failed: %s" % e, file=sys.stderr)
    with STATE_LOCK:
        STATE["catching_up"] = False

    refresh_open_round()
    last_prune = time.time()

    # The loop below always runs so activity changes are noticed within a couple of
    # seconds; actual Kalshi calls only fire when "due", at ACTIVE_ROUND_POLL_S
    # while someone's watching or IDLE_ROUND_RESYNC_S (12h) while nobody is -- so a
    # long quiet stretch costs ~2 Kalshi calls/day instead of one every 15 minutes.
    # BTC-20: near the round boundary (or while the finished round is still the
    # pointer because Kalshi hasn't opened/blessed the next market yet) an active
    # app polls at ROLLOVER_POLL_S so the next round appears within seconds, not
    # most of a minute. Idle stays lazy -- caller_loop keeps the pointer fresh there.
    # Seeded to "now" (not 0) since the current round was just fetched above -- the
    # loop's first iteration shouldn't immediately treat itself as overdue and re-run
    # the just-finished startup backfill a second time.
    last_check = time.time()
    while True:
        active = is_active()
        interval = ACTIVE_ROUND_POLL_S if active else IDLE_ROUND_RESYNC_S
        if active:
            cur = current_round_row()
            if cur is None or time.time() >= cur["close_time"] - ROLLOVER_WINDOW_S:
                interval = ROLLOVER_POLL_S
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

        # 1s granularity while active so the ROLLOVER_POLL_S cadence is real; the
        # extra wakeups are a clock check and one tiny DB read, no network.
        time.sleep(1 if active else IDLE_CHECK_S)


def fetch_cosmetic_price():
    try:
        d = http_get_json(COINBASE_HOST, "/products/BTC-USD/ticker")
        return _f(d["price"]), "coinbase"
    except Exception:  # noqa
        pass
    d = http_get_json(KRAKEN_HOST, "/0/public/Ticker?pair=XBTUSD")
    pair = next(iter(d["result"].values()))
    return _f(pair["c"][0]), "kraken"


_tick_write = {"last_db": 0.0, "last_prune": 0.0}


def record_tick(price, source, now=None):
    """Shared by the stream and the REST poller: STATE on every call, a durable tick
    row at most every PRICE_TICK_DB_MIN_S (the stream fires many times a second)."""
    now = now or time.time()
    with STATE_LOCK:
        STATE["live_price"] = price
        STATE["live_price_source"] = source
        STATE["live_price_ts"] = now
        STATE["recent_ticks"].append((now, price))
        STATE["recent_ticks"] = STATE["recent_ticks"][-300:]
    if now - _tick_write["last_db"] >= PRICE_TICK_DB_MIN_S:
        _tick_write["last_db"] = now
        db.execute("INSERT INTO ticks (ts, price, source) VALUES (?,?,?)", (now, price, source))
        if now - _tick_write["last_prune"] > 300:
            _tick_write["last_prune"] = now
            db.execute("DELETE FROM ticks WHERE ts < ?", (now - TICK_RETENTION_S,))


def price_poller():
    # BTC-17/18: REST is the FALLBACK now, and it never sleeps for good -- the price
    # (and therefore the ALGO's lean input and the tick history) records 24/7. While
    # the websocket stream is delivering, this loop just watches freshness and idles.
    while True:
        with STATE_LOCK:
            age = time.time() - STATE["live_price_ts"]
        if age >= ACTIVE_PRICE_POLL_S:
            try:
                price, source = fetch_cosmetic_price()
                record_tick(price, source)
            except Exception as e:  # noqa
                print("[price_poller] %s" % e, file=sys.stderr)
        time.sleep(ACTIVE_PRICE_POLL_S if is_active() else IDLE_PRICE_POLL_S)


# ---------------------------------------------------------------------------
# BTC-18: a hand-rolled RFC6455 client (this repo is deliberately pip-free) for
# Coinbase's public ticker feed. Sub-second price instead of 2s REST polling.

def _ws_connect(host, path="/"):
    raw = socket.create_connection((host, 443), timeout=10)
    s = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host, key)).encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = s.recv(4096)
        if not chunk:
            raise RuntimeError("ws handshake: connection closed")
        resp += chunk
        if len(resp) > 65536:
            raise RuntimeError("ws handshake: oversized response")
    if b" 101 " not in resp.split(b"\r\n", 1)[0]:
        raise RuntimeError("ws handshake refused: %r" % resp.split(b"\r\n", 1)[0])
    s.settimeout(PRICE_WS_IDLE_TIMEOUT_S)
    return s


def _ws_send(s, payload, opcode=1):
    # Client frames MUST be masked (RFC6455 5.3).
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    mask = os.urandom(4)
    s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def _ws_read_exact(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise RuntimeError("ws: connection closed")
        buf += chunk
    return buf


def _ws_recv(s):
    """One frame -> (opcode, payload). Coinbase sends unfragmented text frames."""
    b1, b2 = _ws_read_exact(s, 2)
    opcode = b1 & 0x0F
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack(">H", _ws_read_exact(s, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", _ws_read_exact(s, 8))[0]
    if b2 & 0x80:  # masked server frame -- never happens, but read the key if so
        mask = _ws_read_exact(s, 4)
        data = _ws_read_exact(s, n)
        return opcode, bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, _ws_read_exact(s, n)


def price_stream():
    """Daemon: Coinbase ticker websocket -> record_tick. Any failure just falls back
    to the REST poller (which watches live_price_ts age) until the next reconnect."""
    backoff = 1
    while True:
        s = None
        try:
            s = _ws_connect(PRICE_WS_HOST)
            _ws_send(s, json.dumps({"type": "subscribe", "product_ids": ["BTC-USD"],
                                    "channels": ["ticker"]}).encode())
            backoff = 1
            while True:
                opcode, payload = _ws_recv(s)
                if opcode == 8:  # close
                    raise RuntimeError("ws: server closed")
                if opcode == 9:  # ping -> pong, same payload
                    _ws_send(s, payload, opcode=10)
                    continue
                if opcode != 1:
                    continue
                try:
                    msg = json.loads(payload)
                except ValueError:
                    continue
                if msg.get("type") == "ticker" and msg.get("price"):
                    record_tick(_f(msg["price"]), "coinbase-ws")
                elif msg.get("type") == "error":
                    raise RuntimeError("ws error: %s" % msg.get("message"))
        except Exception as e:  # noqa
            print("[price_stream] %s (retry in %ds)" % (e, backoff), file=sys.stderr)
        finally:
            try:
                if s:
                    s.close()
            except Exception:  # noqa
                pass
        time.sleep(backoff)
        backoff = min(backoff * 2, 30)


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


def _pct(x):
    # JS Math.round semantics (half toward +inf); Python's round() is banker's.
    return int(x * 100 + 0.5)


def compute_algo_pick(cur, lean):
    """The ALGO Desk's brain, moved server-side (exact port of the page's heuristic):
    Kalshi's own live odds are the signal; odds within ALGO_COINFLIP_EPS of even fall
    back to the live price position. Note to_round_row's `or None` maps a genuine 0.0
    price to None (inherited quirk, kept for parity with what the page always saw)."""
    if not cur:
        return None
    yes, no = cur["kalshi_yes_price"], cur["kalshi_no_price"]
    if yes is not None:
        eff_no = no if no is not None else 1.0 - yes
        if abs(yes - eff_no) < ALGO_COINFLIP_EPS and lean:
            return {"choice": lean["direction"],
                    "reason": "Kalshi\u2019s odds are almost a coin flip (%d%% YES / %d%% NO) \u2014 "
                              "leaning on the live price position instead, currently %s."
                              % (_pct(yes), _pct(eff_no), lean["direction"].upper())}
        choice = "yes" if yes >= eff_no else "no"
        return {"choice": choice,
                "reason": "Kalshi\u2019s own market prices %s higher \u2014 %d%% YES / %d%% NO on real "
                          "order-book pricing." % (choice.upper(), _pct(yes), _pct(eff_no))}
    if lean:
        return {"choice": lean["direction"],
                "reason": "No live odds yet \u2014 going with the current price position, %s target."
                          % ("above" if lean["direction"] == "yes" else "below")}
    return None


# The History Call's static order-3 table -- measured once over 6,682 settled rounds
# (see the study framing in index.html; 105 pre-registered hypotheses, ZERO survived
# FDR correction). The module reports the lean and says when a coin flip is not ruled
# out, which it essentially always is. These numbers must match the page's HC_TABLE.
HC_TABLE = {
    "NNN": {"p": 0.5359, "n": 767, "lo": 0.5005, "hi": 0.5709},
    "NNY": {"p": 0.5069, "n": 870, "lo": 0.4737, "hi": 0.5400},
    "NYN": {"p": 0.5068, "n": 876, "lo": 0.4738, "hi": 0.5399},
    "NYY": {"p": 0.4731, "n": 835, "lo": 0.4394, "hi": 0.5070},
    "YNN": {"p": 0.5276, "n": 870, "lo": 0.4944, "hi": 0.5606},
    "YNY": {"p": 0.4685, "n": 841, "lo": 0.4350, "hi": 0.5023},
    "YYN": {"p": 0.4761, "n": 836, "lo": 0.4424, "hi": 0.5100},
    "YYY": {"p": 0.4962, "n": 784, "lo": 0.4613, "hi": 0.5311},
}


def compute_hist_call(prior_results):
    """prior_results: the last 3 SETTLED results before the current round, CHRONOLOGICAL
    (e.g. ['no','no','yes'] -> context NNY). Returns {'choice','reason'} or None."""
    if not prior_results or len(prior_results) < 3:
        return None
    ctx = "".join("Y" if r == "yes" else "N" for r in prior_results[-3:])
    row = HC_TABLE.get(ctx)
    if not row:
        return None
    yes = row["p"] >= 0.5
    pct = row["p"] if yes else 1.0 - row["p"]
    solid = row["lo"] > 0.5 or row["hi"] < 0.5  # same CI test the page uses
    choice = "yes" if yes else "no"
    reason = "After %s \u2014 history leans %s %.1f%% over %d past rounds (%s)." % (
        " ".join(ctx), choice.upper(), pct * 100, row["n"],
        "outside coin-flip range" if solid else "coin flip not ruled out")
    return {"choice": choice, "reason": reason}


# Derived records, cached briefly: /api/state is polled every 2s per client but records
# only actually change when a round settles, so a 5s TTL makes the GROUP BY free.
_records_cache = (0.0, None)


def get_records():
    global _records_cache
    now = time.time()
    if _records_cache[1] is not None and now < _records_cache[0]:
        return _records_cache[1]
    out = {src: {"wins": 0, "losses": 0, "scored": 0, "pct": None} for src in CALL_SOURCES}
    for r in db.calls_records():
        src = r["source"]
        if src not in out:
            continue
        wins, losses = int(r["wins"] or 0), int(r["losses"] or 0)
        scored = wins + losses
        out[src] = {"wins": wins, "losses": losses, "scored": scored,
                    "pct": round(100.0 * wins / scored, 1) if scored else None}
    cov_rows, cov_n = db.coverage_counts(COVERAGE_WINDOW)
    cov = {r["source"]: int(r["called"] or 0) for r in cov_rows}
    for src in out:
        out[src]["coverage"] = {"called": cov.get(src, 0), "window": cov_n}
    _records_cache = (now + 5.0, out)
    return out


def invalidate_records():
    global _records_cache
    _records_cache = (0.0, None)


def settle_pending_once(now):
    """At most ONE Kalshi call per cycle; settles every pending round it can match.
    No in-loop retries -- the 5s cadence IS the retry. Replaces the old blocking
    settle_round, and runs whether or not anyone is watching (the records and the
    History Call's context need results around the clock)."""
    pending = db.query("SELECT kalshi_ticker FROM rounds WHERE result IS NULL AND close_time <= ? "
                       "AND close_time > ?", (now, now - SETTLE_SCAN_WINDOW_S))
    if not pending:
        return
    try:
        data = kalshi_markets("settled", limit=25)  # 25 rounds is ~6h, matches the scan window
    except Exception as e:  # noqa
        print("[caller] settle scan failed: %s" % e, file=sys.stderr)
        return
    by_ticker = {m["ticker"]: m for m in data.get("markets") or [] if (m.get("result") or "")}
    for p in pending:
        m = by_ticker.get(p["kalshi_ticker"])
        if not m:
            continue
        try:
            db.upsert_round(to_round_row(m))
        except (KeyError, TypeError, ValueError) as e:  # noqa
            # One malformed market must never stall the caller: skip it, keep settling
            # the rest. (A comma-formatted expiration_value once did exactly this,
            # aborting every 5s tick and silently stopping all calls.)
            print("[caller] skip unsettleable %s: %s" % (p["kalshi_ticker"], e), file=sys.stderr)


def _live_lean(cur, now):
    """The current price position vs the strike, refetching if the poller is asleep.
    Shared by the near-lock ALGO call and the early ALGO call."""
    with STATE_LOCK:
        price, price_ts = STATE["live_price"], STATE["live_price_ts"]
    if price is None or now - price_ts > PRICE_STALE_S:
        # The price poller sleeps when the app is idle; the AI still needs a live read.
        try:
            price, source = fetch_cosmetic_price()
            with STATE_LOCK:
                STATE["live_price"], STATE["live_price_source"], STATE["live_price_ts"] = price, source, now
        except Exception:  # noqa
            pass  # stale or absent price -> lean may be None; the odds branch still works
    return compute_lean(price, cur["floor_strike"])


def make_auto_calls(cur, now):
    ticker = cur["kalshi_ticker"]
    lean = _live_lean(cur, now)
    algo = compute_algo_pick(cur, lean)
    if algo:
        db.insert_call_ignore(ticker, "algo", algo["choice"], algo["reason"], now)
    priors = db.query("SELECT result FROM rounds WHERE result IS NOT NULL AND close_time <= ? "
                      "ORDER BY close_time DESC LIMIT 3", (cur["open_time"],))
    hc = compute_hist_call([r["result"] for r in reversed(priors)])
    if hc:
        db.insert_call_ignore(ticker, "histcall", hc["choice"], hc["reason"], now)


def make_early_call(cur, now):
    """BTC-25: the same ALGO heuristic, run ~5 min before close, logged write-once as its
    OWN source so the proven near-lock 'algo' record is never touched. No backfill -- its
    input is the T-5 odds/price, which don't exist after the fact (an honest hole)."""
    lean = _live_lean(cur, now)
    algo = compute_algo_pick(cur, lean)
    if algo:
        db.insert_call_ignore(cur["kalshi_ticker"], "algoearly", algo["choice"],
                              "[Early call, ~5 min before close] " + algo["reason"], now)


def backfill_hist_calls():
    """BTC-17: a restart or Kalshi error inside the pre-lock window used to leave a
    permanent hole in the History Call record. The call is DETERMINISTIC -- a static
    table over the 3 settled priors -- so a missed round can be filled honestly at any
    time. Only rounds after the first-ever live histcall are eligible: the deep past
    stays unscored (the record means "calls made in the live era", not a simulation).
    ALGO holes stay holes on purpose -- its input is near-lock odds, which don't
    exist after the fact."""
    holes = db.query("""
        SELECT r.kalshi_ticker, r.open_time FROM rounds r
        WHERE r.result IS NOT NULL
          AND r.close_time > (SELECT MIN(r2.close_time) FROM calls c2
                              JOIN rounds r2 ON r2.kalshi_ticker = c2.kalshi_ticker
                              WHERE c2.source='histcall')
          AND NOT EXISTS (SELECT 1 FROM calls c WHERE c.kalshi_ticker = r.kalshi_ticker
                          AND c.source='histcall')
        ORDER BY r.close_time ASC LIMIT ?""", (HC_BACKFILL_BATCH,))
    filled = 0
    for h in holes:
        priors = db.query("SELECT result FROM rounds WHERE result IS NOT NULL AND close_time <= ? "
                          "ORDER BY close_time DESC LIMIT 3", (h["open_time"],))
        hc = compute_hist_call([r["result"] for r in reversed(priors)])
        if hc and db.insert_call_ignore(h["kalshi_ticker"], "histcall", hc["choice"],
                                        hc["reason"] + " (backfilled)", time.time()):
            filled += 1
    if filled:
        invalidate_records()
        print("[caller] backfilled %d missed History Call(s)" % filled, file=sys.stderr)
    return filled


def caller_tick():
    now = time.time()
    cur = current_round_row()
    if cur is None or cur["close_time"] <= now:
        # Idle freshness: round_engine only re-syncs every 12h when nobody is watching,
        # but the AI calls every round regardless -- so keep the round pointer alive
        # ourselves (~1-2 Kalshi calls per 15-min round when idle).
        refresh_open_round()
        cur = current_round_row()
    try:
        settle_pending_once(now)
    except Exception as e:  # noqa
        # Settlement is best-effort and must never skip the call windows below it.
        print("[caller] settle failed: %s" % e, file=sys.stderr)
    if not cur or cur["close_time"] <= now:
        return
    # BTC-25: the early ALGO call, at close_time - ALGO_EARLY_OFFSET_S (T-5:00), inside a
    # bounded window so "early" always means ~5 min out. Separate source, write-once.
    early_start = cur["close_time"] - ALGO_EARLY_OFFSET_S
    if early_start <= now < early_start + ALGO_EARLY_WINDOW_S:
        if "algoearly" not in db.calls_for_round(cur["kalshi_ticker"]):
            if not is_active():
                refresh_open_round()  # snapshot ~T-5 odds; row is otherwise ~round-open stale
                cur = current_round_row() or cur
            make_early_call(cur, now)
    if cur["lock_ts"] - CALL_WINDOW_S <= now < cur["lock_ts"]:
        existing = db.calls_for_round(cur["kalshi_ticker"])
        if "algo" in existing and "histcall" in existing:
            return  # already fired for this round
        if not is_active():
            # When active, round_engine refreshed the odds within the last 10s; when
            # idle the row is ~13 minutes old, so snapshot near-lock odds once.
            refresh_open_round()
            cur = current_round_row() or cur  # refresh failure -> use round-open odds
        make_auto_calls(cur, now)


def caller_loop():
    # The third daemon thread (v4.15.0): the AI and the History Call make their calls
    # every round, 24/7, and settlement lives here now -- single owner, never blocks.
    while STATE["catching_up"]:
        time.sleep(1)
    last_hc_sweep = 0.0
    while True:
        try:
            caller_tick()
            if time.time() - last_hc_sweep >= HC_BACKFILL_EVERY_S:
                last_hc_sweep = time.time()
                backfill_hist_calls()
        except Exception as e:  # noqa
            print("[caller] %s" % e, file=sys.stderr)
        time.sleep(CALLER_CHECK_S)


BUCKET_SIZES = {"round": 900, "hour": 3600, "4h": 4 * 3600, "day": 86400, "week": 7 * 86400}


def build_series(rows, size):
    """Bucket settled rounds for the board. Long windows (68d = ~6.4k rounds) are charted
    from these buckets instead of raw rows, so a panel never ships the whole table."""
    buckets = []
    cur = None
    for r in rows:
        sv, fs = r["settlement_value"], r["floor_strike"]
        d = (sv - fs) if (sv is not None and fs is not None) else None
        b0 = int(r["close_time"] // size) * size
        if cur is None or cur["ts"] != b0:
            cur = {"ts": b0, "n": 0, "yes": 0, "no": 0, "o": None, "h": None,
                   "l": None, "c": None, "sum_d": 0.0, "sum_abs": 0.0, "max_abs": 0.0, "nd": 0}
            buckets.append(cur)
        cur["n"] += 1
        if r["result"] == "yes":
            cur["yes"] += 1
        elif r["result"] == "no":
            cur["no"] += 1
        if sv is not None:
            if cur["o"] is None:
                cur["o"] = cur["h"] = cur["l"] = sv
            cur["h"] = max(cur["h"], sv)
            cur["l"] = min(cur["l"], sv)
            cur["c"] = sv
        if d is not None:
            cur["nd"] += 1
            cur["sum_d"] += d
            cur["sum_abs"] += abs(d)
            cur["max_abs"] = max(cur["max_abs"], abs(d))
    out = []
    for b in buckets:
        nd = b["nd"]
        out.append({
            "ts": b["ts"], "n": b["n"], "yes": b["yes"], "no": b["no"],
            "yes_rate": round(100.0 * b["yes"] / b["n"], 2) if b["n"] else None,
            "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
            "avg_delta": round(b["sum_d"] / nd, 2) if nd else None,
            "volatility": round(b["sum_abs"] / nd, 2) if nd else None,
            "max_abs_delta": round(b["max_abs"], 2) if nd else None,
        })
    return out


def build_summary(rows):
    n = len(rows)
    yes = sum(1 for r in rows if r["result"] == "yes")
    deltas = [r["settlement_value"] - r["floor_strike"] for r in rows
              if r["settlement_value"] is not None and r["floor_strike"] is not None]
    by_hour = [{"hour": h, "n": 0, "yes": 0} for h in range(24)]
    by_dow = [{"dow": d, "n": 0, "yes": 0} for d in range(7)]
    for r in rows:
        t = datetime.fromtimestamp(r["close_time"], tz=ZoneInfo("America/New_York"))
        for slot in (by_hour[t.hour], by_dow[t.weekday()]):
            slot["n"] += 1
            if r["result"] == "yes":
                slot["yes"] += 1
    for slot in by_hour + by_dow:
        slot["yes_rate"] = round(100.0 * slot["yes"] / slot["n"], 2) if slot["n"] else None
    s = {
        "rounds": n, "yes": yes, "no": n - yes,
        "yes_rate": round(100.0 * yes / n, 2) if n else None,
        "first_ts": rows[0]["close_time"] if n else None,
        "last_ts": rows[-1]["close_time"] if n else None,
        "span_days": round((rows[-1]["close_time"] - rows[0]["close_time"]) / 86400.0, 2) if n > 1 else 0,
        "volatility": round(sum(abs(d) for d in deltas) / len(deltas), 2) if deltas else None,
        "max_abs_delta": round(max(abs(d) for d in deltas), 2) if deltas else None,
        "last_delta": round(deltas[-1], 2) if deltas else None,
        "by_hour": by_hour, "by_dow": by_dow,
    }
    s.update(compute_road_stats(rows))
    return s


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

    def _redirect(self, location):
        self._send(302, b"", "text/plain; charset=utf-8", {"Location": location})

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
            # Two views: Classic above (fixed on purpose) and the Studio below
            # (movable modules, wearing any skin). The skins are no longer their
            # own pages, so their old URLs land on the Studio already set to that
            # skin. /fluid is gone outright and just opens the Studio.
            if path in ("/fluid", "/fluid.html"):
                return self._redirect("/studio")
            _skin = SKIN_ROUTES.get(path)
            if _skin:
                return self._redirect("/studio?skin=" + _skin)
            if path in ("/studio", "/studio.html"):
                return self._serve_page("studio.html")
            if path.startswith("/fonts/"):
                return self._serve_font(path[len("/fonts/"):])
            if path == "/health":
                return self._send(200, json.dumps({"ok": True, "version": VERSION, "catching_up": STATE["catching_up"]}).encode())
            if path == "/api/state":
                return self._api_state()
            if path == "/api/history":
                return self._api_history(urllib.parse.parse_qs(parsed.query))
            if path == "/api/series":
                return self._api_series(urllib.parse.parse_qs(parsed.query))
            if path == "/api/ticks":
                return self._api_ticks(urllib.parse.parse_qs(parsed.query))
            if path == "/api/layouts":
                return self._send(200, self._layouts_body())
            if path == "/api/calls":
                # Deliberately no touch_client(): watching the records must not flip
                # the app "active" (that would defeat the idle economy).
                return self._send(200, self._calls_body())
            if path == "/api/board":
                return self._send(200, self._kv_body("board"))
            if path == "/api/prefs":
                return self._send(200, json.dumps({
                    "classic_modules": self._kv_obj("classic_modules"),
                    "algo_modules": self._kv_obj("algo_modules")}).encode())
            self._send(404, b'{"error":"not found"}')
        except Exception as e:  # noqa
            print("[http] GET %s failed: %s" % (self.path, e), file=sys.stderr)
            try:
                self._send(500, json.dumps({"error": "internal error"}).encode())
            except Exception:  # noqa
                pass

    LAYOUT_SLOTS = 5
    LAYOUT_MAX_BYTES = 200_000

    def _layouts_body(self):
        slots = []
        for r in db.list_layouts():
            try:
                payload = json.loads(r["payload"])
            except ValueError:
                payload = None
            slots.append({"slot": r["slot"], "name": r["name"], "saved_at": r["saved_at"],
                          "payload": payload})
        return json.dumps({"slots": slots, "max": self.LAYOUT_SLOTS}).encode()

    def _kv_obj(self, key):
        row = db.kv_get(key)
        if not row:
            return None
        try:
            return {"payload": json.loads(row["payload"]), "saved_at": row["saved_at"]}
        except ValueError:
            return None

    def _kv_body(self, key):
        obj = self._kv_obj(key)
        if not obj:
            return json.dumps({"payload": None, "saved_at": None}).encode()
        return json.dumps(obj).encode()

    def _calls_body(self, extra=None):
        with STATE_LOCK:
            ticker = STATE["current_ticker"]
        recent = []
        for r in db.recent_scored_calls(50):
            recent.append({"ticker": r["kalshi_ticker"], "source": r["source"], "choice": r["choice"],
                           "reason": r["reason"], "ts": r["ts"], "result": r["result"],
                           "win": r["choice"] == r["result"], "close_time": r["close_time"]})
        body = {"records": get_records(),
                "current": dict(db.calls_for_round(ticker), ticker=ticker),
                "recent": recent}
        if extra:
            body.update(extra)
        return json.dumps(body).encode()

    def _read_json_body(self, cap):
        """Shared POST body reader. Returns (dict, None) or (None, error-response-sent)."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > cap:
            self._send(413, b'{"error":"body too large"}')
            return None, True
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            self._send(400, b'{"error":"body must be JSON"}')
            return None, True
        if not isinstance(body, dict):
            self._send(400, b'{"error":"body must be a JSON object"}')
            return None, True
        return body, None

    def do_POST(self):
        # The write endpoints. No auth by design: this is a single-owner LAN app, and
        # the DB lock serialises concurrent writers.
        try:
            path = urllib.parse.urlparse(self.path).path
            routes = {"/api/layouts": (self._post_layouts, self.LAYOUT_MAX_BYTES + 50_000),
                      "/api/picks": (self._post_picks, PICKS_MAX_BYTES),
                      "/api/board": (self._post_board, KV_MAX_BYTES + 50_000),
                      "/api/prefs": (self._post_prefs, KV_MAX_BYTES + 50_000),
                      "/api/calls/import": (self._post_import, IMPORT_MAX_BYTES),
                      "/api/calls/reset": (self._post_calls_reset, PICKS_MAX_BYTES),
                      "/api/calls/edit": (self._post_calls_edit, PICKS_MAX_BYTES)}
            route = routes.get(path)
            if not route:
                return self._send(404, b'{"error":"not found"}')
            handler, cap = route
            body, err = self._read_json_body(cap)
            if err:
                return
            return handler(body)
        except Exception as e:  # noqa
            print("[http] POST %s failed: %s" % (self.path, e), file=sys.stderr)
            try:
                self._send(500, json.dumps({"error": "internal error"}).encode())
            except Exception:
                pass

    def _post_layouts(self, body):
        slot = body.get("slot")
        if not isinstance(slot, int) or isinstance(slot, bool) or not (1 <= slot <= self.LAYOUT_SLOTS):
            return self._send(400, b'{"error":"slot must be 1-%d"}' % self.LAYOUT_SLOTS)
        if body.get("delete"):
            db.delete_layout(slot)
        else:
            name = (str(body.get("name") or "").strip() or "Slot %d" % slot)[:60]
            payload = body.get("payload")
            if not isinstance(payload, dict):
                return self._send(400, b'{"error":"payload must be a JSON object"}')
            raw = json.dumps(payload, separators=(",", ":"))
            if len(raw) > self.LAYOUT_MAX_BYTES:
                return self._send(413, b'{"error":"payload too large"}')
            db.upsert_layout(slot, name, raw)
        return self._send(200, self._layouts_body())

    def _post_picks(self, body):
        touch_client()  # a pick is a real visit
        choice = body.get("choice")
        ticker = body.get("ticker")
        if choice not in ("yes", "no") or not isinstance(choice, str):
            return self._send(400, b'{"error":"choice must be yes or no"}')
        if not isinstance(ticker, str) or not ticker:
            return self._send(400, b'{"error":"ticker required"}')
        cur = current_round_row()
        if not cur:
            return self._send(409, b'{"error":"no current round"}')
        if ticker != cur["kalshi_ticker"]:
            return self._send(409, b'{"error":"round is not current"}')
        if time.time() >= cur["lock_ts"]:
            return self._send(409, b'{"error":"locked"}')
        db.upsert_call(ticker, "you", choice, None, time.time())
        return self._send(200, self._calls_body())

    def _post_calls_reset(self, body):
        # BTC-16: wipe the owner's record back to 0-0. Only 'you' -- the ALGO and the
        # History Call records are the app's own history and are never resettable.
        # The kv reset-epoch stamp is what keeps a stale browser's one-time migration
        # import from quietly re-populating the record afterwards (see _post_import).
        touch_client()
        if body.get("source", "you") != "you":
            return self._send(400, b'{"error":"only the you record can be reset"}')
        deleted = db.delete_calls("you")
        db.kv_set("you_reset_ts", json.dumps({"ts": time.time()}))
        invalidate_records()
        return self._send(200, self._calls_body({"reset": True, "deleted": deleted}))

    def _reset_epoch(self):
        row = db.kv_get("you_reset_ts")
        if not row:
            return 0.0
        try:
            return float(json.loads(row["payload"]).get("ts") or 0.0)
        except (ValueError, TypeError):
            return 0.0

    def _post_calls_edit(self, body):
        # BTC-22: the owner can change (or clear) their OWN call on any known round,
        # locked or settled -- they sometimes sell the position early, and the final
        # result then misrepresents the call they actually traded on. Explicit,
        # per-round, 'you' only; the auto-callers stay write-once.
        touch_client()
        ticker = body.get("ticker")
        choice = body.get("choice")
        if not isinstance(ticker, str) or not ticker:
            return self._send(400, b'{"error":"ticker required"}')
        if choice not in ("yes", "no", None):
            return self._send(400, b'{"error":"choice must be yes, no or null"}')
        known = db.query_one("SELECT 1 AS x FROM rounds WHERE kalshi_ticker=?", (ticker,))
        if not known:
            return self._send(404, b'{"error":"unknown round"}')
        if choice is None:
            db.delete_call(ticker, "you")
        else:
            db.upsert_call(ticker, "you", choice, "edited after close", time.time())
        invalidate_records()
        return self._send(200, self._calls_body({"edited": ticker}))

    def _post_board(self, body):
        payload = body.get("payload")
        if not isinstance(payload, dict):
            return self._send(400, b'{"error":"payload must be a JSON object"}')
        raw = json.dumps(payload, separators=(",", ":"))
        if len(raw) > KV_MAX_BYTES:
            return self._send(413, b'{"error":"payload too large"}')
        saved_at = db.kv_set("board", raw)
        return self._send(200, json.dumps({"saved_at": saved_at}).encode())

    def _post_prefs(self, body):
        key = body.get("key")
        if key not in KV_KEYS or key == "board":
            return self._send(400, b'{"error":"unknown key"}')
        payload = body.get("payload")
        if not isinstance(payload, dict):
            return self._send(400, b'{"error":"payload must be a JSON object"}')
        raw = json.dumps(payload, separators=(",", ":"))
        if len(raw) > KV_MAX_BYTES:
            return self._send(413, b'{"error":"payload too large"}')
        saved_at = db.kv_set(key, raw)
        return self._send(200, json.dumps({"saved_at": saved_at}).encode())

    def _post_import(self, body):
        # One-time migration of browser-local records. Only rounds we actually hold, and
        # never overwriting an existing call ('you' imports too: history is history).
        imported = {"you": 0, "algo": 0}
        skipped = 0
        reset_epoch = self._reset_epoch()  # BTC-16: rounds from before a reset stay reset
        for source in ("you", "algo"):
            entries = body.get(source)
            if entries is None:
                continue
            if not isinstance(entries, dict):
                return self._send(400, b'{"error":"you/algo must be objects"}')
            if len(entries) > IMPORT_MAX_ENTRIES:
                return self._send(413, b'{"error":"too many entries"}')
            for ticker, e in entries.items():
                if not isinstance(ticker, str) or len(ticker) > 80 or not isinstance(e, dict):
                    skipped += 1
                    continue
                choice = e.get("choice")
                if choice not in ("yes", "no"):
                    skipped += 1
                    continue
                ts = e.get("ts")
                ts = (ts / 1000.0) if isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts > 1e12 else \
                     (float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) else time.time())
                reason = e.get("reason")
                reason = reason[:500] if isinstance(reason, str) else None
                known = db.query_one("SELECT close_time FROM rounds WHERE kalshi_ticker=?", (ticker,))
                if not known:
                    skipped += 1
                    continue
                if source == "you" and known["close_time"] <= reset_epoch:
                    # A browser that hasn't visited since before a reset would otherwise
                    # re-import the record the owner deliberately wiped.
                    skipped += 1
                    continue
                if db.insert_call_ignore(ticker, source, choice, reason, ts):
                    imported[source] += 1
                else:
                    skipped += 1  # already on the server; write-once stands
        invalidate_records()  # imports can change history; recompute promptly
        return self._send(200, self._calls_body({"imported": imported, "skipped": skipped}))

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
        board_row = db.kv_get("board")
        with STATE_LOCK:
            live_price = STATE["live_price"]
            live_price_source = STATE["live_price_source"]
            live_price_ts = STATE["live_price_ts"]
            ticks = STATE["recent_ticks"][-120:]
        payload = {"now": time.time(), "version": VERSION, "catching_up": STATE["catching_up"], "current_round": None,
                   "last_settled": None, "live_price": live_price,
                   "live_price_source": live_price_source,
                   # BTC-18: when the price was actually FETCHED, so the pages can show
                   # true price age instead of "when did I last poll".
                   "live_price_ts": live_price_ts, "lean": None,
                   "ticks": ticks,
                   "records": get_records(),
                   "calls": db.calls_for_round(cur["kalshi_ticker"] if cur else None),
                   "board_saved_at": board_row["saved_at"] if board_row else None}
        if cur:
            payload["current_round"] = {
                "ticker": cur["kalshi_ticker"], "floor_strike": cur["floor_strike"],
                "open_time": cur["open_time"], "close_time": cur["close_time"], "lock_ts": cur["lock_ts"],
                "locked": time.time() >= cur["lock_ts"],
                "kalshi_yes_price": cur["kalshi_yes_price"], "kalshi_no_price": cur["kalshi_no_price"],
                "robinhood_url": robinhood_url(cur["floor_strike"], cur["open_time"]),
            }
            payload["lean"] = compute_lean(live_price, cur["floor_strike"])
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
        limit = int(float((qs.get("limit") or ["0"])[0]))
        if limit > 0:
            # Newest N, then flipped back to ascending -- a 68-day window is ~6.4k rounds and
            # the bead/table panels only ever render the tail of it.
            rows = db.query("""SELECT kalshi_ticker, close_time, floor_strike, settlement_value, result
                                FROM rounds WHERE result IS NOT NULL AND close_time >= ?
                                ORDER BY close_time DESC LIMIT ?""", (cutoff, limit))
            rows.reverse()
        else:
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
        call_map = {}
        for c in db.query("""SELECT c.kalshi_ticker, c.source, c.choice
                              FROM calls c JOIN rounds r ON r.kalshi_ticker = c.kalshi_ticker
                              WHERE r.close_time >= ?""", (cutoff,)):
            call_map.setdefault(c["kalshi_ticker"], {})[c["source"]] = c["choice"]
        for r in rows:
            r["delta"] = round(r["settlement_value"] - r["floor_strike"], 2) if r["settlement_value"] is not None else None
            r["calls"] = call_map.get(r["kalshi_ticker"], {})
        tallies = {"yes": sum(1 for r in rows if r["result"] == "yes"),
                   "no": sum(1 for r in rows if r["result"] == "no")}
        tallies.update(compute_road_stats(rows))
        self._send(200, json.dumps({"rounds": rows, "tallies": tallies}).encode())

    def _api_series(self, qs):
        touch_client()
        days = float((qs.get("days") or ["0"])[0])  # 0 = every round we hold
        bucket = (qs.get("bucket") or ["day"])[0]
        size = BUCKET_SIZES.get(bucket, 86400)
        sql = ("SELECT close_time, floor_strike, settlement_value, result FROM rounds "
               "WHERE result IS NOT NULL")
        params = ()
        if days > 0:
            sql += " AND close_time >= ?"
            params = (time.time() - days * 86400,)
        rows = db.query(sql + " ORDER BY close_time ASC", params)
        self._send(200, json.dumps({"bucket": bucket, "bucket_size": size,
                                    "buckets": build_series(rows, size),
                                    "summary": build_summary(rows)}).encode())

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
    threading.Thread(target=price_stream, daemon=True).start()
    threading.Thread(target=caller_loop, daemon=True).start()
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
