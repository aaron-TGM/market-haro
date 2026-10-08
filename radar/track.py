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

AFTER COSTS, AND WHICH RANKING (October 2026)

A market-price move is not money in a reader's pocket. Every call that
carried a live Near Mint entry price is also resolved the way a buyer would
live it: bought at that entry, sold at the market price 30 days later less
selling costs (radar/costs.py). And the budget plan the page would have
drawn for $500 and $2,500 on each issue is valued the same way -- the
model portfolio, from the stored issue alone, never re-run.

Issues before 8 October 2026 were ranked by the retired score; later ones
by the hold score (radar/horizon.py). Each row says which, so the record of
the old method stays on the page beside the new one instead of vanishing.
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
PLAN_BUDGETS = (500, 2500)
METHOD_NAMES = {None: "retired score", "horizons-2026-10": "hold score"}


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


def _net_calls(rows: Sequence[dict], series: dict, end: str, cost_cfg: dict | None) -> list[float]:
    """Each call bought at its live entry and sold at the market on `end`, less costs."""
    from . import costs

    out = []
    for r in rows:
        k = (str(r["card_id"]), r.get("printing") or "Normal")
        p1 = _price_at(series.get(k, []), end, before=False)
        n = costs.net_return_pct(r.get("floor_low"), p1, cost_cfg)
        if n is not None:
            out.append(n)
    return out


def plan_outcome(rows: Sequence[dict], series: dict, budget: float, end: str,
                 cost_cfg: dict | None = None, plan_cfg: dict | None = None) -> dict | None:
    """The page's budget plan on a stored issue, valued on `end`.

    Sized exactly as the page sizes it (radar/plan.py) on the issue's own
    entries and copies; valued at the market on `end`, and at what selling
    every copy there would have returned."""
    from . import costs
    from .plan import allocate

    ranked = sorted((r for r in rows if r.get("rank")), key=lambda r: r["rank"])
    pc = plan_cfg or {}
    plans = allocate(ranked, budget, max_position_pct=float(pc.get("max_position_pct", 0.25)),
                     max_set_pct=float(pc.get("max_set_pct", 0.5)))
    cost = value = back = 0.0
    n = 0
    for r, p in zip(ranked, plans):
        if not p["qty"]:
            continue
        k = (str(r["card_id"]), r.get("printing") or "Normal")
        p1 = _price_at(series.get(k, []), end, before=False)
        if not p1:
            return None   # a position we cannot value: say nothing rather than half
        n += 1
        cost += p["cost"]
        value += p["qty"] * p1
        back += p["qty"] * (costs.proceeds(p1, cost_cfg) or 0)
    if not n or not cost:
        return None
    return {"budget": budget, "positions": n, "cost": round(cost, 2), "value": round(value, 2),
            "proceeds": round(back, 2), "market_pct": round((value / cost - 1) * 100, 1),
            "net_pct": round((back / cost - 1) * 100, 1)}


def issues(rankings_dir: Path, series: dict, as_of: str, *, cost_cfg: dict | None = None,
           plan_cfg: dict | None = None) -> list[dict[str, Any]]:
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
        top_rows = [r for r in rows if r["rank"] <= TOP]
        top = [key(r) for r in top_rows]
        pool = [key(r) for r in rows]
        rec: dict[str, Any] = {"date": d, "top_n": len(top), "pool_n": len(pool), "windows": {},
                               "method": METHOD_NAMES.get(snap.get("method"), snap.get("method"))}
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
                    # ...and the way a buyer lives it: bought at the live entry,
                    # sold at the market less costs.
                    rec["calls_30_net"] = _net_calls(top_rows, series, end.isoformat(), cost_cfg)
                    rec["plans_30"] = [p for p in (plan_outcome(rows, series, b, end.isoformat(), cost_cfg, plan_cfg)
                                                   for b in PLAN_BUDGETS) if p]
        elapsed = (today - start).days
        t, tn = _median_change(top, series, d, as_of)
        p, pn = _median_change(pool, series, d, as_of)
        rec["to_date"] = {"days": elapsed, "top": t, "top_n": tn, "pool": p, "pool_n": pn,
                          "spread": round(t - p, 1) if t is not None and p is not None else None}
        rec["plans_to_date"] = [p for p in (plan_outcome(rows, series, b, as_of, cost_cfg, plan_cfg)
                                            for b in PLAN_BUDGETS) if p]
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
    nets = [n for r in recs for n in (r.get("calls_30_net") or [])]
    if nets:
        out.update({"net_calls": len(nets), "net_profitable": sum(1 for n in nets if n > 0),
                    "net_median": round(median(nets), 1)})
    # The model portfolio: the newest issue whose 30 days have closed, per budget.
    closed = [r for r in recs if r.get("plans_30")]
    if closed:
        last = closed[-1]
        out["plans_30"] = {"date": last["date"], "method": last.get("method"), "plans": last["plans_30"]}
    out["methods"] = sorted({r.get("method") or "" for r in recs} - {""})
    return out


def headline(sm: dict) -> str:
    """One plain sentence for the top of the page and the sales copy. Empty until a window closes."""
    if not sm.get("calls_30"):
        return ""
    s = (f"Of {sm['calls_30']} top-20 calls resolved at 30 days, {sm['calls_beat_pct']}% beat their pool "
         f"and {sm['calls_up_pct']}% were up; the median call moved {sm['calls_median']:+.1f}%"
         + (f" against a median spread of {sm['median_spread']:+.1f}% over the pool." if sm.get("closed_30") else "."))
    if sm.get("net_calls"):
        s += (f" Bought at the cheapest Near Mint copy and sold at the market less selling costs, "
              f"{sm['net_profitable']} of {sm['net_calls']} made money (median {sm['net_median']:+.1f}%).")
    return s


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


def _rho(v) -> str:
    return "—" if v is None else f"{v:+.2f}"


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
        rows.append(f'<tr><td><b>{_esc(r["date"])}</b><span class="n">top {r["top_n"]} of {r["pool_n"]} · {_esc(r.get("method") or "")}</span></td>{cells}</tr>')
    prow = []
    for r in reversed(list(recs)):
        for when, key in (("+30 days", "plans_30"), (f"to date ({r['to_date']['days']}d)", "plans_to_date")):
            for pl in r.get(key) or []:
                prow.append(f'<tr><td><b>{_esc(r["date"])}</b><span class="n">{_esc(r.get("method") or "")}</span></td>'
                            f'<td class="num">${pl["budget"]:,.0f}</td><td>{_esc(when)}</td>'
                            f'<td class="num">{pl["positions"]}</td><td class="num">${pl["cost"]:,.2f}</td>'
                            f'{_cell(pl["market_pct"])}{_cell(pl["net_pct"])}</tr>')

    vrows = []
    for v in validations:
        if v.get("kind") == "horizons":
            continue   # the horizon rankings have their own table
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
    # The newest run of each test, never the first: the August calibration
    # said +0.24 and the October run said -0.32, and only one of those is news.
    base = next((v for v in reversed(list(validations)) if (v.get("score_vs_forward") or {}).get("spearman") is not None), None)
    hz = next((v for v in reversed(list(validations)) if v.get("kind") == "horizons"), None)
    w90 = (((hz or {}).get("horizons") or {}).get("mid") or {}).get("windows", {}).get("90") or {}
    if w90.get("splits"):
        head += (f'<div class="tile"><div class="l">Hold ranking, 90 days</div><div class="big {"up" if w90["top_median"] > w90["pool_median"] else "down"}">{w90["top_median"]:+.0f}%</div>'
                 f'<div class="muted">top 20 vs {w90["pool_median"]:+.0f}% for the field · ahead in {w90["top_beat_pool"]} of {w90["splits"]} monthly tests</div></div>')
    if base:
        head += (f'<div class="tile"><div class="l">Retired score vs forward return</div><div class="big {"down" if base["score_vs_forward"]["spearman"] < 0 else ""}">ρ = {base["score_vs_forward"]["spearman"]:+.2f}</div>'
                 f'<div class="muted">walk-forward, {_esc(base.get("ran_at"))}, n={base.get("eligible")}</div></div>')
    hrows = []
    if hz:
        from .horizon import LABELS

        for name in ("mid", "long"):
            for h, w in sorted(((hz["horizons"].get(name) or {}).get("windows") or {}).items(), key=lambda kv: int(kv[0])):
                if not w.get("splits"):
                    hrows.append(f'<tr><td><b>{_esc(LABELS[name])}</b><span class="n">{h} days</span></td><td colspan="6" class="muted">no {h}-day window has closed yet</td></tr>')
                    continue
                hrows.append(f'<tr><td><b>{_esc(LABELS[name])}</b><span class="n">{h} days · {w["splits"]} tests, {_esc(w["first"])} to {_esc(w["last"])}</span></td>'
                             f'<td class="num">{w["rho_mean"]:+.2f}<span class="n">{w["rho_positive"]} positive</span></td>'
                             f'{_cell(w["top_median"])}{_cell(w["pool_median"])}<td class="num">{w["top_beat_pool"]} of {w["splits"]}</td>'
                             f'{_cell(w.get("top_net_median"))}<td class="num">{_rho((w.get("sold") or {}).get("rho_mean"))}</td></tr>')
        sh = hz["horizons"].get("short") or {}
        if sh.get("starts"):
            hrows.append(f'<tr><td><b>{_esc(LABELS["short"])}</b><span class="n">30 days · {len(sh["starts"])} start dates</span></td>'
                         f'<td colspan="6">{_esc(sh.get("verdict") or "")}</td></tr>')
        lg = hz.get("legacy") or {}
        for h, w in sorted((lg.get("windows") or {}).items(), key=lambda kv: int(kv[0])):
            if w.get("splits"):
                hrows.append(f'<tr><td><b>Retired score</b><span class="n">{h} days · {w["splits"]} weekly tests</span></td>'
                             f'<td class="num">{w["rho_mean"]:+.2f}<span class="n">{w["rho_positive"]} positive</span></td>'
                             f'{_cell(w["top_median"])}{_cell(w["pool_median"])}<td class="num">{w["top_beat_pool"]} of {w["splits"]}</td>'
                             f'<td class="num muted">—</td><td class="num muted">—</td></tr>')

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

<h2>If you had followed the budget plan</h2>
<p>The plan the page would have drawn on each issue, sized on that issue&rsquo;s own live entry prices and copies (a quarter of the budget at most per card, half per set), then valued at the market and at what selling every copy there would have returned after the marketplace&rsquo;s cut. Never re-run, never resized.</p>
<div class="tablewrap"><table>
<thead><tr><th>Issue</th><th class="num">Budget</th><th>Valued</th><th class="num">Positions</th><th class="num">Cost</th><th class="num">At market</th><th class="num">After costs</th></tr></thead>
<tbody>{"".join(prow) or '<tr><td colspan="7" class="muted">No issue carried live entry prices yet.</td></tr>'}</tbody></table></div>

<h2>The rankings on the page, walked forward</h2>
<p>Since 8 October 2026 the report ranks by hold horizon. Each ranking is tested monthly on our own archive: every card scored with only what was known on the day, then measured at the horizon it is for. <b>Top 20</b> and <b>field</b> are medians across the tests; <b>after costs</b> is the top 20 bought at the market and sold at the market less selling costs; <b>sold ρ</b> is the same ordering measured on what copies actually sold for.{f" Last run {_esc(hz.get('ran_at'))}." if hz else ""}</p>
<div class="tablewrap"><table>
<thead><tr><th>Ranking</th><th class="num">ρ</th><th class="num">Top 20</th><th class="num">Field</th><th class="num">Ahead</th><th class="num">After costs</th><th class="num">Sold ρ</th></tr></thead>
<tbody>{"".join(hrows) or '<tr><td colspan="7" class="muted">No walk-forward of the horizon rankings yet: run radar validate.</td></tr>'}</tbody></table></div>

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


def build(root: Path, series: dict, as_of: str, *, cost_cfg: dict | None = None,
          plan_cfg: dict | None = None, **kw) -> tuple[str, list[dict]]:
    recs = issues(root / "rankings", series, as_of, cost_cfg=cost_cfg, plan_cfg=plan_cfg)
    vpath = root / "validation_history.json"
    validations = json.loads(vpath.read_text(encoding="utf-8")) if vpath.exists() else []
    return render(recs, validations, as_of=as_of, **kw), recs
