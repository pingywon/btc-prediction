# Pages

Single-page app. One page, no imports to trace — everything (HTML, `<style>`, `<script>`) lives in one file.

## / (the only page)
Entry: `index.html` (400 lines, self-contained — no separate component files, no build step, no bundler)
Dependencies: none (no imports, no external CSS/JS, no CDN assets — the entire page is this one file)

Renders live data via two polled JSON endpoints (`/api/state` every 3s, `/api/history?hours=N` on load + when a round settles) served by `app.py` (see `routes.md`). All rendering is done with plain `document.getElementById` DOM manipulation in an IIFE — no virtual DOM, no templating library.
