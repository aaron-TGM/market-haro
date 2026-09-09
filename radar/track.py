"""The track record: a public page that says how the screen has done.

WHY IT IS PUBLIC

A subscriber paying for a ranking deserves to see the ranking scored, and a
prospect deciding whether to pay deserves the same page before they do. So
this is the one page published without a paywall. It is built from two
things the pipeline already keeps and nobody edits by hand:

  data/rankings/YYYY-MM-DD.json    every issue's ranking, as published
  data/validation_history.json     the monthly walk-forward validation

For every past issue it measures what the top 20 did next against what the
whole candidate pool did next -- median change at +30, +60 and +90 days,
from the stored price series -- and it shows the to-date figure for issues
whose windows have not closed yet, marked as partial. The edge the product
claims is the spread between those two columns, not the top-20 number on
its own: in a rising market everything is up, and in a falling one the
question is only whether the top 20 fell less.

Nothing is dropped. An issue whose top 20 underperformed the pool stays on
the page with its numbers in red.
"""

from __future__ import annotations

import json
from datetime import date as _date
from datetime import timedelta
from pathlib import Path
from statistics import median
from typing import Any, Sequence

from .dashboard import _esc
from .playbook import _price_at

TOP = 20
HORIZONS = (30, 60, 90)


def _changes(keys: Sequence[tuple[str, str]], series: dict, start: str, end: str) -> list[float]:
    ch = []
    for k in keys:
        p0 = _price_at(series.get(k, []), start)
        p1 = _price_at(series.get(k, []), end, before=False)
        if p0 and p1:
            ch.append((p1 / p0 - 1) * 100)
    return ch


def _median_change(keys: Sequence[tuple[str, str]], series: dict, start: str, end: str) -> tuple[float | None, int]:
    ch = _changes(keys, series, start, end)
    return (round(median(ch), 1) if len(ch) >= 5 else None), len(ch)


def issues(rankings_dir: Path, series: dict, as_of: str) -> list[dict[str, Any]]:
    out = []
    today = _date.fromisoformat(as_of)
    for path in sorted(rankings_dir.glob("*.json")):
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        d = snap.get("obs_date") or path.stem
        rows = [r for r in snap.get("rows") or [] if not r.get("disqualified") and r.get("rank")]
        if not rows or d >= as_of:
            continue
        key = lambda r: (str(r["card_id"]), r.get("printing") or "Normal")  # noqa: E731
        top = [key(r) for r in rows if r["rank"] <= TOP]
        pool = [key(r) for r in rows]
        rec: dict[str, Any] = {"date": d, "top_n": len(top), "pool_n": len(pool), "windows": {}}
        start = _date.fromisoformat(d)
        for h in HORIZONS:
            end = start + timedelta(days=h)
            if end <= today:
                t, tn = _median_change(top, series, d, end.isoformat())
                p, pn = _median_change(pool, series, d, end.isoformat())
                rec["windows"][h] = {"top": t, "top_n": tn, "pool": p, "pool_n": pn,
                                     "spread": round(t - p, 1) if t is not None and p is not None else None}
                if h == 30:
                    # Every top-20 call resolved on its own: the number a reader
                    # can hold the product to, one row per call, never edited.
                    rec["calls_30"] = [round(c, 1) for c in _changes(top, series, d, end.isoformat())]
        elapsed = (today - start).days
        t, tn = _median_change(top, series, d, as_of)
        p, pn = _median_change(pool, series, d, as_of)
        rec["to_date"] = {"days": elapsed, "top": t, "top_n": tn, "pool": p, "pool_n": pn,
                          "spread": round(t - p, 1) if t is not None and p is not None else None}
        out.append(rec)
    return out


def summary(recs: Sequence[dict]) -> dict[str, Any]:
    """Across closed +30 windows: how often the top 20 beat the pool, and by how much --
    per issue, and per call (each top-20 pick resolved against its own pool's median)."""
    spreads = [r["windows"][30]["spread"] for r in recs if 30 in r["windows"] and r["windows"][30]["spread"] is not None]
    calls, beat, up = 0, 0, 0
    all_calls: list[float] = []
    for r in recs:
        w = r["windows"].get(30) or {}
        pool = w.get("pool")
        for c in r.get("calls_30") or []:
            calls += 1
            up += c > 0
            beat += pool is not None and c > pool
            all_calls.append(c)
    out: dict[str, Any] = {"closed_30": len(spreads), "calls_30": calls}
    if spreads:
        out.update({"beat": sum(1 for s in spreads if s > 0), "median_spread": round(median(spreads), 1)})
    if calls:
        out.update({"calls_beat_pct": round(100 * beat / calls), "calls_up_pct": round(100 * up / calls),
                    "calls_median": round(median(all_calls), 1)})
    return out


def headline(sm: dict) -> str:
    """One plain sentence for the top of the page and the sales copy. Empty until a window closes."""
    if not sm.get("calls_30"):
        return ""
    return (f"Of {sm['calls_30']} top-20 calls resolved at 30 days, {sm['calls_beat_pct']}% beat their pool "
            f"and {sm['calls_up_pct']}% were up; the median call moved {sm['calls_median']:+.1f}%"
            + (f" against a median spread of {sm['median_spread']:+.1f}% over the pool." if sm.get("closed_30") else "."))


# ---------------------------------------------------------------- the page
CSS = """
*{box-sizing:border-box}
body{margin:0;background:#07090c;color:#f2ead8;font:14px/1.6 "JetBrains Mono",ui-monospace,Menlo,monospace}
.wrap{max-width:960px;margin:0 auto;padding:28px 20px 60px}
.brand{font-size:10.5px;letter-spacing:.2em;text-transform:uppercase;color:#e0a030}
h1{margin:4px 0 6px;font-size:24px;letter-spacing:.12em;text-transform:uppercase;color:#e0a030}
h2{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#e0a030;margin:30px 0 10px}
p{margin:0 0 12px} .muted{color:#9a917f} .up{color:#5fd08a} .down{color:#e0554a}
.big{font-size:30px;font-weight:700;line-height:1.1}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:14px 0}
.tile{background:#0d1117;border:1px solid #2a2418;border-radius:2px;padding:12px 14px}
.tile .l{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#9a917f}
table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0 4px}
th{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#9a917f;text-align:left;padding:6px;border-bottom:1px solid #2a2418;font-weight:400}
th.grp{text-align:center;color:#e0a030;border-bottom:0;padding-bottom:0}
td{padding:7px 6px;border-bottom:1px dotted #2a2418;vertical-align:top}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
td .n{display:block;font-size:9.5px;color:#9a917f;font-weight:400}
.tablewrap{overflow-x:auto}
ul{padding-left:18px} li{margin:4px 0}
.cta{display:inline-block;margin-top:10px;background:#e0a030;color:#07090c;padding:9px 14px;text-decoration:none;font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:11px;border-radius:2px}
footer{margin-top:36px;padding-top:14px;border-top:1px solid #2a2418;color:#9a917f;font-size:11px}
"""


def _cell(v, n=None) -> str:
    if v is None:
        return '<td class="num muted">—</td>'
    cls = "up" if v > 0 else "down" if v < 0 else ""
    nn = f'<span class="n">n={n}</span>' if n is not None else ""
    return f'<td class="num {cls}">{v:+.1f}%{nn}</td>'


def render(recs: Sequence[dict], validations: Sequence[dict], *, as_of: str, brand: str = "Market Haro",
           report_url: str = "") -> str:
    sm = summary(recs)
    rows = []
    for r in reversed(list(recs)):
        cells = ""
        for h in HORIZONS:
            w = r["windows"].get(h)
            if w:
                cells += _cell(w["top"], w["top_n"]) + _cell(w["pool"], w["pool_n"]) + _cell(w["spread"])
            else:
                cells += '<td class="num muted">—</td>' * 3
        td = r["to_date"]
        cells += (_cell(td["top"], td["top_n"]) + _cell(td["pool"], td["pool_n"]) + _cell(td["spread"])
                  + f'<td class="num muted">{td["days"]}d</td>')
        rows.append(f'<tr><td><b>{_esc(r["date"])}</b><span class="n">top {r["top_n"]} of {r["pool_n"]}</span></td>{cells}</tr>')

    vrows = []
    for v in validations:
        tq, al = v.get("top_quintile") or {}, v.get("all_eligible") or {}
        rho = (v.get("score_vs_forward") or {}).get("spearman")
        rho_cell = f'<td class="num">{rho:+.2f}</td>' if rho is not None else '<td class="num muted">—</td>'
        vrows.append(
            f'<tr><td><b>{_esc(v.get("ran_at"))}</b><span class="n">{v.get("horizon_days")}-day horizon · n={v.get("eligible")}</span></td>'
            f'{rho_cell}{_cell(tq.get("median_pct"))}{_cell(al.get("median_pct"))}'
            f'<td>{_esc(v.get("verdict") or "")}</td></tr>')

    ix = ""

    hl = headline(sm)
    head = ""
    if sm.get("calls_30"):
        head += (f'<div class="tile"><div class="l">Calls resolved at +30 days</div><div class="big">{sm["calls_30"]}</div>'
                 f'<div class="muted">{sm["calls_beat_pct"]}% beat their pool · {sm["calls_up_pct"]}% up · median {sm["calls_median"]:+.1f}%</div></div>')
    head += (f'<div class="tile"><div class="l">Issues scored at +30 days</div><div class="big">{sm["closed_30"]}</div>'
            f'<div class="muted">{"top 20 beat the pool in " + str(sm["beat"]) + " of them" if sm["closed_30"] else "first window closes soon"}</div></div>')
    if sm["closed_30"]:
        head += (f'<div class="tile"><div class="l">Median spread, +30d</div><div class="big {"up" if sm["median_spread"] > 0 else "down"}">{sm["median_spread"]:+.1f}%</div>'
                 f'<div class="muted">top 20 minus the whole pool</div></div>')
    base = next((v for v in validations if v.get("score_vs_forward")), None)
    if base:
        head += (f'<div class="tile"><div class="l">Score vs forward return</div><div class="big">ρ = {base["score_vs_forward"]["spearman"]:+.2f}</div>'
                 f'<div class="muted">walk-forward, n={base.get("eligible")}</div></div>')

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(brand)} — track record</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap">
<style>{CSS}</style></head><body><div class="wrap">
<div class="brand">from GUNDECK.AI</div>
<h1>{_esc(brand)} — track record</h1>
<p class="muted">Updated {_esc(as_of)}. Every issue's top 20, scored against the whole candidate pool from the day it was published. Nothing is removed.</p>
{f'<p><b>{_esc(hl)}</b> A call is one card in one issue&rsquo;s top 20; a card that stays in the top 20 is called again the next day and resolved again. Every issue is committed to a public git history the day it is published, so no row here can be added, changed or removed after the fact.</p>' if hl else ''}
<div class="tiles">{head}{ix}</div>

<h2>Issue by issue</h2>
<p>Median change in market price from the issue date. <b>Spread</b> is the top 20 minus the pool: the number the product is actually for. <b>To date</b> is the open window, marked with the days elapsed.</p>
<div class="tablewrap"><table>
<thead><tr><th>Issue</th><th colspan="3" class="grp">+30 days</th><th colspan="3" class="grp">+60 days</th><th colspan="3" class="grp">+90 days</th><th colspan="4" class="grp">To date</th></tr>
<tr><th></th>{"<th class='num'>Top 20</th><th class='num'>Pool</th><th class='num'>Spread</th>" * 4}<th class="num">Days</th></tr></thead>
<tbody>{"".join(rows) or '<tr><td colspan="14" class="muted">No issue is old enough to score yet.</td></tr>'}</tbody></table></div>

<h2>Does the score separate winners from losers?</h2>
<p>Once a month the score is re-fitted on the first half of the stored history and measured on the second — a walk-forward test, the only honest kind. ρ is the rank correlation between score and what happened next. Above +0.20 with the top quintile beating the pool is working; near zero it has stopped separating; below zero it is inverted and the ranking should not be acted on.</p>
<div class="tablewrap"><table>
<thead><tr><th>Run</th><th class="num">ρ</th><th class="num">Top quintile</th><th class="num">All eligible</th><th>Verdict</th></tr></thead>
<tbody>{"".join(vrows) or '<tr><td colspan="5" class="muted">No validation run yet.</td></tr>'}</tbody></table></div>
{"<ul>" + "".join(f"<li>{_esc(c)}</li>" for c in (base.get("caveats") or [])) + "</ul>" if base else ""}

<h2>How to read this page</h2>
<p>The ranking describes what a card has already done: how it trades, how steadily it has climbed, how easily it could be sold. It is not a forecast, and this page is not a promise. In a rising market the top 20 and the pool both go up; in a falling one both go down. What is being measured is whether the screen's top 20 does better than picking from the same pool at random — the spread — and how consistently.</p>
{f'<a class="cta" href="{_esc(report_url)}">Open today&rsquo;s report (members)</a>' if report_url else ''}
<footer>{_esc(brand)} is published by GUNDECK.AI. Nothing here is financial advice; trading cards can lose value. Prices from tcgapi.dev under commercial licence.</footer>
</div></body></html>"""


def build(root: Path, series: dict, as_of: str, **kw) -> tuple[str, list[dict]]:
    recs = issues(root / "rankings", series, as_of)
    vpath = root / "validation_history.json"
    validations = json.loads(vpath.read_text(encoding="utf-8")) if vpath.exists() else []
    return render(recs, validations, as_of=as_of, **kw), recs
