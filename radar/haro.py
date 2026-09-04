"""Market Haro -- the subscriber-facing screen. One self-contained HTML file.

WHAT CHANGED FROM THE FIRST DASHBOARD, AND WHY

The first version was a table with a paragraph above every panel. It was built
for one person who wanted to understand the method. A paying subscriber wants
the opposite: look, decide, close the tab. So the copy went into tooltips and a
single collapsible "how to read", and the page is now three things in order --
the budget tool, the ranking as rich rows with a large card image and a large
90-day chart, and a detail panel on click.

The layout rules come from the dataviz method, applied to a screen that is
mostly one line chart repeated 140 times:

  - the chart is a 2px line with a 10% area wash and an 8px end marker ringed
    in the surface colour; a crosshair readout on hover, never a value on every
    point
  - signed deltas carry their sign as well as their colour, so red/green is
    never the only channel
  - one hero figure per view: the budget summary once a budget is entered,
    the candidate count before that
  - filters in one row above the content; the ranking re-renders against the
    same slice as the plan summary, so the numbers always agree

WHAT IS NEW FOR SUBSCRIBERS

  Watchlist. Star a card; enter copies and cost in the detail panel; the row
  shows unrealised P&L against today's price and flags the moment the trend
  breaks (weeks-up under 50% or a 7-day fall past 10%). Stored in the reader's
  browser only -- the page is static and the same URL every day, so it persists
  across issues without a server knowing anything.

  Rank movement. Each row shows where it sat in the previous issue.

  Catalyst flags. A card from a set with a logged banlist or release event
  wears a small flag, because those are the things the price data cannot see.

Everything the JS computes -- sizing, the plan summary, sorting -- has a Python
twin or a Python source of truth; nothing is decided on the page that the tests
cannot check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .dashboard import CHECKLIST, _esc, _rejected_table, _row_payload

# --------------------------------------------------------------------------
# Styles. Tokens are the gundeck.ai palette; everything else is new.
# --------------------------------------------------------------------------
CSS = r"""
.viz-root{
  --bg:oklch(6.5% .008 220); --surface:oklch(9% .01 220); --surface-2:oklch(12% .012 220);
  --text:oklch(94% .04 85); --text-muted:oklch(62% .02 85); --accent:oklch(78% .18 65);
  --accent-dim:oklch(60% .14 65); --border:oklch(20% .04 65); --up:oklch(68% .18 145);
  --down:oklch(60% .22 25); --warn:oklch(78% .18 65); --cyan:oklch(72% .16 200);
  --cyan-wash:oklch(72% .16 200 / .12); --r:2px;
  --mono:"TRT Terminal Mono","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);font:13px/1.5 var(--mono)}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
b{font-weight:700}
.wrap{max-width:1360px;margin:0 auto;padding:22px 20px 72px}

/* header ------------------------------------------------------------- */
header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;
  padding-bottom:14px;border-bottom:1px solid var(--border)}
.brand{font-size:10.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}
.brand span{color:var(--text-muted);letter-spacing:.12em;margin-right:6px}
h1{margin:2px 0 4px;font-size:26px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.stamp{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted)}
.hbtns{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.ghost{background:transparent;color:var(--accent);border:1px solid var(--border);
  border-radius:var(--r);padding:7px 12px;font:inherit;font-size:11px;letter-spacing:.1em;
  text-transform:uppercase;cursor:pointer}
.ghost:hover{border-color:var(--accent)}
.ghost.on{background:var(--accent);color:var(--bg);border-color:var(--accent)}

/* panels ------------------------------------------------------------- */
.panel{position:relative;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:12px 16px;margin:14px 0}
.panel::before,.panel::after{content:"";position:absolute;width:12px;height:12px;
  border:0 solid var(--accent);pointer-events:none}
.panel::before{top:-1px;left:-1px;border-width:2px 0 0 2px}
.panel::after{bottom:-1px;right:-1px;border-width:0 2px 2px 0}
details.panel>summary{list-style:none;cursor:pointer;display:flex;justify-content:flex-start;
  align-items:center;gap:12px;font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);font-weight:700;user-select:none}
details.panel>summary .sc{margin-left:auto}
details.panel>summary::-webkit-details-marker{display:none}
details.panel>summary::before{content:"";display:inline-block;width:0;height:0;
  border-style:solid;border-width:5px 0 5px 7px;border-color:transparent transparent transparent var(--accent);
  margin-right:8px;transition:transform .15s}
details.panel[open]>summary::before{transform:rotate(90deg)}
details.panel>summary .sc{font-weight:400;color:var(--text-muted);letter-spacing:.1em;
  font-size:10.5px}
details.panel>summary+*{margin-top:10px}
.stale-feed{border-left:2px solid var(--down);font-size:13px}
.stale-feed b{color:var(--down)}

/* budget -- the hero -------------------------------------------------- */
.budget{display:grid;grid-template-columns:auto auto 1fr;gap:14px 22px;align-items:center}
.budget label{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted);
  display:flex;align-items:center;gap:8px}
.budget input[type=number]{background:var(--bg);color:var(--text);border:1px solid var(--border);
  border-radius:var(--r);padding:9px 12px;font:inherit;font-size:16px;width:150px}
.budget input[type=number]:focus{outline:none;border-color:var(--accent)}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:10.5px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--text-muted);cursor:pointer;user-select:none}
.chip input{accent-color:var(--accent)}
.plan-sum{font-size:14px;line-height:1.5}
.plan-sum .hero{font-size:24px;font-weight:700;color:var(--accent);margin-right:6px}
.plan-sum .conc{color:var(--warn)}
.plan-sum .muted{color:var(--text-muted);font-size:12px}

/* kpi strip ---------------------------------------------------------- */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:10px 12px}
.kpi .l{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted)}
.kpi .v{font-size:22px;font-weight:700;margin-top:2px;line-height:1.1}
.kpi .f{font-size:10px;color:var(--text-muted);margin-top:3px;text-transform:uppercase;letter-spacing:.06em}
.kpi.down .v{color:var(--down)} .kpi.up .v{color:var(--up)} .kpi.cyan .v{color:var(--cyan)}

/* since -------------------------------------------------------------- */
.since-chips{display:flex;flex-wrap:wrap;gap:8px}
.since-chips .sc-chip{border:1px solid var(--border);border-radius:var(--r);padding:5px 10px;
  font-size:11px;letter-spacing:.06em}
.since-chips .sc-chip b{color:var(--accent)}
.since-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-top:12px}
.since-grid h5{margin:0 0 6px;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.since-grid ul{margin:0;padding-left:16px;font-size:12px;line-height:1.65}
.since-grid .m{font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-left:6px}

/* toolbar ------------------------------------------------------------ */
.bar{display:flex;flex-wrap:wrap;gap:8px 10px;align-items:center}
.bar input,.bar select{background:var(--bg);color:var(--text);border:1px solid var(--border);
  border-radius:var(--r);padding:7px 10px;font:inherit;font-size:12px}
.bar input:focus,.bar select:focus{outline:none;border-color:var(--accent)}
.bar input[type=search]{min-width:200px}
.bar input[type=number]{width:88px}
.bar .lbl{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted)}
.bar .spacer{flex:1}
.bar .count{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted)}
.setchips{display:flex;gap:6px;overflow-x:auto;padding:2px 0 6px;scrollbar-width:thin}
.setchips button{white-space:nowrap;background:transparent;border:1px solid var(--border);
  color:var(--text-muted);border-radius:var(--r);padding:4px 10px;font:inherit;font-size:10.5px;
  letter-spacing:.06em;cursor:pointer}
.setchips button.on{color:var(--bg);background:var(--accent);border-color:var(--accent)}
.views{display:inline-flex;border:1px solid var(--border);border-radius:var(--r);overflow:hidden}
.views button{background:transparent;color:var(--text-muted);border:0;padding:7px 12px;font:inherit;
  font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;cursor:pointer}
.views button.on{background:var(--accent);color:var(--bg)}

/* the ranking -------------------------------------------------------- */
.rows{display:flex;flex-direction:column;gap:8px}
.row{display:grid;grid-template-columns:44px 96px minmax(180px,1.2fr) minmax(240px,1.6fr) auto 92px 96px 36px;
  gap:0 16px;align-items:center;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:10px 14px;cursor:pointer;position:relative}
.row:hover{border-color:var(--accent-dim)}
.row.open{border-color:var(--accent)}
.row.sized{box-shadow:inset 3px 0 0 var(--accent)}
.row.watched .star{color:var(--accent)}
.rank{display:flex;flex-direction:column;align-items:center;gap:2px}
.rank .n{font-size:16px;font-weight:700;color:var(--accent)}
.rank .d{font-size:10px;color:var(--text-muted);white-space:nowrap}
.rank .d.up{color:var(--up)} .rank .d.down{color:var(--down)}
.art{width:96px;height:134px;border-radius:3px;overflow:hidden;background:var(--surface-2);
  display:flex;align-items:center;justify-content:center}
.art img{width:100%;height:100%;object-fit:cover;display:block}
.art .ph{font-size:9px;letter-spacing:.14em;color:var(--text-muted);text-transform:uppercase}
.who .nm{font-size:15px;font-weight:700;line-height:1.25}
.who .nm a{color:var(--text)}
.who .meta{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);margin-top:4px}
.who .tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.tag{font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:2px 6px;
  border:1px solid var(--border);border-radius:var(--r);color:var(--accent);white-space:nowrap}
.tag.flag{color:var(--down);border-color:var(--down)}
.tag.pos{color:var(--cyan);border-color:var(--cyan)}
.tag.broke{color:var(--bg);background:var(--down);border-color:var(--down)}
.chart{position:relative}
.chart svg{display:block;width:100%;height:72px}
.chart .cap{display:flex;justify-content:space-between;font-size:9.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--text-muted);margin-top:2px}
.stats{display:grid;grid-template-columns:repeat(3,minmax(70px,auto));gap:6px 16px}
.stats .s .l{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted)}
.stats .s .v{font-size:14px;font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--text-muted)}
.score{text-align:center}
.score .n{font-size:28px;font-weight:700;color:var(--accent);line-height:1}
.score .bar{height:3px;background:var(--surface-2);border-radius:2px;margin-top:6px;overflow:hidden}
.score .bar i{display:block;height:100%;background:var(--accent)}
.score .l{font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted);margin-top:4px}
.size{text-align:center}
.pill{display:inline-block;padding:5px 9px;border-radius:var(--r);font-size:11.5px;font-weight:700;
  background:var(--accent);color:var(--bg);white-space:nowrap}
.pill.none{background:transparent;color:var(--text-muted);border:1px solid var(--border);font-weight:400}
.size .l{font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted);margin-top:4px}
.star{background:transparent;border:0;color:var(--text-muted);cursor:pointer;line-height:0;padding:4px}
.star:hover{color:var(--accent)}

/* detail ------------------------------------------------------------- */
.detail{background:var(--surface);border:1px solid var(--accent);border-top:0;border-radius:0 0 var(--r) var(--r);
  margin:-9px 0 0;padding:16px 18px 18px}
.det{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px}
.det h5{margin:0 0 8px;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.det p{margin:0 0 8px;font-size:12.5px;line-height:1.6}
.det .warn{color:var(--warn)}
.det ul{margin:0;padding-left:16px;font-size:12px;line-height:1.6}
.kv{display:flex;justify-content:space-between;gap:12px;padding:4px 0;border-bottom:1px dotted var(--border);font-size:12px}
.kv:last-child{border-bottom:0}
.kv .hot{color:var(--down);font-weight:700} .kv .cool{color:var(--up);font-weight:700}
.big{font-size:18px;font-weight:700;margin:2px 0}
.sub2{color:var(--text-muted);font-size:11.5px;margin:0 0 6px;line-height:1.5}
.cta{display:inline-block;margin-top:8px;border:1px solid var(--accent);padding:7px 12px;
  font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;border-radius:var(--r)}
.crow{display:grid;grid-template-columns:76px 1fr 32px;gap:8px;align-items:center;font-size:11px;margin:3px 0}
.crow .cl{color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;font-size:9.5px}
.crow .ct{height:6px;background:var(--surface-2);border-radius:2px;overflow:hidden}
.crow .ct i{display:block;height:100%;background:var(--accent)}
.crow .cv{text-align:right;font-variant-numeric:tabular-nums}
.pos-form{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:6px 0 8px}
.pos-form label{font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);display:block}
.pos-form input{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);
  border-radius:var(--r);padding:6px 8px;font:inherit}
.pnl{font-size:16px;font-weight:700}

/* misc --------------------------------------------------------------- */
.more{display:flex;justify-content:center;padding:14px 0 0}
.empty{padding:40px;text-align:center;color:var(--text-muted)}
#tip{position:fixed;z-index:50;max-width:340px;background:var(--surface-2);color:var(--text);
  border:1px solid var(--accent);border-radius:var(--r);padding:9px 11px;font-size:11.5px;line-height:1.55;
  pointer-events:none;opacity:0;transition:opacity .08s}
#tip.on{opacity:1}
#tip .tv{font-size:14px;font-weight:700} #tip .tl{color:var(--text-muted);font-size:10.5px;letter-spacing:.06em}
[data-tip]{cursor:help}
.info{display:inline-flex;width:13px;height:13px;border:1px solid var(--text-muted);border-radius:50%;
  font-size:9px;align-items:center;justify-content:center;color:var(--text-muted);margin-left:5px;
  vertical-align:middle;font-weight:400}
.howto ol{margin:0;padding-left:20px;font-size:12.5px;line-height:1.7}
.howto li{margin:3px 0}
.howto b{color:var(--accent)}
.rej{margin-top:14px}
.rej table{width:100%;border-collapse:collapse;font-size:12px}
.rej th{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted);text-align:left;
  padding:6px;border-bottom:1px solid var(--border);font-weight:400}
.rej td{padding:6px;border-bottom:1px dotted var(--border)}
.rej td.num,.rej th.num{text-align:right}
.tablewrap{overflow-x:auto}
footer{margin-top:28px;padding-top:14px;border-top:1px solid var(--border);color:var(--text-muted);
  font-size:11px;line-height:1.65}

@media (max-width:1100px){
  .row{grid-template-columns:40px 84px minmax(160px,1fr) 88px 36px;grid-template-areas:
    "rank art who score star" "rank art chart chart chart" "rank art stats stats size"}
  .rank{grid-area:rank} .art{grid-area:art;width:84px;height:117px} .who{grid-area:who}
  .chart{grid-area:chart;margin-top:8px} .stats{grid-area:stats;margin-top:8px}
  .score{grid-area:score} .size{grid-area:size;margin-top:8px} .star{grid-area:star}
}
@media (max-width:640px){
  .wrap{padding:14px 10px 48px}
  h1{font-size:20px}
  header{flex-direction:column;align-items:flex-start}
  .budget{grid-template-columns:1fr;gap:10px}
  .row{grid-template-columns:72px 1fr 32px;gap:0 10px;padding:10px;grid-template-areas:
    "art who star" "art score score" "chart chart chart" "stats stats stats" "size size size"}
  .rank{display:none}
  .art{width:72px;height:100px}
  .score{text-align:left;margin-top:6px} .score .bar{max-width:120px}
  .size{text-align:left}
  .stats{grid-template-columns:repeat(3,1fr)}
  .kpis{grid-template-columns:repeat(2,1fr)}
  .det{grid-template-columns:1fr}
}
"""

# --------------------------------------------------------------------------
# Behaviour. Sizing and the plan summary are twins of radar/plan.py.
# --------------------------------------------------------------------------
JS = r"""
const DATA = JSON.parse(document.getElementById('haro-data').textContent);
const state = {q:'', set:'', rarity:'', minPrice:null, maxPrice:null, minScore:null, minSales:null,
               sort:'score', dir:-1, limit:30, budget:null, inBudgetOnly:false, view:'all',
               open:new Set()};

const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => v==null ? '—'
  : '$' + (v>=1000 ? v.toLocaleString(undefined,{maximumFractionDigits:0}) : v.toFixed(2));
const pct = (v, digits=0) => {
  if (v==null) return '<span class="flat">—</span>';
  const cls = v > 0.05 ? 'up' : (v < -0.05 ? 'down' : 'flat');
  return `<span class="${cls}">${v>0?'+':''}${v.toFixed(digits)}%</span>`;
};
const key = r => r.card_id + '|' + r.printing;
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const shortDate = d => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d||''); return m ? `${MON[+m[2]-1]} ${+m[3]}` : (d||''); };

// ---- watchlist: the reader's browser only -------------------------------
// Wrapped in try/catch throughout: private windows, blocked storage and
// thumbnail renderers all throw, and the page must work with nothing saved.
const WATCH_KEY = 'haro.watch.v1';
function loadWatch(){ try { return JSON.parse(localStorage.getItem(WATCH_KEY) || '{}') || {}; } catch(e){ return {}; } }
function saveWatch(w){ try { localStorage.setItem(WATCH_KEY, JSON.stringify(w)); } catch(e){} }
let watch = loadWatch();
const isWatched = r => !!watch[key(r)];
function toggleWatch(r){
  const k = key(r);
  if (watch[k]) delete watch[k]; else watch[k] = {qty:null, cost:null, since:DATA.obs_date};
  saveWatch(watch); apply();
}
function setPosition(r, qty, cost){
  const k = key(r);
  watch[k] = Object.assign(watch[k] || {since:DATA.obs_date}, {qty, cost});
  saveWatch(watch);
  const el = document.querySelector(`[data-pnl="${CSS.escape(k)}"]`); if (el) el.innerHTML = pnlHTML(r);
  // The row's tag may change (position / trend broke) without a full re-render.
  const rowEl = document.querySelector(`.row[data-key="${CSS.escape(k)}"] .tags`);
  if (rowEl) rowEl.innerHTML = tagsHTML(r);
}
// "Trend broke" is the exit signal for a hold: the weekly climb has stopped
// being a climb, or the last week gave back more than a normal wobble.
const trendBroke = r => (r.consistency_pct!=null && r.consistency_pct < 50) || (r.change_7d!=null && r.change_7d <= -10);

function pnlHTML(r){
  const w = watch[key(r)] || {};
  const q = Number(w.qty), c = Number(w.cost);
  if (!(q>0) || !(c>0)) return '<p class="sub2">Enter copies and what you paid to see the position.</p>';
  const now = r.market_price, basis = q*c, val = now!=null ? q*now : null;
  if (val==null) return '<p class="sub2">No market price to value it against.</p>';
  const d = val - basis, p = d/basis*100;
  return `<div class="pnl ${d>=0?'up':'down'}">${d>=0?'+':'−'}$${Math.abs(d).toFixed(2)} <span style="font-size:12px">(${p>=0?'+':''}${p.toFixed(1)}%)</span></div>
    <div class="kv"><span>${q} × $${c.toFixed(2)}</span><span>$${basis.toFixed(2)} in</span></div>
    <div class="kv"><span>${q} × ${money(now)} market</span><span>$${val.toFixed(2)} now</span></div>
    ${r.floor_low!=null ? `<div class="kv"><span>Cheapest listing today</span><span>${money(r.floor_low)}</span></div>` : ''}
    ${trendBroke(r) ? '<p class="warn" style="margin-top:8px"><b>Trend broke.</b> The weekly climb has stopped or the last week gave back more than a wobble. This is the exit signal a hold screen can give; it is not a forecast.</p>' : ''}`;
}

// ---- sizing (twin of radar/plan.py::allocate) ----------------------------
function allocate(rows, budget){
  const cfg = DATA.plan || {};
  const maxPct = cfg.max_position_pct ?? 0.25;
  let remaining = budget;
  const out = new Map();
  for (const r of rows){
    const k = key(r);
    const unit = (typeof r.floor_low === 'number' && r.floor_low > 0) ? r.floor_low : null;
    const copies = (typeof r.copies === 'number') ? r.copies : null;
    const plan = {unit, qty:0, cost:0, affordable:false, clears:false, reason:'', pct:0};
    if (unit == null){ plan.reason = 'No live entry price for this card today.'; out.set(k, plan); continue; }
    const cap = budget * maxPct;
    const byCap = Math.floor(cap / unit);
    const byRem = Math.floor(remaining / unit);
    const bySupply = copies == null ? byCap : copies;
    const qty = Math.max(0, Math.min(byCap, byRem, bySupply));
    if (qty < 1){
      plan.reason = byCap < 1
        ? `One copy is ${(unit/budget*100).toFixed(0)}% of the budget, over the ${(maxPct*100).toFixed(0)}% per-position cap.`
        : `$${remaining.toFixed(2)} left — one copy costs $${unit.toFixed(2)}.`;
      out.set(k, plan); continue;
    }
    const cost = qty * unit;
    remaining -= cost;
    Object.assign(plan, {qty, cost, affordable:true, clears: copies!=null && qty>=copies,
      pct: cost/budget*100, remaining,
      limitedBy: (bySupply<=byCap && bySupply<=byRem) ? 'the number of copies listed'
               : (byRem<byCap ? "what's left of the budget" : 'the per-position cap')});
    out.set(k, plan);
  }
  return out;
}

function renderPlanSummary(plans, rows){
  const el = document.getElementById('plan-sum');
  if (!state.budget){
    el.innerHTML = `<span class="hero">${DATA.rows.length}</span> candidates today. <span class="muted">Enter a budget and each row gets a size: copies, cost, and what limited it.</span>`;
    return;
  }
  let n=0, spend=0; const bySet = {};
  for (const r of rows){
    const p = plans.get(key(r)); if (!p || !p.affordable) continue;
    n++; spend += p.cost; const s = r.set_name || '—'; bySet[s] = (bySet[s]||0) + p.cost;
  }
  if (!n){ el.innerHTML = `Nothing fits — one copy of everything costs more than the ${((DATA.plan?.max_position_pct??0.25)*100).toFixed(0)}% per-position cap.`; return; }
  let html = `<span class="hero">${n}</span> ${n===1?'position':'positions'} · <b>$${spend.toFixed(2)}</b> of $${state.budget.toFixed(2)} placed · $${(state.budget-spend).toFixed(2)} left`;
  const top = Object.entries(bySet).sort((a,b)=>b[1]-a[1])[0];
  if (top && spend > 0){ const share = top[1]/spend*100;
    if (share >= 50) html += ` · <span class="conc">${share.toFixed(0)}% of it in ${esc(top[0])}</span>`; }
  html += ` <span class="muted">— sized down the ranking, ${((DATA.plan?.max_position_pct??0.25)*100).toFixed(0)}% cap per card. Arithmetic, not advice.</span>`;
  el.innerHTML = html;
}

// ---- the chart -------------------------------------------------------------
// 2px line, 10% wash, 8px ringed end marker, crosshair readout on hover.
const CH = {w:300, h:72, p:6};
function chart(series, id){
  if (!series || series.length < 2) return '<div class="chart"><div class="empty" style="padding:22px">no history</div></div>';
  const {w,h,p} = CH, ys = series.map(d=>d[1]);
  const lo = Math.min(...ys), hi = Math.max(...ys), span = (hi-lo) || (hi || 1);
  const X = i => p + i*(w-2*p)/(series.length-1);
  const Y = v => h-p - ((v-lo)/span)*(h-2*p);
  const pts = series.map((d,i)=>`${X(i).toFixed(1)},${Y(d[1]).toFixed(1)}`).join(' ');
  const area = `M${X(0).toFixed(1)},${(h-p).toFixed(1)} L${pts.replace(/ /g,' L')} L${X(series.length-1).toFixed(1)},${(h-p).toFixed(1)} Z`;
  const last = series[series.length-1], first = series[0];
  const stroke = last[1] >= first[1] ? 'var(--cyan)' : 'var(--down)';
  return `<div class="chart" data-chart="${esc(id)}">
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="90-day market price, ${money(first[1])} to ${money(last[1])}">
      <path d="${area}" fill="${stroke}" opacity=".12"/>
      <polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
      <line class="xh" x1="0" x2="0" y1="0" y2="${h}" stroke="var(--text-muted)" stroke-width="1" opacity="0"/>
      <circle class="dot" cx="${X(series.length-1).toFixed(1)}" cy="${Y(last[1]).toFixed(1)}" r="4" fill="${stroke}" stroke="var(--surface)" stroke-width="2"/>
    </svg>
    <div class="cap"><span>${shortDate(first[0])} ${money(first[1])} → ${shortDate(last[0])} ${money(last[1])}</span><span>high ${money(hi)}</span></div>
  </div>`;
}
function chartHover(e){
  const box = e.target.closest('.chart'); if (!box) return;
  const r = DATA.rows.find(x => key(x) === box.dataset.chart); if (!r || !r.series || r.series.length < 2) return;
  const svg = box.querySelector('svg'), rect = svg.getBoundingClientRect();
  const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const i = Math.round(frac * (r.series.length-1));
  const [d, v] = r.series[i];
  const xh = svg.querySelector('.xh'); const {w,p} = CH; const x = p + i*(w-2*p)/(r.series.length-1);
  xh.setAttribute('x1', x); xh.setAttribute('x2', x); xh.setAttribute('opacity', '.6');
  tip.innerHTML = `<div class="tv">${money(v)}</div><div class="tl">${esc(d)}</div>`;
  tip.classList.add('on');
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  tip.style.left = Math.max(8, Math.min(e.clientX - tw/2, window.innerWidth - tw - 8)) + 'px';
  tip.style.top = (rect.top - th - 8) + 'px';
}
function chartLeave(e){
  const box = e.target.closest('.chart'); if (!box) return;
  const xh = box.querySelector('.xh'); if (xh) xh.setAttribute('opacity','0');
  hideTip();
}

// ---- rows ------------------------------------------------------------------
const COMPONENTS = [
  ['value','Value','Log-scaled price. $10 scores 0, $200 scores 100.'],
  ['liquidity','Liquidity','Average daily sales and the share of days that saw any sale.'],
  ['trend','Trend','Share of weeks closing above the previous week, plus the 90-day change.'],
  ['stability','Stability','Daily volatility and how far it sits below its 90-day high.'],
  ['scarcity','Scarcity','Rarity tier and how many copies are listed.'],
];
function componentBars(c){
  if (!c) return '';
  return COMPONENTS.map(([k,label,tip])=>{ const v = c[k] ?? 0;
    return `<div class="crow" data-tip="${esc(tip)}"><span class="cl">${label}</span><span class="ct"><i style="width:${Math.max(2,v)}%"></i></span><span class="cv">${v.toFixed(0)}</span></div>`;
  }).join('');
}
function tagsHTML(r){
  const t = [];
  if (r.rarity && r.rarity !== '—') t.push(`<span class="tag">${esc(r.rarity)}</span>`);
  if (r.printing && r.printing !== 'Normal') t.push(`<span class="tag">${esc(r.printing)}</span>`);
  if (r.catalyst) t.push(`<span class="tag flag" data-tip="${esc(r.catalyst)}">catalyst</span>`);
  if (isWatched(r)){
    const w = watch[key(r)];
    t.push(w && Number(w.qty) > 0 ? `<span class="tag pos">${w.qty} held</span>` : '<span class="tag pos">watching</span>');
    if (trendBroke(r)) t.push('<span class="tag broke" data-tip="Weeks-up under 50% or a 7-day fall past 10%. The exit signal a hold screen can give.">trend broke</span>');
  }
  return t.join('');
}
function rankDelta(r){
  const prev = DATA.prev_ranks ? DATA.prev_ranks[key(r)] : undefined;
  if (prev == null) return DATA.prev_ranks ? '<span class="d" data-tip="Not in the previous issue’s ranking.">new</span>' : '';
  const d = prev - r.rank;
  if (d === 0) return '<span class="d">—</span>';
  return `<span class="d ${d>0?'up':'down'}" data-tip="Was #${prev} in the previous issue.">${d>0?'+':'−'}${Math.abs(d)}</span>`;
}
function rowHTML(r, plan){
  const k = key(r), openNow = state.open.has(k), sized = plan && plan.affordable;
  const url = r.tcgplayer_url || (r.tcgplayer_id ? 'https://www.tcgplayer.com/product/'+r.tcgplayer_id+'?Language=English' : null);
  const nm = url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(r.name)}</a>` : esc(r.name);
  const meta = [r.set_name, r.number].filter(Boolean).map(esc).join(' · ');
  const art = r.image_url ? `<img src="${esc(r.image_url)}" alt="" loading="lazy" decoding="async">` : '<span class="ph">no image</span>';
  const prem = r.ask_premium_pct;
  const premHTML = prem==null ? '<span class="flat">—</span>'
    : `<span class="${prem>5?'down':(prem<-2?'up':'flat')}">${prem>0?'+':''}${prem.toFixed(0)}%</span>`;
  return `<div class="row${openNow?' open':''}${sized?' sized':''}${isWatched(r)?' watched':''}" data-key="${esc(k)}" role="button" aria-expanded="${openNow}">
    <div class="rank"><span class="n">${r.rank}</span>${rankDelta(r)}</div>
    <div class="art">${art}</div>
    <div class="who"><div class="nm">${nm}</div><div class="meta">${meta}</div><div class="tags">${tagsHTML(r)}</div></div>
    ${chart(r.series, k)}
    <div class="stats">
      <div class="s" data-tip="${esc(DATA.tips.price)}"><div class="l">Price</div><div class="v">${money(r.market_price)}</div></div>
      <div class="s" data-tip="${esc(DATA.tips.entry)}"><div class="l">Entry</div><div class="v">${money(r.floor_low)}</div></div>
      <div class="s" data-tip="${esc(DATA.tips.prem)}"><div class="l">vs sold</div><div class="v">${premHTML}</div></div>
      <div class="s" data-tip="${esc(DATA.tips.c7)}"><div class="l">7d</div><div class="v">${pct(r.change_7d)}</div></div>
      <div class="s" data-tip="${esc(DATA.tips.c90)}"><div class="l">90d</div><div class="v">${pct(r.change_90d)}</div></div>
      <div class="s" data-tip="${esc(DATA.tips.sales)}"><div class="l">Sales/day</div><div class="v ${(r.avg_daily_sales??0)<1?'down':''}">${r.avg_daily_sales==null?'—':r.avg_daily_sales.toFixed(1)}</div></div>
    </div>
    <div class="score" data-tip="${esc(DATA.tips.score)}"><div class="n">${r.invest_score.toFixed(0)}</div><div class="bar"><i style="width:${Math.max(3,r.invest_score)}%"></i></div><div class="l">score</div></div>
    <div class="size" data-tip="${esc(DATA.tips.buy)}">${sized?`<span class="pill">${plan.qty} · $${plan.cost.toFixed(0)}</span>`:'<span class="pill none">—</span>'}<div class="l">size</div></div>
    <button class="star" data-star="${esc(k)}" aria-label="${isWatched(r)?'Remove from':'Add to'} watchlist" title="Watchlist"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M12 2.5l2.9 6.2 6.8.8-5 4.6 1.3 6.7L12 17.5l-6 3.3 1.3-6.7-5-4.6 6.8-.8z" fill="${isWatched(r)?'currentColor':'none'}" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg></button>
  </div>` + (openNow ? detailHTML(r, plan) : '');
}

function detailHTML(r, plan){
  const url = r.tcgplayer_url || (r.tcgplayer_id ? 'https://www.tcgplayer.com/product/'+r.tcgplayer_id+'?Language=English' : null);
  const k = key(r), w = watch[k] || {};
  let pos;
  if (!state.budget) pos = '<p class="sub2">Enter a budget at the top and this becomes copies and a cost.</p>';
  else if (plan && plan.affordable) pos = `<div class="big">${plan.qty} ${plan.qty===1?'copy':'copies'} · $${plan.cost.toFixed(2)}</div>
      <div class="sub2">at $${plan.unit.toFixed(2)} shipped each · ${plan.pct.toFixed(0)}% of your budget</div>
      <div class="kv"><span>Limited by</span><span>${plan.limitedBy}</span></div>
      <div class="kv"><span>Copies listed</span><span>${r.copies ?? '—'}</span></div>
      <div class="kv"><span>Budget left after</span><span>$${(plan.remaining??0).toFixed(2)}</span></div>
      ${r.avg_daily_sales ? `<div class="kv"><span>Days to sell that many</span><span>~${Math.ceil(plan.qty/r.avg_daily_sales)}</span></div>` : ''}`;
  else pos = `<div class="big">No position</div><p class="sub2">${plan ? plan.reason : 'No live entry price.'}</p>`;

  const entry = (r.floor_low != null)
    ? `<div class="kv"><span>Cheapest NM English, shipped</span><span>$${r.floor_low.toFixed(2)}</span></div>
       <div class="kv"><span>Median listing</span><span>${r.shelf_med!=null?'$'+r.shelf_med.toFixed(2):'—'}</span></div>
       <div class="kv"><span>Entry vs the shelf</span><span>${r.entry_vs_shelf_pct==null?'—':(r.entry_vs_shelf_pct>0?Math.abs(r.entry_vs_shelf_pct).toFixed(0)+'% below median':Math.abs(r.entry_vs_shelf_pct).toFixed(0)+'% above median')}</span></div>
       <div class="kv"><span>Copies at Near Mint</span><span>${r.copies ?? '—'}</span></div>`
    : '<p class="sub2">No live entry price for this card today.</p>';
  const settled = (r.settled_price != null)
    ? `<div class="kv"><span>Trading at</span><span>$${r.settled_price.toFixed(2)}</span></div>
       <div class="kv"><span>Listed price is</span><span class="${r.ask_premium_pct==null?'':(r.ask_premium_pct>5?'hot':(r.ask_premium_pct<-2?'cool':''))}">${r.ask_premium_pct==null?'—':(r.ask_premium_pct>=0?'+'+r.ask_premium_pct.toFixed(1)+'% above':Math.abs(r.ask_premium_pct).toFixed(1)+'% below')}</span></div>
       <div class="kv"><span>Based on</span><span>${r.settled_volume ?? '—'} sales / ${r.settled_days} days</span></div>
       <p class="sub2">${r.ask_premium_pct==null?'':r.ask_premium_pct>5?'Sellers are asking more than buyers have been paying. Cards in this state gave back a median 4% over the next 30 days.':r.ask_premium_pct<-2?'Copies have been selling above the listed price. Cards in this state gained a median 10% over the next 30 days.':'Asking price and sale price agree.'}</p>`
    : '<p class="sub2">Under three days of recorded sales in the last fortnight — not enough to say what it trades at.</p>';

  return `<div class="detail" data-detail="${esc(k)}"><div class="det">
    <div>
      <h5>The case</h5><p>${esc(r.thesis||'')}</p><p class="warn">${esc(r.watch||'')}</p>
      ${r.catalyst ? `<p class="warn"><b>Catalyst on this set:</b> ${esc(r.catalyst)}</p>` : ''}
      ${url?`<a class="cta" href="${esc(url)}" target="_blank" rel="noopener">Open on TCGplayer &rarr;</a>`:''}
    </div>
    <div>
      <h5>Score, broken down</h5>${componentBars(r.components)}
      <div class="kv" style="margin-top:8px"><span>Weighted total</span><span>${r.invest_score.toFixed(0)} / 100</span></div>
      <div class="kv"><span>3d / 7d / 30d / 90d</span><span>${[r.change_3d,r.change_7d,r.change_30d,r.change_90d].map(v=>v==null?'—':(v>0?'+':'')+v.toFixed(0)+'%').join(' / ')}</span></div>
      <div class="kv"><span>Weeks closing up</span><span>${r.consistency_pct ?? '—'}%</span></div>
      <div class="kv"><span>Daily volatility</span><span>${r.volatility_pct ?? '—'}%</span></div>
      <div class="kv"><span>Off its 90-day high</span><span>${r.drawdown_pct ?? '—'}%</span></div>
    </div>
    <div>
      <h5 data-tip="${esc(DATA.tips.settled)}">What it trades at<span class="info">?</span></h5>${settled}
      <h5 style="margin-top:14px">Entry today</h5>${entry}
    </div>
    <div>
      <h5>Size at your budget</h5>${pos}
      <h5 style="margin-top:14px">Your position <span class="sub2" style="display:inline">(saved in this browser)</span></h5>
      <div class="pos-form">
        <div><label>Copies</label><input type="number" min="0" step="1" data-pos="qty" data-k="${esc(k)}" value="${w.qty??''}"></div>
        <div><label>Paid each</label><input type="number" min="0" step="0.01" data-pos="cost" data-k="${esc(k)}" value="${w.cost??''}"></div>
      </div>
      <div data-pnl="${esc(k)}">${pnlHTML(r)}</div>
    </div>
    <div>
      <h5>Before you buy</h5><ul>${DATA.checklist.map(x=>`<li>${x}</li>`).join('')}</ul>
    </div>
  </div></div>`;
}

const SORTERS = {
  score:r=>r.invest_score, price:r=>r.market_price ?? -1, entry:r=>r.floor_low ?? -1,
  prem:r=>r.ask_premium_pct ?? 1e9, c7:r=>r.change_7d ?? -1e9, c90:r=>r.change_90d ?? -1e9,
  sales:r=>r.avg_daily_sales ?? -1, cons:r=>r.consistency_pct ?? -1, name:r=>(r.name||'').toLowerCase(),
  moved:r=>{ const p = DATA.prev_ranks ? DATA.prev_ranks[key(r)] : null; return p==null ? 1e6 : p - r.rank; },
};

function filtered(){
  const q = state.q.trim().toLowerCase();
  return DATA.rows.filter(r=>{
    if (state.view==='watch' && !isWatched(r)) return false;
    if (q && !((r.name||'').toLowerCase().includes(q) || (r.set_name||'').toLowerCase().includes(q) || (r.number||'').toLowerCase().includes(q))) return false;
    if (state.set && r.set_name !== state.set) return false;
    if (state.rarity && r.rarity !== state.rarity) return false;
    if (state.minPrice!=null && (r.market_price??0) < state.minPrice) return false;
    if (state.maxPrice!=null && (r.market_price??Infinity) > state.maxPrice) return false;
    if (state.minScore!=null && r.invest_score < state.minScore) return false;
    if (state.minSales!=null && (r.avg_daily_sales??0) < state.minSales) return false;
    return true;
  });
}

function apply(){
  let rows = filtered();
  const k = SORTERS[state.sort] || SORTERS.score;
  rows.sort((a,b)=>{ const av=k(a), bv=k(b); return av===bv?0:(av>bv?1:-1)*state.dir; });
  // Sizing walks the full ranking by score regardless of the view's sort, so
  // the same budget gives the same plan whatever you are looking at.
  const byScore = DATA.rows.slice().sort((a,b)=>b.invest_score-a.invest_score);
  const plans = state.budget ? allocate(byScore, state.budget) : new Map();
  if (state.budget && (state.inBudgetOnly || state.view==='sized')) rows = rows.filter(r => (plans.get(key(r))||{}).affordable);
  renderPlanSummary(plans, byScore);
  const shown = rows.slice(0, state.limit);
  document.getElementById('rows').innerHTML = shown.length ? shown.map(r=>rowHTML(r, plans.get(key(r)))).join('')
    : `<div class="empty">${state.view==='watch' ? 'Nothing on your watchlist yet — tap the star on any card.' : 'Nothing matches those filters.'}</div>`;
  document.getElementById('count').textContent = `${shown.length?'1–'+shown.length:'0'} of ${rows.length}`;
  const more = document.getElementById('more');
  if (rows.length > shown.length){ more.style.display='flex'; document.getElementById('more-all').textContent = `Show all ${rows.length}`; } else more.style.display='none';
  document.querySelectorAll('.views button').forEach(b=>b.classList.toggle('on', b.dataset.view===state.view));
  document.querySelectorAll('.setchips button').forEach(b=>b.classList.toggle('on', (b.dataset.set||'')===state.set));
  document.getElementById('watch-count').textContent = Object.keys(watch).length ? `(${Object.keys(watch).length})` : '';
  window.__view = rows;
}

function reset(){
  Object.assign(state, {q:'', set:'', rarity:'', minPrice:null, maxPrice:null, minScore:null, minSales:null, sort:'score', dir:-1, limit:30, inBudgetOnly:false, view:'all'});
  document.getElementById('q').value=''; document.getElementById('rarityfilter').value='';
  ['minprice','maxprice','minscore','minsales'].forEach(id=>{const e=document.getElementById(id); if(e) e.value='';});
  document.getElementById('sort').value='score';
  const ib=document.getElementById('inbudget'); if(ib) ib.checked=false;
  state.open.clear(); apply();
}

function exportCSV(){
  const rows = window.__view || DATA.rows;
  const cols = ['rank','name','set_name','number','rarity','printing','market_price','floor_low','shelf_med','copies','settled_price','ask_premium_pct','change_3d','change_7d','change_30d','change_90d','consistency_pct','volatility_pct','drawdown_pct','avg_daily_sales','days_traded_pct','invest_score','tcgplayer_url'];
  const csv = [cols.join(',')].concat(rows.map(r=>cols.map(c=>{ const v=r[c]; if (v==null) return ''; const s=String(v); return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s; }).join(','))).join('\n');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv],{type:'text/csv'}));
  a.download = `market-haro-${DATA.obs_date}.csv`; a.click(); URL.revokeObjectURL(a.href);
}

// ---- tooltips (hover + tap) -------------------------------------------------
const tip = document.getElementById('tip'); let tipAnchor = null;
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
  if (e.target.closest('.chart')) return;
  const el = e.target.closest('[data-tip]'); if (el === tipAnchor) return;
  tipAnchor = el; el ? showTip(el) : hideTip();
});
document.addEventListener('mouseout', e=>{
  const from = e.target.closest('[data-tip]'); if (!from) return;
  const to = e.relatedTarget && e.relatedTarget.closest ? e.relatedTarget.closest('[data-tip]') : null;
  if (to !== from){ tipAnchor = to; to ? showTip(to) : hideTip(); }
});
document.addEventListener('mousemove', e=>{ if (e.target.closest('.chart')) chartHover(e); });
document.addEventListener('mouseout', e=>{ if (e.target.closest('.chart') && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('.chart'))) chartLeave(e); });
window.addEventListener('scroll', ()=>{ if (tipAnchor) showTip(tipAnchor); }, {passive:true});

// ---- clicks -------------------------------------------------------------------
document.addEventListener('click', e=>{
  const star = e.target.closest('[data-star]');
  if (star){ e.stopPropagation(); const r = DATA.rows.find(x=>key(x)===star.dataset.star); if (r) toggleWatch(r); return; }
  const info = e.target.closest('.info, [data-tip].l, .s[data-tip], .score[data-tip], .size[data-tip]');
  if (info && e.target.closest('.row') && (e.target.closest('.info'))){ e.stopPropagation(); const el = e.target.closest('[data-tip]'); if (tipAnchor===el && tip.classList.contains('on')){hideTip(); tipAnchor=null;} else {tipAnchor=el; showTip(el);} return; }
  if (e.target.closest('a, input, select, button, .detail')) { return; }
  const row = e.target.closest('.row');
  if (row){ const k = row.dataset.key; state.open.has(k) ? state.open.delete(k) : state.open.add(k); apply(); return; }
  if (tipAnchor && !e.target.closest('#tip')){ hideTip(); tipAnchor = null; }
});
document.addEventListener('input', e=>{
  const p = e.target.closest('[data-pos]'); if (!p) return;
  const r = DATA.rows.find(x=>key(x)===p.dataset.k); if (!r) return;
  const box = p.closest('.pos-form');
  const qty = Number(box.querySelector('[data-pos=qty]').value), cost = Number(box.querySelector('[data-pos=cost]').value);
  setPosition(r, qty>0?qty:null, cost>0?cost:null);
});

// ---- controls -----------------------------------------------------------------
document.getElementById('q').addEventListener('input', e=>{state.q=e.target.value; state.limit=30; apply();});
document.getElementById('rarityfilter').addEventListener('change', e=>{state.rarity=e.target.value; state.limit=30; apply();});
[['minprice','minPrice'],['maxprice','maxPrice'],['minscore','minScore'],['minsales','minSales']].forEach(([id,k])=>{
  const el = document.getElementById(id); if (!el) return;
  el.addEventListener('input', e=>{ const v = e.target.value===''?null:Number(e.target.value); state[k] = (v==null||Number.isNaN(v))?null:v; state.limit=30; apply(); });
});
document.getElementById('sort').addEventListener('change', e=>{ state.sort = e.target.value; state.dir = (state.sort==='name')?1:-1; apply(); });
document.getElementById('dir').addEventListener('click', ()=>{ state.dir*=-1; document.getElementById('dir').textContent = state.dir===-1?'desc':'asc'; apply(); });
document.getElementById('budget').addEventListener('input', e=>{ const v = e.target.value===''?null:Number(e.target.value); state.budget = (v==null||Number.isNaN(v)||v<=0)?null:v; state.limit=30; apply(); });
const ib = document.getElementById('inbudget'); if (ib) ib.addEventListener('change', e=>{ state.inBudgetOnly = e.target.checked; apply(); });
document.querySelectorAll('.views button').forEach(b=>b.addEventListener('click', ()=>{ state.view=b.dataset.view; state.limit=30; apply(); }));
document.querySelectorAll('.setchips button').forEach(b=>b.addEventListener('click', ()=>{ state.set = (state.set===b.dataset.set)?'':b.dataset.set; state.limit=30; apply(); }));
document.getElementById('more-all').addEventListener('click', ()=>{state.limit=1e9; apply();});
document.getElementById('reset').addEventListener('click', reset);
document.getElementById('csv').addEventListener('click', exportCSV);
apply();
"""

TIPS = {
    "price": "Market price from the daily batch — up to two days behind. A reference, not what you pay.",
    "entry": "Cheapest Near Mint English listing right now, shipping included. This is the number you would pay; it matches TCGplayer’s “As low as”.",
    "prem": "Listed price against what copies actually SOLD for over the last 14 days. Red: sellers are asking more than buyers have paid — historically those gave back a median 4% over 30 days. Green: the reverse, +10%. A timing read, not a quality read.",
    "c7": "Change over 7 days, from stored daily closes. Context; carries no weight in the score.",
    "c90": "Change over 90 days. One of the two inputs to the Trend component.",
    "sales": "Average copies sold per day over 90 days. Under 1.0 shows red — at that rate a stack takes weeks to exit.",
    "score": "Weighted 0–100: value 20%, liquidity 25%, trend 25%, stability 20%, scarcity 10%. Anchored to this market’s own quartiles, so 75+ means top quarter — not a prediction.",
    "buy": "How many copies fit at the budget you entered, and what they cost — sized down the ranking with a per-card cap. Arithmetic on your number and today’s entry price. Not a recommendation.",
    "settled": "Volume-weighted average of what copies actually sold for over 14 days, next to the listed price. Across 1,201 observations the fifth of cards listed ~7% below recent sales returned +10.3% over 30 days; the fifth listed ~9% above returned −4.0% (ρ = −0.31). Describes where it trades, not where it goes.",
}


def _freshness(obs_date: str, today: str | None) -> str:
    if not today:
        return ""
    try:
        from datetime import date as _d

        age = (_d.fromisoformat(today) - _d.fromisoformat(obs_date)).days
    except (ValueError, TypeError):
        return ""
    if age <= 2:
        return ""
    return (f'<div class="panel stale-feed"><b>Price feed is {age} days behind.</b> Market prices are '
            f'from {_esc(obs_date)}. The ranking method is unchanged and entry prices are live; read the '
            f'market column as history until the feed catches up.</div>')


def _since(since: dict | None) -> str:
    """One row of chips; the lists open on click. No prose."""
    if not since or not since.get("has_previous"):
        return ""
    n = lambda k: len(since.get(k) or [])  # noqa: E731
    b = since.get("breadth") or {}
    chips = []
    if n("entered"): chips.append(f'<span class="sc-chip"><b>{n("entered")}</b> entered top 20</span>')
    if n("exited"): chips.append(f'<span class="sc-chip"><b>{n("exited")}</b> left top 20</span>')
    if n("stretched"): chips.append(f'<span class="sc-chip"><b>{n("stretched")}</b> asks ran ahead of sales</span>')
    if n("cheapened"): chips.append(f'<span class="sc-chip"><b>{n("cheapened")}</b> asks fell below sales</span>')
    if b.get("now_pct") is not None and b.get("prev_pct") is not None:
        d = b["now_pct"] - b["prev_pct"]
        chips.append(f'<span class="sc-chip">breadth <b>{b["now_pct"]}%</b> ({d:+d} pts)</span>')
    if not chips:
        return ""

    def card(r):
        return f'<b>{_esc(r["name"])}</b><span class="m">{_esc(r.get("set_name") or "")}</span>'
    blocks = []
    if n("entered"):
        blocks.append("<div><h5>Entered the top 20</h5><ul>" + "".join(
            f'<li>{card(r)} — #{r["rank"]}, {("was #" + str(r["prev_rank"])) if r.get("prev_rank") else "was not a candidate"}</li>'
            for r in since["entered"][:8]) + "</ul></div>")
    if n("exited"):
        blocks.append("<div><h5>Left the top 20</h5><ul>" + "".join(
            f'<li>{card(r)} — was #{r.get("prev_rank")}, {("now #" + str(r["rank"])) if r.get("rank") else _esc(r.get("disqualified") or "screened out")}</li>'
            for r in since["exited"][:8]) + "</ul></div>")
    if n("stretched"):
        blocks.append("<div><h5>Ask ran ahead of sales</h5><ul>" + "".join(
            f'<li>{card(r)} — {r["ask_premium_pct"]:+.0f}% vs sold</li>' for r in since["stretched"][:6]) + "</ul></div>")
    if n("cheapened"):
        blocks.append("<div><h5>Ask fell below sales</h5><ul>" + "".join(
            f'<li>{card(r)} — {r["ask_premium_pct"]:+.0f}% vs sold</li>' for r in since["cheapened"][:6]) + "</ul></div>")
    return (f'<details class="panel since"><summary>Since {_esc(since.get("prev_date") or "last issue")}'
            f'<span class="sc">open for the lists</span></summary>'
            f'<div class="since-chips">{"".join(chips)}</div><div class="since-grid">{"".join(blocks)}</div></details>')


def _catalyst_index(heat: dict | None) -> dict[str, str]:
    """set name -> one-line catalyst, for cards from sets with a logged event.

    Only sets named in a catalyst label get a flag; a generic 'banlist' with no
    set is not attached to anything rather than to everything.
    """
    out: dict[str, str] = {}
    for c in (heat or {}).get("catalysts") or []:
        label = c.get("label") or ""
        for s in (c.get("sets") or []):
            out[s] = f'{c.get("date", "")} · {label}'
    return out


def render(
    ranked: Sequence[dict],
    *,
    obs_date: str,
    stats: dict[str, Any] | None = None,
    top_n: int = 400,
    market: dict[str, Any] | None = None,
    plan_cfg: dict[str, Any] | None = None,
    since: dict[str, Any] | None = None,
    today: str | None = None,
    prev_ranks: dict[str, int] | None = None,
    heat: dict[str, Any] | None = None,
) -> str:
    market = market or {}
    candidates = [r for r in ranked if not r.get("disqualified")]
    rejected = [r for r in ranked if r.get("disqualified")]
    catalysts = _catalyst_index(heat)

    rows = []
    for i, r in enumerate(candidates[:top_n], 1):
        p = _row_payload(r)
        p["rank"] = i
        p["printing"] = r.get("printing") or "Normal"
        p["catalyst"] = catalysts.get(r.get("set_name") or "")
        rows.append(p)
    sets = sorted({r["set_name"] for r in rows if r.get("set_name")})
    rarities = sorted({r["rarity"] for r in rows if r.get("rarity") and r["rarity"] != "—"})
    liquid = sum(1 for r in rows if (r.get("avg_daily_sales") or 0) >= 1.0)
    scores = [r["invest_score"] for r in rows]
    median_score = sorted(scores)[len(scores) // 2] if scores else 0
    breadth = None
    if market.get("priced") and market.get("up_7d") is not None:
        breadth = round(100 * market["up_7d"] / market["priced"])

    payload = json.dumps({
        "rows": rows, "obs_date": obs_date, "checklist": CHECKLIST,
        "plan": plan_cfg or {"max_position_pct": 0.25}, "tips": TIPS,
        "prev_ranks": prev_ranks or None,
    }, separators=(",", ":")).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")

    setchips = "".join(f'<button data-set="{_esc(s)}">{_esc(s)}</button>' for s in sets)
    rarity_opts = "".join(f'<option value="{_esc(x)}">{_esc(x)}</option>' for x in rarities)

    return f"""<!doctype html>
<html lang="en" class="viz-root" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Haro — {_esc(obs_date)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap">
<style>{CSS}</style>
</head>
<body class="viz-root">
<div class="wrap">
<header>
  <div>
    <div class="brand"><span>from</span>GUNDECK.AI</div>
    <h1>Market Haro</h1>
    <div class="stamp">Prices through {_esc(obs_date)} · {len(candidates)} candidates from {len(ranked)} screened · English NM only</div>
  </div>
  <div class="hbtns">
    <button class="ghost" id="csv">Export CSV</button>
    <button class="ghost" id="reset">Reset</button>
  </div>
</header>
{_freshness(obs_date, today)}

<div class="panel budget">
  <label for="budget" data-tip="Total you are willing to put to work. Positions are sized down the ranking, capped per card.">Budget<span class="info">?</span></label>
  <input type="number" id="budget" placeholder="$" min="0" step="50" aria-label="Budget">
  <div class="plan-sum" id="plan-sum"></div>
</div>

<div class="kpis">
  <div class="kpi"><div class="l">Candidates</div><div class="v">{len(candidates)}</div><div class="f">of {len(ranked)} screened</div></div>
  <div class="kpi{' down' if breadth is not None and breadth < 35 else ' up' if breadth is not None and breadth > 55 else ' cyan'}"><div class="l" data-tip="Share of every priced product in the game that is up over 7 days. Whether your candidates are rising with the market or against it.">Market breadth<span class="info">?</span></div><div class="v">{f'{breadth}%' if breadth is not None else '—'}</div><div class="f">{market.get('up_7d', 0):,} of {market.get('priced', 0):,} up over 7d</div></div>
  <div class="kpi up"><div class="l" data-tip="Candidates selling at least one copy a day. Below that, exiting a stack takes weeks.">Liquid enough<span class="info">?</span></div><div class="v">{liquid}</div><div class="f">1+ sales a day</div></div>
  <div class="kpi"><div class="l">Median score</div><div class="v">{median_score:.0f}</div><div class="f">of 100</div></div>
  <div class="kpi down"><div class="l" data-tip="Cards excluded and why — every one is listed at the bottom with its reason.">Screened out<span class="info">?</span></div><div class="v">{len(rejected)}</div><div class="f">listed with reasons</div></div>
</div>

{_since(since)}

<div class="panel bar">
  <input type="search" id="q" placeholder="Search card, set or number" aria-label="Search">
  <select id="rarityfilter" aria-label="Rarity"><option value="">All rarities</option>{rarity_opts}</select>
  <span class="lbl">Price</span><input type="number" id="minprice" placeholder="min" min="0"><input type="number" id="maxprice" placeholder="max" min="0">
  <span class="lbl">Score</span><input type="number" id="minscore" placeholder="min" min="0" max="100">
  <span class="lbl">Sales/day</span><input type="number" id="minsales" placeholder="min" min="0" step="0.1">
  <span class="spacer"></span>
  <span class="lbl">Sort</span>
  <select id="sort" aria-label="Sort by">
    <option value="score">Score</option><option value="moved">Rank movement</option><option value="c7">7-day change</option>
    <option value="c90">90-day change</option><option value="prem">vs sold</option><option value="price">Price</option>
    <option value="entry">Entry price</option><option value="sales">Sales/day</option><option value="cons">Weeks up</option><option value="name">Name</option>
  </select>
  <button class="ghost" id="dir" aria-label="Sort direction">desc</button>
  <span class="views"><button data-view="all" class="on">All</button><button data-view="sized" data-tip="Only cards that get a size at your budget.">Sized</button><button data-view="watch">Watchlist <span id="watch-count"></span></button></span>
  <label class="chip" data-tip="Hide candidates the budget can’t take a position in."><input type="checkbox" id="inbudget"> only what fits</label>
  <span class="count" id="count"></span>
</div>
<div class="setchips"><button data-set="">All sets</button>{setchips}</div>

<div class="rows" id="rows"></div>
<div class="more" id="more" style="display:none"><button class="ghost" id="more-all">Show all</button></div>

<details class="panel howto">
  <summary>How to read this<span class="sc">two minutes, once</span></summary>
  <ol>
    <li><b>Score</b> is 0–100 across value, liquidity, trend, stability and scarcity, anchored to this market’s own quartiles. 75+ means top quarter of what is actually trading. It is not a prediction.</li>
    <li><b>Entry, not Price.</b> Price is a daily batch a day or two behind. Entry is the cheapest Near Mint English copy on the shelf now, shipped — what you would pay.</li>
    <li><b>vs sold</b> is timing. Red: sellers asking more than buyers have paid. Green: the reverse. A great card can be listed ahead of itself.</li>
    <li><b>Budget</b> turns the ranking into positions — copies, cost, what limited it — with a per-card cap so one card cannot eat the whole thing. It is arithmetic on your number.</li>
    <li><b>Tap a row</b> for the case, what would break it, the live shelf, and your position if you hold it. <b>Star</b> a card to keep it on your watchlist; enter copies and cost and the row flags the day the trend breaks.</li>
    <li><b>Screened out</b> at the bottom lists every card that failed a gate and why. Nothing is dropped silently.</li>
  </ol>
</details>

<div class="rej">{_rejected_table(rejected)}</div>

<footer>
  <p><b>Market Haro</b> is published by GUNDECK.AI for its subscribers. Every number on this page describes what a card has already done. Nothing here is a forecast, a recommendation, or financial advice, and nothing knows <em>why</em> a price is moving — bans, reprints, rotation and tournament results end runs and are invisible in price data. Trading cards can lose value. Your watchlist and positions are saved only in this browser. Prices from tcgapi.dev under commercial licence · © GUNDECK.AI</p>
</footer>
</div>
<div id="tip" role="tooltip"></div>
<script type="application/json" id="haro-data">{payload}</script>
<script>{JS}</script>
</body></html>"""


def write(html: str, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p
