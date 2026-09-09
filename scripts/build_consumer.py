"""The consumer preview: Market Haro exactly as a subscriber sees it.

No pitch, no build notes. Three tabs -- the report, today's email, the
track record -- each the real artefact from the current issue, full height,
under the product's own header. out/market-haro.html and .artifact.html.
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


def payload(dashboard: str) -> dict:
    m = re.search(r'id="haro-data">(.*?)</script>', dashboard, re.S)
    return json.loads(m.group(1).replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))


CSS = """
:root{--bg:#07090c;--surface:#0d1117;--line:#2a2418;--line-2:#3d3424;--text:#f2ead8;--muted:#9a917f;--accent:#e0a030;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
*{box-sizing:border-box}
html{color-scheme:dark}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font:13px/1.5 var(--mono);display:flex;flex-direction:column;min-height:100vh}
header{display:flex;align-items:center;gap:18px;padding:12px 18px;border-bottom:1px solid var(--line);background:var(--surface);flex-wrap:wrap}
.brand{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}
.brand b{display:block;font-size:14px;letter-spacing:.14em;color:var(--accent)}
.stamp{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.tabs{display:inline-flex;border:1px solid var(--line-2);border-radius:2px;overflow:hidden;margin-left:auto}
.tabs button{background:transparent;color:var(--muted);border:0;padding:9px 14px;font:inherit;font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;cursor:pointer}
.tabs button.on{background:var(--accent);color:var(--bg)}
.tabs button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.member{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);border:1px solid var(--line-2);border-radius:2px;padding:7px 10px}
.member b{color:var(--text)}
.stage{flex:1;position:relative;min-height:0}
.stage iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:#07090c}
.stage iframe.light{background:#fff}
.stage iframe[hidden]{display:none}
.note{padding:8px 18px;border-top:1px solid var(--line);font-size:10.5px;color:var(--muted);letter-spacing:.04em}
@media (max-width:700px){header{gap:10px}.tabs{margin-left:0;width:100%}.tabs button{flex:1}.member{display:none}}
"""

JS = """
const tabs=[...document.querySelectorAll('.tabs button')], frames=[...document.querySelectorAll('.stage iframe')];
function show(k){tabs.forEach(b=>b.classList.toggle('on',b.dataset.tab===k));frames.forEach(f=>{f.hidden=f.dataset.tab!==k;});try{localStorage.setItem('haro.preview.tab',k);}catch(e){}}
tabs.forEach(b=>b.addEventListener('click',()=>show(b.dataset.tab)));
let start='report';try{start=localStorage.getItem('haro.preview.tab')||'report';}catch(e){}
show(start);
"""


def build() -> tuple[str, str]:
    dash = (OUT / "dashboard.html").read_text(encoding="utf-8")
    p = payload(dash)
    meta = json.loads((OUT / "digest.json").read_text(encoding="utf-8"))
    email_body = (OUT / "digest.html").read_text(encoding="utf-8")
    email_doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>body{{margin:0;background:#f4f2ec;color:#1a1a1a;font:15px/1.6 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif}}.m{{max-width:640px;margin:24px auto;padding:26px 28px 34px;background:#fff;border:1px solid #e6e2d8;border-radius:4px}}.m a{{color:#b8791c}}.env{{max-width:640px;margin:0 auto;padding:22px 0 0;font:13px/1.5 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#555}}.env b{{color:#111}}.env .s{{font-size:17px;font-weight:600;color:#111;margin:0 0 4px}}.hd{{font:700 11px/1.4 ui-monospace,Menlo,monospace;letter-spacing:.18em;text-transform:uppercase;color:#b8791c;margin:0 0 4px}}.tt{{font:700 22px/1.25 ui-monospace,Menlo,monospace;margin:0 0 16px;color:#111}}.cta{{display:inline-block;margin:18px 0 6px;background:#e0a030;color:#111;padding:11px 16px;text-decoration:none;font:700 12px/1 ui-monospace,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase;border-radius:2px}}.ft{{margin-top:26px;padding-top:12px;border-top:1px solid #e6e2d8;font-size:11.5px;color:#777}}</style></head><body>
<div class="env"><p class="s">{html.escape(meta['subject'])}</p><b>Market Haro</b> &lt;haro@gundeck.ai&gt; · to you · {html.escape(meta['run_date'])}, 13:10 UTC</div>
<div class="m"><p class="hd">Market Haro · from GUNDECK.AI</p><p class="tt">{html.escape(meta['subject'].split(' — ', 1)[-1])}</p>
{email_body}
<a class="cta" href="#">Open today’s report</a>
<p class="ft">You are receiving this because you subscribe to Market Haro. Every number describes what a card has already done; nothing here is a forecast or financial advice, and trading cards can lose value. Prices from tcgapi.dev under commercial licence.</p>
</div></body></html>"""
    track = (OUT / "track-record.html").read_text(encoding="utf-8")
    e = lambda s: html.escape(s, quote=True)  # noqa: E731

    body = f"""<title>Market Haro</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap">
<style>{CSS}</style>
<header>
  <div class="brand">from GUNDECK.AI<b>Market Haro</b></div>
  <div class="stamp">Prices through {e(p['obs_date'])} · issue sent {e(meta['run_date'])}</div>
  <div class="tabs" role="tablist">
    <button data-tab="report" role="tab">The report</button>
    <button data-tab="email" role="tab">Today’s email</button>
    <button data-tab="track" role="tab">Track record</button>
  </div>
  <div class="member">Preview · <b>paid member view</b></div>
</header>
<div class="stage">
  <iframe data-tab="report" title="The report" srcdoc="{e(dash)}" sandbox="allow-scripts allow-same-origin allow-popups"></iframe>
  <iframe data-tab="email" class="light" title="Today’s email" srcdoc="{e(email_doc)}" sandbox="allow-same-origin" hidden></iframe>
  <iframe data-tab="track" title="Track record" srcdoc="{e(track)}" sandbox="allow-same-origin" hidden></iframe>
</div>
<div class="note">This is Market Haro as a subscriber sees it: the members-only report, the email that links to it, and the public track record. $9.99 a month or $89 a year, 7-day trial. Watchlist changes made here stay in this browser.</div>
<script>{JS}</script>
"""
    head_end = body.index("</style>") + len("</style>")
    full = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">' + body[:head_end]
            + "</head><body>" + body[head_end:] + "</body></html>")
    return body, full


if __name__ == "__main__":
    body, full = build()
    (OUT / "market-haro.artifact.html").write_text(body, encoding="utf-8")
    (OUT / "market-haro.html").write_text(full, encoding="utf-8")
    print(f"market-haro.html {len(full):,} bytes")
