"""Render the hold screen as one self-contained HTML file.

One question, asked plainly: which cards already have value, are climbing
steadily, and can be sold again? Everything on the page serves that. The
flip-oriented machinery (24h spikes, listing undercuts as a headline) is gone --
an undercut now appears only as *entry quality* on a card that already earned
its place, and a 24h move is context, not a signal.

Everything (CSS, JS, data) is inlined. Card images are the only remote asset.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .invest import CHECKLIST, thesis, watch_for

# Palette: validated default categorical slots 1-3, both modes.
# The five score components use one hue (sequential blue) because they are five
# readings of the same thing, not five different things.
CSS = """
/* ---------------------------------------------------------------------------
   Styled to match gundeck.ai. Palette, type and component language lifted from
   the live site (2026-08-10): oklch tokens read straight off :root, TRT Terminal
   Mono with a JetBrains Mono fallback, 2px radius, uppercase letter-spaced
   labels, and the corner-bracket panel frame.

   Dark only, like gundeck.ai -- there is no light mode to match.

   Accessibility note: the brand's up-green and down-red sit at CVD deltaE 6.8
   (deutan), inside the band that requires secondary encoding. Every delta on
   this page therefore carries an explicit +/- sign, so direction is never
   communicated by colour alone.
--------------------------------------------------------------------------- */
*,*::before,*::after{box-sizing:border-box}
.viz-root{
  color-scheme:dark;
  --bg:oklch(6.5% .008 220);
  --surface:oklch(9% .01 220);
  --surface-2:oklch(10% .012 220);
  --muted-bg:oklch(11% .01 220);
  --raised:oklch(12% .012 220);
  --text:oklch(94% .04 85);
  --text-secondary:oklch(78% .05 220);
  --text-muted:oklch(62% .04 220);
  --accent:oklch(78% .18 65);
  --accent-dim:oklch(55% .14 65);
  --accent-wash:oklch(12% .04 65);
  --border:oklch(20% .04 65);
  --border-soft:oklch(16% .02 220);
  --up:oklch(68% .18 145);
  --down:oklch(60% .22 25);
  --warn:oklch(82% .14 90);
  --cyan:oklch(72% .16 200);
  --bar:oklch(78% .18 65);
  --bar-soft:oklch(16% .05 65);
  --r:2px;
  --mono:"TRT Terminal Mono","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:14px/1.55 var(--mono);
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1400px;margin:0 auto;padding:26px 22px 72px}

/* --- the gundeck panel: hairline box + amber corner brackets, TL and BR --- */
.panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  position:relative}
.panel::before,.panel::after{content:"";position:absolute;width:14px;height:14px;
  border-color:var(--accent);border-style:solid;pointer-events:none}
.panel::before{top:-1px;left:-1px;border-width:2px 0 0 2px}
.panel::after{bottom:-1px;right:-1px;border-width:0 2px 2px 0}

header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;
  flex-wrap:wrap;margin-bottom:6px}
h1{font-size:19px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;
  color:var(--accent);margin:0}
.mission{color:var(--text-secondary);font-size:13px;margin:8px 0 2px;max-width:78ch;
  line-height:1.65}
.stamp{color:var(--text-muted);font-size:11.5px;margin:7px 0 20px;text-transform:uppercase;
  letter-spacing:.09em}
.hbtns{display:flex;gap:8px;flex:none}
button.ghost{background:oklch(7% .01 220 / .6);border:1px solid var(--border);
  border-radius:var(--r);color:var(--accent-dim);padding:6px 12px;cursor:pointer;
  font:inherit;font-size:11px;text-transform:uppercase;letter-spacing:.1em}
button.ghost:hover{color:var(--accent);border-color:var(--accent-dim)}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(172px,1fr));gap:14px;
  margin-bottom:18px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  padding:15px 16px 16px;position:relative;text-align:center}
.tile::before,.tile::after{content:"";position:absolute;width:12px;height:12px;
  border-color:var(--accent);border-style:solid}
.tile::before{top:-1px;left:-1px;border-width:2px 0 0 2px}
.tile::after{bottom:-1px;right:-1px;border-width:0 2px 2px 0}
.tile .label{font-size:10.5px;text-transform:uppercase;letter-spacing:.14em;
  color:var(--text-muted)}
.tile .value{font-size:29px;font-weight:700;margin-top:7px;line-height:1.05;
  color:var(--accent);letter-spacing:.02em}
.tile:nth-child(3) .value{color:var(--up)}
.tile:nth-child(4) .value{color:var(--down)}
.tile:nth-child(6) .value{color:var(--cyan)}
.tile .foot{font-size:10.5px;color:var(--text-muted);margin-top:6px;text-transform:uppercase;
  letter-spacing:.08em;line-height:1.5}

.bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:13px 16px;
  margin-bottom:14px}
.flabel{font-size:10.5px;text-transform:uppercase;letter-spacing:.14em;
  color:var(--text-muted);white-space:nowrap}
input[type=search],select,input[type=number]{background:var(--muted-bg);color:var(--text);
  border:1px solid var(--border);border-radius:var(--r);padding:7px 10px;font:inherit;
  font-size:12px}
input::placeholder{color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;
  font-size:11px}
input:focus,select:focus{outline:none;border-color:var(--accent-dim)}
input[type=search]{min-width:220px}
input[type=number]{width:106px}
.chip{border:1px solid var(--border);background:oklch(7% .01 220 / .6);border-radius:var(--r);
  padding:6px 13px;font-size:11px;cursor:pointer;color:var(--text-muted);user-select:none;
  text-transform:uppercase;letter-spacing:.1em}
.chip:hover{color:var(--accent-dim);border-color:var(--accent-dim)}
.chip[aria-pressed="true"]{color:var(--accent);border-color:var(--accent);
  background:var(--accent-wash)}
.count{color:var(--text-muted);font-size:11px;margin-left:auto;white-space:nowrap;
  text-transform:uppercase;letter-spacing:.1em}
.plan-sum{font-size:12px;color:var(--text-secondary);letter-spacing:.04em}
.plan-sum b{color:var(--accent);font-weight:700}
.plan-sum .conc{color:var(--warn)}
.disc{font-size:10.5px;color:var(--text-muted);margin-left:auto;max-width:46ch;
  text-align:right;line-height:1.6}

h2.sect{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.16em;
  color:var(--accent);margin:26px 0 12px;display:flex;align-items:center;gap:12px}
h2.sect::before{content:"";display:inline-block;width:0;height:0;flex:none;
  border-left:6px solid var(--accent);border-top:5px solid transparent;
  border-bottom:5px solid transparent}
h2.sect .sub{font-size:10px;letter-spacing:.1em;color:var(--text-muted);font-weight:400;
  border:1px solid var(--border);border-radius:var(--r);padding:4px 9px}
h2.sect::after{content:"";flex:1;border-top:1px dashed var(--border)}
.tablewrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--border-soft);
  vertical-align:middle}
thead th{font-size:10px;text-transform:uppercase;letter-spacing:.14em;color:var(--text-muted);
  font-weight:700;white-space:nowrap;position:sticky;top:0;background:var(--surface);z-index:2;
  border-bottom:1px solid var(--border)}
thead th[data-sort]{cursor:pointer}
thead th[data-sort]:hover{color:var(--accent-dim)}
thead th[aria-sort=descending],thead th[aria-sort=ascending]{color:var(--accent)}
thead th[aria-sort=descending]::after,thead th[aria-sort=ascending]::after{
  content:"";display:inline-block;width:0;height:0;margin-left:6px;vertical-align:2px;
  border-left:4px solid transparent;border-right:4px solid transparent}
thead th[aria-sort=descending]::after{border-top:5px solid var(--accent)}
thead th[aria-sort=ascending]::after{border-bottom:5px solid var(--accent)}
tbody tr.row{cursor:pointer}
tbody tr.row:hover{background:var(--muted-bg)}
tbody tr.row .rank::before{content:"";display:inline-block;width:0;height:0;margin-right:9px;
  border-left:5px solid var(--accent-dim);border-top:4px solid transparent;
  border-bottom:4px solid transparent;transition:transform .15s;transform-origin:40% 50%}
tbody tr.row[aria-expanded="true"] .rank::before{transform:rotate(90deg);
  border-left-color:var(--accent)}
tr.buy td:first-child{box-shadow:inset 3px 0 0 var(--accent)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rank{color:var(--text-muted);font-variant-numeric:tabular-nums;width:62px;
  font-size:12px;white-space:nowrap}
.who{display:flex;gap:11px;align-items:center;min-width:250px}
.who img{width:30px;height:42px;object-fit:cover;border-radius:var(--r);
  background:var(--raised);flex:none;border:1px solid var(--border-soft)}
.who .nm{font-weight:700;line-height:1.35;letter-spacing:.02em}
.who a{color:var(--text);text-decoration:none}
.who a:hover{color:var(--accent)}
.who .meta{color:var(--text-muted);font-size:10.5px;margin-top:2px;text-transform:uppercase;
  letter-spacing:.08em}
.up{color:var(--up);font-weight:700}
.down{color:var(--down);font-weight:700}
.flat{color:var(--text-muted)}
/* Market heat: attention data from outside the price feed. Greyed when stale --
   a two-month-old search reading describes a market that has moved on. */
.heat{margin:14px 0}
.heat.stale{opacity:.55}
.heat .hgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px;padding:4px 2px}
.heat h4{margin:0 0 8px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.heat .big{font-size:26px;font-weight:700;line-height:1.1}
.heat .sub2{color:var(--text-muted);font-size:11px;margin:4px 0 0;line-height:1.5}
.heat .kv{display:flex;justify-content:space-between;gap:10px;padding:3px 0;
  border-bottom:1px dotted var(--border);font-size:12px}
.heat .kv:last-child{border-bottom:0}
.heat .verdict{padding:10px 12px;margin:2px 2px 8px;border-left:2px solid var(--accent);
  background:var(--surface);font-size:13px;line-height:1.65}
.heat .cat{display:flex;gap:8px;font-size:11px;padding:3px 0;color:var(--text-muted)}
.heat .cat b{color:var(--text);font-weight:400}
.heat table.mom{width:100%;border-collapse:collapse;font-size:12px;margin-top:4px}
.heat table.mom th{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);
  text-align:left;padding:4px 6px;border-bottom:1px solid var(--border);font-weight:400}
.heat table.mom th.num,.heat table.mom td.num{text-align:right}
.heat table.mom td{padding:6px;border-bottom:1px dotted var(--border);vertical-align:top}
.heat .chip-sm{font-size:9px;letter-spacing:.08em;padding:0 4px;border:1px solid var(--border);border-radius:2px;color:var(--text-muted)}
.heat .tag{font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:1px 5px;
  border:1px solid var(--border);border-radius:2px;white-space:nowrap}
.heat .stalebar{background:var(--surface);border-left:2px solid var(--down);
  padding:8px 12px;margin:2px;font-size:12px;color:var(--down)}
.spark{display:block;width:100%;height:36px;margin:6px 0 2px}
/* Listed above what copies have been selling for / listed below it. */
.hot{color:var(--down);font-weight:700}
.cool{color:var(--up);font-weight:700}
.warnc{color:var(--warn);font-weight:700}
.spark{display:block}
.score{font-variant-numeric:tabular-nums;font-weight:700;font-size:16px;color:var(--accent)}
.scorebar{height:2px;background:var(--accent);margin-top:4px}
.pill{display:inline-block;font-size:10px;padding:3px 8px;border-radius:var(--r);
  border:1px solid var(--up);color:var(--up);background:oklch(14% .05 145);font-weight:700;
  text-transform:uppercase;letter-spacing:.08em}
.pill.none{border-color:var(--border);color:var(--text-muted);background:transparent}
.rar{display:inline-block;font-size:9.5px;padding:2px 6px;border-radius:var(--r);
  border:1px solid var(--border);color:var(--accent-dim);margin-left:7px;
  text-transform:uppercase;letter-spacing:.1em;vertical-align:1px}
.empty{padding:40px;text-align:center;color:var(--text-muted);text-transform:uppercase;
  letter-spacing:.12em;font-size:12px}
.more{display:flex;gap:10px;align-items:center;justify-content:center;padding:16px}

tr.detail > td{padding:0;background:var(--surface-2);
  border-top:1px dashed var(--border);border-bottom:1px solid var(--border)}
.det{display:grid;grid-template-columns:repeat(auto-fit,minmax(262px,1fr));gap:20px 28px;
  padding:18px 20px 20px;position:sticky;left:0;width:min(100%,calc(100vw - 60px))}
.det h5{font-size:10px;text-transform:uppercase;letter-spacing:.16em;color:var(--accent);
  margin:0 0 10px;padding-bottom:7px;border-bottom:1px dashed var(--border)}
.det p{margin:0 0 10px;font-size:12.5px;line-height:1.65;color:var(--text-secondary)}
.det ul{margin:0;padding-left:16px;font-size:11.5px;line-height:1.6;color:var(--text-muted)}
.det li{margin-bottom:7px}
.det li b{color:var(--text-secondary)}
.det .big{font-size:20px;font-weight:700;line-height:1.25;margin-bottom:4px;color:var(--accent)}
.det .sub2{font-size:11.5px;color:var(--text-muted);line-height:1.6}
.det .kv{display:flex;justify-content:space-between;gap:12px;font-size:11.5px;padding:5px 0;
  border-bottom:1px solid var(--border-soft)}
.det .kv:last-child{border-bottom:0}
.det .kv span:last-child{font-variant-numeric:tabular-nums;color:var(--text)}
.det .kv span:first-child{color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em}
.det .warn{color:var(--warn);font-size:12px}
.det .cta{display:inline-block;margin-top:10px;font-size:11px;font-weight:700;
  color:var(--accent);text-decoration:none;text-transform:uppercase;letter-spacing:.1em;
  border:1px solid var(--border);border-radius:var(--r);padding:6px 11px}
.det .cta:hover{border-color:var(--accent-dim);background:var(--accent-wash)}
.crow{display:grid;grid-template-columns:76px 1fr 30px;gap:9px;align-items:center;
  margin-bottom:6px}
.crow .cl{font-size:10px;color:var(--text-muted);text-align:right;text-transform:uppercase;
  letter-spacing:.09em}
.crow .ct{height:10px;background:var(--bar-soft)}
.crow .ct i{display:block;height:100%;background:var(--bar)}
.crow .cv{font-size:11px;color:var(--text-secondary);font-variant-numeric:tabular-nums}

details.gloss,details.rej{margin-bottom:16px}
details summary{cursor:pointer;padding:13px 16px;font-size:11.5px;font-weight:700;
  list-style:none;display:flex;align-items:center;gap:9px;text-transform:uppercase;
  letter-spacing:.14em;color:var(--accent)}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"";display:inline-block;width:0;height:0;
  border-left:5px solid var(--accent-dim);border-top:4px solid transparent;
  border-bottom:4px solid transparent;transition:transform .15s}
details[open] summary::before{transform:rotate(90deg)}
details[open] summary{border-bottom:1px dashed var(--border)}
details summary .sc{color:var(--text-muted);font-weight:400;margin-left:auto;font-size:10.5px;
  letter-spacing:.08em}
.gbody{padding:16px 16px 18px;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px 30px}
.gbody dl{margin:0}
.gbody dt{font-size:11.5px;font-weight:700;margin-top:11px;color:var(--text-secondary)}
.gbody dt:first-child{margin-top:0}
.gbody dd{margin:3px 0 0;font-size:11.5px;color:var(--text-muted);line-height:1.6}
.gbody h4{font-size:10px;text-transform:uppercase;letter-spacing:.16em;color:var(--accent);
  margin:0 0 9px;padding-bottom:7px;border-bottom:1px dashed var(--border)}
.rejbody{padding:0 0 4px}
.rejbody table{font-size:11.5px}
.rejbody td,.rejbody th{padding:8px 12px}
.rejbody td:last-child{color:var(--down)}

footer{margin-top:36px;color:var(--text-muted);font-size:11px;line-height:1.8;
  border-top:1px dashed var(--border);padding-top:18px}
footer code{background:var(--muted-bg);border:1px solid var(--border);padding:2px 6px;
  border-radius:var(--r);color:var(--accent-dim)}
#tip{position:fixed;z-index:50;max-width:320px;background:var(--surface-2);
  border:1px solid var(--accent-dim);color:var(--text-secondary);padding:10px 12px;
  border-radius:var(--r);font-size:11.5px;line-height:1.6;pointer-events:none;opacity:0;
  transition:opacity .12s;box-shadow:0 8px 26px rgba(0,0,0,.6)}
#tip.on{opacity:1}
#tip b{color:var(--accent)}
#tip code{color:var(--accent-dim)}
[data-tip]{cursor:help}
.info{display:inline-flex;align-items:center;justify-content:center;width:12px;height:12px;
  border:1px solid currentColor;border-radius:50%;font-size:8px;line-height:1;margin-left:5px;
  opacity:.6;vertical-align:1px;cursor:help;font-weight:700}
.info:hover{opacity:1}
@media (max-width:1080px){.col-hide{display:none}}
@media (max-width:820px){.wrap{padding:18px 12px 48px}}
"""

JS = r"""
const DATA = JSON.parse(document.getElementById('radar-data').textContent);
const state = {q:'', set:'', rarity:'', minPrice:null, maxPrice:null, minScore:null,
               minSales:null, sort:'score', dir:-1, limit:40, budget:null,
               inBudgetOnly:false, open:new Set()};

const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => v==null ? '—'
  : '$' + (v>=1000 ? v.toLocaleString(undefined,{maximumFractionDigits:0}) : v.toFixed(2));
const pct = v => {
  if (v==null) return '<span class="flat">—</span>';
  const cls = v > 0.05 ? 'up' : (v < -0.05 ? 'down' : 'flat');
  return `<span class="${cls}">${v>0?'+':''}${v.toFixed(0)}%</span>`;
};

function sparkline(series){
  if (!series || series.length < 2) return '<span class="flat">—</span>';
  const w=90,h=26,p=3;
  const ys = series.map(d=>d[1]);
  const lo = Math.min(...ys), hi = Math.max(...ys);
  const span = (hi-lo) || (hi || 1);
  const pts = series.map((d,i)=>{
    const x = p + i*(w-2*p)/(series.length-1);
    const y = h-p - ((d[1]-lo)/span)*(h-2*p);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const lx = w-p, ly = h-p - ((ys[ys.length-1]-lo)/span)*(h-2*p);
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img"
    aria-label="90-day price, ${ys[ys.length-1]>=ys[0]?'up':'down'} to $${ys[ys.length-1].toFixed(2)}">
    <polyline points="${pts}" fill="none" stroke="var(--series-1)" stroke-width="2"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="2.5" fill="var(--series-1)"
      stroke="var(--surface-1)" stroke-width="2"/></svg>`;
}

// ---------------------------------------------------------------------------
// Position sizing -- JS twin of radar/plan.py::allocate(). Keep in step.
// ---------------------------------------------------------------------------
function allocate(rows, budget){
  const cfg = DATA.plan || {};
  const maxPct = cfg.max_position_pct ?? 0.25;
  let remaining = budget;
  const out = new Map();
  for (const r of rows){
    const key = r.card_id + '|' + r.printing;
    const unit = (typeof r.floor_low === 'number' && r.floor_low > 0) ? r.floor_low : null;
    const copies = (typeof r.copies === 'number') ? r.copies : null;
    const plan = {unit, qty:0, cost:0, affordable:false, clears:false, reason:'', pct:0};
    if (unit == null){
      plan.reason = 'No live entry price yet — run <code>radar invest</code>.';
      out.set(key, plan); continue;
    }
    const cap = budget * maxPct;
    const byCap = Math.floor(cap / unit);
    const byRem = Math.floor(remaining / unit);
    const bySupply = copies == null ? byCap : copies;
    const qty = Math.max(0, Math.min(byCap, byRem, bySupply));
    if (qty < 1){
      plan.reason = byCap < 1
        ? `One copy is ${(unit/budget*100).toFixed(0)}% of the budget, over the ${(maxPct*100).toFixed(0)}% per-position cap.`
        : `$${remaining.toFixed(2)} left — one copy costs $${unit.toFixed(2)}.`;
      out.set(key, plan); continue;
    }
    const cost = qty * unit;
    remaining -= cost;
    Object.assign(plan, {qty, cost, affordable:true, clears: copies!=null && qty>=copies,
      pct: cost/budget*100, remaining,
      limitedBy: (bySupply<=byCap && bySupply<=byRem) ? 'the number of copies listed'
               : (byRem<byCap ? "what's left of the budget" : 'the per-position cap')});
    out.set(key, plan);
  }
  return out;
}

const COMPONENTS = [
  ['value','Value','Log-scaled price. $10 scores 0, $200 scores 100.'],
  ['liquidity','Liquidity','Average daily sales and the share of days that saw any sale.'],
  ['trend','Trend','Share of weeks closing above the previous week, plus the 90-day change.'],
  ['stability','Stability','Daily volatility and how far it sits below its 90-day high.'],
  ['scarcity','Scarcity','Rarity tier and how many copies are listed.'],
];

function componentBars(c){
  if (!c) return '';
  return COMPONENTS.map(([k,label,tip])=>{
    const v = c[k] ?? 0;
    return `<div class="crow" data-tip="${esc(tip)}">
      <span class="cl">${label}</span>
      <span class="ct"><i style="width:${Math.max(2,v)}%"></i></span>
      <span class="cv">${v.toFixed(0)}</span></div>`;
  }).join('');
}

function detailHTML(r, plan){
  const url = r.tcgplayer_url || (r.tcgplayer_id ? 'https://www.tcgplayer.com/product/'+r.tcgplayer_id : null);
  let pos;
  if (!state.budget){
    pos = '<p class="sub2">Enter a budget above and this becomes a number of copies and a cost.</p>';
  } else if (plan && plan.affordable){
    pos = `<div class="big">${plan.qty} ${plan.qty===1?'copy':'copies'} · $${plan.cost.toFixed(2)}</div>
      <div class="sub2">at $${plan.unit.toFixed(2)} shipped each · ${plan.pct.toFixed(0)}% of your budget</div>
      <div class="kv"><span>Limited by</span><span>${plan.limitedBy}</span></div>
      <div class="kv"><span>Copies listed</span><span>${r.copies ?? '—'}</span></div>
      <div class="kv"><span>Budget left after</span><span>$${(plan.remaining??0).toFixed(2)}</span></div>
      ${r.avg_daily_sales ? `<div class="kv"><span>Days to sell that many</span><span>~${Math.ceil(plan.qty/r.avg_daily_sales)}</span></div>` : ''}`;
  } else {
    pos = `<div class="big">No position</div><p class="sub2">${plan ? plan.reason : 'No live entry price.'}</p>`;
  }

  const entry = (r.floor_low != null)
    ? `<div class="kv"><span>Cheapest listing now</span><span>$${r.floor_low.toFixed(2)}</span></div>
       <div class="kv"><span>Median listing</span><span>${r.shelf_med!=null?'$'+r.shelf_med.toFixed(2):'—'}</span></div>
       <div class="kv"><span>Entry vs the shelf</span><span>${r.entry_vs_shelf_pct==null?'—'
         : (r.entry_vs_shelf_pct>0
            ? Math.abs(r.entry_vs_shelf_pct).toFixed(0)+'% below median'
            : Math.abs(r.entry_vs_shelf_pct).toFixed(0)+'% above median')}</span></div>
       <div class="kv"><span>Copies at Near Mint</span><span>${r.copies ?? '—'}</span></div>`
    : '<p class="sub2">No live entry price pulled for this card yet.</p>';

  // Where copies have actually been changing hands, and how far the asking
  // price has run ahead of that. Descriptive, not a forecast -- see the tooltip.
  const settled = (r.settled_price != null)
    ? `<div class="kv"><span>Trading at</span><span>$${r.settled_price.toFixed(2)}</span></div>
       <div class="kv"><span>Listed price is</span><span class="${
          r.ask_premium_pct==null?'':(r.ask_premium_pct>5?'hot':(r.ask_premium_pct<-2?'cool':''))}">${
          r.ask_premium_pct==null ? '—'
          : (r.ask_premium_pct>=0 ? '+'+r.ask_premium_pct.toFixed(1)+'% above' 
                                  : Math.abs(r.ask_premium_pct).toFixed(1)+'% below')}</span></div>
       <div class="kv"><span>Based on</span><span>${r.settled_volume ?? '—'} sales / ${r.settled_days} days</span></div>
       <p class="sub2">${
          r.ask_premium_pct==null ? ''
          : r.ask_premium_pct>5
            ? 'Sellers are asking more than buyers have been paying. Cards in this state gave back a median 4% over the next 30 days.'
            : r.ask_premium_pct<-2
              ? 'Copies have been selling above the listed price. Cards in this state gained a median 10% over the next 30 days.'
              : 'Asking price and sale price agree. Nothing to read into.'}</p>`
    : '<p class="sub2">Under three days of recorded sales in the last fortnight — not enough to say what it trades at.</p>';

  return `<tr class="detail"><td colspan="14"><div class="det">
    <div>
      <h5>The case</h5>
      <p>${esc(r.thesis||'')}</p>
      <p class="warn">${esc(r.watch||'')}</p>
      ${url?`<a class="cta" href="${esc(url)}" target="_blank" rel="noopener">Open on TCGplayer &rarr;</a>`:''}
    </div>
    <div>
      <h5>Score, broken down</h5>
      ${componentBars(r.components)}
      <div class="kv" style="margin-top:8px"><span>Weighted total</span><span>${r.invest_score.toFixed(0)} / 100</span></div>
      <div class="kv"><span>3d / 7d / 30d / 90d</span><span>${
        [r.change_3d,r.change_7d,r.change_30d,r.change_90d]
          .map(v=>v==null?'—':(v>0?'+':'')+v.toFixed(0)+'%').join(' / ')}</span></div>
      <div class="kv"><span>Weeks closing up</span><span>${r.consistency_pct ?? '—'}%</span></div>
      <div class="kv"><span>Daily volatility</span><span>${r.volatility_pct ?? '—'}%</span></div>
      <div class="kv"><span>Off its 90-day high</span><span>${r.drawdown_pct ?? '—'}%</span></div>
    </div>
    <div>
      <h5 data-tip="Volume-weighted average of what copies actually SOLD for over the last 14 days, next to what they are listed at. Listings are an asking price; this is a paid price. Measured across 1,201 observations of 290 Gundam cards: the fifth of cards asking ~7% BELOW recent sales returned a median +10.3% over the next 30 days, the fifth asking ~9% above returned -4.0% (rho = -0.31, stable across both halves of the window). It is a description of where the card trades, not a forecast of where it will go.">What it actually trades at<span class="info">?</span></h5>
      ${settled}
      <h5 style="margin-top:14px">Entry today</h5>
      ${entry}
      <h5 style="margin-top:14px">Position at your budget</h5>
      ${pos}
    </div>
    <div>
      <h5>Before you buy</h5>
      <ul>${DATA.checklist.map(x=>`<li>${x}</li>`).join('')}</ul>
    </div>
  </div></td></tr>`;
}

function rowHTML(r, i, plan){
  const key = r.card_id + '|' + r.printing;
  const openNow = state.open.has(key);
  const buy = plan && plan.affordable;
  const url = r.tcgplayer_url || (r.tcgplayer_id ? 'https://www.tcgplayer.com/product/'+r.tcgplayer_id : null);
  const nm = url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(r.name)}</a>` : esc(r.name);
  const img = r.image_url ? `<img src="${esc(r.image_url)}" alt="" loading="lazy" decoding="async">` : '<img alt="">';
  const meta = [r.set_name, r.number, r.printing!=='Normal'?r.printing:null].filter(Boolean).map(esc).join(' · ');
  const sales = r.avg_daily_sales;
  const salesCls = sales==null ? 'flat' : (sales < 1 ? 'warnc' : '');
  return `<tr class="row${buy?' buy':''}" data-key="${esc(key)}" aria-expanded="${openNow}">
    <td class="rank">${i+1}</td>
    <td><div class="who">${img}<div><div class="nm">${nm}<span class="rar">${esc(r.rarity||'—')}</span></div>
      <div class="meta">${meta}</div></div></div></td>
    <td class="num">${money(r.market_price)}</td>
    <td class="num">${r.ask_premium_pct==null ? '<span class="flat">—</span>'
      : `<span class="${r.ask_premium_pct>5?'hot':(r.ask_premium_pct<-2?'cool':'')}">${
          (r.ask_premium_pct>0?'+':'')+r.ask_premium_pct.toFixed(0)}%</span>`}</td>
    <td class="num col-hide">${pct(r.change_3d)}</td>
    <td class="num">${pct(r.change_7d)}</td>
    <td class="num col-hide">${pct(r.change_30d)}</td>
    <td class="num">${pct(r.change_90d)}</td>
    <td>${sparkline(r.series)}</td>
    <td class="num">${r.consistency_pct==null?'<span class="flat">—</span>':r.consistency_pct+'%'}</td>
    <td class="num"><span class="${salesCls}">${sales==null?'—':sales.toFixed(1)}</span></td>
    <td class="num col-hide">${r.floor_low==null?'<span class="flat">—</span>':money(r.floor_low)}</td>
    <td class="num"><div class="score">${r.invest_score.toFixed(0)}</div>
      <div class="scorebar" style="width:${Math.max(4, r.invest_score)}%"></div></td>
    <td class="num">${buy?`<span class="pill">${plan.qty} · $${plan.cost.toFixed(0)}</span>`:'<span class="pill none">—</span>'}</td>
  </tr>` + (openNow ? detailHTML(r, plan) : '');
}

const SORTERS = {
  score:r=>r.invest_score, price:r=>r.market_price ?? -1,
  prem:r=>r.ask_premium_pct ?? 1e9, c3:r=>r.change_3d ?? -1e9, c7:r=>r.change_7d ?? -1e9, c30:r=>r.change_30d ?? -1e9,
  c90:r=>r.change_90d ?? -1e9, cons:r=>r.consistency_pct ?? -1, sales:r=>r.avg_daily_sales ?? -1,
  entry:r=>r.floor_low ?? -1, name:r=>(r.name||'').toLowerCase(),
};

function filtered(){
  const q = state.q.trim().toLowerCase();
  return DATA.rows.filter(r=>{
    if (q && !((r.name||'').toLowerCase().includes(q) || (r.set_name||'').toLowerCase().includes(q)
               || (r.number||'').toLowerCase().includes(q))) return false;
    if (state.set && r.set_name !== state.set) return false;
    if (state.rarity && (r.rarity||'—') !== state.rarity) return false;
    if (state.minPrice != null && !(r.market_price >= state.minPrice)) return false;
    if (state.maxPrice != null && !(r.market_price <= state.maxPrice)) return false;
    if (state.minScore != null && !(r.invest_score >= state.minScore)) return false;
    if (state.minSales != null && !((r.avg_daily_sales ?? 0) >= state.minSales)) return false;
    return true;
  });
}

function renderPlanSummary(plans, rows){
  const el = document.getElementById('plan-sum');
  if (!state.budget){ el.innerHTML = 'Enter a budget to size positions down the ranking.'; return; }
  let n=0, spend=0;
  const bySet = {};
  for (const r of rows){
    const p = plans.get(r.card_id+'|'+r.printing);
    if (!p || !p.affordable) continue;
    n++; spend += p.cost;
    const k = r.set_name || '—';
    bySet[k] = (bySet[k]||0) + p.cost;
  }
  if (!n){
    el.innerHTML = `Nothing here fits — one copy of everything costs more than the ${((DATA.plan?.max_position_pct??0.25)*100).toFixed(0)}% per-position cap.`;
    return;
  }
  let html = `<b>${n}</b> ${n===1?'card':'cards'} · <b>$${spend.toFixed(2)}</b> of $${state.budget.toFixed(2)} placed · $${(state.budget-spend).toFixed(2)} left`;
  // Ranking by score alone can quietly put the whole budget in one set.
  const top = Object.entries(bySet).sort((a,b)=>b[1]-a[1])[0];
  if (top && spend > 0){
    const share = top[1]/spend*100;
    if (share >= 50) html += ` · <span class="conc">${share.toFixed(0)}% of it in ${esc(top[0])}</span>`;
  }
  el.innerHTML = html;
}

function apply(){
  let rows = filtered();
  const key = SORTERS[state.sort] || SORTERS.score;
  rows.sort((a,b)=>{ const av=key(a), bv=key(b); return av===bv?0:(av>bv?1:-1)*state.dir; });

  const plans = state.budget ? allocate(rows, state.budget) : new Map();
  if (state.budget && state.inBudgetOnly)
    rows = rows.filter(r => (plans.get(r.card_id+'|'+r.printing)||{}).affordable);
  renderPlanSummary(plans, rows);

  const shown = rows.slice(0, state.limit);
  document.getElementById('tbody').innerHTML = shown.length
    ? shown.map((r,i)=>rowHTML(r, i, plans.get(r.card_id+'|'+r.printing))).join('')
    : '<tr><td colspan="14" class="empty">Nothing matches those filters.</td></tr>';
  document.getElementById('count').textContent =
    `${shown.length?'1–'+shown.length:'0'} of ${rows.length} candidates`;

  const more = document.getElementById('more');
  if (rows.length > shown.length){ more.style.display='flex';
    document.getElementById('more-all').textContent = `Show all ${rows.length}`; }
  else more.style.display='none';

  document.querySelectorAll('thead th[data-sort]').forEach(th=>
    th.setAttribute('aria-sort', th.dataset.sort===state.sort
      ? (state.dir===-1?'descending':'ascending') : 'none'));
  window.__view = rows;
}

function reset(){
  Object.assign(state, {q:'', set:'', rarity:'', minPrice:null, maxPrice:null, minScore:null,
                        minSales:null, sort:'score', dir:-1, limit:40, inBudgetOnly:false});
  document.getElementById('q').value='';
  ['setfilter','rarityfilter'].forEach(id=>document.getElementById(id).value='');
  ['minprice','maxprice','minscore','minsales'].forEach(id=>{const e=document.getElementById(id); if(e) e.value='';});
  const ib=document.getElementById('inbudget'); if(ib) ib.checked=false;
  state.open.clear();
  apply();
}

function exportCSV(){
  const cols = ['invest_score','name','set_name','number','rarity','printing','market_price',
                'change_3d','change_7d','change_30d','change_90d','consistency_pct','volatility_pct','drawdown_pct',
                'avg_daily_sales','days_traded_pct','floor_low','shelf_med','copies','tcgplayer_url'];
  const e2 = v => { const s = v==null?'':String(v); return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s; };
  const body = [cols.join(',')].concat((window.__view||[]).map(r=>cols.map(c=>e2(r[c])).join(','))).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([body],{type:'text/csv'}));
  a.download = `gundam-hold-screen-${DATA.obs_date}.csv`;
  a.click(); URL.revokeObjectURL(a.href);
}

// tooltips
const tip = document.getElementById('tip');
let tipAnchor = null;
function showTip(el){
  const t = el.getAttribute('data-tip'); if (!t) return;
  tip.innerHTML = t; tip.classList.add('on');
  const r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
  let x = Math.max(8, Math.min(r.left + r.width/2 - w/2, window.innerWidth - w - 8));
  let y = r.top - h - 8; if (y < 8) y = r.bottom + 8;
  tip.style.left = x+'px'; tip.style.top = y+'px';
}
const hideTip = () => tip.classList.remove('on');
document.addEventListener('mouseover', e=>{
  const el = e.target.closest('[data-tip]');
  if (el === tipAnchor) return;
  tipAnchor = el; el ? showTip(el) : hideTip();
});
document.addEventListener('mouseout', e=>{
  const from = e.target.closest('[data-tip]'); if (!from) return;
  const to = e.relatedTarget && e.relatedTarget.closest ? e.relatedTarget.closest('[data-tip]') : null;
  if (to !== from){ tipAnchor = to; to ? showTip(to) : hideTip(); }
});
window.addEventListener('scroll', ()=>{ if (tipAnchor) showTip(tipAnchor); }, {passive:true});

// listeners
document.getElementById('q').addEventListener('input', e=>{state.q=e.target.value; state.limit=40; apply();});
[['setfilter','set'],['rarityfilter','rarity']].forEach(([id,k])=>
  document.getElementById(id).addEventListener('change', e=>{state[k]=e.target.value; state.limit=40; apply();}));
[['minprice','minPrice'],['maxprice','maxPrice'],['minscore','minScore'],['minsales','minSales']]
  .forEach(([id,k])=>{
    const el = document.getElementById(id); if (!el) return;
    el.addEventListener('input', e=>{
      const v = e.target.value===''?null:Number(e.target.value);
      state[k] = (v==null||Number.isNaN(v))?null:v; state.limit=40; apply();
    });
  });
document.getElementById('budget').addEventListener('input', e=>{
  const v = e.target.value===''?null:Number(e.target.value);
  state.budget = (v==null||Number.isNaN(v)||v<=0)?null:v; state.limit=40; apply();
});
const ib = document.getElementById('inbudget');
if (ib) ib.addEventListener('change', e=>{state.inBudgetOnly=e.target.checked; state.limit=40; apply();});
document.getElementById('tbody').addEventListener('click', e=>{
  if (e.target.closest('a')) return;
  const tr = e.target.closest('tr.row'); if (!tr) return;
  const k = tr.dataset.key;
  state.open.has(k) ? state.open.delete(k) : state.open.add(k);
  apply();
});
document.querySelectorAll('thead th[data-sort]').forEach(th=>th.addEventListener('click', ()=>{
  const k = th.dataset.sort;
  if (state.sort===k) state.dir*=-1; else {state.sort=k; state.dir = k==='name'?1:-1;}
  apply();
}));
document.getElementById('more-all').addEventListener('click', ()=>{state.limit=1e9; apply();});
document.getElementById('reset').addEventListener('click', reset);
document.getElementById('csv').addEventListener('click', exportCSV);
apply();
"""

GLOSSARY = """
<details class="panel gloss">
  <summary>How the screen works<span class="sc">what each number means, and what it can't tell you</span></summary>
  <div class="gbody">
    <div>
      <h4>The five components</h4>
      <dl>
        <dt>Value</dt><dd>Log-scaled price: $10 scores 0, $200 scores 100. A 50% move on a $3
          card isn't an investment outcome.</dd>
        <dt>Liquidity</dt><dd>Average daily sales and the share of days with any sale, from 90
          days of history. This is the component that decides whether you can get out.</dd>
        <dt>Trend</dt><dd>Share of weeks closing above the previous week, plus the 90-day change.
          Weekly closes, so one bad day doesn't read as a reversal.</dd>
        <dt>Stability</dt><dd>Daily volatility and distance below the 90-day high. A card that
          triples then halves is not a hold.</dd>
        <dt>Scarcity</dt><dd>Rarity tier and copies listed. The +/++ parallels are printed at a
          fraction of the base rate.</dd>
      </dl>
    </div>
    <div>
      <h4>Where the thresholds came from</h4>
      <dl>
        <dt>Measured, not chosen</dt><dd>Across 212 Gundam singles at $10+ that were up over 30
          days, each with 90 days of daily history.</dd>
        <dt>Weeks closing up</dt><dd>Q1 50% &middot; median 67% &middot; Q3 92%</dd>
        <dt>Daily volatility</dt><dd>Q1 1.1% &middot; median 1.9% &middot; Q3 3.1%</dd>
        <dt>Average daily sales</dt><dd>Q1 0.6 &middot; median 1.3 &middot; Q3 1.8</dd>
        <dt>Days with a sale</dt><dd>Q1 29% &middot; median 47% &middot; Q3 57%</dd>
        <dt>So</dt><dd>A high component score means "top quarter of this actual market", not
          "above a number that sounded good".</dd>
      </dl>
    </div>
    <div>
      <h4>What gets a card thrown out</h4>
      <dl>
        <dt>No sales in 90 days</dt><dd>No exit. The most expensive card in the pool &mdash;
          $4,798 &mdash; has not sold once.</dd>
        <dt>Down over 90 days</dt><dd>Not on the rise, whatever the 24-hour number says.</dd>
        <dt>Too erratic</dt><dd>Daily volatility above 8%. One rejected card was up 338% in 30
          days; that is a different game from holding.</dd>
        <dt>Too new</dt><dd>Under 45 days of history is not a trend, it's a release.</dd>
        <dt>All of them are listed</dt><dd>Open the rejected panel &mdash; nothing is silently
          dropped.</dd>
      </dl>
    </div>
    <div>
      <h4>Listed price vs. sold price</h4>
      <dl>
        <dt>Two different numbers</dt><dd><b>Price</b> is derived from listings &mdash; what
          sellers are asking. <b>Trading at</b> is the volume-weighted average of what copies
          actually changed hands for over the last 14 days.</dd>
        <dt>vs sold</dt><dd>The gap between them. Green means buyers have been paying more than
          the current ask. Red means sellers are ahead of the market.</dd>
        <dt>What it predicted</dt><dd>Over 1,201 observations of 290 Gundam cards: the fifth of
          cards asking ~7% <i>below</i> recent sales returned a median <b>+10.3%</b> over the
          next 30 days; the fifth asking ~9% above returned <b>&minus;4.0%</b>. Spearman
          &rho;&nbsp;=&nbsp;&minus;0.31, and it held in both halves of the window
          (&minus;0.32 / &minus;0.28) and after removing momentum (&minus;0.23).</dd>
        <dt>Why it isn't in the score</dt><dd>It's a timing read, not a quality read. A card can
          be worth owning and still be listed ahead of itself &mdash; that says wait, not no. It
          shows in the row and in the Watch line, and carries no weight in the ranking.</dd>
        <dt>Blank</dt><dd>Fewer than three days with a recorded sale in the fortnight. Two
          transactions averaged together is not a price.</dd>
      </dl>
    </div>
    <div>
      <h4>What this can't tell you</h4>
      <dl>
        <dt>Why</dt><dd>Nothing here knows about bans, reprints, rotation or tournament results.
          Those are what actually end a run.</dd>
        <dt>The future</dt><dd>Every number describes what a card has already done. None of it
          is a forecast, and a steady 90-day climb is not a promise of a 91st day.</dd>
        <dt>A settling price</dt><dd>Tested and not built. Across 47 run-ups of 25%+, the size of
          the run, the sales velocity and the speed all failed to predict what came next
          (|r|&nbsp;&lt;&nbsp;0.15), rarity buckets were too small to measure, and listing counts
          only exist as of today so testing them against the past would be cheating. There was
          also nothing to settle back to: after a 25% run the median card was up another 24%
          thirty days later. <b>Trading at</b> is what survived &mdash; a price copies are
          changing hands at, not a price they are heading to.</dd>
        <dt>Freshness</dt><dd>Market price and history come from a daily batch that runs up to
          two days behind. The entry price is live as of your last <code>radar invest</code>.</dd>
        <dt>Condition depth</dt><dd>Entry prices and copy counts are Near&nbsp;Mint only. Played
          copies are a separate market.</dd>
      </dl>
    </div>
  </div>
</details>
"""


def _esc(s: Any) -> str:
    return (
        str("" if s is None else s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _options(values: Sequence[str], label: str) -> str:
    opts = "".join(f'<option value="{_esc(v)}">{_esc(v)}</option>' for v in values)
    return f'<option value="">{_esc(label)}</option>{opts}'


def _row_payload(r: dict) -> dict:
    return {
        "card_id": r.get("card_id"),
        "name": r.get("name"),
        "set_name": r.get("set_name"),
        "number": r.get("number"),
        "rarity": r.get("rarity") or "—",
        "printing": r.get("printing") or "Normal",
        "image_url": r.get("image_url"),
        "tcgplayer_id": r.get("tcgplayer_id"),
        "tcgplayer_url": r.get("tcgplayer_url"),
        "market_price": r.get("market_price"),
        "change_3d": r.get("h3d"),
        "change_7d": r.get("h7d") if r.get("h7d") is not None else r.get("change_7d"),
        "change_30d": r.get("h30d") if r.get("h30d") is not None else r.get("change_30d"),
        "change_90d": r.get("change_90d"),
        "consistency_pct": r.get("consistency_pct"),
        "volatility_pct": r.get("volatility_pct"),
        "drawdown_pct": r.get("drawdown_pct"),
        "avg_daily_sales": r.get("avg_daily_sales"),
        "days_traded_pct": r.get("days_traded_pct"),
        "floor_low": r.get("floor_low"),
        "shelf_med": r.get("shelf_med"),
        "copies": r.get("copies"),
        "entry_vs_shelf_pct": r.get("entry_vs_shelf_pct"),
        "settled_price": r.get("settled_price"),
        "ask_premium_pct": r.get("ask_premium_pct"),
        "settled_days": r.get("settled_days"),
        "settled_volume": r.get("settled_volume"),
        "invest_score": r.get("invest_score", 0.0),
        "components": r.get("components"),
        "thesis": thesis(r),
        "watch": watch_for(r),
        "series": [[d, round(v, 2)] for d, v in (r.get("series") or [])],
    }


def _rejected_table(rejected: Sequence[dict]) -> str:
    if not rejected:
        return ""
    rows = "".join(
        f"""<tr>
      <td><strong>{_esc(r.get('name'))}</strong>
        <span class="rar">{_esc(r.get('rarity') or '—')}</span><br>
        <span class="flat">{_esc(r.get('set_name'))}</span></td>
      <td class="num">{'—' if r.get('market_price') is None else f"${r['market_price']:,.2f}"}</td>
      <td class="num">{'—' if r.get('change_30d') is None else f"{r['change_30d']:+.0f}%"}</td>
      <td class="num">{'—' if r.get('change_90d') is None else f"{r['change_90d']:+.0f}%"}</td>
      <td class="num">{'—' if r.get('avg_daily_sales') is None else f"{r['avg_daily_sales']:.1f}"}</td>
      <td class="num">{'—' if r.get('volatility_pct') is None else f"{r['volatility_pct']:.1f}%"}</td>
      <td>{_esc(r.get('disqualified'))}</td>
    </tr>"""
        for r in rejected
    )
    return f"""
<details class="panel rej">
  <summary>Screened out<span class="sc">{len(rejected)} cards, and exactly why</span></summary>
  <div class="rejbody tablewrap"><table><thead><tr>
    <th>Card</th><th class="num">Price</th><th class="num">30d</th><th class="num">90d</th>
    <th class="num">Sales/day</th><th class="num">Volatility</th><th>Reason</th>
  </tr></thead><tbody>{rows}</tbody></table></div>
</details>"""


TIPS = {
    "price": "Market price from the daily batch feed &mdash; up to two days behind. Used for the "
             "Value component and as a reference, not as the price you pay.",
    "prem": "How far the listed price has run ahead of what copies have actually been "
            "SOLD for in the last 14 days. Green means buyers have been paying more than "
            "the current ask; red means sellers are asking more than anyone has paid. "
            "Sorted low to high, the cheapest fifth returned a median +10.3% over the next "
            "30 days and the priciest fifth -4.0% (n=1,201, rho=-0.31). Blank means fewer "
            "than three days of recorded sales &mdash; too thin to average.",
    "c3": "Change over 3 days, computed from the stored daily series rather than taken from "
          "the API's 24-hour field &mdash; that field reads zero on 97% of Gundam products and "
          "misses most real moves. 3 days rather than 1 because a single day shows a move on "
          "only 37% of days, while 3 days catches 63% and the typical move is 3.5% instead of "
          "2.1%. Context only; it carries no weight in the score.",
    "c7": "Change over 7 days. Useful for spotting a candidate that has just turned, but the "
          "score is built on the 90-day picture, not this.",
    "c30": "Change over 30 days. Context only; the screen ranks on the 90-day picture.",
    "c90": "Change over 90 days. One of the two inputs to the Trend component.",
    "trend90": "90 days of daily market price. This is the shape you are buying into.",
    "cons": "Share of the last 13 weeks that closed above the week before. Median across the "
            "market is 67%; the top quarter is above 92%.",
    "sales": "Average copies sold per day over 90 days. Below 1.0 is shown in orange &mdash; at "
             "that rate, exiting a stack takes weeks. Median across the market is 1.3.",
    "entry": "Cheapest <b>English</b> Near Mint listing right now, shipping included &mdash; what "
             "you would actually pay. Matches the &quot;As low as&quot; figure on the TCGplayer "
             "page with the English filter on. Japanese and other printings trade in a separate "
             "market and are excluded everywhere on this page.",
    "score": "Weighted blend of value, liquidity, trend, stability and scarcity. Click any row "
             "for the breakdown. It ranks how well a card fits a buy-and-hold thesis; it is not "
             "a prediction.",
    "buy": "Copies and cost at your budget, sized down the ranking with a per-position cap.",
    "card": "Click the name for the TCGplayer page. Click anywhere else on the row to open the "
            "full case.",
}


def _spark(values: Sequence[float], *, w: int = 240, h: int = 36) -> str:
    """Inline sparkline. Same shape as the price sparkline so the two read alike."""
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < 3:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = w / (len(vals) - 1)
    pts = " ".join(
        f"{i * step:.1f},{h - 2 - (v - lo) / rng * (h - 4):.1f}" for i, v in enumerate(vals)
    )
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline points="{pts}" fill="none" stroke="var(--cyan)" stroke-width="1.5"/></svg>'
    )


def _heat_panel(h: dict[str, Any] | None) -> str:
    """Attention outside the price feed.

    Deliberately placed above the table rather than tucked in a footer: it is the
    number most likely to disagree with the ranking, and a disagreement you have
    to go looking for is one you will not find.
    """
    if not h:
        return ""

    lead = h.get("lead")
    stale = h.get("stale")
    banner = ""
    if stale:
        banner = (
            f'<div class="stalebar">Captured {_esc(h["captured_at"])} — '
            f'{h["age_days"]} days ago. Search interest moves weekly; treat this as history, '
            f'not as the current state. Run <code>radar heat --template</code> to refresh.</div>'
        )

    cols = []

    if lead:
        arrow = {"rising": "up", "falling": "down", "flat": "flat"}[h["direction"]]
        cls = {"up": "cool", "down": "hot", "flat": "flat"}[arrow]
        cols.append(f'''<div>
      <h4 data-tip="Google Trends relative search interest for &quot;{_esc(lead["name"])}&quot;, US, weekly. Scaled 0-100 against this term&#39;s own peak in the captured window &mdash; NOT comparable to the other series. Source: {_esc(h.get("trends_source") or "Google Trends")}.">Search interest<span class="info">?</span></h4>
      <div class="big">{lead["latest"]}<span class="sub2" style="font-size:12px"> / 100</span></div>
      {_spark(lead["series"])}
      <div class="kv"><span>Share of launch peak</span><span>{lead["pct_of_peak"]}%</span></div>
      <div class="kv"><span>Peak was</span><span>{_esc(lead["peak_date"])}</span></div>
      <div class="kv"><span>Off the low since</span><span>{lead["vs_trough_pct"]:+}%</span></div>
      <div class="kv"><span>Last 12 weeks</span><span class="{cls}">{lead["quarter_change_pct"]:+}%</span></div>
      <p class="sub2">{_esc(lead["name"])} · weekly, US</p>
    </div>''')

    yt = next((v for v in (h.get("youtube") or {}).values() if v.get("enough")), None)
    if yt:
        ycls = "cool" if (yt["quarter_change_pct"] or 0) >= 15 else (
            "hot" if (yt["quarter_change_pct"] or 0) <= -15 else "flat")
        cols.append(f'''<div>
      <h4 data-tip="The same Google Trends measurement restricted to YouTube search. Video interest is where a TCG&#39;s casual audience shows up first &mdash; openings, deck techs, pull videos &mdash; so it tends to lead web search on the way in and on the way out.">YouTube interest<span class="info">?</span></h4>
      <div class="big">{yt["latest"]}<span class="sub2" style="font-size:12px"> / 100</span></div>
      {_spark(yt["series"])}
      <div class="kv"><span>Share of launch peak</span><span>{yt["pct_of_peak"]}%</span></div>
      <div class="kv"><span>Last 12 weeks</span><span class="{ycls}">{yt["quarter_change_pct"]:+}%</span></div>
      <p class="sub2">{_esc(yt["name"])} · YouTube search, US</p>
    </div>''')

    sem = h.get("semrush") or []
    if sem:
        rows = "".join(
            f'<div class="kv"><span>{_esc(k["keyword"])}</span>'
            f'<span>{k["volume"]:,}</span></div>'
            for k in sem[:7]
        )
        cols.append(f'''<div>
      <h4 data-tip="Estimated monthly US search volume. Unlike the Trends indexes these ARE absolute and comparable across rows &mdash; the peer terms are here as the scale check. Source: {_esc(h.get("semrush_source") or "Semrush")}.">Monthly searches<span class="info">?</span></h4>
      {rows}
      <p class="sub2">Absolute volume, US. Peer rows are the scale check.</p>
    </div>''')

    ranks = h.get("rank_series") or []
    rq = h.get("rising_queries") or []
    if ranks or rq:
        rank_rows = "".join(
            f'<div class="kv"><span>{_esc(r["period"])}</span><span>#{r["rank"]}</span></div>'
            for r in ranks[-4:]
        )
        q_rows = "".join(
            f'<div class="kv"><span>{_esc(q)}</span><span>{v:,.0f}</span></div>'
            for q, v in rq[:3]
        )
        cols.append(f'''<div>
      <h4 data-tip="Where the game ranks by gross merchandise value among all TCGs on TCGplayer, from the quarterly seller report. This is dollars actually spent on the largest marketplace &mdash; the closest thing to a share-of-wallet number. Rising related searches are from Google Trends and are the earliest warning available: a set code or &quot;ban list&quot; climbing here moves before price does.">Marketplace &amp; rising<span class="info">?</span></h4>
      {rank_rows}
      <p class="sub2" style="margin:8px 0 2px">Rising searches</p>
      {q_rows}
    </div>''')

    sets = h.get("sets") or []
    if sets:
        PHASE = {
            "peaking": ("hot", "at its peak"),
            "cooling": ("hot", "cooling"),
            "faded": ("flat", "faded"),
            "evergreen": ("", "evergreen"),
        }
        parts = []
        for st in sets:
            cls = PHASE[st["phase"]][0]
            code = (
                f' <span class="chip-sm">{_esc(st["set_code"])}</span>'
                if st.get("set_code") else ""
            )
            age = "" if st["evergreen"] else f' &middot; {st["weeks_since_peak"]}w'
            parts.append(
                f'<div class="kv"><span>{_esc(st["name"].title())}{code}</span>'
                f'<span class="{cls}">{st["pct_of_peak"]}% of peak{age}</span></div>'
            )
        rows = "".join(parts)
        newest = next((x for x in sets if not x["evergreen"]), None)
        spark = _spark(newest["series"]) if newest else ""
        cols.append(f'''<div>
      <h4 data-tip="Search interest per expansion, all queried together so these ARE comparable to each other (unlike the headline index). The pattern is the point: every set so far spikes the week of launch and gives most of it back within two quarters. Newtype Rising is at 4% of its peak; Steel Requiem at 7%. Where the newest set sits on that curve is the difference between buying into rising attention and buying the decay.">Set attention<span class="info">?</span></h4>
      {rows}
      {spark}
      <p class="sub2">{_esc(newest["name"].title()) if newest else ""} · newest set, weekly</p>
    </div>''')

    daily = h.get("daily") or []
    if daily:
        WIN = ("1d", "3d", "7d", "14d", "30d", "60d", "90d")
        head = "".join(f'<th class="num">{w}</th>' for w in WIN)
        body = []
        for dser in daily:
            cells = []
            for w in WIN:
                v = (dser.get("windows") or {}).get(w)
                if v is None:
                    cells.append('<td class="num"><span class="flat">&mdash;</span></td>')
                else:
                    cls = "cool" if v > 0 else ("hot" if v < 0 else "")
                    cells.append(f'<td class="num"><span class="{cls}">{v:+.0f}%</span></td>')
            tag = "buy intent" if dser.get("intent") == "transactional" else "awareness"
            body.append(
                f'<tr><td>{_esc(dser["name"])}<br>'
                f'<span class="chip-sm">{tag}</span> '
                f'<span class="chip-sm">{_esc(dser.get("resolution", ""))}</span></td>'
                + "".join(cells) + "</tr>"
            )
        cols.append(f'''<div style="grid-column:1/-1">
      <h4 data-tip="Search demand measured on the same windows as the price columns, so the two can be read side by side. This is the only leading number in the project &mdash; price tells you a card already moved, whereas buying-intent search is people forming an intention before they transact. Blank cells are honest: Google only publishes daily resolution for terms above a volume threshold, and the buy-intent terms are exactly the ones too small to clear it, so their short windows come from weekly data and 1d/3d do not exist at all.">Demand momentum<span class="info">?</span></h4>
      <table class="mom"><thead><tr><th>Term</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>
      <p class="sub2">Trailing means, not point readings &mdash; a single day of Trends is noise.
        A negative short window with a positive long one is a release spike unwinding, not demand
        leaving.</p>
    </div>''')

    intent = h.get("intent") or []
    if intent:
        buy = [k for k in intent if k.get("intent") == "transactional"][:6]
        rows = "".join(
            f'<div class="kv"><span>{_esc(k["keyword"])}</span><span>{k["volume"]:,}</span></div>'
            for k in buy
        )
        zero = h.get("zero_volume") or []
        zline = (
            f'<p class="sub2">No measurable volume: {_esc(", ".join(zero))}.</p>' if zero else ""
        )
        cols.append(f'''<div>
      <h4 data-tip="Terms with buying intent rather than curiosity &mdash; booster box, starter deck, pre order, where to buy. Someone searching &quot;gundam booster box&quot; is closer to a transaction than someone searching &quot;gundam tcg&quot;, so this is the demand number with the least noise in it. Semrush volume is a trailing 12-month average, which is why a set released three weeks ago barely registers here even while Google Trends has it at an all-time high.">Buying intent<span class="info">?</span></h4>
      {rows}
      <p class="sub2">Monthly US searches, absolute.</p>
      {zline}
    </div>''')

    cats = h.get("catalysts") or []
    cat_html = ""
    if cats:
        items = "".join(
            f'<div class="cat"><span class="tag">{_esc(c.get("kind", ""))}</span>'
            f'<b>{_esc(c.get("date", ""))}</b> {_esc(c.get("label", ""))}</div>'
            for c in cats[-6:]
        )
        ban = h.get("banlist") or {}
        proof = ""
        if ban.get("cards"):
            # Prefer cards the hold screen would actually have shown you. A 94%
            # drop on a $2 common is true and irrelevant; a 14% drop on a $46
            # card is the one that would have been in your positions.
            pool = [c for c in ban["cards"] if (c.get("before") or 0) >= 10] or ban["cards"]
            moves = sorted(pool, key=lambda c: abs(c.get("pct") or 0), reverse=True)[:3]
            proof = (
                '<p class="sub2" style="margin-top:8px">What the last banlist did to price, '
                f'{_esc(ban.get("effective", ""))} onward: '
                + ", ".join(
                    f'{_esc(m["name"])} ${m["before"]:,.2f} &rarr; ${m["after"]:,.2f} '
                    f'({m["pct"]:+.0f}%)' for m in moves
                )
                + '. None of it was visible in the price data beforehand.</p>'
            )
        cat_html = f'''<div style="grid-column:1/-1">
      <h4 data-tip="Set releases and banlist updates. These are the events that actually start and end runs, and nothing in the price data anticipates them &mdash; the screen can only show you the aftermath.">Catalysts the screen cannot see<span class="info">?</span></h4>
      {items}{proof}
    </div>'''

    return f'''<details class="panel heat{" stale" if stale else ""}" open>
  <summary>Market heat<span class="sc">is anyone outside this dashboard paying attention?</span></summary>
  {banner}
  <div class="verdict">{_esc(h.get("verdict") or "")}</div>
  <div class="hgrid">{"".join(cols)}{cat_html}</div>
  <p class="sub2" style="padding:0 2px 4px">Captured {_esc(h.get("captured_at"))}. Trends indexes
    are relative to each term&#39;s own peak and are not comparable to each other; Semrush volumes
    are absolute. None of this is a forecast &mdash; it is how much attention the game has now
    versus its own past.</p>
</details>'''


def render(
    ranked: Sequence[dict],
    *,
    obs_date: str,
    stats: dict[str, Any] | None = None,
    top_n: int = 200,
    market: dict[str, Any] | None = None,
    plan_cfg: dict[str, Any] | None = None,
    scope_note: str = "",
    heat: dict[str, Any] | None = None,
) -> str:
    stats = stats or {}
    market = market or {}
    candidates = [r for r in ranked if not r.get("disqualified")]
    rejected = [r for r in ranked if r.get("disqualified")]

    rows = [_row_payload(r) for r in candidates[:top_n]]
    sets = sorted({r["set_name"] for r in rows if r.get("set_name")})
    rarities = sorted({r["rarity"] for r in rows if r.get("rarity")})

    scores = [r["invest_score"] for r in rows]
    median_score = sorted(scores)[len(scores) // 2] if scores else 0
    top = rows[0] if rows else None
    liquid = sum(1 for r in rows if (r.get("avg_daily_sales") or 0) >= 1.0)

    payload = (
        json.dumps(
            {
                "rows": rows,
                "obs_date": obs_date,
                "checklist": CHECKLIST,
                "plan": plan_cfg or {"max_position_pct": 0.25},
            },
            separators=(",", ":"),
        )
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )

    breadth = ""
    if market.get("priced") and market.get("up_7d"):
        pct = round(100 * market["up_7d"] / market["priced"])
        breadth = f"""
  <div class="tile"><div class="label" data-tip="Share of every priced product in the game that is up over 7 days. Context for whether your candidates are rising with the market or against it.">Market breadth<span class="info">?</span></div>
    <div class="value">{pct}%</div>
    <div class="foot">{market['up_7d']:,} of {market['priced']:,} up over 7d</div></div>"""

    return f"""<!doctype html>
<html lang="en" class="viz-root" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gundam Hold Screen — {_esc(obs_date)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap">
<style>{CSS}</style>
</head>
<body class="viz-root">
<div class="wrap">
<header>
  <div>
    <h1>Gundam Hold Screen</h1>
    <p class="mission">Cards that already have value, have been climbing for months rather than
      days, and sell often enough to get out of. Ranked for buying and sitting on &mdash; not for
      flipping.</p>
    <p class="stamp">{_esc(obs_date)} · {len(candidates)} candidates from {len(ranked)} screened ·
      English printings only · source: tcgapi.dev{(' · ' + _esc(scope_note)) if scope_note else ''}</p>
  </div>
  <div class="hbtns">
    <button class="ghost" id="csv">Export CSV</button>
  </div>
</header>

<div class="tiles">
  <div class="tile"><div class="label" data-tip="Cards that cleared every gate: real price, enough history, recorded sales, up over 90 days, and not too volatile.">Candidates<span class="info">?</span></div>
    <div class="value">{len(candidates)}</div>
    <div class="foot">of {len(ranked)} screened</div></div>
  <div class="tile"><div class="label" data-tip="Half the candidates score above this. Useful as a bar: anything well under it is in the list but not compelling.">Median score<span class="info">?</span></div>
    <div class="value">{median_score:.0f}</div>
    <div class="foot">weighted, out of 100</div></div>
  <div class="tile"><div class="label" data-tip="Candidates selling at least one copy a day. Below that, exiting a stack takes weeks.">Liquid enough<span class="info">?</span></div>
    <div class="value">{liquid}</div>
    <div class="foot">1+ sales a day</div></div>
  <div class="tile"><div class="label" data-tip="Cards excluded and why. Open the Screened out panel to see every one.">Screened out<span class="info">?</span></div>
    <div class="value">{len(rejected)}</div>
    <div class="foot">all listed with reasons</div></div>
  <div class="tile"><div class="label" data-tip="Highest-scoring candidate right now.">Top of the list<span class="info">?</span></div>
    <div class="value">{top['invest_score']:.0f}</div>
    <div class="foot">{_esc(top['name']) if top else '—'}</div></div>{breadth}
</div>

{_heat_panel(heat)}

<div class="panel bar">
  <span class="flabel" data-tip="Total you're willing to put to work. Positions are sized down the ranking, capped per card.">Budget<span class="info">?</span></span>
  <input type="number" id="budget" placeholder="$" min="0" step="50" aria-label="Budget">
  <label class="chip" style="display:inline-flex;gap:6px;align-items:center"
         data-tip="Hide candidates the budget can't take a position in.">
    <input type="checkbox" id="inbudget"> Only what fits</label>
  <span class="plan-sum" id="plan-sum"></span>
  <span class="disc">Sizing is arithmetic on your budget and the live entry price. Nothing here
    forecasts a price.</span>
</div>

{GLOSSARY}

<div class="panel bar">
  <input type="search" id="q" placeholder="Search card, set or number…" aria-label="Search"
         data-tip="Matches card name, set name or collector number.">
  <select id="setfilter" aria-label="Set">{_options(sets, 'All sets')}</select>
  <select id="rarityfilter" aria-label="Rarity">{_options(rarities, 'All rarities')}</select>
  <span class="flabel" data-tip="Price band you want to buy in.">Price</span>
  <input type="number" id="minprice" placeholder="min $" min="0" step="10" aria-label="Minimum price">
  <input type="number" id="maxprice" placeholder="max $" min="0" step="10" aria-label="Maximum price">
  <span class="flabel" data-tip="Hide anything below this score.">Score</span>
  <input type="number" id="minscore" placeholder="min" min="0" max="100" step="5" aria-label="Minimum score" style="width:74px">
  <span class="flabel" data-tip="Minimum average sales per day. Set 1.0 to keep only what you can exit reasonably quickly.">Sales/day</span>
  <input type="number" id="minsales" placeholder="min" min="0" step="0.5" aria-label="Minimum sales per day" style="width:74px">
  <button class="ghost" id="reset">Reset</button>
  <span class="count" id="count"></span>
</div>

<h2 class="sect">Hold candidates<span class="sub">ranked by weighted score</span></h2>
<div class="panel tablewrap"><table><thead><tr>
  <th class="rank">#</th>
  <th data-sort="name" data-tip="{TIPS['card']}">Card</th>
  <th class="num" data-sort="price" data-tip="{TIPS['price']}">Price</th>
  <th class="num" data-sort="prem" data-tip="{TIPS['prem']}">vs sold</th>
  <th class="num col-hide" data-sort="c3" data-tip="{TIPS['c3']}">3d</th>
  <th class="num" data-sort="c7" data-tip="{TIPS['c7']}">7d</th>
  <th class="num col-hide" data-sort="c30" data-tip="{TIPS['c30']}">30d</th>
  <th class="num" data-sort="c90" data-tip="{TIPS['c90']}">90d</th>
  <th data-tip="{TIPS['trend90']}">90-day trend</th>
  <th class="num" data-sort="cons" data-tip="{TIPS['cons']}">Weeks up</th>
  <th class="num" data-sort="sales" data-tip="{TIPS['sales']}">Sales/day</th>
  <th class="num col-hide" data-sort="entry" data-tip="{TIPS['entry']}">Entry</th>
  <th class="num" data-sort="score" aria-sort="descending" data-tip="{TIPS['score']}">Score</th>
  <th class="num" data-tip="{TIPS['buy']}">Buy</th>
</tr></thead><tbody id="tbody"></tbody></table>
<div class="more" id="more" style="display:none">
  <button class="ghost" id="more-all">Show all</button>
</div></div>

{_rejected_table(rejected)}

<footer>
  <p>Every number here describes what a card has already done. Nothing on this page is a
  forecast, and nothing knows <em>why</em> a price is moving &mdash; bans, reprints, rotation and
  tournament results are the things that end a run, and none of them are visible in price data.</p>
  <p>Thresholds and weights live in <code>config.yaml</code> under <code>invest:</code> ·
  regenerate with <code>python -m radar invest</code></p>
</footer>
</div>
<div id="tip" role="tooltip"></div>
<script type="application/json" id="radar-data">{payload}</script>
<script>{JS}</script>
</body></html>"""


def write(html: str, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p
