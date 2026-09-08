"""What changed since the last issue -- the newsletter, computed.

WHY A DIFF AND NOT A SUMMARY

A daily report that restates the whole ranking every morning teaches readers to
stop opening it. What a subscriber actually wants at 8am is the delta: who is new
near the top, who fell out, whose asking price ran ahead of sales overnight, and
whether the market as a whole widened or narrowed. That is a diff against
yesterday's ranking, so yesterday's ranking has to be kept.

Each run writes `data/rankings/YYYY-MM-DD.json` -- the scored rows, minus the
series, which the archive already holds. The digest reads the most recent file
older than today and compares. If there is no previous file the digest says so
and sends anyway: the promise is that an issue goes out every day, including the
first one and including the days the feed is late.

WHAT COUNTS AS NEWS

  entered     in the top N today, was not yesterday (or was not a candidate)
  exited      in the top N yesterday, not today -- with the reason if it was
              screened out, because "dropped to #23" and "no longer has any
              recorded sales" are different news
  climbers    biggest score gains among cards in both rankings
  fallers     biggest score losses among cards in both rankings
  stretched   ask premium crossed above +5% today (was at or below yesterday)
  cheapened   ask premium crossed below -2% today
  breadth     share of the market up over 7 days, today vs yesterday
  freshness   how old the price feed is, so a late feed is the first line and
              not a footnote

Everything is computed from the two stored rankings and nothing else, so the
digest can be regenerated for any past pair of days.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Sequence

TOP_N = 20
STRETCH_PCT = 5.0
CHEAP_PCT = -2.0
MOVERS = 5

# Kept per row. `series` is deliberately not here -- the archive has it, and a
# year of daily rankings with 90 floats per row would be most of the repo.
KEEP = (
    "card_id", "printing", "name", "set_name", "number", "rarity", "tcgplayer_id",
    "tcgplayer_url", "market_price", "floor_low", "shelf_med", "copies",
    "settled_price", "ask_premium_pct", "invest_score", "disqualified",
    "change_7d", "change_30d", "change_90d", "avg_daily_sales", "consistency_pct",
)


def _key(r: dict) -> tuple[str, str]:
    return (str(r.get("card_id")), r.get("printing") or "Normal")


def snapshot(ranked: Sequence[dict], *, obs_date: str, market: dict | None) -> dict[str, Any]:
    """Today's ranking, trimmed to what a diff needs."""
    rows = []
    rank = 0
    for r in ranked:
        if not r.get("disqualified"):
            rank += 1
        rows.append({**{k: r.get(k) for k in KEEP}, "rank": rank if not r.get("disqualified") else None})
    m = market or {}
    priced = m.get("priced") or 0
    return {
        "obs_date": obs_date,
        "rows": rows,
        "breadth_pct": round(100 * (m.get("up_7d") or 0) / priced) if priced else None,
        "priced": priced,
    }


def save(snap: dict, root: str | Path) -> Path:
    d = Path(root) / "rankings"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{snap['obs_date']}.json"
    p.write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")
    return p


def previous(root: str | Path, before: str) -> dict | None:
    """The most recent stored ranking strictly older than `before`."""
    d = Path(root) / "rankings"
    if not d.exists():
        return None
    cands = sorted(p for p in d.glob("*.json") if p.stem < before)
    if not cands:
        return None
    try:
        return json.loads(cands[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def diff(today: dict, prev: dict | None, *, top_n: int = TOP_N, run_date: str | None = None) -> dict[str, Any]:
    """Two rankings -> what changed."""
    run_date = run_date or date.today().isoformat()
    try:
        feed_age = (date.fromisoformat(run_date) - date.fromisoformat(today["obs_date"])).days
    except (ValueError, TypeError, KeyError):
        feed_age = None

    t_rows = {_key(r): r for r in today["rows"]}
    t_top = {_key(r) for r in today["rows"] if r.get("rank") and r["rank"] <= top_n}

    out: dict[str, Any] = {
        "date": today["obs_date"],
        "run_date": run_date,
        "feed_age_days": feed_age,
        "feed_late": feed_age is not None and feed_age > 2,
        "has_previous": prev is not None,
        "prev_date": prev["obs_date"] if prev else None,
        "top_n": top_n,
        "candidates": sum(1 for r in today["rows"] if r.get("rank")),
        "screened": sum(1 for r in today["rows"] if r.get("disqualified")),
        "top": [r for r in today["rows"] if r.get("rank") and r["rank"] <= top_n],
        "breadth": {"now_pct": today.get("breadth_pct"), "prev_pct": prev.get("breadth_pct") if prev else None},
        "entered": [], "exited": [], "climbers": [], "fallers": [],
        "stretched": [], "cheapened": [],
    }
    if not prev:
        return out

    p_rows = {_key(r): r for r in prev["rows"]}
    p_top = {_key(r) for r in prev["rows"] if r.get("rank") and r["rank"] <= top_n}

    for k in sorted(t_top - p_top, key=lambda k: t_rows[k]["rank"]):
        r = dict(t_rows[k])
        r["prev_rank"] = (p_rows.get(k) or {}).get("rank")
        out["entered"].append(r)

    for k in sorted(p_top - t_top, key=lambda k: p_rows[k]["rank"]):
        r = dict(p_rows[k])
        now = t_rows.get(k) or {}
        r["prev_rank"] = r.get("rank")
        r["rank"] = now.get("rank")
        # Absent from today's rows entirely means it left the candidate pool --
        # the pre-filter is "$10+ and up over 30 days", so one of those failed.
        r["disqualified"] = now.get("disqualified") or (
            "left the pool — no longer $10+ and up over 30 days" if not now else None)
        out["exited"].append(r)

    both = [(k, t_rows[k], p_rows[k]) for k in t_rows.keys() & p_rows.keys()
            if t_rows[k].get("invest_score") is not None and p_rows[k].get("invest_score") is not None
            and not t_rows[k].get("disqualified") and not p_rows[k].get("disqualified")]
    moves = []
    for k, t, p in both:
        d = round(t["invest_score"] - p["invest_score"], 1)
        if d:
            moves.append({**t, "score_delta": d, "prev_score": p["invest_score"], "prev_rank": p.get("rank")})
    moves.sort(key=lambda r: r["score_delta"], reverse=True)
    out["climbers"] = [m for m in moves if m["score_delta"] > 0][:MOVERS]
    out["fallers"] = sorted([m for m in moves if m["score_delta"] < 0], key=lambda r: r["score_delta"])[:MOVERS]

    for k, t, p in both:
        tp, pp = t.get("ask_premium_pct"), p.get("ask_premium_pct")
        if tp is None or pp is None:
            continue
        if tp > STRETCH_PCT >= pp:
            out["stretched"].append({**t, "prev_premium": pp})
        elif tp < CHEAP_PCT <= pp:
            out["cheapened"].append({**t, "prev_premium": pp})
    out["stretched"].sort(key=lambda r: -r["ask_premium_pct"])
    out["cheapened"].sort(key=lambda r: r["ask_premium_pct"])
    return out


# --------------------------------------------------------------------------
# Rendering. Email HTML has to be boring: inline styles, tables, no scripts,
# no external CSS. Ghost strips or rewrites most of what a browser would allow.
# --------------------------------------------------------------------------
def _money(v):
    return "—" if v is None else f"${v:,.2f}"


def _pct(v):
    return "—" if v is None else f"{v:+.0f}%"


def _esc(x: Any) -> str:
    return (str("" if x is None else x).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def to_html(d: dict, *, report_url: str | None = None, brand: str = "Market Haro",
            note: dict | None = None, lead: str | None = None) -> str:
    """The email body. Plain, table-based, safe for every mail client."""
    A = "#f0a030"
    MUTED = "#8a8f98"
    st_h = f'style="margin:22px 0 6px;font:700 11px/1.4 ui-monospace,Menlo,monospace;letter-spacing:.14em;text-transform:uppercase;color:{A}"'
    st_p = 'style="margin:0 0 10px;font:14px/1.6 -apple-system,Segoe UI,Helvetica,Arial,sans-serif"'
    st_li = 'style="margin:0 0 6px;font:14px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif"'
    st_m = f'style="font-size:12px;color:{MUTED}"'

    def card(r):
        url = r.get("tcgplayer_url") or (
            f'https://www.tcgplayer.com/product/{r["tcgplayer_id"]}?Language=English'
            if r.get("tcgplayer_id") else None)
        nm = f'<a href="{_esc(url)}" style="color:inherit">{_esc(r["name"])}</a>' if url else _esc(r["name"])
        return f'<b>{nm}</b> <span {st_m}>{_esc(r.get("set_name") or "")}</span>'

    parts = []

    if lead:
        parts.append(f'<p style="margin:0 0 16px;font:17px/1.55 -apple-system,Segoe UI,Helvetica,Arial,sans-serif">{_esc(lead)}</p>')

    if note and note.get("html"):
        parts.append(f'<h3 {st_h}>This week</h3><div style="font:15px/1.6 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
                     f'margin:0 0 18px;padding:0 0 14px;border-bottom:1px solid #2a2418">{note["html"]}</div>')

    if d["feed_late"]:
        parts.append(
            f'<p style="margin:0 0 14px;padding:10px 12px;border-left:3px solid #d94a3d;'
            f'font:14px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
            f'<b>Price feed is {d["feed_age_days"]} days behind.</b> This issue is built on prices '
            f'through {_esc(d["date"])}. The ranking method is unchanged and entry prices are live, '
            f'but read the market column as history until the feed catches up.</p>')

    parts.append(
        f'<p {st_p}>{d["candidates"]} candidates from {d["candidates"] + d["screened"]} screened, '
        f'prices through <b>{_esc(d["date"])}</b>.'
        + (f' Market breadth <b>{d["breadth"]["now_pct"]}%</b>' if d["breadth"].get("now_pct") is not None else "")
        + (f' ({d["breadth"]["now_pct"] - d["breadth"]["prev_pct"]:+d} pts since {_esc(d["prev_date"])})'
           if d["breadth"].get("prev_pct") is not None and d["breadth"].get("now_pct") is not None else "")
        + ".</p>")

    if not d["has_previous"]:
        parts.append(f'<p {st_p}><i>First issue &mdash; no previous ranking to diff against. '
                     f'From tomorrow this section shows what moved.</i></p>')

    def section(title, rows, fmt):
        if not rows:
            return
        parts.append(f"<h3 {st_h}>{title}</h3><ul style=\"padding-left:18px;margin:0\">"
                     + "".join(f"<li {st_li}>{fmt(r)}</li>" for r in rows) + "</ul>")

    def entered_line(r):
        was = f', was #{r["prev_rank"]}' if r.get("prev_rank") else ", was not a candidate"
        return (f'{card(r)} &mdash; #{r["rank"]}, score {r["invest_score"]:.0f}{was}'
                f' · entry {_money(r.get("floor_low"))}')

    section("New to the top 20", d["entered"], entered_line)
    section("Dropped out of the top 20", d["exited"],
            lambda r: f'{card(r)} &mdash; was #{r["prev_rank"]}, '
                      + (f'now #{r["rank"]}' if r.get("rank") else f'screened out: {_esc(r.get("disqualified"))}'))
    section("Asking price ran ahead of sales", d["stretched"],
            lambda r: f'{card(r)} &mdash; listed {_pct(r["ask_premium_pct"])} vs what copies sold for '
                      f'(was {_pct(r["prev_premium"])}). Historically that gave a little back.')
    section("Asking price fell below sales", d["cheapened"],
            lambda r: f'{card(r)} &mdash; listed {_pct(r["ask_premium_pct"])} vs what copies sold for '
                      f'(was {_pct(r["prev_premium"])}).')
    section("Biggest score gains", d["climbers"],
            lambda r: f'{card(r)} &mdash; {r["prev_score"]:.0f} &rarr; {r["invest_score"]:.0f} '
                      f'({r["score_delta"]:+.0f}), #{r.get("prev_rank") or "—"} &rarr; #{r["rank"]}')
    section("Biggest score losses", d["fallers"],
            lambda r: f'{card(r)} &mdash; {r["prev_score"]:.0f} &rarr; {r["invest_score"]:.0f} '
                      f'({r["score_delta"]:+.0f}), #{r.get("prev_rank") or "—"} &rarr; #{r["rank"]}')

    # Always: the top of the list, so the email stands on its own.
    top = d["top"][:10]
    if top:
        rows = "".join(
            f'<tr><td style="padding:5px 8px 5px 0;font:13px ui-monospace,Menlo,monospace;color:{MUTED}">{r["rank"]}</td>'
            f'<td style="padding:5px 8px 5px 0;font:13px -apple-system,Segoe UI,Helvetica,Arial,sans-serif">{card(r)}</td>'
            f'<td style="padding:5px 8px 5px 0;font:13px ui-monospace,Menlo,monospace;text-align:right">{_money(r.get("market_price"))}</td>'
            f'<td style="padding:5px 8px 5px 0;font:13px ui-monospace,Menlo,monospace;text-align:right">{_money(r.get("floor_low"))}</td>'
            f'<td style="padding:5px 0;font:13px ui-monospace,Menlo,monospace;text-align:right;font-weight:700">{r["invest_score"]:.0f}</td></tr>'
            for r in top)
        parts.append(
            f'<h3 {st_h}>Top 10 today</h3>'
            f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%">'
            f'<tr><th></th><th style="text-align:left;font:10px ui-monospace,Menlo,monospace;letter-spacing:.1em;color:{MUTED}">CARD</th>'
            f'<th style="text-align:right;font:10px ui-monospace,Menlo,monospace;letter-spacing:.1em;color:{MUTED}">PRICE</th>'
            f'<th style="text-align:right;font:10px ui-monospace,Menlo,monospace;letter-spacing:.1em;color:{MUTED}">ENTRY</th>'
            f'<th style="text-align:right;font:10px ui-monospace,Menlo,monospace;letter-spacing:.1em;color:{MUTED}">SCORE</th></tr>'
            f'{rows}</table>')

    if report_url:
        parts.append(
            f'<p style="margin:22px 0 8px"><a href="{_esc(report_url)}" '
            f'style="display:inline-block;padding:10px 16px;background:{A};color:#0b0d10;'
            f'font:700 13px ui-monospace,Menlo,monospace;letter-spacing:.08em;text-transform:uppercase;'
            f'text-decoration:none;border-radius:2px">Open the full report &rarr;</a></p>')

    parts.append(
        f'<p style="margin:18px 0 0;font:12px/1.6 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:{MUTED}">'
        f'{_esc(brand)} is published by GUNDECK.AI. Every number describes what a card has already '
        f'done. Nothing here is a forecast, a recommendation, or financial advice. Trading cards can '
        f'lose value. Entry prices are the cheapest Near Mint English listing, shipping included, at '
        f'build time.</p>')
    return "\n".join(parts)


def to_markdown(d: dict, *, report_url: str | None = None, lead: str | None = None) -> str:
    """Same content, for a plain-text preview or a second channel."""
    L = []
    if lead:
        L.append(lead + "\n")
    if d["feed_late"]:
        L.append(f"**Price feed is {d['feed_age_days']} days behind** — built on prices through {d['date']}.\n")
    L.append(f"{d['candidates']} candidates from {d['candidates'] + d['screened']} screened, prices through {d['date']}."
             + (f" Breadth {d['breadth']['now_pct']}%." if d['breadth'].get('now_pct') is not None else ""))
    if not d["has_previous"]:
        L.append("\n_First issue — nothing to diff against yet._")

    def sec(title, rows, fmt):
        if rows:
            L.append(f"\n**{title}**")
            L.extend(f"- {fmt(r)}" for r in rows)

    sec("New to the top 20", d["entered"], lambda r: f"{r['name']} — #{r['rank']}, score {r['invest_score']:.0f}, entry {_money(r.get('floor_low'))}")
    sec("Dropped out of the top 20", d["exited"], lambda r: f"{r['name']} — was #{r['prev_rank']}, " + (f"now #{r['rank']}" if r.get('rank') else f"screened out: {r.get('disqualified')}"))
    sec("Asking price ran ahead of sales", d["stretched"], lambda r: f"{r['name']} — {_pct(r['ask_premium_pct'])} vs sold (was {_pct(r['prev_premium'])})")
    sec("Asking price fell below sales", d["cheapened"], lambda r: f"{r['name']} — {_pct(r['ask_premium_pct'])} vs sold (was {_pct(r['prev_premium'])})")
    sec("Biggest score gains", d["climbers"], lambda r: f"{r['name']} — {r['prev_score']:.0f} → {r['invest_score']:.0f}")
    sec("Biggest score losses", d["fallers"], lambda r: f"{r['name']} — {r['prev_score']:.0f} → {r['invest_score']:.0f}")
    if d["top"]:
        L.append("\n**Top 10 today**")
        L.extend(f"{r['rank']}. {r['name']} — {_money(r.get('market_price'))}, entry {_money(r.get('floor_low'))}, score {r['invest_score']:.0f}"
                 for r in d["top"][:10])
    if report_url:
        L.append(f"\n[Open the full report]({report_url})")
    return "\n".join(L)


def subject(d: dict, *, brand: str = "Market Haro") -> str:
    """One line. Leads with the most useful fact, which is usually a change."""
    if d["feed_late"]:
        return f"{brand} {d['date']} — feed {d['feed_age_days']} days behind"
    if d["entered"]:
        r = d["entered"][0]
        return f"{brand} {d['date']} — {r['name']} enters the top 20 at #{r['rank']}"
    if d["stretched"]:
        return f"{brand} {d['date']} — {len(d['stretched'])} asking price{'s' if len(d['stretched']) != 1 else ''} ran ahead of sales"
    top = d["top"][0] if d["top"] else None
    return f"{brand} {d['date']} — {top['name']} leads at {top['invest_score']:.0f}" if top else f"{brand} {d['date']}"
