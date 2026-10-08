#!/usr/bin/env python3
"""Build index.html from src/index.src.html.

The version in the footer comes from the VERSION file and every number on the
page from tools/data.json, so the page cannot drift from either.
"""
import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
version = (ROOT / "VERSION").read_text().strip()
d = json.loads((ROOT / "tools" / "data.json").read_text())
page = (ROOT / "src" / "index.src.html").read_text(encoding="utf-8")


def n(x):
    return f"{x:,}"


def pos(pct):
    """Place a percentage on the 50-100 axis."""
    return f"{max(0.0, min(100.0, (pct - 50) * 2)):.2f}"


def dumbbell():
    rows = []
    for a in d["algo"]:
        lo, hi = sorted((a["price_pct"], a["pct"]))
        label = html.escape(a["label"], quote=True)
        rows.append(
            f'<div class="db-row" tabindex="0" data-label="{label}" data-won="{a["pct"]}" data-price="{a["price_pct"]}" '
            f'data-wins="{n(a["wins"])}" data-scored="{n(a["scored"])}">'
            f'<span class="lab">{html.escape(a["label"].replace("ALGO, ", "").capitalize())}</span>'
            f'<div class="track"><span class="link" style="left:{pos(lo)}%;width:{float(pos(hi)) - float(pos(lo)):.2f}%"></span>'
            f'<span class="ring" style="left:{pos(a["price_pct"])}%"></span><span class="dot" style="left:{pos(a["pct"])}%"></span></div>'
            f'<span class="n">{a["price_pct"]}%</span><span class="n won">{a["pct"]}%</span></div>')
    return "\n      ".join(rows)


def bands_table():
    rows = "".join(
        f'<tr><td>{b["lo"]} to {b["hi"]}%</td><td class="num">{n(b["n"])}</td>'
        f'<td class="num">{b["price_pct"]}%</td><td class="num">{b["win_pct"]}%</td></tr>'
        for b in d["bands"])
    return ('<table><thead><tr><th>Market price</th><th class="num">Calls</th><th class="num">Average price</th>'
            f'<th class="num">Won</th></tr></thead><tbody>{rows}</tbody></table>')


# The copy makes claims; refuse to build if the numbers stop backing them.
assert d["yes"] + d["no"] == d["rounds"]
assert all(abs(x - 50) < 2 for x in (d["yes_pct"], d["flip_pct"], d["histcall"]["pct"])), "a headline number left the coin-flip range"
assert all(abs(a["pct"] - a["price_pct"]) < 3 for a in d["algo"]), "ALGO win rate moved away from the market price"
assert all(a["priced"] == a["scored"] for a in d["algo"]), "some ALGO calls carry no market price"
streak3 = next(s for s in d["streaks"] if s["k"] == 3)
final = d["algo"][-1]

tokens = {
    "VERSION": version,
    "APP_VERSION": d["app_version"],
    "AS_OF": d["as_of"],
    "FIRST_ROUND": d["first_round"],
    "ROUNDS": n(d["rounds"]),
    "DAYS": str(d["days"]),
    "YES": n(d["yes"]),
    "YES_PCT": f'{d["yes_pct"]:.1f}',
    "FLIPS": n(d["flips"]),
    "PAIRS": n(d["pairs"]),
    "FLIP_PCT": f'{d["flip_pct"]:.1f}',
    "HIST_WINS": n(d["histcall"]["wins"]),
    "HIST_SCORED": n(d["histcall"]["scored"]),
    "HIST_PCT": f'{d["histcall"]["pct"]:.1f}',
    "STREAK3_PCT": f'{streak3["pct"]:.1f}',
    "FINAL_PCT": str(round(final["pct"])),
    "FINAL_PRICE": str(round(final["price_pct"])),
    "ALGO_CALLS": n(sum(a["scored"] for a in d["algo"])),
    "CALLS_SINCE": d["calls_since"],
    "CALLS_TOTAL": n(d["calls_total"]),
    "DUMBBELL": dumbbell(),
    "BANDS_TABLE": bands_table(),
}
for k, v in tokens.items():
    page = page.replace("{{" + k + "}}", v)

left = re.findall(r"\{\{[A-Z0-9_]+\}\}", page)
if left:
    sys.exit(f"unfilled tokens: {sorted(set(left))}")

missing = [m for m in re.findall(r'(?:href|src)="(img/[^"#]+)"', page) if not (ROOT / m).exists()]
if missing:
    sys.exit(f"missing files: {sorted(set(missing))}")

(ROOT / "index.html").write_text(page, encoding="utf-8")
print(f"built index.html  page v{version}  app v{d['app_version']}  {len(page) // 1024} KB")
