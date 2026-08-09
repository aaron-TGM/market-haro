"""Render the radar as one self-contained HTML file.

Everything (CSS, JS, data) is inlined so the file can be emailed, dropped in
Dropbox, or opened from disk with no server. Card images are the only remote
asset, loaded lazily from TCGplayer's CDN.

Layout: stat tiles -> filters -> two breadth charts -> the ranked table.
The charts and the table read from the same filtered set, so narrowing to a
rarity or a price band re-draws everything together.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .signals import explain
from .snipe import explain as explain_snipe

# Palette: validated default categorical slots 1-3 (all-pairs, both modes).
# sustained = blue, spike = orange, breakout = aqua. Every badge also carries a
# text label, so identity never rests on color alone. Charts are single-series
# and use the sequential blue, so they need no legend.
CSS = """
*,*::before,*::after{box-sizing:border-box}
.viz-root{
  color-scheme:light;
  --surface-1:#fcfcfb; --plane:#f9f9f7;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
  --series-1:#2a78d6; --series-2:#eb6834; --series-3:#1baf7a;
  --bar:#2a78d6; --bar-soft:#9ec5f4;
  --up:#006300; --down:#d03b3b;
  --tint-1:rgba(42,120,214,0.12); --tint-2:rgba(235,104,52,0.12); --tint-3:rgba(27,175,122,0.14);
}
@media (prefers-color-scheme:dark){
  :root:where(:not([data-theme="light"])) .viz-root{
    color-scheme:dark;
    --surface-1:#1a1a19; --plane:#0d0d0d;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70;
    --bar:#3987e5; --bar-soft:#256abf;
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
  --bar:#3987e5; --bar-soft:#256abf;
  --up:#0ca30c; --down:#d03b3b;
  --tint-1:rgba(57,135,229,0.18); --tint-2:rgba(217,89,38,0.18); --tint-3:rgba(25,158,112,0.20);
}
html,body{margin:0;padding:0}
body{background:var(--plane);color:var(--text-primary);
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1420px;margin:0 auto;padding:28px 20px 72px}
header{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap}
h1{font-size:22px;font-weight:650;letter-spacing:-.01em;margin:0}
.sub{color:var(--text-secondary);font-size:13px;margin:3px 0 22px}
.hbtns{display:flex;gap:8px}
button.ghost{background:none;border:1px solid var(--border);border-radius:8px;
  color:var(--text-secondary);padding:5px 11px;cursor:pointer;font:inherit;font-size:12px}
button.ghost:hover{background:var(--surface-1);color:var(--text-primary)}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:13px 15px}
.tile .label{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted)}
.tile .value{font-size:26px;font-weight:600;margin-top:4px;line-height:1.1}
.tile .foot{font-size:12px;color:var(--text-secondary);margin-top:3px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.meter{height:4px;border-radius:2px;background:var(--grid);margin-top:8px;overflow:hidden}
.meter i{display:block;height:100%;background:var(--bar);border-radius:2px}

.panel{background:var(--surface-1);border:1px solid var(--border);border-radius:12px}
.filters{padding:13px 15px;margin-bottom:16px}
.frow{display:flex;gap:9px;flex-wrap:wrap;align-items:center}
.frow + .frow{margin-top:10px;padding-top:10px;border-top:1px solid var(--grid)}
.flabel{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);
  margin-right:2px;white-space:nowrap}
input[type=search],select,input[type=number]{background:var(--plane);color:var(--text-primary);
  border:1px solid var(--border);border-radius:8px;padding:6px 9px;font:inherit;font-size:13px}
input[type=search]{min-width:220px}
input[type=number]{width:82px}
select{max-width:260px}
.chip{border:1px solid var(--border);background:var(--plane);border-radius:999px;
  padding:5px 12px;font-size:12.5px;cursor:pointer;color:var(--text-secondary);user-select:none}
.chip:hover{color:var(--text-primary)}
.chip[aria-pressed="true"]{color:var(--text-primary);font-weight:600;border-color:currentColor}
.chip[data-sig="sustained"][aria-pressed="true"]{background:var(--tint-1)}
.chip[data-sig="spike"][aria-pressed="true"]{background:var(--tint-2)}
.chip[data-sig="breakout"][aria-pressed="true"]{background:var(--tint-3)}
.chip[data-band][aria-pressed="true"]{background:var(--tint-1)}
.count{color:var(--text-muted);font-size:12.5px;margin-left:auto;white-space:nowrap}

.charts{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px}
@media (max-width:900px){.charts{grid-template-columns:1fr}}
.chart{padding:14px 16px 16px}
.chart h3{font-size:13px;font-weight:620;margin:0 0 2px}
.chart .cap{font-size:11.5px;color:var(--text-muted);margin:0 0 12px}
.bars{display:flex;flex-direction:column;gap:2px}
.brow{display:grid;grid-template-columns:150px 1fr 42px;gap:8px;align-items:center}
.brow .bl{font-size:12px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;text-align:right}
.brow .bt{height:16px;background:var(--bar);border-radius:0 4px 4px 0;min-width:2px}
.brow .bv{font-size:12px;color:var(--text-secondary);font-variant-numeric:tabular-nums}
.brow.empty .bt{background:var(--grid)}
.chart .none{color:var(--text-muted);font-size:12.5px;padding:12px 0}
.board{margin-bottom:18px;overflow:hidden}
.board .bhead{display:flex;justify-content:space-between;align-items:baseline;gap:10px;
  flex-wrap:wrap;padding:14px 16px 10px}
.board h3{font-size:14px;font-weight:640;margin:0}
.board .cap{font-size:11.5px;color:var(--text-muted);margin:2px 0 0;max-width:70ch}
.board table td,.board table th{padding:7px 11px}
.mode{font-size:11px;padding:2.5px 8px;border-radius:999px;border:1px solid;font-weight:560;
  white-space:nowrap}
.mode.discount{color:var(--series-3);border-color:var(--series-3);background:var(--tint-3)}
.mode.squeeze{color:var(--series-2);border-color:var(--series-2);background:var(--tint-2)}
.thin{color:var(--series-2);font-weight:640}
.buy{font-size:12px;color:var(--series-1);text-decoration:none;white-space:nowrap;font-weight:560}
.buy:hover{text-decoration:underline}
.chead{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap}
.seg{display:flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;flex:none}
.segb{background:var(--plane);border:0;border-right:1px solid var(--border);padding:5px 10px;
  font:inherit;font-size:12px;color:var(--text-secondary);cursor:pointer}
.segb:last-child{border-right:0}
.segb:hover{color:var(--text-primary)}
.segb[aria-pressed="true"]{background:var(--tint-1);color:var(--text-primary);font-weight:600}

h2{font-size:15px;font-weight:620;margin:28px 0 10px}
h2 .hint{font-weight:400;color:var(--text-muted);font-size:12.5px;margin-left:8px}
.tablewrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:8px 11px;border-bottom:1px solid var(--grid);vertical-align:middle}
thead th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted);
  font-weight:600;white-space:nowrap;position:sticky;top:0;background:var(--surface-1);z-index:2}
thead th[data-sort]{cursor:pointer}
thead th[data-sort]:hover{color:var(--text-secondary)}
thead th[aria-sort=descending]::after{content:"\\2193";margin-left:5px;opacity:.75}
thead th[aria-sort=ascending]::after{content:"\\2191";margin-left:5px;opacity:.75}
tbody tr:hover{background:var(--plane)}
tbody tr:last-child td{border-bottom:none}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rank{color:var(--text-muted);font-variant-numeric:tabular-nums;width:36px}
.who{display:flex;gap:10px;align-items:center;min-width:240px}
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
.scorebar{height:3px;border-radius:2px;background:var(--bar);margin-top:3px}
.why{color:var(--text-secondary);font-size:12px;min-width:150px;max-width:220px}
.empty{padding:36px;text-align:center;color:var(--text-muted)}
.more{display:flex;gap:10px;align-items:center;justify-content:center;padding:14px}
footer{margin-top:34px;color:var(--text-muted);font-size:12px;line-height:1.7}
footer code{background:var(--surface-1);border:1px solid var(--border);padding:1px 5px;border-radius:4px}
@media (max-width:1000px){.why,.col-listings{display:none}}
@media (max-width:820px){.wrap{padding:20px 12px 48px}.brow{grid-template-columns:110px 1fr 36px}}
"""

JS = r"""
const DATA = JSON.parse(document.getElementById('radar-data').textContent);
const BANDS = [
  {key:'u5',   label:'Under $5',   min:0,    max:5},
  {key:'5-20', label:'$5-20',      min:5,    max:20},
  {key:'20-100',label:'$20-100',   min:20,   max:100},
  {key:'o100', label:'$100+',      min:100,  max:Infinity},
];
const state = {q:'', sigs:new Set(), bands:new Set(), set:'', rarity:'', type:'', printing:'',
               min:null, max:null, sort:'score', dir:-1, limit:50, dim:'band',
               maxCopies:null, gapDir:''};

const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => v==null ? '—' : '$' + (v>=1000 ? v.toLocaleString(undefined,{maximumFractionDigits:0}) : v.toFixed(2));
const pct = v => {
  if (v==null) return '<span class="flat">—</span>';
  const cls = v > 0.05 ? 'up' : (v < -0.05 ? 'down' : 'flat');
  return `<span class="${cls}">${v>0?'+':''}${v.toFixed(1)}%</span>`;
};

const gapCell = r => {
  if (r.gap_pct == null) return '<span class="flat">—</span>';
  if (r.gap_pct > 0) return `<span class="up">+${r.gap_pct.toFixed(0)}%</span>`;
  const m = r.floor_multiple;
  return `<span class="down">${m ? m.toFixed(1)+'\u00d7' : r.gap_pct.toFixed(0)+'%'}</span>`;
};

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
  const lx = w-p, ly = h-p - ((ys[ys.length-1]-lo)/span)*(h-2*p);
  const dir = ys[ys.length-1] >= ys[0] ? 'rising' : 'falling';
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img"
    aria-label="${series.length} points, ${dir}, latest $${ys[ys.length-1].toFixed(2)}">
    <polyline points="${pts}" fill="none" stroke="var(--series-1)" stroke-width="2"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="2.5" fill="var(--series-1)"
      stroke="var(--surface-1)" stroke-width="2"/></svg>`;
}

function rowHTML(r, i){
  const badges = (r.signals||[]).map(s=>`<span class="badge ${s}">${s}</span>`).join('');
  const url = r.tcgplayer_url || (r.tcgplayer_id ? 'https://www.tcgplayer.com/product/'+r.tcgplayer_id : null);
  const nm = url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(r.name)}</a>` : esc(r.name);
  const img = r.image_url ? `<img src="${esc(r.image_url)}" alt="" loading="lazy" decoding="async">` : '<img alt="">';
  const meta = [r.set_name, r.number, r.rarity, r.printing!=='Normal'?r.printing:null]
    .filter(Boolean).map(esc).join(' · ');
  return `<tr>
    <td class="rank">${i+1}</td>
    <td><div class="who">${img}<div><div class="nm">${nm}</div>
      <div class="meta">${meta}</div></div></div></td>
    <td class="num">${money(r.market_price)}</td>
    <td class="num">${pct(r.change_24h)}</td>
    <td class="num">${pct(r.change_7d)}</td>
    <td class="num">${pct(r.change_30d)}</td>
    <td>${sparkline(r.series)}</td>
    <td class="num">${r.floor_low==null?'<span class="flat">—</span>':money(r.floor_low)}</td>
    <td class="num">${r.copies==null?'<span class="flat">—</span>'
      :`<span class="${r.copies<=DATA.thin?'thin':''}">${r.copies}</span>`}</td>
    <td class="num">${gapCell(r)}</td>
    <td class="num col-listings">${r.total_listings==null?'—':r.total_listings}</td>
    <td><div class="badges">${badges}</div></td>
    <td class="num"><div class="score">${r.score.toFixed(0)}</div>
      <div class="scorebar" style="width:${Math.max(4, r.score)}%"></div></td>
    <td class="why">${esc(r.why||'')}</td>
  </tr>`;
}

const SORTERS = {
  score:r=>r.score, price:r=>r.market_price ?? -1, c24:r=>r.change_24h ?? -1e9,
  c7:r=>r.change_7d ?? -1e9, c30:r=>r.change_30d ?? -1e9,
  listings:r=>r.total_listings ?? -1, name:r=>(r.name||'').toLowerCase(),
  floor:r=>r.floor_low ?? -1, copies:r=>r.copies ?? 1e9, gap:r=>r.gap_pct ?? -1e9,
  snipe:r=>r.snipe_score ?? -1,
};

function inBands(r){
  if (!state.bands.size) return true;
  const p = r.market_price;
  if (p == null) return false;
  return [...state.bands].some(k=>{ const b = BANDS.find(x=>x.key===k); return p>=b.min && p<b.max; });
}

function filtered(){
  const q = state.q.trim().toLowerCase();
  return DATA.rows.filter(r=>{
    if (q && !((r.name||'').toLowerCase().includes(q) || (r.set_name||'').toLowerCase().includes(q)
               || (r.number||'').toLowerCase().includes(q))) return false;
    if (state.set && r.set_name !== state.set) return false;
    if (state.rarity && (r.rarity||'—') !== state.rarity) return false;
    if (state.type && r.product_type !== state.type) return false;
    if (state.printing && r.printing !== state.printing) return false;
    if (state.min != null && !(r.market_price >= state.min)) return false;
    if (state.max != null && !(r.market_price <= state.max)) return false;
    if (!inBands(r)) return false;
    if (state.sigs.size && !(r.signals||[]).some(s=>state.sigs.has(s))) return false;
    if (state.maxCopies != null && !(r.copies != null && r.copies <= state.maxCopies)) return false;
    if (state.gapDir === 'under' && !(r.gap_pct > 0)) return false;
    if (state.gapDir === 'over'  && !(r.gap_pct < 0)) return false;
    return true;
  });
}

function barChart(el, entries, caption){
  if (!entries.length){ el.innerHTML = '<p class="none">Nothing in view.</p>'; return; }
  const max = Math.max(...entries.map(e=>e[1])) || 1;
  el.innerHTML = entries.map(([label, v])=>`
    <div class="brow${v?'':' empty'}">
      <span class="bl" title="${esc(label)}">${esc(label)}</span>
      <span class="bt" style="width:${Math.max(2,(v/max)*100)}%"></span>
      <span class="bv">${v}</span>
    </div>`).join('');
}

function drawCharts(rows){
  const bySet = {};
  rows.forEach(r=>{ const k=r.set_name||'—'; bySet[k]=(bySet[k]||0)+1; });
  const setEntries = Object.entries(bySet).sort((a,b)=>b[1]-a[1]).slice(0,10);
  barChart(document.getElementById('chart-sets'), setEntries);

  let entries;
  if (state.dim === 'band'){
    entries = BANDS.map(b=>[b.label, rows.filter(r=>r.market_price>=b.min && r.market_price<b.max).length]);
  } else {
    const key = state.dim === 'rarity' ? 'rarity' : 'printing';
    const g = {};
    rows.forEach(r=>{ const k=r[key]||'—'; g[k]=(g[k]||0)+1; });
    entries = Object.entries(g).sort((a,b)=>b[1]-a[1]).slice(0,10);
  }
  barChart(document.getElementById('chart-bands'), entries);
}

function apply(){
  let rows = filtered();
  const key = SORTERS[state.sort] || SORTERS.score;
  rows.sort((a,b)=>{ const av=key(a), bv=key(b); return av===bv ? 0 : (av>bv?1:-1)*state.dir; });

  drawCharts(rows);

  const shown = rows.slice(0, state.limit);
  document.getElementById('tbody').innerHTML = shown.length
    ? shown.map(rowHTML).join('')
    : '<tr><td colspan="14" class="empty">Nothing matches those filters.</td></tr>';

  document.getElementById('count').textContent =
    `${shown.length ? '1–'+shown.length : '0'} of ${rows.length} matching · ${DATA.rows.length} tracked`;

  const more = document.getElementById('more');
  if (rows.length > shown.length){
    more.style.display = 'flex';
    document.getElementById('more-n').textContent = Math.min(50, rows.length - shown.length);
    document.getElementById('more-all').textContent = `Show all ${rows.length}`;
  } else { more.style.display = 'none'; }

  document.querySelectorAll('thead th[data-sort]').forEach(th=>{
    th.setAttribute('aria-sort', th.dataset.sort===state.sort
      ? (state.dir===-1?'descending':'ascending') : 'none');
  });
  window.__view = rows;
}

function reset(){
  Object.assign(state, {q:'', sigs:new Set(), bands:new Set(), set:'', rarity:'', type:'',
                        printing:'', min:null, max:null, limit:50, maxCopies:null, gapDir:''});
  const mc = document.getElementById('maxcopies'); if (mc) mc.value = '';
  document.getElementById('q').value = '';
  ['setfilter','rarityfilter','typefilter','printfilter'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('minp').value = '';
  document.getElementById('maxp').value = '';
  document.querySelectorAll('.chip').forEach(c=>c.setAttribute('aria-pressed','false'));
  apply();
}

function exportCSV(){
  const cols = ['score','snipe_score','snipe_mode','name','set_name','number','rarity','printing',
                'product_type','market_price','floor_low','floor_ship','copies','gap_pct',
                'change_24h','change_7d','change_30d','total_listings','signals','tcgplayer_url'];
  const esc2 = v => {
    const s = Array.isArray(v) ? v.join('|') : (v==null?'':String(v));
    return /[",\n]/.test(s) ? '"'+s.replace(/"/g,'""')+'"' : s;
  };
  const body = [cols.join(',')].concat((window.__view||[]).map(r=>cols.map(c=>esc2(r[c])).join(','))).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([body], {type:'text/csv'}));
  a.download = `gundam-radar-${DATA.obs_date}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

document.getElementById('q').addEventListener('input', e=>{state.q=e.target.value; state.limit=50; apply();});
[['setfilter','set'],['rarityfilter','rarity'],['typefilter','type'],['printfilter','printing']]
  .forEach(([id,k])=>document.getElementById(id)
    .addEventListener('change', e=>{state[k]=e.target.value; state.limit=50; apply();}));
['minp','maxp'].forEach((id,i)=>document.getElementById(id).addEventListener('input', e=>{
  const v = e.target.value === '' ? null : Number(e.target.value);
  state[i===0?'min':'max'] = (v==null || Number.isNaN(v)) ? null : v;
  state.limit=50; apply();
}));
document.querySelectorAll('.chip[data-sig]').forEach(c=>c.addEventListener('click', ()=>{
  const s=c.dataset.sig;
  state.sigs.has(s) ? state.sigs.delete(s) : state.sigs.add(s);
  c.setAttribute('aria-pressed', state.sigs.has(s)); state.limit=50; apply();
}));
document.querySelectorAll('.chip[data-band]').forEach(c=>c.addEventListener('click', ()=>{
  const b=c.dataset.band;
  state.bands.has(b) ? state.bands.delete(b) : state.bands.add(b);
  c.setAttribute('aria-pressed', state.bands.has(b)); state.limit=50; apply();
}));
document.querySelectorAll('thead th[data-sort]').forEach(th=>th.addEventListener('click', ()=>{
  const k=th.dataset.sort;
  if (state.sort===k) state.dir*=-1; else {state.sort=k; state.dir = k==='name' ? 1 : -1;}
  apply();
}));
const mc = document.getElementById('maxcopies');
if (mc) mc.addEventListener('input', e=>{
  const v = e.target.value === '' ? null : Number(e.target.value);
  state.maxCopies = (v==null || Number.isNaN(v)) ? null : v; state.limit=50; apply();
});
document.querySelectorAll('.chip[data-gap]').forEach(c=>c.addEventListener('click', ()=>{
  const g = c.dataset.gap;
  state.gapDir = state.gapDir === g ? '' : g;
  document.querySelectorAll('.chip[data-gap]').forEach(x=>
    x.setAttribute('aria-pressed', x.dataset.gap === state.gapDir));
  state.limit=50; apply();
}));
document.querySelectorAll('.segb').forEach(b=>b.addEventListener('click', ()=>{
  state.dim = b.dataset.dim;
  document.querySelectorAll('.segb').forEach(x=>x.setAttribute('aria-pressed', x===b));
  apply();
}));
document.getElementById('more-btn').addEventListener('click', ()=>{state.limit+=50; apply();});
document.getElementById('more-all').addEventListener('click', ()=>{state.limit=1e9; apply();});
document.getElementById('reset').addEventListener('click', reset);
document.getElementById('csv').addEventListener('click', exportCSV);

const themeBtn = document.getElementById('theme');
const osDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
if (!document.documentElement.getAttribute('data-theme'))
  themeBtn.textContent = osDark ? 'Light mode' : 'Dark mode';
themeBtn.addEventListener('click', ()=>{
  const next = document.documentElement.getAttribute('data-theme')==='dark' ? 'light' : 'dark';
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
        "rarity": r.get("rarity") or "—",
        "printing": r.get("printing") or "Normal",
        "product_type": r.get("product_type") or "Cards",
        "image_url": r.get("image_url"),
        "tcgplayer_id": r.get("tcgplayer_id"),
        "tcgplayer_url": r.get("tcgplayer_url"),
        "market_price": r.get("market_price"),
        "change_24h": r.get("change_24h"),
        "change_7d": r.get("change_7d"),
        "change_30d": r.get("change_30d"),
        "total_listings": r.get("total_listings"),
        "sales_volume": r.get("sales_volume"),
        "floor_low": r.get("floor_low"),
        "floor_ship": r.get("floor_ship"),
        "copies": r.get("copies"),
        "gap_pct": r.get("gap_pct"),
        "floor_multiple": r.get("floor_multiple"),
        "snipe_score": r.get("snipe_score"),
        "snipe_mode": r.get("snipe_mode"),
        "score": r.get("score", 0.0),
        "signals": r.get("signals", []),
        "why": explain(r) if r.get("signals") else "",
        "series": [[d, round(v, 2)] for d, v in (r.get("series") or [])],
    }


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


def render(
    ranked: Sequence[dict],
    *,
    obs_date: str,
    stats: dict[str, Any],
    top_n: int = 400,
    fallers: Sequence[dict] = (),
    watchlist: Sequence[dict] = (),
    market: dict[str, Any] | None = None,
    scope_note: str = "",
    snipe_board: Sequence[dict] = (),
    thin_supply: int = 12,
) -> str:
    """`top_n` caps how many rows are embedded; the page itself pages through them."""
    market = market or {}
    scored = [r for r in ranked if not r.get("filtered")]
    flagged = [r for r in scored if r.get("signals")]

    # Embed flagged first, then the rest of the scored rows up to the cap, so the
    # table can be browsed past the calls without a second file.
    ordered = flagged + [r for r in scored if not r.get("signals")]
    rows = [_row_payload(r) for r in ordered[:top_n]]

    n_sus = sum(1 for r in flagged if "sustained" in r["signals"])
    n_spk = sum(1 for r in flagged if "spike" in r["signals"])
    n_brk = sum(1 for r in flagged if "breakout" in r["signals"])
    top = flagged[0] if flagged else None

    sets = sorted({r["set_name"] for r in rows if r.get("set_name")})
    rarities = sorted({r["rarity"] for r in rows if r.get("rarity")})
    printings = sorted({r["printing"] for r in rows if r.get("printing")})
    types = sorted({r["product_type"] for r in rows if r.get("product_type")})

    breadth_up = market.get("up_7d")
    breadth_total = market.get("priced")
    breadth_pct = (
        round(100 * breadth_up / breadth_total) if breadth_up and breadth_total else None
    )

    payload = (
        json.dumps({"rows": rows, "obs_date": obs_date, "thin": thin_supply},
                   separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )

    def static_table(title: str, hint: str, data: Sequence[dict]) -> str:
        if not data:
            return ""
        body = "".join(_static_row(r, i) for i, r in enumerate(data))
        return f"""
  <h2>{_esc(title)}<span class="hint">{_esc(hint)}</span></h2>
  <div class="panel tablewrap"><table><thead><tr>
    <th class="rank">#</th><th>Card</th><th class="num">Market</th>
    <th class="num">24h</th><th class="num">7d</th><th class="num">30d</th>
    <th>Trend</th><th class="num">Floor</th><th class="num">Copies</th>
    <th class="num col-listings">Listings</th><th>Signals</th>
    <th class="num">Score</th><th class="why">Note</th>
  </tr></thead><tbody>{body}</tbody></table></div>"""

    breadth_tile = ""
    if breadth_pct is not None:
        breadth_tile = f"""
  <div class="tile"><div class="label">Market breadth</div>
    <div class="value">{breadth_pct}%</div>
    <div class="foot">{breadth_up:,} of {breadth_total:,} up over 7d</div>
    <div class="meter"><i style="width:{breadth_pct}%"></i></div></div>"""

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
    <p class="sub">Market snapshot {_esc(obs_date)} · {len(rows):,} products in view ·
      {stats.get('snapshot_dates', 0)} day{'' if stats.get('snapshot_dates', 0) == 1 else 's'}
      of own snapshots · source: tcgapi.dev{(' · ' + _esc(scope_note)) if scope_note else ''}</p>
  </div>
  <div class="hbtns">
    <button class="ghost" id="csv">Export CSV</button>
    <button class="ghost" id="theme">Dark mode</button>
  </div>
</header>

<div class="tiles">
  <div class="tile"><div class="label">Cards flagged</div>
    <div class="value">{len(flagged)}</div>
    <div class="foot">of {len(scored):,} that cleared the filters</div></div>
  <div class="tile"><div class="label">Sustained climb</div>
    <div class="value">{n_sus}</div><div class="foot">up over 7d and 30d</div></div>
  <div class="tile"><div class="label">24h spike</div>
    <div class="value">{n_spk}</div><div class="foot">sudden jump today</div></div>
  <div class="tile"><div class="label">Breakout</div>
    <div class="value">{n_brk}</div><div class="foot">above its own prior range</div></div>
  <div class="tile"><div class="label">Top mover</div>
    <div class="value">{(f"{top['change_7d']:+.0f}%" if top and top.get('change_7d') is not None else '—')}</div>
    <div class="foot">{_esc(top['name']) if top else 'nothing flagged today'}</div></div>{breadth_tile}
</div>

{_snipe_board(snipe_board, thin_supply)}

<div class="panel filters">
  <div class="frow">
    <input type="search" id="q" placeholder="Search card, set or number…" aria-label="Search">
    <select id="setfilter" aria-label="Set">{_options(sets, 'All sets')}</select>
    <select id="rarityfilter" aria-label="Rarity">{_options(rarities, 'All rarities')}</select>
    <select id="printfilter" aria-label="Printing">{_options(printings, 'All printings')}</select>
    <select id="typefilter" aria-label="Product type">{_options(types, 'Cards + sealed')}</select>
    <button class="ghost" id="reset">Reset</button>
  </div>
  <div class="frow">
    <span class="flabel">Value</span>
    <button class="chip" data-band="u5" aria-pressed="false">Under $5</button>
    <button class="chip" data-band="5-20" aria-pressed="false">$5–20</button>
    <button class="chip" data-band="20-100" aria-pressed="false">$20–100</button>
    <button class="chip" data-band="o100" aria-pressed="false">$100+</button>
    <input type="number" id="minp" placeholder="min $" min="0" step="0.5" aria-label="Minimum price">
    <input type="number" id="maxp" placeholder="max $" min="0" step="0.5" aria-label="Maximum price">
    <span class="flabel" style="margin-left:12px">Supply</span>
    <input type="number" id="maxcopies" placeholder="max copies" min="1" step="1"
           aria-label="Maximum copies listed" style="width:110px">
    <button class="chip" data-gap="under" aria-pressed="false">Floor under market</button>
    <button class="chip" data-gap="over" aria-pressed="false">Floor over market</button>
    <span class="flabel" style="margin-left:12px">Signal</span>
    <button class="chip" data-sig="sustained" aria-pressed="false">Sustained</button>
    <button class="chip" data-sig="spike" aria-pressed="false">Spike</button>
    <button class="chip" data-sig="breakout" aria-pressed="false">Breakout</button>
    <span class="count" id="count"></span>
  </div>
</div>

<div class="charts">
  <div class="panel chart">
    <h3>Where the movement is</h3>
    <p class="cap">Products in view, by set — top 10. Updates with the filters.</p>
    <div class="bars" id="chart-sets"></div>
  </div>
  <div class="panel chart">
    <div class="chead">
      <div><h3>Breakdown</h3>
      <p class="cap">Where in the market the action sits.</p></div>
      <div class="seg" role="group" aria-label="Breakdown dimension">
        <button class="segb" data-dim="band" aria-pressed="true">Price band</button>
        <button class="segb" data-dim="rarity" aria-pressed="false">Rarity</button>
        <button class="segb" data-dim="printing" aria-pressed="false">Printing</button>
      </div>
    </div>
    <div class="bars" id="chart-bands"></div>
  </div>
</div>

<div class="panel tablewrap"><table><thead><tr>
  <th class="rank">#</th>
  <th data-sort="name">Card</th>
  <th class="num" data-sort="price">Market</th>
  <th class="num" data-sort="c24">24h</th>
  <th class="num" data-sort="c7">7d</th>
  <th class="num" data-sort="c30">30d</th>
  <th>Trend</th>
  <th class="num" data-sort="floor">Floor</th>
  <th class="num" data-sort="copies">Copies</th>
  <th class="num" data-sort="gap">Gap</th>
  <th class="num col-listings" data-sort="listings">Listings</th>
  <th>Signals</th>
  <th class="num" data-sort="score" aria-sort="descending">Score</th>
  <th class="why">Note</th>
</tr></thead><tbody id="tbody"></tbody></table>
<div class="more" id="more" style="display:none">
  <button class="ghost" id="more-btn">Show <span id="more-n">50</span> more</button>
  <button class="ghost" id="more-all">Show all</button>
</div></div>

{static_table("Watchlist", "tracked regardless of score", [_row_payload(r) for r in watchlist])}
{static_table("Biggest fallers", "context — and where dips show up", [_row_payload(r) for r in fallers])}

<footer>
  <p><strong>Reading this:</strong> Score is a 0–100 blend of the three detectors, nudged up for
  higher-priced cards and cards with recorded sales. It ranks attention, not conviction.
  Trend sparklines mix API history with your own daily snapshots, so they get denser the longer
  you run it. Export CSV writes exactly what the current filters show.</p>
  <p>Tune thresholds in <code>config.yaml</code> · regenerate with
  <code>python -m radar run</code></p>
</footer>
</div>
<script type="application/json" id="radar-data">{payload}</script>
<script>{JS}</script>
</body></html>"""


def _gap_cell(r: dict) -> str:
    """Discount reads as a percentage off; a squeeze reads as a multiple."""
    gap = r.get("gap_pct")
    if gap is None:
        return '<span class="flat">—</span>'
    if gap > 0:
        return f'<span class="up">+{gap:.0f}%</span>'
    mult = r.get("floor_multiple")
    body = f"{mult:.1f}&times;" if mult else f"{gap:.0f}%"
    return f'<span class="down">{body}</span>'


def _snipe_board(board: Sequence[dict], thin: int) -> str:
    """The buy list: live listing floor vs the daily batch price, and how many copies."""
    if not board:
        return ""
    rows = []
    for i, r in enumerate(board):
        mode = r.get("snipe_mode") or ""
        gap = r.get("gap_pct")
        copies = r.get("copies")
        low, ship = r.get("floor_low"), r.get("floor_ship")
        url = r.get("tcgplayer_url") or (
            f"https://www.tcgplayer.com/product/{r['tcgplayer_id']}" if r.get("tcgplayer_id") else None
        )
        copies_cell = (
            "—" if copies is None
            else (f'<span class="thin">{copies}</span>' if copies <= thin else str(copies))
        )
        meta = " · ".join(
            _esc(x) for x in [r.get("set_name"), r.get("number"),
                              r.get("printing") if r.get("printing") != "Normal" else None] if x
        )
        rows.append(f"""<tr>
      <td class="rank">{i + 1}</td>
      <td><div class="who"><div><div class="nm">{_esc(r.get('name'))}</div>
        <div class="meta">{meta}</div></div></div></td>
      <td class="num">{'—' if r.get('market_price') is None else f"${r['market_price']:,.2f}"}</td>
      <td class="num">{'—' if low is None else f"${low:,.2f}"}</td>
      <td class="num">{'—' if ship is None else f"${ship:,.2f}"}</td>
      <td class="num">{copies_cell}</td>
      <td class="num">{_gap_cell(r)}</td>
      <td><span class="mode {mode}">{mode}</span></td>
      <td class="num score">{r.get('snipe_score', 0):.0f}</td>
      <td class="why">{_esc(explain_snipe(r))}</td>
      <td>{f'<a class="buy" href="{_esc(url)}" target="_blank" rel="noopener">Open &rarr;</a>' if url else ''}</td>
    </tr>""")

    return f"""
<div class="panel board">
  <div class="bhead">
    <div><h3>Snipe board</h3>
    <p class="cap">Live Near&nbsp;Mint listing floor vs. the daily batch market price, with how many
    copies are actually listed. <strong>discount</strong> = copies sitting under the recorded price.
    <strong>squeeze</strong> = the cheap copies are gone and the batch price hasn't caught up.
    Orange copy counts are {thin} or fewer — one buyer can clear that shelf.</p></div>
  </div>
  <div class="tablewrap"><table><thead><tr>
    <th class="rank">#</th><th>Card</th><th class="num">Market</th><th class="num">Floor</th>
    <th class="num">Shipped</th><th class="num">Copies</th><th class="num">Gap</th>
    <th>Setup</th><th class="num">Snipe</th><th class="why">Read</th><th></th>
  </tr></thead><tbody>{''.join(rows)}</tbody></table></div>
</div>"""


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
    printing = r.get("printing")
    meta = " · ".join(
        _esc(x)
        for x in [r.get("set_name"), r.get("number"), r.get("rarity"),
                  printing if printing not in (None, "Normal") else None]
        if x
    )
    return f"""<tr>
  <td class="rank">{i + 1}</td>
  <td><div class="who">{img}<div><div class="nm">{name}</div>
    <div class="meta">{meta}</div></div></div></td>
  <td class="num">{'—' if mp is None else f'${mp:,.2f}'}</td>
  <td class="num">{pct(r.get('change_24h'))}</td>
  <td class="num">{pct(r.get('change_7d'))}</td>
  <td class="num">{pct(r.get('change_30d'))}</td>
  <td>{_spark_svg(r.get('series'))}</td>
  <td class="num">{'—' if r.get('floor_low') is None else f"${r['floor_low']:,.2f}"}</td>
  <td class="num">{'—' if r.get('copies') is None else r['copies']}</td>
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
