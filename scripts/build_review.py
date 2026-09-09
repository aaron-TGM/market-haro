"""Build the review page: everything in the build, live, on one page.

Writes out/build-review.html (a full document) and out/build-review.artifact.html
(the same page without the document wrapper, for hosting). Each product
surface is embedded as it is -- the report, the email, an alert, the track
record -- so a reviewer can use them, not read about them.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from radar.note import to_html as md_html  # noqa: E402

OUT = ROOT / "out"


def srcdoc(path: Path) -> str:
    return html.escape(path.read_text(encoding="utf-8"), quote=True)


def payload(dashboard: str) -> dict:
    m = re.search(r'id="haro-data">(.*?)</script>', dashboard, re.S)
    return json.loads(m.group(1).replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))


CSS = """
:root{--bg:#07090c;--surface:#0d1117;--surface-2:#121820;--line:#2a2418;--line-2:#3a3222;--text:#f2ead8;
  --muted:#9a917f;--accent:#e0a030;--up:#5fd08a;--down:#e0554a;--cyan:#5cc8d8;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;--sans:"IBM Plex Sans",-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
*{box-sizing:border-box}
html{color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 var(--sans)}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.shell{display:grid;grid-template-columns:220px minmax(0,1fr);gap:0;max-width:1480px;margin:0 auto}
.rail{position:sticky;top:0;height:100vh;overflow:auto;padding:26px 18px;border-right:1px solid var(--line);font-family:var(--mono)}
.rail .brand{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}
.rail h1{margin:4px 0 14px;font-size:16px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);line-height:1.25}
.rail .facts{font-size:11px;color:var(--muted);line-height:1.7;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--line)}
.rail .facts b{color:var(--text)}
.rail nav a{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:6px 0;border-bottom:1px dotted var(--line)}
.rail nav a:hover{color:var(--accent);text-decoration:none}
.rail nav a .st{float:right;font-size:9px;letter-spacing:.1em}
main{padding:26px 34px 80px;min-width:0}
section{padding:26px 0 34px;border-bottom:1px solid var(--line)}
section:last-child{border-bottom:0}
.eyebrow{font:700 10.5px/1 var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--accent);margin:0 0 10px;display:flex;align-items:center;gap:10px}
h2{margin:0 0 10px;font:700 24px/1.2 var(--mono);letter-spacing:.02em;text-wrap:balance}
.prose{max-width:68ch}
.prose p{margin:0 0 12px}
.prose p:last-child{margin-bottom:0}
.chip{display:inline-block;font:700 9.5px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;padding:5px 8px;border-radius:2px;border:1px solid var(--line-2);color:var(--muted)}
.chip.built{color:var(--up);border-color:var(--up)} .chip.you{color:var(--accent);border-color:var(--accent)} .chip.scoped{color:var(--cyan);border-color:var(--cyan)}
.frame{margin-top:18px;border:1px solid var(--line-2);border-radius:3px;background:var(--surface);overflow:hidden}
.frame .bar{display:flex;align-items:center;gap:12px;padding:8px 12px;border-bottom:1px solid var(--line);font:11px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.frame .bar b{color:var(--text)}
.frame .bar button{margin-left:auto;background:transparent;border:1px solid var(--line-2);color:var(--accent);font:inherit;padding:5px 10px;border-radius:2px;cursor:pointer}
.frame .bar button:hover{border-color:var(--accent)}
.frame iframe{display:block;width:100%;height:760px;border:0;background:#07090c}
.frame.tall iframe{height:1600px}
.frame.light iframe{background:#fff}
.feat{width:100%;border-collapse:collapse;margin-top:16px;font-size:14px}
.feat th{font:400 10px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--muted);text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
.feat td{padding:10px;border-bottom:1px dotted var(--line);vertical-align:top}
.feat td:first-child{font-family:var(--mono);font-weight:700;white-space:nowrap}
.feat td:last-child{white-space:nowrap}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0 0}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:2px;padding:10px 12px}
.tile .l{font:400 9.5px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.tile .v{font:700 22px/1.15 var(--mono);margin-top:4px;font-variant-numeric:tabular-nums}
.tile .f{font:400 10.5px/1.4 var(--mono);color:var(--muted);margin-top:3px}
.up{color:var(--up)} .down{color:var(--down)}
.doc{max-width:76ch;font-size:15px}
.doc h1{font:700 20px/1.3 var(--mono);margin:0 0 10px}
.doc h2{font:700 15px/1.3 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--accent);margin:24px 0 8px}
.doc h3,.doc h4{font:700 13px/1.3 var(--mono);letter-spacing:.06em;text-transform:uppercase;margin:18px 0 6px}
.doc table{border-collapse:collapse;font-size:13.5px;margin:10px 0}
.doc th,.doc td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
.doc th{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.doc hr{border:0;border-top:1px solid var(--line);margin:22px 0}
.doc code{font-family:var(--mono);font-size:13px;background:var(--surface-2);padding:1px 5px;border-radius:2px}
.doc ul,.doc ol{padding-left:22px}
.doc li{margin:4px 0}
.todo{list-style:none;padding:0;margin:14px 0 0;max-width:76ch}
.todo li{display:grid;grid-template-columns:26px 1fr;gap:10px;padding:10px 0;border-bottom:1px dotted var(--line)}
.todo li i{display:block;width:16px;height:16px;border:1.5px solid var(--accent);border-radius:2px;margin-top:3px}
.todo li b{font-family:var(--mono)}
@media (max-width:900px){.shell{grid-template-columns:1fr}.rail{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}main{padding:20px 16px 60px}}
"""

JS = """
document.querySelectorAll('[data-grow]').forEach(b=>b.addEventListener('click',()=>{const f=b.closest('.frame');f.classList.toggle('tall');b.textContent=f.classList.contains('tall')?'Shorter':'Taller';}));
"""


def _sow_html() -> str:
    md = (ROOT / "docs" / "SOW-two-fifties.md").read_text(encoding="utf-8")
    # The note renderer handles paragraphs/lists/headings; tables get a small pass here.
    out, table = [], []

    def flush_table():
        if not table:
            return
        rows = [r.strip().strip("|").split("|") for r in table if not re.match(r"^\s*\|?\s*-{2,}", r)]
        head, body = rows[0], rows[1:]
        out.append("<table><thead><tr>" + "".join(f"<th>{_inl(c.strip())}</th>" for c in head) + "</tr></thead><tbody>"
                   + "".join("<tr>" + "".join(f"<td>{_inl(c.strip())}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>")
        table.clear()

    def _inl(s):
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<em>\1</em>", s)
        return s

    buf = []
    for line in md.splitlines():
        if line.startswith("|"):
            if buf:
                out.append(md_html("\n".join(buf))); buf = []
            table.append(line); continue
        flush_table()
        if line.strip() == "---":
            if buf:
                out.append(md_html("\n".join(buf))); buf = []
            out.append("<hr>"); continue
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            if buf:
                out.append(md_html("\n".join(buf))); buf = []
            out.append(f"<h{len(m.group(1))}>{_inl(m.group(2))}</h{len(m.group(1))}>"); continue
        buf.append(line)
    if buf:
        out.append(md_html("\n".join(buf)))
    flush_table()
    return "\n".join(out).replace("<p>", "<p>").replace("`", "")


def build() -> tuple[str, str]:
    dash = (OUT / "dashboard.html").read_text(encoding="utf-8")
    p = payload(dash)
    ix = p.get("index") or {}
    rows = p["rows"]
    sealed = p.get("sealed") or []
    nxt = next((m for m in p.get("releases", []) if m["date"] > p["obs_date"]), None)
    top = rows[0]
    pct = lambda v: "—" if v is None else f'<span class="{"up" if v > 0 else "down" if v < 0 else ""}">{v:+.1f}%</span>'  # noqa: E731

    tiles = f"""
    <div class="tiles">
      <div class="tile"><div class="l">Prices through</div><div class="v">{html.escape(p['obs_date'])}</div><div class="f">last complete day on the feed</div></div>
      <div class="tile"><div class="l">Market Haro 50</div><div class="v">{ix.get('value', 0):.1f}</div><div class="f">7d {pct(ix.get('change_7d'))} · 30d {pct(ix.get('change_30d'))}</div></div>
      <div class="tile"><div class="l">Pass the screen</div><div class="v">{len(rows)}</div><div class="f">singles $10+, up over 30d, gated</div></div>
      <div class="tile"><div class="l">#1 today</div><div class="v" style="font-size:15px">{html.escape(top['name'])}</div><div class="f">score {top['invest_score']:.0f} · entry ${top['floor_low'] or 0:,.2f} · 90d {pct(top.get('change_90d'))}</div></div>
      <div class="tile"><div class="l">Sealed tracked</div><div class="v">{len(sealed)}</div><div class="f">boxes, decks, cases</div></div>
      <div class="tile"><div class="l">Next release</div><div class="v">{html.escape(nxt['label']) if nxt else '—'}</div><div class="f">{html.escape(nxt['date']) if nxt else ''}</div></div>
    </div>"""

    features = [
        ("Market Haro 50", "One number for the market: equal-weight, chain-linked, fifty most-traded singles $5+, base 100, a year of history with release marks.", "built", ""),
        ("Your holdings", "Positions, cost in, value now, P&L, trend-broke count at the top; follows the member across devices once the Worker is live.", "built", "Worker deploy needed for sync"),
        ("Weekly note", "A person’s few hundred words, shown ten days on the page and the email. First note is in.", "built", "you write them"),
        ("Hold screen", "127 singles scored 0–100, gated, with art, release-marked charts, verdicts, budget sizing, watchlist.", "built", ""),
        ("Sealed screen", "Boxes, decks, cases against earliest price, days since release, drawdown, units a day. Not scored.", "built", ""),
        ("Release playbook", "Prior set / new set / market at +30/60/90 for all eight releases on record.", "built", ""),
        ("Daily email", "What moved since the last issue; quick hits then the link.", "built", ""),
        ("Alerts", "Trend broke, below sold, top-20 moves, release in 7 days — on change, once a day, per member.", "built", "Worker + Resend deploy"),
        ("Track record", "Public: every issue’s top 20 vs its pool, losers kept, validation history.", "built", ""),
        ("Chart ranges", "30 days / 90 days / 1 year in every detail; 6-month and 1-year change.", "built", ""),
        ("GUNDECK 50 (most played)", "Every version priced, alt premium, its own page and index.", "scoped", "needs a play-data source"),
        ("Graded / eBay comps", "PSA 10 spreads and eBay actual sales for the top 50.", "later", "API cost decision"),
    ]
    frows = "".join(
        f'<tr><td>{html.escape(n)}</td><td>{html.escape(d)}</td><td><span class="chip {"built" if s == "built" else "scoped" if s == "scoped" else ""}">{s}</span>'
        f'{(" <span class=chip you>" + html.escape(note) + "</span>") if note else ""}</td></tr>'
        for n, d, s, note in features)

    def frame(title, path, *, light=False, tall=False, sub=""):
        return (f'<div class="frame{" light" if light else ""}{" tall" if tall else ""}"><div class="bar"><b>{html.escape(title)}</b>'
                f'{("<span>" + html.escape(sub) + "</span>") if sub else ""}<button data-grow>{"Shorter" if tall else "Taller"}</button></div>'
                f'<iframe title="{html.escape(title)}" srcdoc="{srcdoc(path)}" sandbox="allow-scripts allow-same-origin allow-popups" loading="lazy"></iframe></div>')

    body = f"""<title>Market Haro Build</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>{CSS}</style>
<div class="shell">
<aside class="rail">
  <div class="brand">from GUNDECK.AI</div>
  <h1>Market Haro<br>the build</h1>
  <div class="facts">Issue <b>{html.escape(p['obs_date'])}</b><br>Built 2026-09-06<br><b>{len(rows)}</b> pass the screen<br>MH50 <b>{ix.get('value', 0):.1f}</b><br>$9.99/mo · $89/yr</div>
  <nav>
    <a href="#built">What we built</a>
    <a href="#report">The report <span class="st">live</span></a>
    <a href="#email">The daily email <span class="st">live</span></a>
    <a href="#alerts">Alerts <span class="st">sample</span></a>
    <a href="#track">Track record <span class="st">live</span></a>
    <a href="#data">Data &amp; method</a>
    <a href="#next">Next: the two Fifties</a>
    <a href="#you">What needs you</a>
  </nav>
</aside>
<main>
<section id="built">
  <p class="eyebrow">Market Haro · from GUNDECK.AI <span class="chip built">built 2026-09-06</span></p>
  <h2>Everything in the build, on one page, live.</h2>
  <div class="prose"><p>Each surface below is embedded as it ships — the report you can filter and tap, the email as it lands, an alert as a member would get it, the public track record — on the last complete day the price feed has, <b>{html.escape(p['obs_date'])}</b>. The batch feed stamps most rows Sep 4 and runs a day behind the daily history; the charts, short-window changes and the settled price include Friday.</p></div>
  {tiles}
  <table class="feat"><thead><tr><th>Feature</th><th>What it is</th><th>Status</th></tr></thead><tbody>{frows}</tbody></table>
</section>

<section id="report">
  <p class="eyebrow">The report <span class="chip built">live · paid page</span></p>
  <h2>The dashboard a subscriber opens every morning.</h2>
  <div class="prose"><p>Top to bottom: the Market Haro 50, your holdings, the weekly note, the budget tool, the ranking with four views (All, Sized, Watchlist, Sealed), the release playbook, how to read it, everything screened out and why. Enter a budget, tap a row, star a card, switch the chart to a year — it all works in this frame. Watchlist changes stay in this browser.</p></div>
  {frame("out/dashboard.html", OUT / "dashboard.html", tall=True, sub="4.3 MB · art embedded · one file")}
</section>

<section id="email">
  <p class="eyebrow">The daily email <span class="chip built">live · paid post</span></p>
  <h2>What moved since the last issue, then the link.</h2>
  <div class="prose"><p>Sent by Ghost to every paying member at 13:10 UTC. The weekly note leads when there is one; then entries and exits from the top 20, climbers and fallers, asks that ran ahead of or fell below sales, market breadth, and the feed age. The subject line is the biggest change.</p></div>
  {frame("out/digest.html", OUT / "digest.html", light=True, sub="Ghost paid post · segment status:-free")}
</section>

<section id="alerts">
  <p class="eyebrow">Alerts <span class="chip built">sample · needs the Worker</span></p>
  <h2>One email on the days something changed on the cards you follow.</h2>
  <div class="prose"><p>Rules: a held or watched card broke trend today and had not yesterday; a watched card is now listed below what it sells for; a card left or entered the top 20; a set releases in seven days. On change only, one email per member per day at most, with the holder’s P&amp;L on top. This is the documented test case rendered by the Worker’s own mail template.</p></div>
  {frame("worker · mailHTML(sample)", OUT / "alert-sample.html", light=True, sub="Resend · from Market Haro")}
</section>

<section id="track">
  <p class="eyebrow">Track record <span class="chip built">live · public page</span></p>
  <h2>Every issue’s top 20, scored against its own pool. Losers kept.</h2>
  <div class="prose"><p>The one page without a paywall. Median change of the top 20 and of the whole candidate pool at +30/60/90 days; the spread is the number the product is for. Open windows are marked with days elapsed. The Aug 11 issue is running behind its pool to date — that number stays on the page.</p></div>
  {frame("out/track-record.html", OUT / "track-record.html", sub="Ghost public page · /track-record/")}
</section>

<section id="data">
  <p class="eyebrow">Data &amp; method</p>
  <h2>What is under it.</h2>
  <div class="tiles">
    <div class="tile"><div class="l">Price points</div><div class="v">98,134</div><div class="f">13 months · NDJSON archive in git</div></div>
    <div class="tile"><div class="l">Products with history</div><div class="v">798</div><div class="f">every single $2+ and every sealed</div></div>
    <div class="tile"><div class="l">Daily · weekly</div><div class="v">90d · 1y</div><div class="f">measured by date, not by count</div></div>
    <div class="tile"><div class="l">Releases measured</div><div class="v">8</div><div class="f">from the API's own calendar</div></div>
    <div class="tile"><div class="l">Tests</div><div class="v">53 + 2</div><div class="f">Python + the Worker's mirror</div></div>
    <div class="tile"><div class="l">Daily API cost</div><div class="v">~60</div><div class="f">of 10,000 Pro requests</div></div>
  </div>
  <div class="prose" style="margin-top:16px"><p>The score is 0–100 on value, liquidity, trend, stability and scarcity, anchored to this market’s own quartiles; gates remove the un-holdable and every rejection is listed with its reason. The settled price (ask vs sold) is the one timing signal that survived testing: ρ = −0.31 against the next 30 days across 1,201 observations. Set releases come from the API and label themselves from card numbers. Nothing is hand-maintained except the weekly note. The long version is <code>docs/METHOD.md</code>; the code map is <code>docs/ARCHITECTURE.md</code>.</p></div>
</section>

<section id="next">
  <p class="eyebrow">Next <span class="chip scoped">scoped</span></p>
  <h2>The two Fifties.</h2>
  <div class="doc">{_sow_html()}</div>
</section>

<section id="you">
  <p class="eyebrow">What needs you <span class="chip you">your side</span></p>
  <h2>Six things, none of them code.</h2>
  <ul class="todo">
    <li><i></i><span><b>Ghost tier.</b> Settings → Membership: $9.99 monthly, $89 yearly, 7-day trial on, subscription access paid-members only, free tier hidden in Portal.</span></li>
    <li><i></i><span><b>Repo secrets.</b> TCGAPI_KEY, GHOST_URL, GHOST_ADMIN_KEY — then run the workflow once by hand and watch it go green.</span></li>
    <li><i></i><span><b>The Worker.</b> <code>cd worker && npm install && npx wrangler kv namespace create HARO && npx wrangler deploy</code>; secrets ADMIN_SECRET and RESEND_API_KEY; put the Worker URL in <code>config.yaml → publish.sync_url</code> and the same secret in the repo as HARO_ADMIN_SECRET. DEPLOY.md §5b.</span></li>
    <li><i></i><span><b>Resend.</b> Verify the sending domain; set MAIL_FROM in <code>worker/wrangler.toml</code>.</span></li>
    <li><i></i><span><b>The weekly note.</b> <code>data/notes/YYYY-MM-DD.md</code>, a few hundred words, once a week. The one thing subscribers forward.</span></li>
    <li><i></i><span><b>The GUNDECK 50 data source.</b> Decide where “most played” comes from (gundeck.ai deck data is the recommendation) and send one week of it as a sample. Nothing in that scope starts until then.</span></li>
  </ul>
</section>
</main>
</div>
<script>{JS}</script>
"""
    full = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">' + body.replace("<title>", "", 0)
            + "</head></html>")
    # a proper full document: head holds title/links/style, body holds the rest
    head_end = body.index("</style>") + len("</style>")
    full = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">' + body[:head_end]
            + "</head><body>" + body[head_end:] + "</body></html>")
    return body, full


if __name__ == "__main__":
    body, full = build()
    (OUT / "build-review.artifact.html").write_text(body, encoding="utf-8")
    (OUT / "build-review.html").write_text(full, encoding="utf-8")
    print(f"build-review.html {len(full):,} bytes")
