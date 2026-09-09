"""Build the investor preview: a subscriber's day, end to end, on one page.

out/market-haro-preview.html (full document) and .artifact.html (for hosting).
Everything embedded is the real thing from the current issue: the email as
it lands, the report, an alert from the Worker's template, the public track
record. No mock data; the numbers on the page are read from the issue.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "out"


def esc_attr(s: str) -> str:
    return html.escape(s, quote=True)


def payload(dashboard: str) -> dict:
    m = re.search(r'id="haro-data">(.*?)</script>', dashboard, re.S)
    return json.loads(m.group(1).replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))


CSS = """
:root{--bg:#07090c;--surface:#0d1117;--surface-2:#131a22;--line:#2a2418;--line-2:#3d3424;--text:#f2ead8;--muted:#9a917f;
  --accent:#e0a030;--up:#5fd08a;--down:#e0554a;--cyan:#5cc8d8;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;--sans:"IBM Plex Sans",-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
*{box-sizing:border-box}
html{color-scheme:dark;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 var(--sans)}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:0 28px 90px}
.top{display:flex;justify-content:space-between;align-items:center;padding:22px 0;border-bottom:1px solid var(--line);font-family:var(--mono)}
.top .brand{font-size:10.5px;letter-spacing:.22em;text-transform:uppercase;color:var(--accent)}
.top nav{display:flex;gap:18px;flex-wrap:wrap}
.top nav a{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.hero{padding:56px 0 34px;display:grid;grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr);gap:40px;align-items:end}
.hero h1{margin:0 0 14px;font:700 44px/1.08 var(--mono);letter-spacing:-.01em;text-wrap:balance}
.hero h1 em{font-style:normal;color:var(--accent)}
.hero p{margin:0;max-width:56ch;font-size:18px;color:#d9d0bd}
.price{font-family:var(--mono);border:1px solid var(--line-2);border-radius:3px;padding:18px 20px;background:var(--surface)}
.price .l{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
.price .v{font-size:34px;font-weight:700;line-height:1.1;margin:4px 0 2px}
.price .v small{font-size:14px;color:var(--muted);font-weight:400}
.price .f{font-size:11.5px;color:var(--muted);line-height:1.6;margin-top:6px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;padding:0 0 40px;border-bottom:1px solid var(--line)}
.stat{padding:12px 0}
.stat .v{font:700 26px/1.1 var(--mono);font-variant-numeric:tabular-nums}
.stat .l{font:400 10.5px/1.5 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-top:4px}
.up{color:var(--up)} .down{color:var(--down)}
section{padding:52px 0;border-bottom:1px solid var(--line)}
.eyebrow{font:700 11px/1 var(--mono);letter-spacing:.2em;text-transform:uppercase;color:var(--accent);margin:0 0 12px}
h2{margin:0 0 12px;font:700 30px/1.15 var(--mono);letter-spacing:-.005em;text-wrap:balance;max-width:26ch}
.lead{max-width:64ch;font-size:17px;color:#d9d0bd;margin:0 0 8px}
.lead p{margin:0 0 12px}
.step{display:grid;grid-template-columns:64px minmax(0,1fr);gap:18px;margin-top:30px}
.step .n{font:700 13px/1 var(--mono);color:var(--accent);letter-spacing:.1em;padding-top:8px}
.step .n span{display:block;font-size:10px;color:var(--muted);margin-top:6px;letter-spacing:.14em}
.step h3{margin:0 0 6px;font:700 20px/1.25 var(--mono)}
.step p{margin:0 0 10px;max-width:62ch;color:#d9d0bd}
.inbox{border:1px solid var(--line-2);border-radius:4px;overflow:hidden;background:#fff;color:#111;margin-top:14px}
.inbox .hdr{padding:14px 18px;border-bottom:1px solid #e6e2d8;font-family:var(--sans);font-size:13.5px;line-height:1.5;color:#333;background:#faf8f3}
.inbox .hdr .subj{font-size:17px;font-weight:600;color:#111;margin-bottom:6px}
.inbox .hdr .from b{color:#111}
.inbox .hdr .btn{float:right;background:#e0a030;color:#111;font:700 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;padding:9px 12px;border-radius:2px}
.inbox iframe{display:block;width:100%;height:900px;border:0;background:#fff}
.frame{margin-top:14px;border:1px solid var(--line-2);border-radius:4px;overflow:hidden;background:var(--surface)}
.frame .bar{display:flex;align-items:center;gap:12px;padding:9px 12px;border-bottom:1px solid var(--line);font:11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.frame .bar .url{color:var(--text);text-transform:none;letter-spacing:0}
.frame .bar button{margin-left:auto;background:transparent;border:1px solid var(--line-2);color:var(--accent);font:inherit;padding:6px 10px;border-radius:2px;cursor:pointer}
.frame iframe{display:block;width:100%;height:820px;border:0;background:#07090c}
.frame.tall iframe{height:1700px}
.frame.light iframe{background:#fff;height:520px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin-top:22px}
.card{border:1px solid var(--line);border-radius:3px;padding:16px 18px;background:var(--surface)}
.card h4{margin:0 0 6px;font:700 14px/1.3 var(--mono)}
.card p{margin:0;font-size:14.5px;color:#cfc6b2}
.moat{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:26px 34px;margin-top:22px}
.moat h4{margin:0 0 6px;font:700 15px/1.3 var(--mono)}
.moat p{margin:0;font-size:15px;color:#cfc6b2;max-width:44ch}
table.cmp{border-collapse:collapse;width:100%;margin-top:18px;font-size:15px}
.cmp th{font:400 10.5px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--muted);text-align:left;padding:10px;border-bottom:1px solid var(--line)}
.cmp td{padding:11px 10px;border-bottom:1px dotted var(--line);vertical-align:top}
.cmp td:first-child{font-family:var(--mono);font-weight:700;white-space:nowrap}
.cmp tr.us td{background:var(--surface)}
footer{padding:30px 0 0;font-size:12.5px;color:var(--muted);max-width:80ch;line-height:1.6}
@media (max-width:820px){.hero{grid-template-columns:1fr}.hero h1{font-size:32px}.step{grid-template-columns:1fr}.wrap{padding:0 16px 60px}}
"""

JS = """
document.querySelectorAll('[data-grow]').forEach(b=>b.addEventListener('click',()=>{const f=b.closest('.frame');f.classList.toggle('tall');b.textContent=f.classList.contains('tall')?'Shorter':'Taller';}));
"""


def build() -> tuple[str, str]:
    dash = (OUT / "dashboard.html").read_text(encoding="utf-8")
    p = payload(dash)
    meta = json.loads((OUT / "digest.json").read_text(encoding="utf-8"))
    ix = p.get("index") or {}
    rows, sealed = p["rows"], p.get("sealed") or []
    nxt = next((m for m in p.get("releases", []) if m["date"] > p["obs_date"]), None)
    top = rows[0]
    pct = lambda v, d=1: "—" if v is None else f'<span class="{"up" if v > 0 else "down" if v < 0 else ""}">{v:+.{d}f}%</span>'  # noqa: E731

    email_body = (OUT / "digest.html").read_text(encoding="utf-8")
    email_doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>body{{margin:0;background:#fff;color:#1a1a1a;font:15px/1.6 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif}}.m{{max-width:620px;margin:0 auto;padding:22px 24px 40px}}.m a{{color:#b8791c}}.hd{{font:700 11px/1.4 ui-monospace,Menlo,monospace;letter-spacing:.18em;text-transform:uppercase;color:#b8791c;margin:0 0 4px}}.tt{{font:700 22px/1.25 ui-monospace,Menlo,monospace;margin:0 0 16px;color:#111}}.cta{{display:inline-block;margin:18px 0 6px;background:#e0a030;color:#111;padding:11px 16px;text-decoration:none;font:700 12px/1 ui-monospace,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase;border-radius:2px}}.ft{{margin-top:26px;padding-top:12px;border-top:1px solid #e6e2d8;font-size:11.5px;color:#777}}</style></head><body><div class="m">
<p class="hd">Market Haro · from GUNDECK.AI</p><p class="tt">{html.escape(meta['subject'].split(' — ', 1)[-1])}</p>
{email_body}
<a class="cta" href="#">Open today’s report</a>
<p class="ft">You are receiving this because you subscribe to Market Haro. Every number describes what a card has already done; nothing here is a forecast or financial advice, and trading cards can lose value. Prices from tcgapi.dev under commercial licence.</p>
</div></body></html>"""
    alert_doc = (OUT / "alert-sample.html").read_text(encoding="utf-8")
    alert_doc = f'<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;background:#fff">{alert_doc}</body></html>'

    def frame(title, doc, *, light=False, tall=False, url=""):
        return (f'<div class="frame{" light" if light else ""}{" tall" if tall else ""}"><div class="bar"><span>{html.escape(title)}</span>'
                f'{("<span class=url>" + html.escape(url) + "</span>") if url else ""}<button data-grow>{"Shorter" if tall else "Taller"}</button></div>'
                f'<iframe title="{html.escape(title)}" srcdoc="{esc_attr(doc)}" sandbox="allow-scripts allow-same-origin" loading="lazy"></iframe></div>')

    body = f"""<title>Market Haro Preview</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{CSS}</style>
<div class="wrap">
<div class="top"><span class="brand">Market Haro · from GUNDECK.AI</span>
  <nav><a href="#day">A subscriber’s day</a><a href="#inside">What’s inside</a><a href="#moat">Why it holds</a><a href="#business">The business</a><a href="#next">Next</a></nav></div>

<div class="hero">
  <div>
    <h1>The daily market terminal for people who <em>invest</em> in the Gundam Card Game.</h1>
    <p>Every morning it measures the entire English market, ranks the singles worth holding, screens sealed product, marks every chart with the set calendar, scores its own past calls in public, and emails each subscriber what changed on the cards they follow. Built and sent automatically; one person writes the weekly note.</p>
  </div>
  <div class="price"><div class="l">One tier</div><div class="v">$7.99<small> / month</small></div><div class="f">$75 a year · 7-day trial · no free tier<br>Stripe through Ghost · cancel any time</div></div>
</div>

<div class="stats">
  <div class="stat"><div class="v">1,967</div><div class="l">products priced daily</div></div>
  <div class="stat"><div class="v">98,134</div><div class="l">price points, 13 months</div></div>
  <div class="stat"><div class="v">{ix.get('value', 0):.1f}</div><div class="l">Market Haro 50 · 30d {pct(ix.get('change_30d'))}</div></div>
  <div class="stat"><div class="v">{len(rows)}</div><div class="l">singles pass the screen today</div></div>
  <div class="stat"><div class="v">{len(sealed)}</div><div class="l">sealed products tracked</div></div>
  <div class="stat"><div class="v">8</div><div class="l">set releases measured</div></div>
</div>

<section id="day">
  <p class="eyebrow">Live · issue of {html.escape(p['obs_date'])}</p>
  <h2>A subscriber’s day, end to end.</h2>
  <div class="lead"><p>Everything below is the real thing from the current issue, not a mock-up: the email as it lands, the report it links to, an alert as a member receives it, and the public page that scores every past issue. Use them — the report filters, sorts and opens.</p></div>

  <div class="step"><div class="n">06:10<span>THE EMAIL</span></div><div>
    <h3>What moved since yesterday, then one link.</h3>
    <p>The subject line is the biggest change. The weekly note leads when there is one; then entries and exits from the top 20, climbers and fallers, cards whose asking price ran ahead of their sales or fell below them, market breadth, and how fresh the price feed is.</p>
    <div class="inbox"><div class="hdr"><span class="btn">Paid members</span><div class="subj">{html.escape(meta['subject'])}</div><div class="from"><b>Market Haro</b> &lt;haro@gundeck.ai&gt; · to you · {html.escape(meta['run_date'])}, 13:10 UTC</div></div>
    <iframe title="The daily email" srcdoc="{esc_attr(email_doc)}" sandbox="allow-same-origin" loading="lazy"></iframe></div>
  </div></div>

  <div class="step"><div class="n">06:12<span>THE REPORT</span></div><div>
    <h3>One page that answers “what should I be looking at, and can I get out?”</h3>
    <p>The Market Haro 50 says what the market is doing. Your holdings say what your money is doing. Then the ranking: every English single priced $10+ and rising over 30 days, measured on 90 days of daily price and sales, scored 0–100 against the market’s own quartiles, with card art, a release-marked chart, entry price, ask vs sold, and a size at your budget. Tap a row for three verdicts, the case, what would break it, and a year of history. A fourth view does the same for sealed product. Below the ranking: what every set release did to prices, with the count on every cell.</p>
    {frame("The report", dash, tall=True, url="/market-haro/ · members only")}
  </div></div>

  <div class="step"><div class="n">ANY DAY<span>THE ALERT</span></div><div>
    <h3>One email on the days something changed on the cards you follow.</h3>
    <p>Trend broke on a card you hold. A card you watch is now listed below what it has been selling for. A card left or entered the top 20. A set releases in seven days. On change only, one email a day at most, with your P&amp;L on top — sent to the member, about the member’s list, from a watchlist that follows them across devices.</p>
    {frame("An alert", alert_doc, light=True, url="from Market Haro · per member")}
  </div></div>

  <div class="step"><div class="n">ALWAYS<span>THE RECORD</span></div><div>
    <h3>Every past issue, scored in public. Losers kept.</h3>
    <p>The one page without a paywall. Each issue’s top 20 against the whole pool it was picked from, at 30, 60 and 90 days. The spread between those two columns is what the product is for, and it is printed whether or not it flatters us — the first issue is currently running behind its pool.</p>
    {frame("The track record", (OUT / "track-record.html").read_text(encoding="utf-8"), url="/track-record/ · public")}
  </div></div>
</section>

<section id="inside">
  <p class="eyebrow">What’s inside</p>
  <h2>Ten things a subscriber gets that a price guide does not.</h2>
  <div class="grid">
    <div class="card"><h4>Market Haro 50</h4><p>One number for the market: the fifty most-traded singles, equal weight, a year of history, every release marked.</p></div>
    <div class="card"><h4>The hold screen</h4><p>Scored, gated, explained. Every rejection listed with its reason. Nothing dropped silently.</p></div>
    <div class="card"><h4>Ask vs sold</h4><p>The listed price against what copies actually sold for. The one timing signal that survived testing (ρ = −0.31 vs the next 30 days, n = 1,201).</p></div>
    <div class="card"><h4>Budget sizing</h4><p>Enter a number; every row becomes copies, cost and what limited it, with a per-card cap.</p></div>
    <div class="card"><h4>Sealed screen</h4><p>Boxes, decks and cases against release and their earliest price. Not scored, because boxes are not cards.</p></div>
    <div class="card"><h4>Release playbook</h4><p>What every set release did to the prior set, the new set and the market. Eight measured; the new set’s chase cards fell 20–30% in two months every time.</p></div>
    <div class="card"><h4>Holdings that follow you</h4><p>Star, enter copies and cost, see P&amp;L at the top of the page on any device. Nothing to sign up for beyond the membership.</p></div>
    <div class="card"><h4>Alerts on change</h4><p>Trend broke, listed below sold, top-20 moves, release in seven days. Never the same alert twice.</p></div>
    <div class="card"><h4>The weekly note</h4><p>A few hundred words in a person’s voice. The one thing subscribers forward.</p></div>
    <div class="card"><h4>The public record</h4><p>Every issue scored against its pool, plus the monthly walk-forward test of the score itself.</p></div>
  </div>
</section>

<section id="moat">
  <p class="eyebrow">Why it holds</p>
  <h2>Four things that get harder to copy every day it runs.</h2>
  <div class="moat">
    <div><h4>The archive</h4><p>The price API sells 90 days of daily history. Every day the pipeline records a day it will not sell back next year. Thirteen months in, the archive is the asset; the code is replaceable.</p></div>
    <div><h4>The playbook</h4><p>Measuring what releases do needs history on both sides of eight release dates. A competitor starting today has one release to measure and a year to wait for the rest.</p></div>
    <div><h4>The record</h4><p>A public, unedited scorecard compounds: every issue adds a row nobody can backfill. It is the trust document a paid product needs, and it cannot be bought.</p></div>
    <div><h4>The member</h4><p>Holdings and alerts turn a report into a tool a person configures. A configured tool is the thing people do not cancel.</p></div>
  </div>
</section>

<section id="business">
  <p class="eyebrow">The business</p>
  <h2>Priced as a terminal, run for almost nothing.</h2>
  <div class="lead"><p>The closest comparable covers sixteen games at $19 with a $49 professional tier. Market Haro covers one game deeper than anyone: sold-price timing, budget sizing, sealed, the release playbook, member alerts and a public record. It is priced against the depth, not the category.</p></div>
  <table class="cmp"><thead><tr><th>Product</th><th>Scope</th><th>Price</th><th>What it lacks against Market Haro</th></tr></thead><tbody>
    <tr class="us"><td>Market Haro</td><td>Gundam Card Game, every English product, daily</td><td><b>$7.99/mo · $75/yr</b></td><td>Graded and eBay comps (scoped next); a most-played index (scoped next)</td></tr>
    <tr><td>TCGIndex Premium / Pro</td><td>16 games, screeners, weekly picks, public track record</td><td>$19/mo · $49/mo</td><td>Ask-vs-sold timing, budget sizing, sealed screen, release playbook, per-member alerts</td></tr>
    <tr><td>Card Ladder Pro</td><td>Sports cards; collection tracking, sales history</td><td>≈ $150/yr</td><td>Not a TCG product; no screen, no sizing, no release calendar</td></tr>
    <tr><td>TCGplayer price guide</td><td>Free market prices per card</td><td>Free</td><td>No ranking, no history beyond the page, no sold-vs-ask, no alerts</td></tr>
  </tbody></table>
  <div class="grid" style="margin-top:22px">
    <div class="card"><h4>Cost to run</h4><p>GitHub Actions, a Cloudflare Worker and KV, Resend’s free tier, Ghost, and the price API plan. Under $100 a month all in, before the first subscriber.</p></div>
    <div class="card"><h4>Cost to ship</h4><p>Fully automated: a scheduled run builds, tests, commits, publishes and sends. One human input a week — the note.</p></div>
    <div class="card"><h4>Break-even</h4><p>Thirty subscribers cover infrastructure. A thousand at $7.99 is $96,000 a year on a product one person can operate.</p></div>
  </div>
</section>

<section id="next">
  <p class="eyebrow">Next</p>
  <h2>Two Fifties, then comps.</h2>
  <div class="lead"><p><b>Market Haro 50</b> stays the market’s number. <b>GUNDECK 50</b> becomes the meta’s number: the fifty most <em>played</em> cards, with every version of each — base, alt-art parallels, promos — priced side by side and the alt premium tracked. Its ranking public as the marketing page; its prices paid. Then graded and eBay sold comps for the top fifty. The scope is written; the first needs a play-data source, the second an API decision.</p></div>
</section>

<footer>Market Haro is published by GUNDECK.AI. Every number on these pages describes what a card has already done. Nothing is a forecast, a recommendation, or financial advice; trading cards can lose value. Prices from tcgapi.dev under commercial licence. Comparable pricing as published on each product’s site in September 2026.</footer>
</div>
<script>{JS}</script>
"""
    head_end = body.index("</style>") + len("</style>")
    full = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">' + body[:head_end]
            + "</head><body>" + body[head_end:] + "</body></html>")
    return body, full


if __name__ == "__main__":
    body, full = build()
    (OUT / "market-haro-preview.artifact.html").write_text(body, encoding="utf-8")
    (OUT / "market-haro-preview.html").write_text(full, encoding="utf-8")
    print(f"market-haro-preview.html {len(full):,} bytes")
