# Bundled fonts

Three variable web fonts, self-hosted so the app has **no external requests at runtime** — the
house rule for every page here is zero CDN, and both of the v3 skins are typography-led (they need
a real weight 200, which no system font stack provides).

Each file is the latin-subset variable build, one file covering the full weight axis:

| File | Family | Axis | Licence |
|---|---|---|---|
| `inter.woff2` | Inter | `wght` 100–900 | SIL Open Font License 1.1 |
| `manrope.woff2` | Manrope | `wght` 200–800 | SIL Open Font License 1.1 |
| `jetbrains-mono.woff2` | JetBrains Mono | `wght` 100–800 | SIL Open Font License 1.1 |

All three are licensed under the **SIL Open Font License, Version 1.1**, which permits bundling and
redistribution with software provided the fonts are not sold on their own and the licence travels
with them. Full text: <https://openfontlicense.org/>

Upstream: the `@fontsource-variable/*` packages, which repackage the upstream Google Fonts /
JetBrains releases as subsetted variable woff2.

- Inter — Rasmus Andersson, <https://github.com/rsms/inter>
- Manrope — Mikhail Sharanda, <https://github.com/sharanda/manrope>
- JetBrains Mono — JetBrains, <https://github.com/JetBrains/JetBrainsMono>

Served by `app.py` at `/fonts/<name>.woff2` and referenced from each page's `@font-face` block.
