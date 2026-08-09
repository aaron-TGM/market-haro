"""Render the radar as one self-contained HTML file.

Everything (CSS, JS, data) is inlined so the file can be emailed, dropped in
Dropbox, or opened from disk with no server. Card images are the only remote
asset, loaded lazily from TCGplayer's CDN.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from .signals import explain

# Palette: validated default categorical slots 1-3 (all-pairs, both modes).
# sustained = blue, spike = orange, breakout = aqua. Every badge also carries a
# text label, so identity never rests on color alone.
CSS = """
*,*::before,*::after{box-sizing:border-box}
.viz-root{
  color-scheme:light;
  --surface-1:#fcfcfb; --plane:#f9f9f7;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
  --series-1:#2a78d6; --series-2:#eb6834; --series-3:#1baf7a;
  --up:#006300; --down:#d03b3b; --good:#0ca30c; --warning:#fab219;
  --tint-1:rgba(42,120,214,0.12); --tint-2:rgba(235,104,52,0.12); --tint-3:rgba(27,175,122,0.14);
}
@media (prefers-color-scheme:dark){
  :root:where(:not([data-theme="light"])) .viz-root{
    color-scheme:dark;
    --surface-1:#1a1a19; --plane:#0d0d0d;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70;
    --up:#0ca30c; --down:#d03b3b;
    --tint-1:rgba(57,135,229,0.18); --tint-2:rgba(217,89,38,0.18); --tint-3:rgba(25,158,112,0.20);
  }
}
:root[data-theme="dark"] .viz-root{
  color-scheme:dark;
  --surface-1:#1a1a19; --plane:#0d0d0d;
  --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
  --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70;
  --up:#0ca30c; --down:#d03b3b;
  --tint-1:rgba(57,135,229,0.18); --tint-2:rgba(217,89,38,0.18); --tint-3:rgba(25,158,112,0.20);
}
html,body{margin:0;padding:0}
body{background:var(--plane);color:var(--text-primary);
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;}
.wrap{max-width:1280px;margin:0 auto;padding:28px 20px 64px}
header{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:4px}
h1{font-size:22px;font-weight:650;letter-spacing:-.01em;margin:0}
.sub{color:var(--text-secondary);font-size:13px;margin:2px 0 22px}
button.theme{background:none;border:1px solid var(--border);border-radius:8px;
  color:var(--text-secondary);padding:5px 11px;cursor:pointer;font:inherit;font-size:12px}
button.theme:hover{background:var(--surface-1)}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px;margin-bottom:22px}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.tile .label{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted)}
.tile .value{font-size:27px;font-weight:600;margin-top:5px;line-height:1.1}
.tile .foot{font-size:12px;color:var(--text-secondary);margin-top:3px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

.controls{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.controls input[type=search],.controls select{background:var(--surface-1);color:var(--text-primary);
  border:1px solid var(--border);border-radius:8px;padding:7px 10px;font:inherit;font-size:13px}
.controls input[type=search]{min-width:230px}
.chip{border:1px solid var(--border);background:var(--surface-1);border-radius:999px;
  padding:6px 13px;font-size:12.5px;cursor:pointer;color:var(--text-secondary);user-select:none}
.chip[aria-pressed="true"]{color:var(--text-primary);font-weight:600;border-color:currentColor}
.chip[data-sig="sustained"][aria-pressed="true"]{background:var(--tint-1)}
.chip[data-sig="spike"][aria-pressed="true"]{background:var(--tint-2)}
.chip[data-sig="breakout"][aria-pressed="true"]{background:var(--tint-3)}
.count{color:var(--text-muted);font-size:12.5px;margin-left:auto}

.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;overflow:hidden}
h2{font-size:15px;font-weight:620;margin:30px 0 10px}
h2 .hint{font-weight:400;color:var(--text-muted);font-size:12.5px;margin-left:8px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:8px 11px;border-bottom:1px solid var(--grid);vertical-align:middle}
thead th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted);
  font-weight:600;white-space:nowrap;cursor:pointer;position:sticky;top:0;background:var(--surface-1);z-index:2}
thead th:hover{color:var(--text-secondary)}
thead th[aria-sort]:not([aria-sort=none])::after{content:"";margin-left:5px;opacity:.75}
thead th[aria-sort=descending]::after{content:"\\2193"}
thead th[aria-sort=ascending]::after{content:"\\2191"}
tbody tr:hover{background:var(--plane)}
tbody tr:last-child td{border-bottom:none}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rank{color:var(--text-muted);font-variant-numeric:tabular-nums;width:34px}
.who{display:flex;gap:10px;align-items:center;min-width:250px}
.who img{width:32px;height:44px;object-fit:cover;border-radius:4px;background:var(--grid);flex:none}
.who .nm{font-weight:560;line-height:1.3}
.who a{color:inherit;text-decoration:none}
.who a:hover{text-decoration:underline}
.who .meta{color:var(--text-muted);font-size:11.5px;margin-top:1px}
.up{color:var(--up);font-weight:560}
.down{color:var(--down)}
.flat{color:var(--text-muted)}
.badges{display:flex;gap:5px;flex-wrap:wrap}
.badge{font-size:11px;padding:2.5px 8px;border-radius:999px;border:1px solid;white-space:nowrap;font-weight:560}
.badge.sustained{color:var(--series-1);border-color:var(--series-1);background:var(--tint-1)}
.badge.spike{color:var(--series-2);border-color:var(--series-2);background:var(--tint-2)}
.badge.breakout{color:var(--series-3);border-color:var(--series-3);background:var(--tint-3)}
.spark{display:block}
.score{font-variant-numeric:tabular-nums;font-weight:600}
.scorebar{height:3px;border-radius:2px;background:var(--series-1);margin-top:3px}
.why{color:var(--text-secondary);font-size:12px;min-width:170px;max-width:230px}
.empty{padding:36px;text-align:center;color:var(--text-muted)}
footer{margin-top:34px;color:var(--text-muted);font-size:12px;line-height:1.7}
footer code{background:var(--surface-1);border:1px solid var(--border);padding:1px 5px;border-radius:4px}
@media (max-width:820px){
  .why,.col-listings{display:none}
  .wrap{padding:20px 12px 48px}
}
"""

JS = """
const DATA = JSON.parse(document.getElementById('radar-data').textContent);
const state = {q:'', sigs:new Set(), set:'', sort:'score', dir:-1};

const fmtMoney = v => v==null ? '—' : '$' + v.toFixed(2);
const fmtPct = v => {
  if (v==null) return '<span class="flat">—</span>';
  const cls = v > 0.05 ? 'up' : (v < -0.05 ? 'down' : 'flat');
  const sign = v > 0 ? '+' : '';
  return `<span class="${cls}">${sign}${v.toFixed(1)}%</span>`;
};
const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function sparkline(series){
  if (!series || series.length < 2) return '<span class="flat">—</span>';
  const w=88,h=26,p=3;
  const ys = series.map(d=>d[1]);
  const lo = Math.min(...ys), hi = Math.max(...ys);
  const span = (hi-lo) || (hi || 1);
  const pts = series.map((d,i)=>{
    const x = p + i*(w-2*p)/(series.length-1);
    const y = h-p - ((d[1]-lo)/span)*(h-2*p);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const last = series[series.length-1];
  const lx = w-p, ly = h-p - ((last[1]-lo)/span)*(h-2*p);
  const rising = ys[ys.length-1] >= ys[0];
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img"
    aria-label="${series.length} points, ${rising?'rising':'falling'}, latest $${last[1].toFixed(2)}">
    <polyline points="${pts}" fill="none" stroke="var(--series-1)" stroke-width="2"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="2.5" fill="var(--series-1)"
      stroke="var(--surface-1)" stroke-width="2"/>
  </svg>`;
}

function rowHTML(r, i){
  const badges = (r.signals||[]).map(s=>`<span class="badge ${s}">${s}</span>`).join('');
  const url = r.tcgplayer_url || (r.tcgplayer_id ? 'https://www.tcgplayer.com/product/'+r.tcgplayer_id : null);
  const nameCell = url
    ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(r.name)}</a>`
    : esc(r.name);
  const img = r.image_url
    ? `<img src="${esc(r.image_url)}" alt="" loading="lazy" decoding="async">` : '<img alt="">';
  const printing = r.printing && r.printing!=='Normal' ? ' · '+esc(r.printing) : '';
  return `<tr>
    <td class="rank">${i+1}</td>
    <td><div class="who">${img}<div>
      <div class="nm">${nameCell}</div>
      <div class="meta">${esc(r.set_name||'')}${r.number?' · '+esc(r.number):''}${r.rarity?' · '+esc(r.rarity):''}${printing}</div>
    </div></div></td>
    <td class="num">${fmtMoney(r.market_price)}</td>
    <td class="num">${fmtPct(r.change_24h)}</td>
    <td class="num">${fmtPct(r.change_7d)}</td>
    <td class="num">${fmtPct(r.change_30d)}</td>
    <td>${sparkline(r.series)}</td>
    <td class="num col-listings">${r.total_listings==null?'—':r.total_listings}</td>
    <td><div class="badges">${badges}</div></td>
    <td class="num"><div class="score">${r.score.toFixed(0)}</div>
      <div class="scorebar" style="width:${Math.max(4, r.score)}%"></div></td>
    <td class="why">${esc(r.why||'')}</td>
  </tr>`;
}

const SORTERS = {
  score: r=>r.score, price: r=>r.market_price ?? -1,
  c24: r=>r.change_24h ?? -1e9, c7: r=>r.change_7d ?? -1e9, c30: r=>r.change_30d ?? -1e9,
  listings: r=>r.total_listings ?? -1, name: r=>(r.name||'').toLowerCase()
};

function apply(){
  const q = state.q.trim().toLowerCase();
  let rows = DATA.rows.filter(r=>{
    if (q && !((r.name||'').toLowerCase().includes(q) ||
               (r.set_name||'').toLowerCase().includes(q) ||
               (r.number||'').toLowerCase().includes(q))) return false;
    if (state.set && r.set_name !== state.set) return false;
    if (state.sigs.size && !(r.signals||[]).some(s=>state.sigs.has(s))) return false;
    return true;
  });
  const key = SORTERS[state.sort] || SORTERS.score;
  rows.sort((a,b)=>{
    const av=key(a), bv=key(b);
    if (av===bv) return 0;
    return (av>bv?1:-1) * state.dir;
  });
  document.getElementById('tbody').innerHTML = rows.length
    ? rows.map(rowHTML).join('')
    : '<tr><td colspan="11" class="empty">Nothing matches those filters.</td></tr>';
  document.getElementById('count').textContent =
    `${rows.length} of ${DATA.rows.length} shown`;
  document.querySelectorAll('thead th[data-sort]').forEach(th=>{
    th.setAttribute('aria-sort', th.dataset.sort===state.sort
      ? (state.dir===-1?'descending':'ascending') : 'none');
  });
}

document.getElementById('q').addEventListener('input', e=>{state.q=e.target.value; apply();});
document.getElementById('setfilter').addEventListener('change', e=>{state.set=e.target.value; apply();});
document.querySelectorAll('.chip[data-sig]').forEach(c=>{
  c.addEventListener('click', ()=>{
    const s=c.dataset.sig;
    if (state.sigs.has(s)) state.sigs.delete(s); else state.sigs.add(s);
    c.setAttribute('aria-pressed', state.sigs.has(s));
    apply();
  });
});
document.querySelectorAll('thead th[data-sort]').forEach(th=>{
  th.addEventListener('click', ()=>{
    const k=th.dataset.sort;
    if (state.sort===k) state.dir*=-1; else {state.sort=k; state.dir = k==='name' ? 1 : -1;}
    apply();
  });
});
const themeBtn = document.getElementById('theme');
const osDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
if (!document.documentElement.getAttribute('data-theme'))
  themeBtn.textContent = osDark ? 'Light mode' : 'Dark mode';
themeBtn.addEventListener('click', ()=>{
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur==='dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  themeBtn.textContent = next==='dark' ? 'Light mode' : 'Dark mode';
});
apply();
"""


def _row_payload(r: dict) -> dict:
    return {
        "card_id": r.get("card_id"),
        "name": r.get("name"),
        "set_name": r.get("set_name"),
        "number": r.get("number"),
        "rarity": r.get("rarity"),
        "printing": r.get("printing"),
        "image_url": r.get("image_url"),
        "tcgplayer_id": r.get("tcgplayer_id"),
        "tcgplayer_url": r.get("tcgplayer_url"),
        "market_price": r.get("market_price"),
        "change_24h": r.get("change_24h"),
        "change_7d": r.get("change_7d"),
        "change_30d": r.get("change_30d"),
        "total_listings": r.get("total_listings"),
        "sales_volume": r.get("sales_volume"),
        "score": r.get("score", 0.0),
        "signals": r.get("signals", []),
        "why": explain(r) if r.get("signals") else "",
        "series": [[d, round(v, 2)] for d, v in (r.get("series") or [])],
    }


def render(
    ranked: Sequence[dict],
    *,
    obs_date: str,
    stats: dict[str, Any],
    top_n: int = 60,
    fallers: Sequence[dict] = (),
    watchlist: Sequence[dict] = (),
) -> str:
    flagged = [r for r in ranked if r.get("signals")]
    shown = flagged[:top_n]
    if not shown:
        shown = [r for r in ranked if not r.get("filtered")][:top_n]

    rows = [_row_payload(r) for r in shown]
    watch_rows = [_row_payload(r) for r in watchlist]
    fall_rows = [_row_payload(r) for r in fallers]

    n_sus = sum(1 for r in flagged if "sustained" in r["signals"])
    n_spk = sum(1 for r in flagged if "spike" in r["signals"])
    n_brk = sum(1 for r in flagged if "breakout" in r["signals"])
    top = flagged[0] if flagged else None

    set_names = sorted({r["set_name"] for r in rows if r.get("set_name")})
    set_options = "".join(f'<option value="{_esc(s)}">{_esc(s)}</option>' for s in set_names)

    # Escape the angle brackets/ampersands so card text can never break out of
    # the <script> block (a card named "</script>" would otherwise be an XSS).
    payload = (
        json.dumps({"rows": rows}, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )

    def table(title: str, hint: str, data: Sequence[dict], tid: str) -> str:
        if not data:
            return ""
        body = "".join(
            _static_row(r, i) for i, r in enumerate(data)
        )
        return f"""
  <h2>{_esc(title)}<span class="hint">{_esc(hint)}</span></h2>
  <div class="card"><table id="{tid}"><thead><tr>
    <th class="rank">#</th><th>Card</th><th class="num">Market</th>
    <th class="num">24h</th><th class="num">7d</th><th class="num">30d</th>
    <th>Trend</th><th class="num col-listings">Listings</th><th>Signals</th>
    <th class="num">Score</th><th class="why">Note</th>
  </tr></thead><tbody>{body}</tbody></table></div>"""

    return f"""<!doctype html>
<html lang="en" class="viz-root">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gundam Price Radar — {_esc(obs_date)}</title>
<style>{CSS}</style>
</head>
<body class="viz-root">
<div class="wrap">
<header>
  <div>
    <h1>Gundam Price Radar</h1>
    <p class="sub">Market snapshot {_esc(obs_date)} · {stats.get('cards', 0):,} products tracked ·
      {stats.get('snapshot_dates', 0)} day{'' if stats.get('snapshot_dates', 0) == 1 else 's'} of own snapshots · source: tcgapi.dev</p>
  </div>
  <button class="theme" id="theme">Dark mode</button>
</header>

<div class="tiles">
  <div class="tile"><div class="label">Cards flagged</div>
    <div class="value">{len(flagged)}</div>
    <div class="foot">out of {sum(1 for r in ranked if not r.get('filtered')):,} that cleared the filters</div></div>
  <div class="tile"><div class="label">Sustained climb</div>
    <div class="value">{n_sus}</div><div class="foot">up over 7d and 30d</div></div>
  <div class="tile"><div class="label">24h spike</div>
    <div class="value">{n_spk}</div><div class="foot">sudden jump today</div></div>
  <div class="tile"><div class="label">Breakout</div>
    <div class="value">{n_brk}</div><div class="foot">above its own 90-day high</div></div>
  <div class="tile"><div class="label">Top mover</div>
    <div class="value">{(f"{top['change_7d']:+.0f}%" if top and top.get('change_7d') is not None else '—')}</div>
    <div class="foot">{_esc(top['name']) if top else 'nothing flagged today'}</div></div>
</div>

<div class="controls">
  <input type="search" id="q" placeholder="Search card, set or number…" aria-label="Search">
  <select id="setfilter" aria-label="Filter by set"><option value="">All sets</option>{set_options}</select>
  <button class="chip" data-sig="sustained" aria-pressed="false">Sustained</button>
  <button class="chip" data-sig="spike" aria-pressed="false">Spike</button>
  <button class="chip" data-sig="breakout" aria-pressed="false">Breakout</button>
  <span class="count" id="count"></span>
</div>

<div class="card"><table><thead><tr>
  <th class="rank">#</th>
  <th data-sort="name">Card</th>
  <th class="num" data-sort="price">Market</th>
  <th class="num" data-sort="c24">24h</th>
  <th class="num" data-sort="c7">7d</th>
  <th class="num" data-sort="c30">30d</th>
  <th>Trend</th>
  <th class="num col-listings" data-sort="listings">Listings</th>
  <th>Signals</th>
  <th class="num" data-sort="score" aria-sort="descending">Score</th>
  <th class="why">Note</th>
</tr></thead><tbody id="tbody"></tbody></table></div>

{table("Watchlist", "tracked regardless of score", watch_rows, "watch")}
{table("Biggest fallers", "context — and where dips show up", fall_rows, "fallers")}

<footer>
  <p><strong>Reading this:</strong> Score is a 0–100 blend of the three detectors, nudged up for
  higher-priced cards and cards with recorded sales. It ranks attention, not conviction.
  Trend sparklines mix weekly API history with your own daily snapshots, so they get denser
  the longer you run it.</p>
  <p>Tune thresholds in <code>config.yaml</code> · regenerate with <code>python -m radar sync &amp;&amp; python -m radar report</code></p>
</footer>
</div>
<script type="application/json" id="radar-data">{payload}</script>
<script>{JS}</script>
</body></html>"""


def _esc(s: Any) -> str:
    return (
        str("" if s is None else s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _spark_svg(series: Sequence[Sequence[Any]]) -> str:
    """Same sparkline as the JS one, rendered server-side for static tables."""
    pts = [(d, float(v)) for d, v in (series or []) if v is not None]
    if len(pts) < 2:
        return '<span class="flat">—</span>'
    w, h, p = 88, 26, 3
    ys = [v for _, v in pts]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or (hi or 1.0)
    coords = []
    for i, (_, v) in enumerate(pts):
        x = p + i * (w - 2 * p) / (len(pts) - 1)
        y = h - p - ((v - lo) / span) * (h - 2 * p)
        coords.append(f"{x:.1f},{y:.1f}")
    lx = w - p
    ly = h - p - ((ys[-1] - lo) / span) * (h - 2 * p)
    direction = "rising" if ys[-1] >= ys[0] else "falling"
    return (
        f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="{len(pts)} points, {direction}, latest ${ys[-1]:.2f}">'
        f'<polyline points="{" ".join(coords)}" fill="none" stroke="var(--series-1)" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.5" fill="var(--series-1)" '
        f'stroke="var(--surface-1)" stroke-width="2"/></svg>'
    )


def _static_row(r: dict, i: int) -> str:
    """Server-rendered row for the secondary tables (no JS filtering there)."""

    def pct(v: Any) -> str:
        if v is None:
            return '<span class="flat">—</span>'
        cls = "up" if v > 0.05 else ("down" if v < -0.05 else "flat")
        return f'<span class="{cls}">{v:+.1f}%</span>'

    url = r.get("tcgplayer_url") or (
        f"https://www.tcgplayer.com/product/{r['tcgplayer_id']}" if r.get("tcgplayer_id") else None
    )
    name = (
        f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(r.get("name"))}</a>'
        if url
        else _esc(r.get("name"))
    )
    img = (
        f'<img src="{_esc(r.get("image_url"))}" alt="" loading="lazy" decoding="async">'
        if r.get("image_url")
        else '<img alt="">'
    )
    badges = "".join(f'<span class="badge {s}">{s}</span>' for s in r.get("signals", []))
    mp = r.get("market_price")
    printing = f' · {_esc(r.get("printing"))}' if r.get("printing") not in (None, "Normal") else ""
    meta = " · ".join(
        x for x in [_esc(r.get("set_name")), _esc(r.get("number")), _esc(r.get("rarity"))] if x
    )
    return f"""<tr>
  <td class="rank">{i + 1}</td>
  <td><div class="who">{img}<div><div class="nm">{name}</div>
    <div class="meta">{meta}{printing}</div></div></div></td>
  <td class="num">{'—' if mp is None else f'${mp:.2f}'}</td>
  <td class="num">{pct(r.get('change_24h'))}</td>
  <td class="num">{pct(r.get('change_7d'))}</td>
  <td class="num">{pct(r.get('change_30d'))}</td>
  <td>{_spark_svg(r.get('series'))}</td>
  <td class="num col-listings">{r.get('total_listings') if r.get('total_listings') is not None else '—'}</td>
  <td><div class="badges">{badges}</div></td>
  <td class="num"><div class="score">{r.get('score', 0):.0f}</div></td>
  <td class="why">{_esc(r.get('why'))}</td>
</tr>"""


def write(html: str, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p
