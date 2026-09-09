"""Market Haro -- the subscriber-facing screen. One self-contained HTML file.

THE SHAPE OF THE PAGE, AND WHY

A paying reader wants to look, decide, close the tab. So the page is three
things in order -- the budget tool, the ranking as rich rows with a large card
image and a large 90-day chart, and a detail panel on click -- and everything
that explains the method lives in tooltips and one collapsed "how to read".

The v3 pass (this file) was a usability review from a person's point of view:

  - Card art is embedded in the file (radar/art.py). The CDN was never the
    problem; sandboxed previews were. Art is 120x168 in the row, 200x280 in
    the detail, and a card that has no image gets a labelled frame, never a
    broken-image glyph.
  - Filters are two layers. What you touch every day -- search, the three
    views, sort -- is one row. Everything else -- set, rarity, price, score,
    sales -- is behind one "Filters" button that shows how many are on. The
    "only what fits" checkbox is gone; that was the Sized view wearing a
    second hat.
  - The detail panel reads top-down like a card, not a spreadsheet: art, the
    name, three verdict chips (timing, trend, exit), four hero numbers, then
    the case and what would break it as a callout, then score / shelf / your
    money / checklist as four boxes. Colour is on the verdicts and signed
    numbers only, so it means something when it appears.
  - The "since last issue" panel is gone from the page; that comparison is
    the email digest's job.

The layout rules come from the dataviz method, applied to a screen that is
mostly one line chart repeated 140 times: a 2px line with a 10% area wash and
a ringed end marker, a crosshair readout on hover; signed deltas carry their
sign as well as their colour; one hero figure per view.

WHAT IS THERE FOR SUBSCRIBERS

  Watchlist. Star a card; enter copies and cost in the detail panel; the row
  shows unrealised P&L against today's price and flags the moment the trend
  breaks (weeks-up under 50% or a 7-day fall past 10%). Stored in the reader's
  browser only -- the page is static and the same URL every day, so it persists
  across issues without a server knowing anything.

  Rank movement. Each row shows where it sat in the previous issue.

  Release marks. Every chart carries a dashed mark where a set released --
  GD05, a wave of starter decks -- read from the API's own release calendar,
  so a reader can see how price responded to supply. Days that moved more
  than 15% get a ring. Nothing here is hand-maintained (radar/releases.py).

Everything the JS computes -- sizing, the plan summary, sorting -- has a Python
twin or a Python source of truth; nothing is decided on the page that the tests
cannot check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .dashboard import CHECKLIST, _esc, _rejected_table, _row_payload
from .sealed import CHECKLIST as SEALED_CHECKLIST

# --------------------------------------------------------------------------
# Styles. Tokens are the gundeck.ai palette; everything else is new.
# --------------------------------------------------------------------------
CSS = r"""
.viz-root{
  --bg:oklch(6.5% .008 220); --surface:oklch(9% .01 220); --surface-2:oklch(12% .012 220);
  --surface-3:oklch(15% .014 220);
  --text:oklch(94% .04 85); --text-muted:oklch(62% .02 85); --accent:oklch(78% .18 65);
  --accent-dim:oklch(60% .14 65); --accent-wash:oklch(78% .18 65 / .12);
  --border:oklch(20% .04 65); --border-2:oklch(28% .04 65);
  --up:oklch(68% .18 145); --up-wash:oklch(68% .18 145 / .14);
  --down:oklch(60% .22 25); --down-wash:oklch(60% .22 25 / .14);
  --warn:oklch(78% .18 65); --cyan:oklch(72% .16 200); --cyan-wash:oklch(72% .16 200 / .12);
  --r:2px;
  --mono:"TRT Terminal Mono","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);font:13px/1.5 var(--mono)}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
b{font-weight:700}
.wrap{max-width:1360px;margin:0 auto;padding:22px 20px 72px}
[hidden]{display:none!important}

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
  text-transform:uppercase;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.ghost:hover{border-color:var(--accent)}
.ghost.on{background:var(--accent);color:var(--bg);border-color:var(--accent)}
.ghost .badge{background:var(--accent);color:var(--bg);border-radius:9px;min-width:16px;height:16px;
  font-size:10px;display:inline-flex;align-items:center;justify-content:center;padding:0 5px}
.ghost.on .badge{background:var(--bg);color:var(--accent)}

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
.chart .rl{position:absolute;top:-1px;font-size:8.5px;letter-spacing:.06em;color:var(--text-muted);white-space:nowrap;
  transform:translateX(-50%);pointer-events:none;line-height:1}
.chart .rl.start{transform:none} .chart .rl.end{transform:translateX(-100%)}
.bigchart .chart .rl{font-size:10px;top:0}
.bigchart{margin-top:16px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:12px 14px 8px}
.bigchart .bl{display:flex;justify-content:space-between;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);margin-bottom:6px}
.bigchart .bl span:last-child{color:var(--text-muted);text-transform:none;letter-spacing:.04em}
.bigchart .chart svg{height:150px}
.ranges{display:inline-flex;border:1px solid var(--border-2);border-radius:var(--r);overflow:hidden}
.ranges button{background:transparent;color:var(--text-muted);border:0;padding:4px 10px;font:inherit;font-size:10px;letter-spacing:.08em;text-transform:uppercase;cursor:pointer}
.ranges button.on{background:var(--accent);color:var(--bg)} .ranges button[disabled]{opacity:.4;cursor:default}
.legend{display:flex;gap:16px;font-size:10px;color:var(--text-muted);margin-top:6px;letter-spacing:.04em}
.legend i{display:inline-block;width:14px;border-top:1px dashed var(--accent-dim);vertical-align:middle;margin-right:5px}
.legend b{display:inline-block;width:8px;height:8px;border:1.5px solid var(--warn);border-radius:50%;vertical-align:middle;margin-right:5px}
.note .nh{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
.note .nl{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);font-weight:700}
.note .nd{font-size:10.5px;color:var(--text-muted);letter-spacing:.06em}
.note .nb{font-size:14px;line-height:1.65;max-width:76ch}
.note .nb p{margin:0 0 10px} .note .nb p:last-child{margin-bottom:0}
.note .nb h3,.note .nb h4,.note .nb h5{margin:12px 0 4px;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent)}
.note .nb ul{margin:0 0 10px;padding-left:20px}
.portfolio{padding:10px 16px}
.pf{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;font-size:13px}
.pfl{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}
.pfv{font-weight:700;font-variant-numeric:tabular-nums} .pfv.muted{color:var(--text-muted);font-weight:400}
.pfv.pnl{font-size:16px}
.pf .ghost{margin-left:auto}
.sync{font-size:10.5px;letter-spacing:.06em;color:var(--text-muted);margin-top:6px} .sync.on{color:var(--up)}
.gindex{padding:12px 16px 10px}
.gindex[open]{padding-bottom:10px}
.gindex>summary .sc{color:var(--text);letter-spacing:.04em;text-transform:none;font-size:12px}
.gindex>summary .ixsv{font-size:15px;color:var(--text);margin-right:2px}
.gindex .ixhead{margin-top:12px}
.gindex .chart svg{height:120px}
.ixhead{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:8px}
.ixname{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);font-weight:700}
.ixwhat{font-size:11.5px;color:var(--text-muted);margin-top:2px}
.ixval{font-size:34px;font-weight:700;line-height:1.05;margin-top:2px;font-variant-numeric:tabular-nums}
.ixsub{font-size:10.5px;color:var(--text-muted);letter-spacing:.04em;margin-top:3px}
.ixchanges{display:flex;gap:8px}
.ixc{background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:6px 10px;min-width:64px;text-align:center}
.ixc .l{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted)}
.ixc .v{font-size:14px;font-weight:700;font-variant-numeric:tabular-nums}
.stale-feed{border-left:2px solid var(--down);font-size:13px}
.stale-feed b{color:var(--down)}

/* budget -- the hero -------------------------------------------------- */
.budget{display:grid;grid-template-columns:auto auto 1fr;gap:14px 22px;align-items:center}
.budget label{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted);
  display:flex;align-items:center;gap:8px}
.money-in{position:relative;display:inline-block}
.money-in::before{content:"$";position:absolute;left:12px;top:50%;transform:translateY(-50%);
  color:var(--text-muted);font-size:16px;pointer-events:none}
.budget input[type=number]{background:var(--bg);color:var(--text);border:1px solid var(--border-2);
  border-radius:var(--r);padding:9px 12px 9px 26px;font:inherit;font-size:16px;width:160px}
.budget input[type=number]:focus{outline:none;border-color:var(--accent)}
.plan-sum{font-size:14px;line-height:1.5}
.plan-sum .hero{font-size:24px;font-weight:700;color:var(--accent);margin-right:6px}
.plan-sum .conc{color:var(--warn)}
.plan-sum .muted{color:var(--text-muted);font-size:12px}

/* kpi strip ---------------------------------------------------------- */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:10px 12px}
.kpi .l{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted)}
.kpi .v{font-size:22px;font-weight:700;margin-top:2px;line-height:1.1}
.kpi .f{font-size:10px;color:var(--text-muted);margin-top:3px;text-transform:uppercase;letter-spacing:.06em}
.kpi.down .v{color:var(--down)} .kpi.up .v{color:var(--up)} .kpi.cyan .v{color:var(--cyan)}
a.kpi{display:block;color:inherit} a.kpi:hover{text-decoration:none;border-color:var(--accent-dim)}

/* toolbar: what you touch every day ----------------------------------- */
.toolbar{display:flex;flex-wrap:wrap;gap:8px 10px;align-items:center;margin:14px 0 0}
.toolbar input,.toolbar select,.filters input,.filters select{background:var(--bg);color:var(--text);
  border:1px solid var(--border-2);border-radius:var(--r);padding:8px 10px;font:inherit;font-size:12px}
.toolbar input:focus,.toolbar select:focus,.filters input:focus{outline:none;border-color:var(--accent)}
.toolbar input[type=search]{flex:1 1 220px;min-width:180px}
.toolbar .lbl,.filters .lbl{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted)}
.toolbar .count{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);margin-left:auto}
.views{display:inline-flex;border:1px solid var(--border-2);border-radius:var(--r);overflow:hidden}
.views button{background:transparent;color:var(--text-muted);border:0;padding:8px 12px;font:inherit;
  font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;cursor:pointer}
.views button.on{background:var(--accent);color:var(--bg)}
.sortbox{display:inline-flex;align-items:center;gap:6px}
.dirbtn{background:transparent;border:1px solid var(--border-2);border-radius:var(--r);color:var(--accent);
  width:34px;height:34px;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;padding:0}
.dirbtn:hover{border-color:var(--accent)}
.dirbtn svg{transition:transform .15s}
.dirbtn.asc svg{transform:rotate(180deg)}

/* filters: the second layer -------------------------------------------- */
.filters{margin:10px 0 0;padding:14px 16px}
.filters .frow{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:flex-start}
.filters .fgroup{display:flex;flex-direction:column;gap:6px}
.filters .fgroup .lbl{margin-bottom:0}
.filters .frow+.frow{margin-top:12px;padding-top:12px;border-top:1px dotted var(--border)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips button{background:transparent;border:1px solid var(--border-2);color:var(--text-muted);
  border-radius:var(--r);padding:5px 10px;font:inherit;font-size:10.5px;letter-spacing:.06em;cursor:pointer}
.chips button:hover{border-color:var(--accent)}
.chips button.on{color:var(--bg);background:var(--accent);border-color:var(--accent)}
.filters input[type=number]{width:96px}
.range{display:flex;align-items:center;gap:6px}
.range span{color:var(--text-muted)}
.filters .factions{margin-left:auto;align-self:flex-end}

/* the ranking -------------------------------------------------------- */
.rows{display:flex;flex-direction:column;gap:8px;margin-top:12px}
.row{display:grid;grid-template-columns:44px 120px minmax(180px,1.2fr) minmax(240px,1.6fr) auto 92px 96px 36px;
  gap:0 16px;align-items:center;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:10px 14px;cursor:pointer;position:relative}
.row:hover{border-color:var(--accent-dim)}
.row.open{border-color:var(--accent);border-bottom-color:transparent;border-radius:var(--r) var(--r) 0 0}
.row.sized{box-shadow:inset 3px 0 0 var(--accent)}
.row.watched .star{color:var(--accent)}
.rank{display:flex;flex-direction:column;align-items:center;gap:2px}
.rank .n{font-size:16px;font-weight:700;color:var(--accent)}
.rank .d{font-size:10px;color:var(--text-muted);white-space:nowrap}
.rank .d.up{color:var(--up)} .rank .d.down{color:var(--down)}
.art{width:120px;height:168px;border-radius:4px;overflow:hidden;background:var(--surface-2);
  display:flex;align-items:center;justify-content:center;position:relative;flex:none}
.art img{width:100%;height:100%;object-fit:cover;display:block}
.art .ph,.dart .ph{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:6px;padding:10px;text-align:center;border:1px dashed var(--border-2);border-radius:4px;
  font-size:9px;letter-spacing:.12em;color:var(--text-muted);text-transform:uppercase;line-height:1.4}
.art .ph b,.dart .ph b{font-size:11px;color:var(--text);letter-spacing:.04em;text-transform:none}
.dart .ph{font-size:10px;letter-spacing:.14em;gap:8px} .dart .ph b{font-size:14px}
.who .nm{font-size:16px;font-weight:700;line-height:1.25}
.who .nm a{color:var(--text)}
.who .meta{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);margin-top:4px}
.who .tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.tag{font-size:9px;letter-spacing:.1em;text-transform:uppercase;padding:2px 6px;
  border:1px solid var(--border-2);border-radius:var(--r);color:var(--accent);white-space:nowrap}
.tag.flag{color:var(--down);border-color:var(--down)}
.tag.pos{color:var(--cyan);border-color:var(--cyan)}
.tag.broke{color:var(--bg);background:var(--down);border-color:var(--down)}
.chart{position:relative}
.chart svg{display:block;width:100%;height:80px}
.chart .cap{display:flex;justify-content:space-between;font-size:9.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--text-muted);margin-top:2px}
.stats{display:grid;grid-template-columns:repeat(3,minmax(70px,auto));gap:6px 16px}
.stats .s .l{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted)}
.stats .s .v{font-size:14px;font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--text-muted)}
.score{text-align:center}
.score .n{font-size:28px;font-weight:700;color:var(--text);line-height:1}
.score.top .n{color:var(--accent)}
.score .bar{height:3px;background:var(--surface-2);border-radius:2px;margin-top:6px;overflow:hidden}
.score .bar i{display:block;height:100%;background:var(--text-muted)}
.score.top .bar i{background:var(--accent)}
.score .l{font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted);margin-top:4px}
.size{text-align:center}
.pill{display:inline-block;padding:5px 9px;border-radius:var(--r);font-size:11.5px;font-weight:700;
  background:var(--accent);color:var(--bg);white-space:nowrap}
.pill.none{background:transparent;color:var(--text-muted);border:1px solid var(--border);font-weight:400}
.size .l{font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted);margin-top:4px}
.star{background:transparent;border:0;color:var(--text-muted);cursor:pointer;line-height:0;padding:4px}
.star:hover{color:var(--accent)}

/* detail: reads top-down like a card ----------------------------------- */
.detail{background:var(--surface);border:1px solid var(--accent);border-top:0;
  border-radius:0 0 var(--r) var(--r);margin:-8px 0 0;padding:18px 18px 18px}
.dtop{display:grid;grid-template-columns:200px 1fr;gap:22px;align-items:start}
.dart{width:200px;height:280px;border-radius:6px;overflow:hidden;background:var(--surface-2);position:relative}
.dart img{width:100%;height:100%;object-fit:cover;display:block}
.dart .ph{font-size:10px}
.dhead .nm{font-size:22px;font-weight:700;line-height:1.2}
.dhead .nm a{color:var(--text)}
.dhead .meta{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-muted);margin-top:4px}
.verdicts{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 14px}
.vchip{display:inline-flex;flex-direction:column;gap:1px;padding:7px 11px;border-radius:var(--r);
  border:1px solid var(--border-2);background:var(--surface-2);min-width:150px}
.vchip .vt{font-size:12px;font-weight:700}
.vchip .vs{font-size:10px;letter-spacing:.06em;color:var(--text-muted)}
.vchip.good{border-color:var(--up);background:var(--up-wash)} .vchip.good .vt{color:var(--up)}
.vchip.bad{border-color:var(--down);background:var(--down-wash)} .vchip.bad .vt{color:var(--down)}
.vchip.warn{border-color:var(--warn);background:var(--accent-wash)} .vchip.warn .vt{color:var(--warn)}
.heroes{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:14px}
.hero-n{background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:9px 12px}
.hero-n .l{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted)}
.hero-n .v{font-size:21px;font-weight:700;line-height:1.15;margin-top:2px;font-variant-numeric:tabular-nums}
.hero-n .f{font-size:10px;color:var(--text-muted);margin-top:2px}
.hero-n.accent .v{color:var(--accent)}
.callout{border-left:3px solid var(--border-2);padding:8px 12px;margin:0 0 10px;font-size:12.5px;line-height:1.6;
  background:var(--surface-2);border-radius:0 var(--r) var(--r) 0}
.callout .cl{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted);display:block;margin-bottom:3px}
.callout.warn{border-left-color:var(--warn)} .callout.warn .cl{color:var(--warn)}
.callout.bad{border-left-color:var(--down)} .callout.bad .cl{color:var(--down)}
.callout.good{border-left-color:var(--up)} .callout.good .cl{color:var(--up)}
.dbtns{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
.cta{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--accent);padding:8px 14px;
  font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;border-radius:var(--r);background:var(--accent);color:var(--bg)}
.cta:hover{text-decoration:none;filter:brightness(1.1)}
.cta.quiet{background:transparent;color:var(--accent)}
.dgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:18px}
.dbox{background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:12px 14px}
.dbox h5{margin:0 0 10px;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);
  display:flex;align-items:center;gap:6px}
.dbox h5 .sub{color:var(--text-muted);font-weight:400;letter-spacing:.06em;text-transform:none;font-size:10.5px;margin-left:auto}
.kv{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:5px 0;
  border-bottom:1px dotted var(--border);font-size:12px}
.kv:last-child{border-bottom:0}
.kv .k{color:var(--text-muted)} .kv .vv{font-weight:700;font-variant-numeric:tabular-nums;text-align:right}
.big{font-size:20px;font-weight:700;margin:2px 0;line-height:1.2}
.sub2{color:var(--text-muted);font-size:11.5px;margin:0 0 6px;line-height:1.5}
.crow{display:grid;grid-template-columns:72px 1fr 34px;gap:8px;align-items:center;font-size:11px;margin:5px 0}
.crow .cl{color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;font-size:9.5px}
.crow .ct{height:7px;background:var(--surface-2);border-radius:2px;overflow:hidden}
.crow .ct i{display:block;height:100%;background:var(--text-muted)}
.crow.hi .ct i{background:var(--up)} .crow.lo .ct i{background:var(--down)}
.crow .cv{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
.crow.hi .cv{color:var(--up)} .crow.lo .cv{color:var(--down)}
.score-line{margin-bottom:10px}
.score-line .n{font-size:32px;font-weight:700;line-height:1;display:block} .score-line.top .n{color:var(--accent)}
.score-line .t{font-size:10px;color:var(--text-muted);letter-spacing:.04em;display:block;margin-top:4px}
.changes{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:10px}
.changes div{background:var(--surface-2);border-radius:var(--r);padding:6px 8px;text-align:center}
.changes .l{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted)}
.changes .v{font-size:13px;font-weight:700;font-variant-numeric:tabular-nums}
.pos-form{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:6px 0 8px}
.pos-form label{font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);display:block;margin-bottom:3px}
.pos-form input{width:100%;background:var(--surface);color:var(--text);border:1px solid var(--border-2);
  border-radius:var(--r);padding:7px 8px;font:inherit}
.pos-form input:focus{outline:none;border-color:var(--accent)}
.pnl{font-size:18px;font-weight:700}
.checklist{margin:0;padding-left:18px;font-size:11.5px;line-height:1.55;color:var(--text-muted)}
.checklist li{margin:4px 0} .checklist li::marker{color:var(--accent)}

/* misc --------------------------------------------------------------- */
.more{display:flex;justify-content:center;padding:14px 0 0}
.empty{padding:40px;text-align:center;color:var(--text-muted)}
#tip{position:fixed;z-index:50;max-width:340px;background:var(--surface-3);color:var(--text);
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
.playbook .lead{margin:0 0 10px;font-size:12.5px;line-height:1.6;color:var(--text-muted)}
.playbook .lead b{font-size:13px}
.playbook table{width:100%;border-collapse:collapse;font-size:12px}
.playbook th{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-muted);text-align:left;padding:6px;border-bottom:1px solid var(--border);font-weight:400}
.playbook th.grp{text-align:center;color:var(--accent);border-bottom:0;padding-bottom:0}
.playbook td{padding:7px 6px;border-bottom:1px dotted var(--border);vertical-align:top}
.playbook td.num,.playbook th.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
.playbook td .n{display:block;font-size:9px;color:var(--text-muted);font-weight:400}
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
  .row{grid-template-columns:40px 104px minmax(160px,1fr) 88px 36px;grid-template-areas:
    "rank art who score star" "rank art chart chart chart" "rank art stats stats size"}
  .rank{grid-area:rank} .art{grid-area:art;width:104px;height:146px} .who{grid-area:who}
  .chart{grid-area:chart;margin-top:8px} .stats{grid-area:stats;margin-top:8px}
  .score{grid-area:score} .size{grid-area:size;margin-top:8px} .star{grid-area:star}
}
@media (max-width:640px){
  .wrap{padding:14px 10px 48px}
  h1{font-size:20px}
  header{flex-direction:column;align-items:flex-start}
  .budget{grid-template-columns:1fr;gap:10px}
  .toolbar .count{margin-left:0;width:100%}
  .row{grid-template-columns:88px 1fr 32px;gap:0 10px;padding:10px;grid-template-areas:
    "art who star" "art score score" "chart chart chart" "stats stats stats" "size size size"}
  .rank{display:none}
  .art{width:88px;height:123px}
  .score{text-align:left;margin-top:6px} .score .bar{max-width:120px}
  .size{text-align:left}
  .stats{grid-template-columns:repeat(3,1fr)}
  .kpis{grid-template-columns:repeat(2,1fr)}
  .detail{padding:14px 12px}
  .dtop{grid-template-columns:1fr}
  .dart{width:140px;height:196px}
  .dhead .nm{font-size:18px}
  .heroes{grid-template-columns:repeat(2,1fr)}
  .dgrid{grid-template-columns:1fr}
}
"""

# --------------------------------------------------------------------------
# Behaviour. Sizing and the plan summary are twins of radar/plan.py.
# --------------------------------------------------------------------------
JS = r"""
const DATA = JSON.parse(document.getElementById('haro-data').textContent);
const state = {q:'', set:'', rarity:'', minPrice:null, maxPrice:null, minScore:null, minSales:null,
               sort:'score', dir:-1, limit:30, budget:null, view:'all', open:new Set(), range:'90'};

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
const TOP_SCORE = 75;  // top quarter of what is trading, per the score's own anchoring
const SEALED = DATA.sealed || [];
const ALL = DATA.rows.concat(SEALED);
const findRow = k => ALL.find(x => key(x) === k);
const isSealed = r => r.kind === 'sealed';
const cardURL = r => r.tcgplayer_url || (r.tcgplayer_id ? 'https://www.tcgplayer.com/product/'+r.tcgplayer_id+'?Language=English' : null);

// ---- card art ------------------------------------------------------------
// The thumbnail is embedded in the file, so it shows with the network
// unplugged. The detail asks the CDN for a sharp copy and falls back to the
// thumbnail; a card with neither gets a labelled frame, never a broken glyph.
function placeholder(r){
  return `<div class="ph"><b>${esc(r.name)}</b>${esc(r.number||'')}<span>no image</span></div>`;
}
function artHTML(r){
  const src = r.thumb || r.image_url;
  if (!src) return placeholder(r);
  return `<img src="${esc(src)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-ph="${esc(key(r))}">`;
}
function bigArtHTML(r){
  const big = r.image_large || r.image_url, small = r.thumb || '';
  if (!big && !small) return placeholder(r);
  const fallback = small ? `data-fallback="${esc(small)}"` : '';
  return `<img src="${esc(big||small)}" alt="" decoding="async" referrerpolicy="no-referrer" ${fallback} data-ph="${esc(key(r))}">`;
}
document.addEventListener('error', e=>{
  const img = e.target; if (!(img instanceof HTMLImageElement) || !img.dataset.ph) return;
  if (img.dataset.fallback){ img.src = img.dataset.fallback; delete img.dataset.fallback; return; }
  const r = findRow(img.dataset.ph);
  if (r) img.outerHTML = placeholder(r);
}, true);

// ---- watchlist: the reader's browser only -------------------------------
// Wrapped in try/catch throughout: private windows, blocked storage and
// thumbnail renderers all throw, and the page must work with nothing saved.
const WATCH_KEY = 'haro.watch.v1';
function loadWatch(){ try { return JSON.parse(localStorage.getItem(WATCH_KEY) || '{}') || {}; } catch(e){ return {}; } }
function saveWatch(w){ try { localStorage.setItem(WATCH_KEY, JSON.stringify(w)); } catch(e){} if (typeof syncQueue === 'function') syncQueue(); }
let watch = loadWatch();
const isWatched = r => !!watch[key(r)];

// ---- account sync ----------------------------------------------------------
// Off by default, and off entirely unless this page is served from the
// members' site with a sync URL configured. Then, and only then: ask Ghost
// for the signed session token it issues to the logged-in member, and use
// it to read and write the same watchlist at the sync service. Nothing goes
// anywhere else, and a reader who is not signed in keeps a browser-only
// list exactly as before. Two fetches, both named here, nowhere else.
const SYNC_URL = (DATA.sync_url || '').replace(/\/$/, '');
const sync = {token:null, state: SYNC_URL ? 'idle' : 'off', timer:null};
function syncStatus(msg, cls){
  const el = document.getElementById('sync-status'); if (!el) return;
  el.textContent = msg; el.className = 'sync ' + (cls||''); el.hidden = !msg;
}
async function syncInit(){
  if (!SYNC_URL || !/^https?:$/.test(location.protocol)) return;
  try {
    const t = await fetch('/members/api/session', {credentials:'same-origin'});
    if (!t.ok) { syncStatus('Sign in on the site to keep your watchlist across devices.', 'muted'); return; }
    sync.token = (await t.text()).trim();
    const r = await fetch(SYNC_URL + '/positions', {headers:{Authorization:'Bearer ' + sync.token}});
    if (!r.ok) throw new Error('positions ' + r.status);
    const remote = await r.json();
    const localCount = Object.keys(watch).length, remoteCount = Object.keys(remote.positions||{}).length;
    if (remoteCount || !localCount){ watch = remote.positions || {}; saveWatch(watch); apply(); }
    else { await syncPush(); }  // first sign-in with a local list: it becomes the account's
    sync.state = 'on'; syncStatus('Watchlist synced to your account.', 'on');
  } catch(e){ sync.state = 'error'; syncStatus('Could not reach the sync service; using this browser\u2019s copy.', 'muted'); }
}
async function syncPush(){
  if (!sync.token) return;
  const r = await fetch(SYNC_URL + '/positions', {method:'PUT', headers:{Authorization:'Bearer ' + sync.token, 'Content-Type':'application/json'},
    body: JSON.stringify({positions: watch})});
  if (!r.ok) throw new Error('push ' + r.status);
}
function syncQueue(){
  if (sync.state !== 'on') return;
  clearTimeout(sync.timer);
  sync.timer = setTimeout(()=>{ syncPush().catch(()=>syncStatus('Last change did not sync; it is saved in this browser.', 'muted')); }, 800);
}
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
    <div class="kv"><span class="k">${q} × $${c.toFixed(2)}</span><span class="vv">$${basis.toFixed(2)} in</span></div>
    <div class="kv"><span class="k">${q} × ${money(now)} market</span><span class="vv">$${val.toFixed(2)} now</span></div>
    ${r.floor_low!=null ? `<div class="kv"><span class="k">Cheapest listing today</span><span class="vv">${money(r.floor_low)}</span></div>` : ''}
    ${trendBroke(r) ? '<div class="callout bad" style="margin-top:10px"><span class="cl">Trend broke</span>The weekly climb has stopped, or the last week gave back more than a wobble. This is the exit signal a hold screen can give; it is not a forecast.</div>' : ''}`;
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
    el.innerHTML = `<span class="hero">${DATA.rows.length}</span> cards pass the screen today. <span class="muted">Enter a budget and each row gets a size: copies, cost, and what limited it.</span>`;
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
// Marks: a dashed line where a set released (label above it), a ring on any
// day that moved more than ANOMALY_PCT. Releases come from the API's own
// calendar; anomalies are computed from the series right here.
const CH = {w:300, h:80, p:6, top:12};
const ANOMALY_PCT = 15;
const RELEASES = DATA.releases || [];
function seriesFor(r, range){
  if (!r) return null;
  if (range === '1y') return (r.series_long && r.series_long.length > 2) ? r.series_long : r.series;
  if (range === '30' && r.series && r.series.length){
    const last = r.series[r.series.length-1][0];
    const cut = new Date(last + 'T00:00:00Z'); cut.setUTCDate(cut.getUTCDate() - 30);
    const c = cut.toISOString().slice(0,10);
    return r.series.filter(d => d[0] >= c);
  }
  return r.series;
}
function marksFor(series){
  const dates = series.map(d=>d[0]);
  const rel = RELEASES.map(m => ({...m, i: dates.findIndex(d => d >= m.date)}))
    .filter(m => m.i > 0 && m.date >= dates[0] && m.date <= dates[dates.length-1]);
  const anomalies = [];
  for (let i=1;i<series.length;i++){ const a = series[i-1][1], b = series[i][1];
    if (a > 0){ const c = (b-a)/a*100; if (Math.abs(c) >= ANOMALY_PCT) anomalies.push({i, pct:c}); } }
  return {rel, anomalies};
}
function chart(series, id, big, range){
  if (!series || series.length < 2) return '<div class="chart"><div class="empty" style="padding:22px">no history</div></div>';
  const rangeAttr = range ? ` data-range="${esc(range)}"` : '';
  const fmt = id === '__index' ? (v => v.toFixed(1)) : money;
  // The big chart's viewBox is wide so rings and the end dot stay round:
  // the SVG is stretched to its box, and a 300-wide box stretched to 1200px
  // turns every circle into an ellipse.
  const w = big ? 1200 : CH.w, h = big ? 150 : CH.h, p = CH.p, top = CH.top, ys = series.map(d=>d[1]);
  const lo = Math.min(...ys), hi = Math.max(...ys), span = (hi-lo) || (hi || 1);
  const X = i => p + i*(w-2*p)/(series.length-1);
  const Y = v => h-p - ((v-lo)/span)*(h-p-top);
  const pts = series.map((d,i)=>`${X(i).toFixed(1)},${Y(d[1]).toFixed(1)}`).join(' ');
  const area = `M${X(0).toFixed(1)},${(h-p).toFixed(1)} L${pts.replace(/ /g,' L')} L${X(series.length-1).toFixed(1)},${(h-p).toFixed(1)} Z`;
  const last = series[series.length-1], first = series[0];
  const stroke = last[1] >= first[1] ? 'var(--cyan)' : 'var(--down)';
  const {rel, anomalies} = marksFor(series);
  // Labels are HTML, not SVG text: the SVG is stretched to fit its box and
  // text inside it would stretch with it.
  const relSVG = rel.map(m => { const x = X(m.i).toFixed(1);
    return `<line x1="${x}" x2="${x}" y1="${top-2}" y2="${h-p}" stroke="var(--accent-dim)" stroke-width="1" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>`; }).join('');
  const relLabels = rel.map(m => { const f = m.i/(series.length-1); const pos = f > 0.85 ? 'end' : (f < 0.1 ? 'start' : 'mid');
    return `<span class="rl ${pos}" style="left:${(X(m.i)/w*100).toFixed(2)}%">${esc(m.label)}</span>`; }).join('');
  const anomSVG = anomalies.map(a => `<circle cx="${X(a.i).toFixed(1)}" cy="${Y(series[a.i][1]).toFixed(1)}" r="${big?5:3.5}" fill="none" stroke="var(--warn)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`).join('');
  return `<div class="chart" data-chart="${esc(id)}"${rangeAttr}>
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="${id==='__index'?'index level':'market price'}, ${fmt(first[1])} to ${fmt(last[1])}${rel.length?'; releases marked: '+rel.map(m=>m.label).join(', '):''}">
      <path d="${area}" fill="${stroke}" opacity=".12"/>
      ${relSVG}
      <polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
      ${anomSVG}
      <line class="xh" x1="0" x2="0" y1="0" y2="${h}" stroke="var(--text-muted)" stroke-width="1" opacity="0"/>
      <circle class="dot" cx="${X(series.length-1).toFixed(1)}" cy="${Y(last[1]).toFixed(1)}" r="4" fill="${stroke}" stroke="var(--surface)" stroke-width="2"/>
    </svg>
    ${relLabels}
    <div class="cap"><span>${shortDate(first[0])} ${fmt(first[1])} → ${shortDate(last[0])} ${fmt(last[1])}</span><span>high ${fmt(hi)}</span></div>
  </div>`;
}
function chartHover(e){
  const box = e.target.closest('.chart'); if (!box) return;
  const r = box.dataset.chart === '__index' ? {series: DATA.index.levels} : findRow(box.dataset.chart);
  const ser = box.dataset.range ? seriesFor(r, box.dataset.range) : (r && r.series);
  if (!r || !ser || ser.length < 2) return;
  const svg = box.querySelector('svg'), rect = svg.getBoundingClientRect();
  const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const i = Math.round(frac * (ser.length-1));
  const [d, v] = ser[i];
  const xh = svg.querySelector('.xh'); const w = svg.viewBox.baseVal.width || CH.w, p = CH.p; const x = p + i*(w-2*p)/(ser.length-1);
  xh.setAttribute('x1', x); xh.setAttribute('x2', x); xh.setAttribute('opacity', '.6');
  const {rel, anomalies} = marksFor(ser);
  const prev = i > 0 ? ser[i-1][1] : null;
  const dayPct = prev > 0 ? (v-prev)/prev*100 : null;
  const an = anomalies.find(a => a.i === i);
  const rl = rel.filter(m => Math.abs(m.i - i) <= 1);
  let extra = '';
  const step = ser === r.series ? 'on the day' : 'since the previous point';
  if (dayPct != null) extra += `<div class="tl">${dayPct>=0?'+':''}${dayPct.toFixed(1)}% ${step}${an ? ' <b style="color:var(--warn)">— big move</b>' : ''}</div>`;
  rl.forEach(m => { extra += `<div class="tl" style="color:var(--accent)">Released ${shortDate(m.date)}: ${esc(m.names.join(', '))}</div>`; });
  tip.innerHTML = `<div class="tv">${box.dataset.chart==='__index' ? v.toFixed(1) : money(v)}</div><div class="tl">${esc(d)}</div>${extra}`;
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

// ---- your holdings, at the top --------------------------------------------------
function renderPortfolio(){
  const el = document.getElementById('portfolio'); if (!el) return;
  let n=0, basis=0, value=0, broke=[], watching=0;
  for (const [k, w] of Object.entries(watch)){
    const r = findRow(k); if (!r) continue;
    const q = Number(w.qty), c = Number(w.cost);
    if (q>0 && c>0 && r.market_price!=null){ n++; basis += q*c; value += q*r.market_price; if (trendBroke(r)) broke.push(r.name); }
    else watching++;
  }
  if (!n && !watching){ el.hidden = true; return; }
  const d = value - basis, p = basis ? d/basis*100 : 0;
  el.innerHTML = n
    ? `<div class="pf"><span class="pfl">Your holdings</span><span class="pfv">${n} ${n===1?'position':'positions'}</span>
        <span class="pfv">$${basis.toFixed(2)} in</span><span class="pfv">$${value.toFixed(2)} now</span>
        <span class="pfv pnl ${d>=0?'up':'down'}">${d>=0?'+':'−'}$${Math.abs(d).toFixed(2)} (${p>=0?'+':''}${p.toFixed(1)}%)</span>
        ${broke.length?`<span class="pfv down"><b>${broke.length}</b> trend broke: ${esc(broke.slice(0,3).join(', '))}${broke.length>3?'…':''}</span>`:''}
        ${watching?`<span class="pfv muted">${watching} watching</span>`:''}
        <button class="ghost" data-view-jump="watch">Open watchlist</button></div>`
    : `<div class="pf"><span class="pfl">Watching</span><span class="pfv">${watching} ${watching===1?'card':'cards'}</span><span class="pfv muted">Enter copies and cost in a card\u2019s detail to track the position.</span><button class="ghost" data-view-jump="watch">Open watchlist</button></div>`;
  el.hidden = false;
}

// ---- the index ---------------------------------------------------------------
function renderIndex(){
  const el = document.getElementById('gindex'); const ix = DATA.index;
  if (!el) return;
  if (!ix || !ix.levels || ix.levels.length < 2){ el.hidden = true; return; }
  const ch = [['1d',ix.change_1d],['7d',ix.change_7d],['30d',ix.change_30d],['90d',ix.change_90d],['1y',ix.change_1y]]
    .filter(([,v])=>v!=null).map(([l,v])=>`<div class="ixc"><div class="l">${l}</div><div class="v">${pct(v,1)}</div></div>`).join('');
  const br = ix.measured_7d ? `${Math.round(100*ix.up_7d/ix.measured_7d)}% of members up over 7d` : '';
  el.innerHTML = `<summary>${esc(ix.name)}<span class="sc"><b class="ixsv">${ix.value.toFixed(1)}</b>${ix.change_7d!=null?` · 7d <span class="${ix.change_7d>0?'up':(ix.change_7d<0?'down':'flat')}">${pct(ix.change_7d,1)}</span>`:''}${ix.change_30d!=null?` · 30d <span class="${ix.change_30d>0?'up':(ix.change_30d<0?'down':'flat')}">${pct(ix.change_30d,1)}</span>`:''} · ${ix.members} singles, one number</span></summary><div class="ixhead">
      <div><div class="ixwhat" data-tip="Equal-weight index of the ${ix.members} most-traded English singles priced $5+ (copies sold over 90 days), base 100 on ${esc(ix.base_date)}. Members are fixed for the calendar month and rebalanced on the 1st. Descriptive: the market's own average, not a forecast.">The ${ix.members} most traded, most investable Gundam singles, as one number.<span class="info">?</span></div>
        <div class="ixval">${ix.value.toFixed(1)}</div>
        <div class="ixsub">${esc(ix.as_of)} · high ${ix.high.toFixed(1)} on ${shortDate(ix.high_date)}${br?' · '+br:''}</div></div>
      <div class="ixchanges">${ch}</div>
    </div>
    ${chart(ix.levels, '__index', true, '1y')}
    <div class="legend"><span><i></i>set release</span><span><b></b>${ANOMALY_PCT}%+ in a step</span><span>${ix.members} members · month of ${esc(ix.month||'')}</span></div>`;
  el.hidden = false;
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
  return COMPONENTS.map(([k,label,tip])=>{ const v = c[k] ?? 0; const cls = v>=75?'hi':(v<40?'lo':'');
    return `<div class="crow ${cls}" data-tip="${esc(tip)}"><span class="cl">${label}</span><span class="ct"><i style="width:${Math.max(2,v)}%"></i></span><span class="cv">${v.toFixed(0)}</span></div>`;
  }).join('');
}
const realRarity = r => r.rarity && r.rarity !== '—' && r.rarity !== 'None';
function tagsHTML(r){
  const t = [];
  if (realRarity(r)) t.push(`<span class="tag">${esc(r.rarity)}</span>`);
  if (r.printing && r.printing !== 'Normal') t.push(`<span class="tag">${esc(r.printing)}</span>`);
  if (isWatched(r)){
    const w = watch[key(r)];
    t.push(w && Number(w.qty) > 0 ? `<span class="tag pos">${w.qty} held</span>` : '<span class="tag pos">watching</span>');
    if (trendBroke(r)) t.push('<span class="tag broke" data-tip="Weeks-up under 50% or a 7-day fall past 10%. The exit signal a hold screen can give.">trend broke</span>');
  }
  return t.join('');
}
function rankDelta(r){
  if (isSealed(r)) return '';
  const prev = DATA.prev_ranks ? DATA.prev_ranks[key(r)] : undefined;
  if (prev == null) return DATA.prev_ranks ? '<span class="d" data-tip="Not in the previous issue’s ranking.">new</span>' : '';
  const d = prev - r.rank;
  if (d === 0) return '<span class="d">—</span>';
  return `<span class="d ${d>0?'up':'down'}" data-tip="Was #${prev} in the previous issue.">${d>0?'+':'−'}${Math.abs(d)}</span>`;
}
function rowHTML(r, plan){
  const k = key(r), openNow = state.open.has(k), sized = plan && plan.affordable;
  const url = cardURL(r);
  const nm = url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(r.name)}</a>` : esc(r.name);
  const meta = [r.set_name, r.number].filter(Boolean).map(esc).join(' · ');
  const prem = r.ask_premium_pct;
  const premHTML = prem==null ? '<span class="flat">—</span>'
    : `<span class="${prem>5?'down':(prem<-2?'up':'flat')}">${prem>0?'+':''}${prem.toFixed(0)}%</span>`;
  return `<div class="row${openNow?' open':''}${sized?' sized':''}${isWatched(r)?' watched':''}" data-key="${esc(k)}" role="button" aria-expanded="${openNow}">
    <div class="rank"><span class="n">${r.rank}</span>${rankDelta(r)}</div>
    <div class="art">${artHTML(r)}</div>
    <div class="who"><div class="nm">${nm}</div><div class="meta">${meta}</div><div class="tags">${tagsHTML(r)}</div></div>
    ${chart(r.series, k)}
    <div class="stats">
      <div class="s" data-tip="${esc(DATA.tips.price)}"><div class="l">Price</div><div class="v">${money(r.market_price)}</div></div>
      ${isSealed(r) ? `<div class="s" data-tip="Change over 30 days, from stored daily closes."><div class="l">30d</div><div class="v">${pct(r.change_30d)}</div></div>`
                     : `<div class="s" data-tip="${esc(DATA.tips.entry)}"><div class="l">Entry</div><div class="v">${money(r.floor_low)}</div></div>`}
      <div class="s" data-tip="${esc(DATA.tips.prem)}"><div class="l">vs sold</div><div class="v">${premHTML}</div></div>
      <div class="s" data-tip="${esc(DATA.tips.c7)}"><div class="l">7d</div><div class="v">${pct(r.change_7d)}</div></div>
      <div class="s" data-tip="${esc(DATA.tips.c90)}"><div class="l">90d</div><div class="v">${pct(r.change_90d)}</div></div>
      <div class="s" data-tip="${esc(DATA.tips.sales)}"><div class="l">Sales/day</div><div class="v ${(r.avg_daily_sales??0)<1?'down':''}">${r.avg_daily_sales==null?'—':r.avg_daily_sales.toFixed(1)}</div></div>
    </div>
    ${isSealed(r)
      ? `<div class="score" data-tip="Change from the earliest price we hold for it${r.first_date?' ('+shortDate(r.first_date)+')':''}. Days since the set released, from the API's own calendar."><div class="n" style="font-size:20px">${r.change_since_first==null?'—':pct(r.change_since_first)}</div><div class="l">since ${r.first_date?shortDate(r.first_date):'first seen'}</div></div>
         <div class="size"><span class="pill none">${r.days_since_release!=null?r.days_since_release+'d':'—'}</span><div class="l">since release</div></div>`
      : `<div class="score${r.invest_score>=TOP_SCORE?' top':''}" data-tip="${esc(DATA.tips.score)}"><div class="n">${r.invest_score.toFixed(0)}</div><div class="bar"><i style="width:${Math.max(3,r.invest_score)}%"></i></div><div class="l">score</div></div>
         <div class="size" data-tip="${esc(DATA.tips.buy)}">${sized?`<span class="pill">${plan.qty} · $${plan.cost.toFixed(0)}</span>`:'<span class="pill none">—</span>'}<div class="l">size</div></div>`}
    <button class="star" data-star="${esc(k)}" aria-label="${isWatched(r)?'Remove from':'Add to'} watchlist" title="Watchlist"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M12 2.5l2.9 6.2 6.8.8-5 4.6 1.3 6.7L12 17.5l-6 3.3 1.3-6.7-5-4.6 6.8-.8z" fill="${isWatched(r)?'currentColor':'none'}" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg></button>
  </div>` + (openNow ? detailHTML(r, plan) : '');
}

// ---- the detail ------------------------------------------------------------
// Three verdicts a person actually asks about -- is it priced ahead of
// itself, is the climb intact, can I get out -- then the numbers, then the
// words. Colour appears only where a verdict is made.
function verdicts(r){
  const v = [];
  const p = r.ask_premium_pct;
  if (p == null) v.push({c:'', t:'No read on price', s:'too few recent sales'});
  else if (p > 5) v.push({c:'bad', t:`Asking ${p.toFixed(0)}% above sales`, s:'listed ahead of itself'});
  else if (p < -2) v.push({c:'good', t:`Asking ${Math.abs(p).toFixed(0)}% below sales`, s:'copies selling above the list'});
  else v.push({c:'good', t:'Asking what it sells for', s:'list and sales agree'});
  const cons = r.consistency_pct;
  if (trendBroke(r)) v.push({c:'bad', t:'Trend broke', s: (r.change_7d!=null && r.change_7d<=-10) ? `${r.change_7d.toFixed(0)}% this week` : `up ${cons??'—'}% of weeks`});
  else if (cons != null && cons >= 70) v.push({c:'good', t:`Up ${cons}% of weeks`, s:'the climb is intact'});
  else if (cons != null) v.push({c:'warn', t:`Up ${cons}% of weeks`, s:'a choppy climb'});
  const s = r.avg_daily_sales;
  if (s == null) v.push({c:'', t:'No sales data', s:''});
  else if (s >= 2) v.push({c:'good', t:`${s.toFixed(1)} sales a day`, s:'easy to exit'});
  else if (s >= 1) v.push({c:'good', t:`${s.toFixed(1)} sales a day`, s:'a stack clears in days'});
  else v.push({c:'bad', t:`${s.toFixed(1)} sales a day`, s:'slow to exit'});
  if (r.drawdown_pct != null && r.drawdown_pct >= 10) v.push({c:'warn', t:`${r.drawdown_pct.toFixed(0)}% off its high`, s:'90-day high'});
  // The shelf: supply, which a price chart cannot show. Shrinking while copies
  // still sell is demand eating supply; growing is sellers arriving.
  const lc = r.listings_change_30d ?? r.listings_change_7d; const lw = r.listings_change_30d != null ? '30d' : '7d';
  if (lc != null && r.total_listings != null){
    if (lc <= -20) v.push({c:'good', t:`Shelf ${lc.toFixed(0)}% in ${lw}`, s:`${r.total_listings} listed · supply draining`});
    else if (lc >= 25) v.push({c:'warn', t:`Shelf +${lc.toFixed(0)}% in ${lw}`, s:`${r.total_listings} listed · sellers arriving`});
  }
  return v.map(x=>`<span class="vchip ${x.c}"><span class="vt">${esc(x.t)}</span>${x.s?`<span class="vs">${esc(x.s)}</span>`:''}</span>`).join('');
}
const cleanWatch = s => { const t = String(s||'').replace(/^Watch:\s*/i,'').replace(/\s*Reprints, ban-list changes and rotation[^.]*\.\s*$/,'').trim(); return t ? t[0].toUpperCase() + t.slice(1) : ''; };
function detailHTML(r, plan){
  const url = cardURL(r);
  const k = key(r), w = watch[k] || {};
  const meta = [r.set_name, r.number, realRarity(r) ? r.rarity : null, r.printing && r.printing!=='Normal' ? r.printing : null].filter(Boolean).map(esc).join(' · ');

  let pos;
  if (isSealed(r)) pos = '<p class="sub2">Sealed is not sized by the budget tool — it is priced per unit at the listing, not from a Near Mint shelf. Enter what you hold below.</p>';
  else if (!state.budget) pos = '<p class="sub2">Enter a budget at the top and this becomes copies and a cost.</p>';
  else if (plan && plan.affordable) pos = `<div class="big">${plan.qty} ${plan.qty===1?'copy':'copies'} · $${plan.cost.toFixed(2)}</div>
      <div class="sub2">at $${plan.unit.toFixed(2)} shipped each · ${plan.pct.toFixed(0)}% of your budget</div>
      <div class="kv"><span class="k">Limited by</span><span class="vv">${plan.limitedBy}</span></div>
      <div class="kv"><span class="k">Budget left after</span><span class="vv">$${(plan.remaining??0).toFixed(2)}</span></div>
      ${r.avg_daily_sales ? `<div class="kv"><span class="k">Days to sell that many</span><span class="vv">~${Math.ceil(plan.qty/r.avg_daily_sales)}</span></div>` : ''}`;
  else pos = `<div class="big">No position</div><p class="sub2">${plan ? plan.reason : 'No live entry price.'}</p>`;

  const shelf = (r.floor_low != null)
    ? `<div class="kv"><span class="k">Cheapest NM English, shipped</span><span class="vv">$${r.floor_low.toFixed(2)}</span></div>
       <div class="kv"><span class="k">Median listing</span><span class="vv">${r.shelf_med!=null?'$'+r.shelf_med.toFixed(2):'—'}</span></div>
       <div class="kv"><span class="k">Entry vs the shelf</span><span class="vv ${r.entry_vs_shelf_pct==null?'':(r.entry_vs_shelf_pct>0?'up':'down')}">${r.entry_vs_shelf_pct==null?'—':(r.entry_vs_shelf_pct>0?Math.abs(r.entry_vs_shelf_pct).toFixed(0)+'% below median':Math.abs(r.entry_vs_shelf_pct).toFixed(0)+'% above median')}</span></div>
       <div class="kv"><span class="k">Copies at Near Mint</span><span class="vv">${r.copies ?? '—'}</span></div>`
    : '<p class="sub2">No live entry price for this card today.</p>';
  const supplyLine = (r.total_listings != null)
    ? `<div class="kv"><span class="k" data-tip="Listings on TCGplayer, all conditions, against 7 and 30 days ago. Fewer listings while copies keep selling is demand eating supply; more is sellers arriving. Recorded daily since 2026-09-03.">All listings<span class="info">?</span></span><span class="vv">${r.total_listings}${r.listings_change_7d!=null?` <span class="${r.listings_change_7d<0?'up':'down'}">${pct(r.listings_change_7d,0)} 7d</span>`:''}${r.listings_change_30d!=null?` <span class="${r.listings_change_30d<0?'up':'down'}">${pct(r.listings_change_30d,0)} 30d</span>`:''}</span></div>`
    : '';
  const soldLine = r.settled_price != null
    ? `<div class="kv"><span class="k">Sold for, 14-day average</span><span class="vv">$${r.settled_price.toFixed(2)}</span></div>
       <div class="kv"><span class="k">Based on</span><span class="vv">${r.settled_volume ?? '—'} sales / ${r.settled_days} days</span></div>`
    : '<div class="kv"><span class="k">Sold for, 14-day average</span><span class="vv flat">under 3 days of sales</span></div>';

  const premCls = r.ask_premium_pct==null ? '' : (r.ask_premium_pct>5 ? 'down' : (r.ask_premium_pct<-2 ? 'up' : ''));
  const heroes = isSealed(r) ? `
    <div class="hero-n accent"><div class="l">Market price</div><div class="v">${money(r.market_price)}</div><div class="f">${r.total_listings!=null?r.total_listings+' listed':'daily batch'}</div></div>
    <div class="hero-n"><div class="l">Sold for</div><div class="v">${money(r.settled_price)}</div><div class="f">14-day sales average</div></div>
    <div class="hero-n"><div class="l">vs sold</div><div class="v ${premCls}">${r.ask_premium_pct==null?'—':(r.ask_premium_pct>0?'+':'')+r.ask_premium_pct.toFixed(1)+'%'}</div><div class="f">list against sales</div></div>
    <div class="hero-n"><div class="l">Since ${r.first_date?shortDate(r.first_date):'first seen'}</div><div class="v">${r.change_since_first==null?'—':pct(r.change_since_first)}</div><div class="f">from ${money(r.first_price)}</div></div>` : `
    <div class="hero-n accent"><div class="l">Entry today</div><div class="v">${money(r.floor_low)}</div><div class="f">cheapest NM, shipped</div></div>
    <div class="hero-n"><div class="l">Sold for</div><div class="v">${money(r.settled_price)}</div><div class="f">14-day sales average</div></div>
    <div class="hero-n"><div class="l">vs sold</div><div class="v ${premCls}">${r.ask_premium_pct==null?'—':(r.ask_premium_pct>0?'+':'')+r.ask_premium_pct.toFixed(1)+'%'}</div><div class="f">list against sales</div></div>
    <div class="hero-n"><div class="l">90 days</div><div class="v">${pct(r.change_90d)}</div><div class="f">market ${money(r.market_price)} now</div></div>`;

  const watchTxt = cleanWatch(r.watch);
  const calm = /^nothing in the numbers/i.test(watchTxt);
  const changes = [['3d',r.change_3d],['7d',r.change_7d],['30d',r.change_30d],['90d',r.change_90d]]
    .map(([l,v])=>`<div><div class="l">${l}</div><div class="v">${pct(v)}</div></div>`).join('');

  return `<div class="detail" data-detail="${esc(k)}">
    <div class="dtop">
      <div class="dart">${bigArtHTML(r)}</div>
      <div class="dhead">
        <div class="nm">${url?`<a href="${esc(url)}" target="_blank" rel="noopener">${esc(r.name)}</a>`:esc(r.name)}</div>
        <div class="meta">${meta}</div>
        <div class="verdicts">${verdicts(r)}</div>
        <div class="heroes">${heroes}</div>
        <div class="callout"><span class="cl">The case</span>${esc(r.thesis||'')}</div>
        ${watchTxt ? `<div class="callout ${calm?'good':'warn'}"><span class="cl">${calm?'Nothing flashing':'What would break it'}</span>${esc(watchTxt)}</div>` : ''}
        <div class="dbtns">${url?`<a class="cta" href="${esc(url)}" target="_blank" rel="noopener">Open on TCGplayer</a>`:''}
          <button class="cta quiet" data-star="${esc(k)}">${isWatched(r)?'Remove from watchlist':'Add to watchlist'}</button></div>
      </div>
    </div>
    <div class="bigchart">
      <div class="bl"><span>Market price</span>
        <span class="ranges">${[['30','30 days'],['90','90 days'],['1y','1 year']].map(([v,l])=>`<button data-range="${v}" class="${state.range===v?'on':''}"${v==='1y'&&!(r.series_long&&r.series_long.length>2)?' disabled title="No weekly history yet for this card"':''}>${l}</button>`).join('')}</span>
        <span>dashed marks are set releases, rings are ${state.range==='1y'?'weeks':'days'} that moved ${ANOMALY_PCT}%+</span></div>
      ${chart(seriesFor(r, state.range), k, true, state.range)}
      <div class="legend"><span><i></i>set release</span><span><b></b>${ANOMALY_PCT}%+ in a ${state.range==='1y'?'week':'day'}</span>${r.change_1y!=null?`<span>1 year: ${pct(r.change_1y)}</span>`:''}${r.change_180d!=null?`<span>6 months: ${pct(r.change_180d)}</span>`:''}</div>
    </div>
    <div class="dgrid">
      ${isSealed(r) ? `<div class="dbox">
        <h5>Since release</h5>
        <div class="kv"><span class="k">Set released</span><span class="vv">${r.release_date ? esc(r.release_date) : '—'}</span></div>
        <div class="kv"><span class="k">Days on the market</span><span class="vv">${r.days_since_release ?? '—'}</span></div>
        <div class="kv"><span class="k">Earliest price we hold</span><span class="vv">${money(r.first_price)}${r.first_date?' · '+shortDate(r.first_date):''}</span></div>
        <div class="kv"><span class="k">Since then</span><span class="vv">${r.change_since_first==null?'—':pct(r.change_since_first)}</span></div>
        <div class="changes">${changes}</div>
        <div class="kv" style="margin-top:8px"><span class="k">Off its 90-day high</span><span class="vv">${r.drawdown_pct ?? '—'}%</span></div>
        <div class="kv"><span class="k">Units sold a day</span><span class="vv">${r.avg_daily_sales ?? '—'}</span></div>
        <p class="sub2" style="margin-top:8px">Sealed is not scored. The singles model measures rarity and copies; a box's price is print waves and time, so it gets the questions above instead of a number.</p>
      </div>` : `<div class="dbox">
        <h5>Score <span class="sub">${r.invest_score>=TOP_SCORE?'top quarter':'of 100'}</span></h5>
        <div class="score-line${r.invest_score>=TOP_SCORE?' top':''}"><span class="n">${r.invest_score.toFixed(0)}</span><span class="t">value 20 · liquidity 25 · trend 25 · stability 20 · scarcity 10</span></div>
        ${componentBars(r.components)}
        <div class="changes">${changes}</div>
        <div class="kv" style="margin-top:8px"><span class="k">Daily volatility</span><span class="vv">${r.volatility_pct ?? '—'}%</span></div>
        <div class="kv"><span class="k">Off its 90-day high</span><span class="vv">${r.drawdown_pct ?? '—'}%</span></div>
      </div>`}
      <div class="dbox">
        <h5 data-tip="${esc(DATA.tips.settled)}">The shelf today<span class="info">?</span></h5>
        ${isSealed(r) ? `<div class="kv"><span class="k">Market price</span><span class="vv">${money(r.market_price)}</span></div>
          <div class="kv"><span class="k">Lowest listing</span><span class="vv">${money(r.low_price)}</span></div>
          <div class="kv"><span class="k">Median listing</span><span class="vv">${money(r.median_price)}</span></div>` : shelf}${supplyLine}${soldLine}
      </div>
      <div class="dbox">
        <h5>Your money <span class="sub">saved in this browser</span></h5>
        <div class="kv" style="border:0;padding:0 0 4px"><span class="k">Size at your budget</span></div>
        ${pos}
        <div class="pos-form" style="margin-top:12px">
          <div><label>${isSealed(r)?'Units you hold':'Copies you hold'}</label><input type="number" min="0" step="1" data-pos="qty" data-k="${esc(k)}" value="${w.qty??''}"></div>
          <div><label>Paid each</label><input type="number" min="0" step="0.01" data-pos="cost" data-k="${esc(k)}" value="${w.cost??''}"></div>
        </div>
        <div data-pnl="${esc(k)}">${pnlHTML(r)}</div>
      </div>
      <div class="dbox">
        <h5>Before you buy</h5><ol class="checklist">${(isSealed(r) ? DATA.sealed_checklist : DATA.checklist).map(x=>`<li>${x}</li>`).join('')}</ol>
      </div>
    </div>
  </div>`;
}

const SORTERS = {
  score:r=>r.invest_score, price:r=>r.market_price ?? -1, entry:r=>r.floor_low ?? -1,
  prem:r=>r.ask_premium_pct ?? 1e9, c7:r=>r.change_7d ?? -1e9, c90:r=>r.change_90d ?? -1e9,
  sales:r=>r.avg_daily_sales ?? -1, cons:r=>r.consistency_pct ?? -1, name:r=>(r.name||'').toLowerCase(),
  moved:r=>{ const p = DATA.prev_ranks ? DATA.prev_ranks[key(r)] : null; return p==null ? 1e6 : p - r.rank; },
  c30:r=>r.change_30d ?? -1e9, since:r=>r.change_since_first ?? -1e9, age:r=>r.days_since_release ?? 1e9,
};

function filtered(){
  const q = state.q.trim().toLowerCase();
  const src = state.view==='sealed' ? SEALED : (state.view==='watch' ? ALL : DATA.rows);
  return src.filter(r=>{
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
const activeFilters = () => ['set','rarity','minPrice','maxPrice','minScore','minSales'].filter(k => state[k]!=null && state[k]!=='').length;

function apply(){
  let rows = filtered();
  const k = SORTERS[state.sort] || SORTERS.score;
  rows.sort((a,b)=>{ const av=k(a), bv=k(b); return av===bv?0:(av>bv?1:-1)*state.dir; });
  // Sizing walks the full ranking by score regardless of the view's sort, so
  // the same budget gives the same plan whatever you are looking at.
  const byScore = DATA.rows.slice().sort((a,b)=>b.invest_score-a.invest_score);
  const plans = state.budget ? allocate(byScore, state.budget) : new Map();
  if (state.view==='sized') rows = state.budget ? rows.filter(r => (plans.get(key(r))||{}).affordable) : [];
  renderPlanSummary(plans, byScore);
  const shown = rows.slice(0, state.limit);
  const emptyMsg = state.view==='watch' ? 'Nothing on your watchlist yet — tap the star on any card.'
    : (state.view==='sized' && !state.budget) ? 'Enter a budget at the top and this view shows only the cards it can take a position in.'
    : 'Nothing matches those filters.';
  document.getElementById('rows').innerHTML = shown.length ? shown.map(r=>rowHTML(r, plans.get(key(r)))).join('')
    : `<div class="empty">${emptyMsg}</div>`;
  document.getElementById('count').textContent = `${shown.length?'1–'+shown.length:'0'} of ${rows.length}`;
  const more = document.getElementById('more');
  if (rows.length > shown.length){ more.style.display='flex'; document.getElementById('more-all').textContent = `Show all ${rows.length}`; } else more.style.display='none';
  document.querySelectorAll('.views button').forEach(b=>b.classList.toggle('on', b.dataset.view===state.view));
  document.querySelectorAll('[data-set]').forEach(b=>b.classList.toggle('on', (b.dataset.set||'')===state.set));
  document.querySelectorAll('[data-rarity]').forEach(b=>b.classList.toggle('on', (b.dataset.rarity||'')===state.rarity));
  document.getElementById('watch-count').textContent = Object.keys(watch).length ? `(${Object.keys(watch).length})` : '';
  const n = activeFilters(), fb = document.getElementById('fbtn');
  fb.querySelector('.badge').textContent = n; fb.querySelector('.badge').hidden = !n;
  fb.classList.toggle('on', !!n);
  window.__view = rows;
  renderPortfolio();
}

function clearFilters(){
  Object.assign(state, {set:'', rarity:'', minPrice:null, maxPrice:null, minScore:null, minSales:null, limit:30});
  ['minprice','maxprice','minscore','minsales'].forEach(id=>{const e=document.getElementById(id); if(e) e.value='';});
  apply();
}
function reset(){
  clearFilters();
  Object.assign(state, {q:'', sort:'score', dir:-1, view:'all'});
  document.getElementById('q').value=''; document.getElementById('sort').value='score';
  document.getElementById('dir').classList.remove('asc');
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
  if (star){ e.stopPropagation(); const r = findRow(star.dataset.star); if (r) toggleWatch(r); return; }
  const jump = e.target.closest('[data-view-jump]');
  if (jump){ state.view = jump.dataset.viewJump; state.limit = 30; apply(); document.getElementById('rows').scrollIntoView({behavior:'smooth'}); return; }
  const rng = e.target.closest('[data-range]');
  if (rng){ e.stopPropagation(); state.range = rng.dataset.range; apply(); return; }
  if (e.target.closest('.info')){ e.stopPropagation(); const el = e.target.closest('[data-tip]'); if (tipAnchor===el && tip.classList.contains('on')){hideTip(); tipAnchor=null;} else {tipAnchor=el; showTip(el);} return; }
  const setBtn = e.target.closest('[data-set]');
  if (setBtn){ state.set = (state.set===setBtn.dataset.set)?'':setBtn.dataset.set; state.limit=30; apply(); return; }
  const rarBtn = e.target.closest('[data-rarity]');
  if (rarBtn){ state.rarity = (state.rarity===rarBtn.dataset.rarity)?'':rarBtn.dataset.rarity; state.limit=30; apply(); return; }
  if (e.target.closest('a, input, select, button, .detail')) { return; }
  hideTip();  // a tap on a chart leaves a readout behind on touch screens
  const row = e.target.closest('.row');
  if (row){ const k = row.dataset.key; state.open.has(k) ? state.open.delete(k) : state.open.add(k); apply(); return; }
  if (tipAnchor && !e.target.closest('#tip')){ hideTip(); tipAnchor = null; }
});
document.addEventListener('input', e=>{
  const p = e.target.closest('[data-pos]'); if (!p) return;
  const r = findRow(p.dataset.k); if (!r) return;
  const box = p.closest('.pos-form');
  const qty = Number(box.querySelector('[data-pos=qty]').value), cost = Number(box.querySelector('[data-pos=cost]').value);
  setPosition(r, qty>0?qty:null, cost>0?cost:null);
});

// ---- controls -----------------------------------------------------------------
document.getElementById('q').addEventListener('input', e=>{state.q=e.target.value; state.limit=30; apply();});
[['minprice','minPrice'],['maxprice','maxPrice'],['minscore','minScore'],['minsales','minSales']].forEach(([id,k])=>{
  const el = document.getElementById(id); if (!el) return;
  el.addEventListener('input', e=>{ const v = e.target.value===''?null:Number(e.target.value); state[k] = (v==null||Number.isNaN(v))?null:v; state.limit=30; apply(); });
});
document.getElementById('sort').addEventListener('change', e=>{ state.sort = e.target.value; state.dir = (state.sort==='name')?1:-1; document.getElementById('dir').classList.toggle('asc', state.dir===1); apply(); });
document.getElementById('dir').addEventListener('click', ()=>{ state.dir*=-1; document.getElementById('dir').classList.toggle('asc', state.dir===1); apply(); });
document.getElementById('budget').addEventListener('input', e=>{ const v = e.target.value===''?null:Number(e.target.value); state.budget = (v==null||Number.isNaN(v)||v<=0)?null:v; state.limit=30; apply(); });
document.querySelectorAll('.views button').forEach(b=>b.addEventListener('click', ()=>{
  const was = state.view; state.view=b.dataset.view; state.limit=30;
  // Sealed has no score: the sensible default there is what is moving now.
  if (state.view==='sealed' && state.sort==='score'){ state.sort='c30'; document.getElementById('sort').value='c30'; }
  if (was==='sealed' && state.view!=='sealed' && state.sort==='c30'){ state.sort='score'; document.getElementById('sort').value='score'; }
  apply(); }));
document.getElementById('fbtn').addEventListener('click', ()=>{ const f = document.getElementById('filters'); f.hidden = !f.hidden; document.getElementById('fbtn').setAttribute('aria-expanded', String(!f.hidden)); });
document.getElementById('clear').addEventListener('click', clearFilters);
document.getElementById('more-all').addEventListener('click', ()=>{state.limit=1e9; apply();});
document.getElementById('reset').addEventListener('click', reset);
document.getElementById('csv').addEventListener('click', exportCSV);
renderIndex();
apply();
syncInit();
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

_SORT_ICON = ('<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">'
              '<path d="M8 3v10M4 9l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8" '
              'stroke-linecap="round" stroke-linejoin="round"/></svg>')


RARITY_ORDER = ["Common", "C+", "C++", "Uncommon", "U+", "U++", "Rare", "R+", "R++",
                "Legend Rare", "LR+", "LR++", "Promo"]


def _rarity_order(name: str) -> tuple[int, str]:
    """Tier order for the rarity chips: common to legendary, promos last, unknowns after."""
    try:
        return (RARITY_ORDER.index(name), name)
    except ValueError:
        return (len(RARITY_ORDER), name)


def _pct_cell(v, n) -> str:
    if v is None:
        return '<td class="num flat">—</td>'
    cls = "up" if v > 0 else "down" if v < 0 else "flat"
    return f'<td class="num {cls}">{v:+d}%<span class="n">n={n}</span></td>'


def _playbook_panel(pb: dict | None) -> str:
    """What releases did to prices, from our own history. Counts on every cell."""
    if not pb or not pb.get("events"):
        return ""
    ev = pb["events"]
    hs = (30, 60, 90)
    rows = []
    for e in ev:
        names = ", ".join(e.get("names") or [])
        rows.append(
            f'<tr><td><b>{_esc(e["label"])}</b><br><span class="flat">{_esc(e["date"])}'
            f'{" · after " + _esc(e["prior_set"]) if e.get("prior_set") else ""}</span></td>'
            + "".join(_pct_cell(e["prior"].get(f"d{h}"), e["prior"].get(f"n{h}", 0)) for h in hs)
            + "".join(_pct_cell(e["new"].get(f"d{h}"), e["new"].get(f"n{h}", 0)) for h in hs)
            + "".join(_pct_cell(e["market"].get(f"d{h}"), e["market"].get(f"n{h}", 0)) for h in hs)
            + "</tr>")
    sm = pb["summary"]
    lead = ""
    p30, pn = sm["prior"]["d30"]
    m30, mn = sm["market"]["d30"]
    if p30 is not None and m30 is not None:
        lead = (f'Across {pn} measured {"release" if pn == 1 else "releases"}, the previous set\u2019s top '
                f'{pb["top_n"]} were <b class="{"down" if p30 < 0 else "up"}">{p30:+d}%</b> a month later while '
                f'the whole market was <b class="{"down" if m30 < 0 else "up"}">{m30:+d}%</b>.')
    return f"""
<details class="panel playbook" open>
  <summary>What releases did to prices<span class="sc">our own history, counts on every cell</span></summary>
  <p class="lead">{lead} Medians of per-card change; the new set is measured from a week after release, once listings settle. Blank means the window has not happened yet.</p>
  <div class="tablewrap"><table>
    <thead><tr><th>Release</th><th colspan="3" class="grp">Previous set, top {pb["top_n"]}</th><th colspan="3" class="grp">The new set, top {pb["top_n"]}</th><th colspan="3" class="grp">Whole market</th></tr>
    <tr><th></th>{"".join(f'<th class="num">+{h}d</th>' for h in hs)}{"".join(f'<th class="num">+{h}d</th>' for h in hs)}{"".join(f'<th class="num">+{h}d</th>' for h in hs)}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table></div>
</details>"""


def _note_panel(note: dict | None) -> str:
    """A person's note, shown while it is fresh. See radar/note.py."""
    if not note or not note.get("html"):
        return ""
    return (f'<div class="panel note"><div class="nh"><span class="nl">This week</span>'
            f'<span class="nd">{_esc(note["date"])}</span></div><div class="nb">{note["html"]}</div></div>')


def _index_payload(ix: dict | None) -> dict | None:
    if not ix or not ix.get("levels"):
        return None
    keep = ("name", "as_of", "value", "members", "base_date", "change_1d", "change_7d", "change_30d",
            "change_90d", "change_1y", "high", "high_date", "up_7d", "measured_7d", "month")
    return {**{k: ix.get(k) for k in keep}, "levels": [[d, v] for d, v in ix["levels"]]}


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
    art_cache: Path | None = None,
    fetch_art: bool = False,
    releases: list[dict] | None = None,
    index: dict[str, Any] | None = None,
    sealed: Sequence[dict] | None = None,
    playbook: dict[str, Any] | None = None,
    sync_url: str | None = None,
    note: dict[str, Any] | None = None,
    commentary: dict[str, dict] | None = None,
    record: dict[str, Any] | None = None,
    track_url: str = "",
) -> str:
    """`since` and `heat` are accepted for compatibility and unused: the
    issue-to-issue comparison is the email digest's job, and the hand-kept
    catalyst list was replaced by the release calendar (`releases`)."""
    market = market or {}
    candidates = [r for r in ranked if not r.get("disqualified")]
    rejected = [r for r in ranked if r.get("disqualified")]
    releases = releases or []

    rows = []
    for i, r in enumerate(candidates[:top_n], 1):
        p = _row_payload(r)
        p["rank"] = i
        p["printing"] = r.get("printing") or "Normal"
        rows.append(p)
    # The model's case and watch replace the template's wherever it wrote one
    # the guard accepted (radar/commentary.py). Absent key: the template stands.
    for p in rows:
        c = (commentary or {}).get(f"{p['card_id']}|{p['printing']}")
        if c:
            p["thesis"], p["watch"] = c["case"], c["watch"]
            p["written"] = True
    sealed_rows = []
    for r in sealed or []:
        p = _row_payload(r)
        p["printing"] = r.get("printing") or "Normal"
        for k in ("kind", "rank", "release_date", "days_since_release", "first_date", "first_price",
                  "change_since_first", "low_price", "median_price", "total_listings", "thesis", "watch"):
            p[k] = r.get(k)
        c = (commentary or {}).get(f"{p['card_id']}|{p['printing']}")
        if c:
            p["thesis"], p["watch"] = c["case"], c["watch"]
            p["written"] = True
        sealed_rows.append(p)
    if art_cache is not None:
        from . import art

        art.embed(rows, art_cache, fetch=fetch_art)
        art.embed(sealed_rows, art_cache, fetch=fetch_art)
    sets = sorted({r["set_name"] for r in rows if r.get("set_name")})
    rarities = sorted({r["rarity"] for r in rows if r.get("rarity") and r["rarity"] not in ("—", "None")},
                      key=_rarity_order)
    liquid = sum(1 for r in rows if (r.get("avg_daily_sales") or 0) >= 1.0)
    breadth = None
    if market.get("priced") and market.get("up_7d") is not None:
        breadth = round(100 * market["up_7d"] / market["priced"])
    breadth_word = ("—" if breadth is None else "falling market" if breadth < 35
                    else "rising market" if breadth > 55 else "mixed market")
    nxt = next((m for m in releases if m["date"] > (today or obs_date)), None)
    next_tile = ""
    if nxt:
        from datetime import date as _d

        try:
            days = (_d.fromisoformat(nxt["date"]) - _d.fromisoformat(today or obs_date)).days
            when = f"in {days} days" if days > 1 else "tomorrow"
        except (ValueError, TypeError):
            when = nxt["date"]
        names = ", ".join(nxt.get("names") or [])
        next_tile = (f'<div class="kpi cyan"><div class="l" data-tip="{_esc(names)}">Next release<span class="info">?</span></div>'
                     f'<div class="v">{_esc(nxt["label"])}</div><div class="f">{_esc(nxt["date"])} · {when}</div></div>')

    record_tile = ""
    if record and record.get("calls_30"):
        record_tile = (f'<a class="kpi" href="{_esc(track_url or "#")}" data-tip="Every top-20 pick, scored 30 days after the issue it appeared in against that issue&#39;s whole pool. Public, committed to git the day it is published, never edited."><div class="l">The record<span class="info">?</span></div>'
                       f'<div class="v">{record["calls_beat_pct"]}%</div><div class="f">of {record["calls_30"]} calls beat their pool at +30d · median {record["calls_median"]:+.1f}%</div></a>')

    payload = json.dumps({
        "rows": rows, "obs_date": obs_date, "checklist": CHECKLIST,
        "plan": plan_cfg or {"max_position_pct": 0.25}, "tips": TIPS,
        "prev_ranks": prev_ranks or None,
        "releases": [{"date": m["date"], "label": m["label"], "kind": m.get("kind"),
                      "names": m.get("names") or []} for m in releases],
        "index": _index_payload(index),
        "sealed": sealed_rows,
        "sealed_checklist": SEALED_CHECKLIST,
        "sync_url": sync_url or "",
    }, separators=(",", ":")).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")

    setchips = "".join(f'<button data-set="{_esc(s)}">{_esc(s)}</button>' for s in sets)
    rarchips = "".join(f'<button data-rarity="{_esc(x)}">{_esc(x)}</button>' for x in rarities)

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
    <div class="stamp">Prices through {_esc(obs_date)} · {len(candidates)} cards pass the screen · English NM only</div>
  </div>
  <div class="hbtns">
    <button class="ghost" id="csv">Export CSV</button>
  </div>
</header>
{_freshness(obs_date, today)}

<details class="panel gindex" id="gindex" hidden></details>
<div class="panel portfolio" id="portfolio" hidden></div>
{_note_panel(note)}
<div class="sync" id="sync-status" hidden></div>

<div class="panel budget">
  <label for="budget" data-tip="Total you are willing to put to work. Positions are sized down the ranking, capped per card.">Budget<span class="info">?</span></label>
  <span class="money-in"><input type="number" id="budget" placeholder="amount" min="0" step="50" aria-label="Budget in dollars"></span>
  <div class="plan-sum" id="plan-sum"></div>
</div>

<div class="kpis">
  <div class="kpi{' down' if breadth is not None and breadth < 35 else ' up' if breadth is not None and breadth > 55 else ' cyan'}"><div class="l" data-tip="Share of every priced product in the game that is up over 7 days. Whether your candidates are rising with the market or against it.">Market breadth<span class="info">?</span></div><div class="v">{f'{breadth}%' if breadth is not None else '—'}</div><div class="f">{breadth_word} · {market.get('up_7d', 0):,} of {market.get('priced', 0):,} up over 7d</div></div>
  <div class="kpi"><div class="l">Pass the screen</div><div class="v">{len(candidates)}</div><div class="f">of {len(ranked):,} screened</div></div>
  <div class="kpi up"><div class="l" data-tip="Candidates selling at least one copy a day. Below that, exiting a stack takes weeks.">Liquid enough<span class="info">?</span></div><div class="v">{liquid}</div><div class="f">1+ sales a day</div></div>
  <a class="kpi" href="#screened-out"><div class="l">Screened out</div><div class="v">{len(rejected)}</div><div class="f">every one listed with its reason</div></a>
  {next_tile}{record_tile}
</div>

<div class="toolbar">
  <input type="search" id="q" placeholder="Search card, set or number" aria-label="Search">
  <span class="views"><button data-view="all" class="on">All</button><button data-view="sized" data-tip="Only cards that get a size at your budget.">Sized</button><button data-view="watch">Watchlist <span id="watch-count"></span></button><button data-view="sealed" data-tip="Booster boxes, starter decks and deck build boxes: price against release, days on the market, what is moving. Not scored.">Sealed</button></span>
  <span class="sortbox"><span class="lbl">Sort</span>
  <select id="sort" aria-label="Sort by">
    <option value="score">Score</option><option value="moved">Rank movement</option><option value="c7">7-day change</option>
    <option value="c90">90-day change</option><option value="prem">vs sold</option><option value="price">Price</option>
    <option value="c30">30-day change</option><option value="entry">Entry price</option><option value="sales">Sales/day</option><option value="cons">Weeks up</option><option value="since">Since first seen</option><option value="age">Days since release</option><option value="name">Name</option>
  </select>
  <button class="dirbtn" id="dir" aria-label="Flip sort direction" title="Flip sort direction">{_SORT_ICON}</button></span>
  <button class="ghost" id="fbtn" aria-expanded="false" aria-controls="filters">Filters <span class="badge" hidden>0</span></button>
  <span class="count" id="count"></span>
</div>
<div class="panel filters" id="filters" hidden>
  <div class="frow">
    <div class="fgroup"><span class="lbl">Set</span><div class="chips">{setchips}</div></div>
  </div>
  <div class="frow">
    <div class="fgroup"><span class="lbl">Rarity</span><div class="chips">{rarchips}</div></div>
    <div class="fgroup"><span class="lbl">Market price</span><div class="range"><input type="number" id="minprice" placeholder="min" min="0" aria-label="Minimum price"><span>to</span><input type="number" id="maxprice" placeholder="max" min="0" aria-label="Maximum price"></div></div>
    <div class="fgroup"><span class="lbl">Score at least</span><input type="number" id="minscore" placeholder="e.g. 70" min="0" max="100" aria-label="Minimum score"></div>
    <div class="fgroup"><span class="lbl">Sales/day at least</span><input type="number" id="minsales" placeholder="e.g. 1" min="0" step="0.1" aria-label="Minimum sales per day"></div>
    <div class="factions"><button class="ghost" id="clear">Clear filters</button> <button class="ghost" id="reset">Reset everything</button></div>
  </div>
</div>

<div class="rows" id="rows"></div>
<div class="more" id="more" style="display:none"><button class="ghost" id="more-all">Show all</button></div>

{_playbook_panel(playbook)}

<details class="panel howto">
  <summary>How to read this<span class="sc">two minutes, once</span></summary>
  <ol>
    <li><b>Score</b> is 0–100 across value, liquidity, trend, stability and scarcity, anchored to this market’s own quartiles. 75+ means top quarter of what is actually trading. It is not a prediction.</li>
    <li><b>Entry, not Price.</b> Price is a daily batch a day or two behind. Entry is the cheapest Near Mint English copy on the shelf now, shipped — what you would pay.</li>
    <li><b>vs sold</b> is timing. Red: sellers asking more than buyers have paid. Green: the reverse. A great card can be listed ahead of itself.</li>
    <li><b>Budget</b> turns the ranking into positions — copies, cost, what limited it — with a per-card cap so one card cannot eat the whole thing. It is arithmetic on your number.</li>
    <li><b>Marks on the chart.</b> A dashed line is a set release (GD05, a wave of starter decks) so you can see how price answered new supply; a ring is a day that moved 15% or more. Hover either for the detail.</li>
    <li><b>Tap a row</b> for the verdicts, the case, what would break it, the live shelf, and your position if you hold it. <b>Star</b> a card to keep it on your watchlist; enter copies and cost and the row flags the day the trend breaks.</li>
    <li><b>Screened out</b> at the bottom lists every card that failed a gate and why. Nothing is dropped silently.</li>
  </ol>
</details>

<div class="rej" id="screened-out">{_rejected_table(rejected)}</div>

<footer>
  <p><b>Market Haro</b> is published by GUNDECK.AI for its subscribers. Every number on this page describes what a card has already done. Nothing here is a forecast, a recommendation, or financial advice, and nothing knows <em>why</em> a price is moving — bans, reprints, rotation and tournament results end runs and are invisible in price data. Trading cards can lose value. Your watchlist and positions are saved in this browser, and to your account when you are signed in on the site — nowhere else. Prices from tcgapi.dev under commercial licence · © GUNDECK.AI</p>
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
