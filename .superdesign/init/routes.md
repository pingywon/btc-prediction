# Routes

No router, no framework. Pure stdlib Python `http.server` backend (`app.py`), one HTML route.

| Path | Handler | Renders |
|---|---|---|
| `GET /` or `GET /index.html` | `Handler._serve_page()` in `app.py` | Serves `index.html` verbatim (read fresh from disk on every request, no caching, no templating — the entire UI is one static file whose JS then polls JSON APIs) |
| `GET /health` | `Handler.do_GET` | `{"ok": true, "catching_up": bool}` |
| `GET /api/state` | `Handler._api_state()` | Current-round + live-price JSON, polled every 3s by the page |
| `GET /api/history?hours=N` | `Handler._api_history()` | Settled rounds + stats JSON for the Big Road, `N` defaults to 24 |

There is exactly one user-facing page: the root `/`. Everything else is a JSON API the page's own JS consumes.
