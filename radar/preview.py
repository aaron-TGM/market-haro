"""The front door: the real dashboard, cut to ten rows.

What a stranger sees at marketharo.io, and what a signed-in reader without a
subscription sees too. Rebuilt every morning with the report and pushed
beside it, so everything on it is today's: the same header and KPI tiles as
the report (one function, radar/haro.py::kpi_tiles, so they cannot drift),
then the top ten of the ranking rendered as the report renders them -- the
first row open, with the large art and the full-width 90-day chart with its
release marks, the other nine closed with their sparklines -- then three
blurred rows standing in for the rest, then the two plans.

The page is self-contained (report CSS, card art embedded, no scripts of its
own) and knows nothing about identity or billing. The Worker fills four
markers when it serves it:

    <!--haro:head-->     Clerk's script tag, in the head
    <!--haro:auth-->     the state line: sign in / signed in as … / sign out
    <!--haro:script-->   the door's script (checkout return, plan buttons)
    a[data-plan]         the two plan buttons; the script sets their href

So the Worker never learns a card, and this file never learns a URL.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .dashboard import _esc, _row_payload
from .haro import CSS as REPORT_CSS, kpi_tiles

TOP = 10
GHOSTS = 3
ANOMALY_PCT = 15   # twin of haro.JS ANOMALY_PCT
TOP_SCORE = 75     # twin of haro.JS TOP_SCORE
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CSS = r"""
/* the door: what the report's stylesheet does not cover ------------------- */
.row{cursor:default}.row:hover{border-color:var(--border)}.row.open:hover{border-color:var(--accent)}
/* the first row is open: its chart sits beside the art, where the report's detail would */
.row.open .chart{grid-area:dx;margin-top:10px}
.row.open .stats{justify-content:start;column-gap:28px}
.tagline{font-size:12px;color:var(--text-muted);margin:6px 0 0;letter-spacing:.02em}
.hbtns{align-items:center}
.who-line{font-size:11.5px;color:var(--text-muted);line-height:1.5}.who-line b{color:var(--text)}
.hbtns .ghost{white-space:nowrap}
.rows.top{gap:8px}
.row.ghost{pointer-events:none;user-select:none}
.row.ghost .nm,.row.ghost .meta,.row.ghost .stats .v,.row.ghost .stats .l,.row.ghost .score .n,.row.ghost .rank .n,.row.ghost .cap{color:var(--border-2);filter:blur(3px)}
.row.ghost .art{background:var(--surface-2)}.row.ghost .score .bar i{background:var(--border-2)}
.row.ghost .chart svg{opacity:.35;filter:blur(2px)}
.row.ghost .tag{color:var(--border-2);border-color:var(--border)}
.fade{position:relative;margin-top:-140px;height:140px;background:linear-gradient(180deg,rgba(7,9,12,0),var(--bg) 78%);pointer-events:none}
.door{position:relative;margin-top:-10px}
.morerow{font-size:13px;letter-spacing:.04em;color:var(--text);margin:0 0 12px}
.morerow b{color:var(--accent);font-size:16px}
.morerow span{color:var(--text-muted)}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:0 0 12px}
.plan{position:relative;background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:18px 18px 16px}
.plan::before{content:"";position:absolute;top:-1px;left:-1px;width:12px;height:12px;border:2px solid var(--accent);border-right:0;border-bottom:0}
.plan .l{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--text-muted)}
.plan .v{font-size:30px;font-weight:700;color:var(--accent);line-height:1.1;margin:6px 0 2px}.plan .v small{font-size:13px;color:var(--text-muted);font-weight:400}
.plan .f{font-size:12px;color:var(--text-muted);margin-bottom:14px}
a.btn{display:inline-block;background:var(--accent);color:var(--bg);text-decoration:none;font-weight:700;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:11px 16px;border-radius:var(--r)}
a.btn:hover{text-decoration:none;filter:brightness(1.1)}
a.btn.quiet{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.fine{font-size:11px;color:var(--text-muted);line-height:1.6;margin:0}
#pending .l{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--text-muted)}#pending .v{font-size:18px;font-weight:700;color:var(--accent);margin:4px 0 2px}#pending .f{font-size:12px;color:var(--text-muted)}
@media (max-width:640px){
  header{flex-direction:column;align-items:flex-start;gap:10px}
  .hbtns{justify-content:flex-start}
  .fade{margin-top:-120px;height:120px}
  .row.ghost:last-child{display:none}
}
"""


# ---------------------------------------------------------------- formatting
def money(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    return f"${v:,.0f}" if v >= 1000 else f"${v:,.2f}"


def _pct(v, digits: int = 0) -> str:
    if v is None:
        return '<span class="flat">—</span>'
    v = float(v)
    cls = "up" if v > 0.05 else "down" if v < -0.05 else "flat"
    return f'<span class="{cls}">{"+" if v > 0 else ""}{v:.{digits}f}%</span>'


def _short(d: str | None) -> str:
    d = str(d or "")
    if len(d) >= 10 and d[4] == "-" and d[7] == "-":
        try:
            return f"{MON[int(d[5:7]) - 1]} {int(d[8:10])}"
        except (ValueError, IndexError):
            pass
    return d


# ---------------------------------------------------------------- the chart
# A Python twin of haro.JS::chart(): 2px line, 12% wash, ringed end marker,
# a dashed mark where a set released, a ring on any day that moved 15%+.
def _marks(series: Sequence[Sequence], releases: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    dates = [str(d[0]) for d in series]
    rel = []
    for m in releases:
        if not (dates[0] <= m["date"] <= dates[-1]):
            continue
        i = next((j for j, d in enumerate(dates) if d >= m["date"]), -1)
        if i > 0:
            rel.append({**m, "i": i})
    anomalies = []
    for i in range(1, len(series)):
        a, b = float(series[i - 1][1]), float(series[i][1])
        if a > 0 and abs((b - a) / a * 100) >= ANOMALY_PCT:
            anomalies.append({"i": i, "pct": (b - a) / a * 100})
    return rel, anomalies


def chart(series: Sequence[Sequence], releases: Sequence[dict] = (), *, big: bool = False,
          legend: bool = False) -> str:
    if not series or len(series) < 2:
        return '<div class="chart"><div class="empty" style="padding:22px">no history</div></div>'
    w, h = (1200, 150) if big else (300, 80)
    p, top = 6, 12
    ys = [float(d[1]) for d in series]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or (hi or 1.0)
    n = len(series)
    X = lambda i: p + i * (w - 2 * p) / (n - 1)  # noqa: E731
    Y = lambda v: h - p - ((v - lo) / span) * (h - p - top)  # noqa: E731
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(ys))
    area = f"M{X(0):.1f},{h - p:.1f} L{pts.replace(' ', ' L')} L{X(n - 1):.1f},{h - p:.1f} Z"
    first, last = series[0], series[-1]
    stroke = "var(--cyan)" if float(last[1]) >= float(first[1]) else "var(--down)"
    rel, anomalies = _marks(series, releases)
    rel_svg = "".join(
        f'<line x1="{X(m["i"]):.1f}" x2="{X(m["i"]):.1f}" y1="{top - 2}" y2="{h - p}" stroke="var(--accent-dim)" '
        f'stroke-width="1" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>' for m in rel)
    labels = []
    for m in rel:
        f = m["i"] / (n - 1)
        pos = "end" if f > 0.85 else "start" if f < 0.1 else "mid"
        labels.append(f'<span class="rl {pos}" style="left:{X(m["i"]) / w * 100:.2f}%">{_esc(m["label"])}</span>')
    anom_svg = "".join(
        f'<circle cx="{X(a["i"]):.1f}" cy="{Y(ys[a["i"]]):.1f}" r="{5 if big else 3.5}" fill="none" stroke="var(--warn)" '
        f'stroke-width="1.5" vector-effect="non-scaling-stroke"/>' for a in anomalies)
    aria = f"market price, {money(first[1])} to {money(last[1])}"
    if rel:
        aria += "; releases marked: " + ", ".join(m["label"] for m in rel)
    head = ('<div class="bl"><span>Market price · 90 days</span><span>dashed marks are set releases, rings are days that moved '
            f'{ANOMALY_PCT}%+</span></div>') if big else ""
    leg = (f'<div class="legend"><span><i></i>set release</span><span><b></b>{ANOMALY_PCT}%+ in a day</span></div>'
           if legend else "")
    return (f'<div class="chart">{head}<div class="cv">'
            f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="{_esc(aria)}">'
            f'<path d="{area}" fill="{stroke}" opacity=".12"/>{rel_svg}'
            f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="2" stroke-linejoin="round" '
            f'stroke-linecap="round" vector-effect="non-scaling-stroke"/>{anom_svg}'
            f'<circle cx="{X(n - 1):.1f}" cy="{Y(ys[-1]):.1f}" r="4" fill="{stroke}" stroke="var(--surface)" stroke-width="2"/>'
            f'</svg>{"".join(labels)}</div>'
            f'<div class="cap"><span>{_short(first[0])} {money(first[1])} → {_short(last[0])} {money(last[1])}</span>'
            f'<span>high {money(hi)}</span></div>{leg}</div>')


# ---------------------------------------------------------------- rows
def _art(r: dict) -> str:
    # Embedded art only: this page has no script to swap a failed remote
    # image for a frame, so a card the cache lacks gets the frame outright.
    src = r.get("thumb")
    if not src:
        return f'<div class="ph"><b>{_esc(r.get("name") or "")}</b>{_esc(r.get("number") or "")}<span>no image</span></div>'
    return f'<img src="{_esc(src)}" alt="" decoding="async">'


def _tags(r: dict) -> str:
    t = []
    rar = r.get("rarity")
    if rar and rar not in ("—", "None"):
        t.append(f'<span class="tag">{_esc(rar)}</span>')
    pr = r.get("printing")
    if pr and pr != "Normal":
        t.append(f'<span class="tag">{_esc(pr)}</span>')
    return "".join(t)


def _stat(label: str, value: str, cls: str = "") -> str:
    return f'<div class="s"><div class="l">{label}</div><div class="v{(" " + cls) if cls else ""}">{value}</div></div>'


def row(r: dict, releases: Sequence[dict], *, open_: bool = False) -> str:
    """One row exactly as the report draws it: rank, art, name, chart, stats,
    score. `open_` is the first row -- the large art and the big chart."""
    prem = r.get("ask_premium_pct")
    prem_html = ('<span class="flat">—</span>' if prem is None else
                 f'<span class="{"down" if prem > 5 else "up" if prem < -2 else "flat"}">{"+" if prem > 0 else ""}{prem:.0f}%</span>')
    sales = r.get("avg_daily_sales")
    score = float(r.get("invest_score") or 0)
    meta = " · ".join(_esc(x) for x in (r.get("set_name"), r.get("number")) if x)
    return (
        f'<div class="row{" open" if open_ else ""}" aria-expanded="{"true" if open_ else "false"}">'
        f'<div class="rank"><span class="n">{r["rank"]}</span></div>'
        f'<div class="art">{_art(r)}</div>'
        f'<div class="who"><div class="nm">{_esc(r.get("name") or "")}</div><div class="meta">{meta}</div><div class="tags">{_tags(r)}</div></div>'
        f'{chart(r.get("series") or [], releases, big=open_, legend=open_)}'
        f'<div class="stats">'
        f'{_stat("Price", money(r.get("market_price")))}'
        f'{_stat("Entry", money(r.get("floor_low")))}'
        f'{_stat("vs sold", prem_html)}'
        f'{_stat("7d", _pct(r.get("change_7d")))}'
        f'{_stat("90d", _pct(r.get("change_90d")))}'
        f'{_stat("Sales/day", "—" if sales is None else f"{float(sales):.1f}", "down" if (sales or 0) < 1 else "")}'
        f'</div>'
        f'<div class="score{" top" if score >= TOP_SCORE else ""}"><div class="n">{score:.0f}</div>'
        f'<div class="bar"><i style="width:{max(3.0, score):.0f}%"></i></div><div class="l">score</div></div>'
        f'</div>')


def ghost_row(i: int) -> str:
    """A blurred stand-in for a row the reader has not paid for."""
    pts = " ".join(f"{6 + j * 288 / 29:.1f},{74 - ((j * 7) % 11) * 4 - (j * 1.4):.1f}" for j in range(30))
    return (
        f'<div class="row ghost" aria-hidden="true">'
        f'<div class="rank"><span class="n">{i}</span></div>'
        f'<div class="art"></div>'
        f'<div class="who"><div class="nm">██████ █████</div><div class="meta">██████ · ████-███</div>'
        f'<div class="tags"><span class="tag">███</span></div></div>'
        f'<div class="chart"><div class="cv"><svg viewBox="0 0 300 80" preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline points="{pts}" fill="none" stroke="var(--cyan)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg></div>'
        f'<div class="cap"><span>███ ██ → ███ ██</span><span>███</span></div></div>'
        f'<div class="stats">{"".join(_stat(l, "$███") for l in ("Price", "Entry", "vs sold", "7d", "90d", "Sales/day"))}</div>'
        f'<div class="score"><div class="n">██</div><div class="bar"><i style="width:60%"></i></div><div class="l">score</div></div>'
        f'</div>')


# ---------------------------------------------------------------- the page
def render(
    ranked: Sequence[dict],
    *,
    obs_date: str,
    market: dict[str, Any] | None = None,
    releases: Sequence[dict] | None = None,
    today: str | None = None,
    record: dict[str, Any] | None = None,
    art_cache: Path | None = None,
    fetch_art: bool = False,
    top: int = TOP,
    total_pass: int | None = None,
    pool_n: int | None = None,
    sealed_n: int = 0,
    site_url: str = "",
) -> str:
    """`total_pass`, `pool_n`, `sealed_n` and `site_url` are accepted for
    compatibility with older callers and derived from `ranked` when absent."""
    candidates = [r for r in ranked if not r.get("disqualified")]
    rejected = [r for r in ranked if r.get("disqualified")]
    releases = [{"date": m["date"], "label": m["label"], "names": m.get("names") or []} for m in (releases or [])]
    rows = []
    for i, r in enumerate(candidates[:top], 1):
        p = _row_payload(r)
        p["rank"] = i
        p["series"] = r.get("series") or []
        rows.append(p)
    if art_cache is not None:
        from . import art

        art.embed(rows, art_cache, fetch=fetch_art)
    n_pass = total_pass if total_pass is not None else len(candidates)
    more = max(n_pass - len(rows), 0)
    kpis = kpi_tiles(candidates, rejected, market=market, releases=releases, record=record,
                     today=today, obs_date=obs_date, screened_href=None, track_url="")
    body_rows = "".join(row(r, releases, open_=(i == 0)) for i, r in enumerate(rows))
    ghosts = "".join(ghost_row(i) for i in range(len(rows) + 1, len(rows) + 1 + GHOSTS))
    return f"""<!doctype html>
<html lang="en" class="viz-root" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Haro — today's top 10</title>
<meta name="description" content="Today's Gundam Card Game market, ranked. The top ten singles worth holding, free; the other {more} and every box in the full report.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap">
<style>{REPORT_CSS}{CSS}</style>
<!--haro:head-->
</head>
<body class="viz-root">
<div class="wrap">
<header>
  <div>
    <div class="brand"><span>from</span>GUNDECK.AI</div>
    <h1>Market Haro</h1>
    <div class="stamp">Prices through {_esc(obs_date)} · {n_pass} cards pass the screen · English NM only</div>
    <p class="tagline">Today's Gundam Card Game market, ranked — rebuilt every morning from the whole English market on TCGplayer.</p>
  </div>
  <div class="hbtns" id="auth"><!--haro:auth--></div>
</header>

<div class="panel" id="pending" hidden><div class="l">One moment</div><div class="v">Finishing your subscription…</div><div class="f" id="pending-f">Stripe is telling your GUNDECK account about it. This usually takes a few seconds.</div></div>

<div class="kpis">
{kpis}
</div>

<div class="rows top" id="rows">
{body_rows}
{ghosts}
</div>
<div class="fade"></div>

<div class="door" id="door">
  <p class="morerow"><b>+{more}</b> more rows below these, every box measured against its singles, the live shelf, your watchlist and holdings <span>— in the full report.</span></p>
  <div class="plans" id="plans">
    <div class="plan"><div class="l">Monthly</div><div class="v">$8<small> / month</small></div><div class="f">7-day free trial · cancel any time</div><a class="btn" href="#" data-plan="monthly">Start monthly</a></div>
    <div class="plan"><div class="l">Annual</div><div class="v">$88<small> / year</small></div><div class="f">7-day free trial · eleven months for twelve</div><a class="btn" href="#" data-plan="annual">Start annual</a></div>
  </div>
  <p class="fine">Card entered at sign-up, nothing charged for seven days. Sign in with a GUNDECK.AI account — free to create, the same login if you already play with GUNDECK. Signing in takes you to gundeck.ai for a moment and brings you straight back.</p>
</div>

<footer>Market Haro is published by GUNDECK.AI. Every number describes what a card has already done. Nothing here is a forecast, a recommendation or financial advice; trading cards can lose value. Prices from tcgapi.dev under commercial licence.</footer>
</div>
<!--haro:script-->
</body></html>"""
