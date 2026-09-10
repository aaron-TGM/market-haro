"""The public preview: today's top ten, then the door.

What a stranger sees at marketharo.io/preview. Rebuilt every morning with the
report and pushed beside it, so the numbers are the real ones -- the same ten
rows a subscriber sees at the top of the ranking -- and nothing more. Below
them, a faded strip stands in for the rest and says what the full report adds;
then the two plans. If the track record has resolved calls, one line of it.

Self-contained: card art embedded (ten thumbnails, ~200 KB), no scripts, no
Clerk. The Worker serves it public and cacheable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .dashboard import _esc

TOP = 10


def _pct(v, extra: str = "") -> str:
    if v is None:
        return f'<td class="num flat{extra}">—</td>'
    v = round(float(v))   # so -0.3 reads as 0%, not -0%
    cls = "up" if v > 0 else "down" if v < 0 else "flat"
    return f'<td class="num {cls}{extra}">{v:+d}%</td>'


def _price(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    return f"${v:,.2f}" if v < 100 else f"${v:,.0f}"


def _row(i: int, r: dict) -> str:
    thumb = r.get("thumb")
    art = (f'<img src="{thumb}" alt="" loading="lazy" width="40" height="56">' if thumb
           else '<span class="noart"></span>')
    sub = " · ".join(x for x in (r.get("set_name"), r.get("number"), r.get("rarity")) if x and x != "—")
    printing = r.get("printing") or ""
    if printing and printing != "Normal":
        sub += f" · {printing}"
    sales = r.get("avg_daily_sales")
    sales_s = "—" if sales is None else (f"{float(sales):.1f}" if float(sales) < 10 else f"{float(sales):.0f}")
    score = r.get("invest_score")
    score_s = "—" if score is None else f"{float(score):.0f}"
    return (f'<tr><td class="rk">{i}</td>'
            f'<td class="card">{art}<div><b>{_esc(r.get("name") or "")}</b><span class="n">{_esc(sub)}</span></div></td>'
            f'<td class="num">{_price(r.get("market_price"))}</td>'
            f'{_pct(r.get("change_7d"), " c7")}{_pct(r.get("change_30d"))}'
            f'<td class="num csales">{sales_s}</td>'
            f'<td class="num score">{score_s}</td></tr>')


def _ghost_row(i: int) -> str:
    return (f'<tr class="ghost"><td class="rk">{i}</td><td class="card"><span class="noart"></span>'
            f'<div><b>████████████</b><span class="n">██████ · ████-███</span></div></td>'
            f'<td class="num">$███</td><td class="num c7">██%</td><td class="num">██%</td>'
            f'<td class="num csales">█.█</td><td class="num score">██</td></tr>')


def render(
    ranked: Sequence[dict],
    *,
    obs_date: str,
    total_pass: int,
    pool_n: int,
    sealed_n: int = 0,
    record: dict[str, Any] | None = None,
    site_url: str = "",
    art_cache: Path | None = None,
    fetch_art: bool = False,
    top: int = TOP,
) -> str:
    rows = [dict(r) for r in ranked if not r.get("disqualified")][:top]
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    if art_cache is not None:
        from . import art

        art.embed(rows, art_cache, fetch=fetch_art)
    home = (site_url.rstrip("/") + "/") if site_url else "/"
    more = max(total_pass - len(rows), 0)
    rec_line = ""
    if record and record.get("calls_30"):
        rec_line = (f'<p class="rec"><b>The record so far:</b> of {record["calls_30"]} top-20 calls made 30 days '
                    f'earlier, {record["calls_beat_pct"]}% beat their pool at +30d (median {record["calls_median"]:+.1f}%). '
                    f'Every call is scored against the whole pool of its day and kept, losers included.</p>')
    body_rows = "".join(_row(r["rank"], r) for r in rows) + "".join(_ghost_row(i) for i in range(len(rows) + 1, len(rows) + 4))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Haro — today's top 10</title>
<meta name="description" content="Today's Gundam Card Game market, ranked. The top ten singles worth holding, free; the other {more} and every box in the full report.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap">
<style>
:root{{--bg:#07090c;--surface:#0d1117;--line:#2a2418;--text:#f2ead8;--muted:#9a917f;--accent:#e0a030;--up:#5fd08a;--down:#e06a5a}}
*{{box-sizing:border-box}}html,body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 "JetBrains Mono",ui-monospace,Menlo,monospace}}
.wrap{{max-width:860px;margin:0 auto;padding:36px 20px 80px}}
.brand{{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}}
h1{{margin:6px 0 4px;font-size:30px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}}
h2{{margin:34px 0 6px;font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}}
.tag{{color:var(--muted);font-size:13px;margin:0 0 22px}}p{{max-width:68ch}}
.tablewrap{{overflow-x:auto;border:1px solid var(--line);border-radius:2px;background:var(--surface)}}
table{{border-collapse:collapse;width:100%;min-width:640px}}th,td{{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:middle;text-align:left}}
th{{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:400}}
th.num,td.num{{text-align:right;white-space:nowrap}}td.rk{{color:var(--muted);width:2.2em}}
td.card{{display:flex;gap:10px;align-items:center;min-width:280px}}td.card img{{width:40px;height:56px;object-fit:cover;border-radius:2px;background:#151a22}}
.noart{{display:inline-block;width:40px;height:56px;border-radius:2px;background:#151a22}}
td.card b{{display:block;font-weight:700}}.n{{display:block;font-size:11px;color:var(--muted)}}
.up{{color:var(--up)}}.down{{color:var(--down)}}.flat{{color:var(--muted)}}td.score{{color:var(--accent);font-weight:700}}
tr.ghost td{{color:#3a3a3a;filter:blur(2px);user-select:none}}tr.ghost .noart,tr.ghost b,tr.ghost .n{{color:#2a2a2a;background:#0f1319}}
.more{{position:relative;margin-top:-1px;background:linear-gradient(180deg,rgba(7,9,12,0),var(--bg) 70%);padding:18px 0 0}}
.plans{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:18px 0 12px}}
.plan{{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:2px;padding:18px 18px 16px}}
.plan::before{{content:"";position:absolute;top:-1px;left:-1px;width:12px;height:12px;border:2px solid var(--accent);border-right:0;border-bottom:0}}
.plan .l{{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}}
.plan .v{{font-size:30px;font-weight:700;color:var(--accent);line-height:1.1;margin:6px 0 2px}}.plan .v small{{font-size:13px;color:var(--muted);font-weight:400}}
.plan .f{{font-size:12px;color:var(--muted);margin-bottom:14px}}
a.btn{{display:inline-block;background:var(--accent);color:var(--bg);text-decoration:none;font-weight:700;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:11px 16px;border-radius:2px}}
a.btn.quiet{{background:transparent;color:var(--accent);border:1px solid var(--accent)}}
ul{{padding-left:18px;color:var(--muted);margin:8px 0 0}}li{{margin:4px 0}}
.rec{{border-left:2px solid var(--accent);padding-left:12px;color:var(--muted);font-size:13px}}.rec b{{color:var(--text)}}
footer{{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:11px;line-height:1.6}}
@media (max-width:560px){{.wrap{{padding:28px 14px 60px}}table{{min-width:0}}.c7,.csales{{display:none}}th,td{{padding:8px 6px;font-size:13px}}td.card{{min-width:0;gap:8px}}td.card img,.noart{{width:32px;height:45px}}.n{{font-size:10px}}td.rk{{width:1.6em;padding-right:0}}h1{{font-size:24px}}}}
</style></head><body><div class="wrap">
<div class="brand">from GUNDECK.AI</div><h1>Market Haro</h1>
<p class="tag">Today's Gundam Card Game market, ranked. Rebuilt every morning from the whole English market on TCGplayer. Prices as of {_esc(obs_date)}.</p>
<p>Every single is scored 0–100 on value, liquidity, trend, stability and scarcity, then gated on the things that make a card un-holdable — a thin market, a price that whipsaws, a printing that keeps coming. Today {total_pass} of {pool_n} qualifying singles pass the screen. These are the top ten.</p>
{rec_line}
<h2>Today's top 10 — free</h2>
<div class="tablewrap"><table>
<thead><tr><th>#</th><th>Card</th><th class="num">Market</th><th class="num c7">7d</th><th class="num">30d</th><th class="num csales">Sales/day</th><th class="num">Score</th></tr></thead>
<tbody>{body_rows}</tbody></table></div>
<div class="more">
<p><b>{more} more singles below these</b>, in the full report — with, for every one of them: the 90-day chart with every set release marked; days of shelf and dollars to clear; the tracked high and how far off it the price sits; who is buying, at what pace. Plus every box, deck and case measured against the cards inside it, and your watchlist and holdings with P&amp;L, following you across devices.</p>
<div class="plans">
  <div class="plan"><div class="l">Monthly</div><div class="v">$8<small> / month</small></div><div class="f">7-day free trial · cancel any time</div><a class="btn" href="{_esc(home)}">Start monthly</a></div>
  <div class="plan"><div class="l">Annual</div><div class="v">$88<small> / year</small></div><div class="f">7-day free trial · eleven months for twelve</div><a class="btn" href="{_esc(home)}">Start annual</a></div>
</div>
<p class="tag">Card entered at sign-up, nothing charged for seven days. Sign in with a GUNDECK.AI account — free to create. <a class="btn quiet" href="{_esc(home)}" style="margin-left:8px">Already subscribed? Open the report</a></p>
</div>
<footer>Market Haro is published by GUNDECK.AI. Every number describes what a card has already done. Nothing here is a forecast, a recommendation or financial advice; trading cards can lose value. Prices from tcgapi.dev under commercial licence.</footer>
</div></body></html>"""
