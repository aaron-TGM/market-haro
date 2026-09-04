"""One set, from release to now: has the post-release fall stopped?

WHY THIS IS NOT THE HOLD SCREEN

`invest.py` asks "has this been climbing for months, and can I get out of it".
Every threshold in it needs 45+ days of daily history and a 90-day trend. A set
released six weeks ago has neither, so running the hold screen over a new set
disqualifies almost all of it as "too new" -- correctly, and uselessly.

A new set has one question worth asking: **is it still repricing downward, or
has it found a floor?** That needs the price path since release, which is short
but real, and it has to be read per price tier because the tiers do not behave
alike.

WHAT IT FOUND ON GD05 FREEDOM ASCENSION

Released 2026-07-24, measured to 2026-09-03 across 162 products with at least
ten post-release closes:

    median off its post-release peak     -56.9%
    median since release                 -50.8%
    last 7 days vs the 7 before          -21.7%
    still falling                        152 of 162

Graded almost perfectly by price at release:

    $0-25     n=119   off peak -71.1%   last 7d -42.9%
    $25-100   n= 17   off peak -38.4%   last 7d  -9.3%
    $100-500  n= 17   off peak -17.0%   last 7d  -3.5%
    $500+     n=  9   off peak  -4.8%   last 7d  -0.9%

That is a release flooding into supply. The commons and mid-rares have given up
two thirds of their value and were STILL dropping 43% in the final week; the
genuine chase cards barely moved. The most useful thing this report says is that
the fall has not stopped -- so "it's down 70%, it must be cheap" is the wrong
read, because there is no floor visible in the data yet.

It also matches what the attention data said before the prices moved. GD05 peaked
in Google Trends on 2026-07-19 -- the week BEFORE release -- and was at 43% of
that peak by 2026-08-10. `heat.py` called it "singles from it are being bought
into falling attention, not rising". The prices followed.

WHAT IT DELIBERATELY DOES NOT DO

No score, no ranking, no buy call. "Still falling" describes the last fortnight,
not the next one, and a set that has fallen 70% can fall further. The one thing
it asserts is negative and safe: nothing here shows a floor, so nothing here
supports calling a bottom.
"""

from __future__ import annotations

import statistics
from typing import Any, Sequence

# Bands by price AT RELEASE, not by price today -- a card that opened at $40 and
# now sits at $8 belongs with the mid-tier it was priced into, not with the bulk
# it has fallen to. Bucketing on today's price would hide the whole effect.
PRICE_BANDS = (
    (0, 25, "$0–25"),
    (25, 100, "$25–100"),
    (100, 500, "$100–500"),
    (500, float("inf"), "$500+"),
)

# Below this many post-release closes there is no path to read, only noise.
MIN_POINTS = 10

# The "has it stopped" window. Seven days against the seven before: long enough
# to survive one quiet day, short enough to notice a turn.
RECENT_DAYS = 7


def _median(xs: Sequence[float]) -> float | None:
    return round(statistics.median(xs), 1) if xs else None


def trajectory(series: Sequence[Sequence[Any]], released: str) -> dict[str, Any] | None:
    """The post-release price path -> where it stands against its own peak.

    `series` is [(date, price, ...), ...] ascending. Points before the release
    date are dropped: preorder listings trade on a different basis, and several
    GD05 products carry them back to 2026-06-06.
    """
    post = [(d, p) for d, p, *_ in series if p and d >= released]
    if len(post) < MIN_POINTS:
        return None

    px = [p for _, p in post]
    first, last = px[0], px[-1]
    peak = max(px)
    peak_date = post[px.index(peak)][0]

    recent = px[-RECENT_DAYS:]
    prior = px[-RECENT_DAYS * 2 : -RECENT_DAYS]
    last7 = None
    if prior:
        a, b = statistics.mean(recent), statistics.mean(prior)
        if b:
            last7 = round((a / b - 1) * 100, 1)

    return {
        "release_price": round(first, 2),
        "peak": round(peak, 2),
        "peak_date": peak_date,
        "now": round(last, 2),
        "off_peak_pct": round((last / peak - 1) * 100, 1) if peak else None,
        "since_release_pct": round((last / first - 1) * 100, 1) if first else None,
        "last7_pct": last7,
        "points": len(post),
        "path": px,
    }


def compare(rows: Sequence[dict], released: str) -> dict[str, Any]:
    """Rows carrying `series` and metadata -> the set-level picture."""
    scored = []
    for r in rows:
        t = trajectory(r.get("series") or [], released)
        if not t:
            continue
        spread = None
        if r.get("entry") and r.get("shelf_med"):
            spread = round((r["shelf_med"] / r["entry"] - 1) * 100, 1)
        scored.append({**r, **t, "spread": spread})

    if not scored:
        return {
            "rows": [], "n": 0, "bands": [], "rarity": [],
            "verdict": "No product has enough post-release history yet.",
        }

    singles = [r for r in scored if r.get("product_type") != "Sealed Products"]
    sealed = [r for r in scored if r.get("product_type") == "Sealed Products"]
    last7 = [r["last7_pct"] for r in scored if r["last7_pct"] is not None]

    bands = []
    for lo, hi, label in PRICE_BANDS:
        g = [r for r in scored if lo <= r["release_price"] < hi]
        if not g:
            continue
        g7 = [r["last7_pct"] for r in g if r["last7_pct"] is not None]
        bands.append({
            "label": label,
            "n": len(g),
            "off_peak": _median([r["off_peak_pct"] for r in g]),
            "since_release": _median([r["since_release_pct"] for r in g]),
            "last7": _median(g7),
            "falling": sum(1 for x in g7 if x < 0),
            "n7": len(g7),
        })

    by_rarity: dict[str, list[float]] = {}
    for r in singles:
        by_rarity.setdefault(r.get("rarity") or "—", []).append(r["off_peak_pct"])
    rarity = sorted(
        ({"rarity": k, "n": len(v), "off_peak": _median(v)} for k, v in by_rarity.items()),
        key=lambda x: -x["n"],
    )

    return {
        # Worst off its peak first -- that is the list worth reading.
        "rows": sorted(scored, key=lambda r: r["off_peak_pct"]),
        "n": len(scored),
        "median_off_peak": _median([r["off_peak_pct"] for r in scored]),
        "median_since_release": _median([r["since_release_pct"] for r in scored]),
        "median_last7": _median(last7),
        "still_falling": sum(1 for x in last7 if x < 0),
        "n_last7": len(last7),
        "median_singles": _median([r["off_peak_pct"] for r in singles]),
        "median_sealed": _median([r["off_peak_pct"] for r in sealed]),
        "n_singles": len(singles),
        "n_sealed": len(sealed),
        "bands": bands,
        "rarity": rarity,
        "verdict": verdict(scored, bands, last7),
    }


def verdict(scored: Sequence[dict], bands: Sequence[dict], last7: Sequence[float]) -> str:
    """States whether the fall has stopped. Refuses to call a bottom."""
    if not scored:
        return "Not enough post-release history to say anything."

    off = statistics.median(r["off_peak_pct"] for r in scored)
    parts = [f"The median product is {off:+.1f}% off its post-release peak."]

    if last7:
        med7 = statistics.median(last7)
        falling = sum(1 for x in last7 if x < 0)
        if med7 <= -3:
            parts.append(
                f"It has not stopped: {falling} of {len(last7)} are lower over the last week "
                f"than the week before, median {med7:+.1f}%."
            )
        elif med7 >= 3:
            parts.append(
                f"The last week turned up — median {med7:+.1f}% against the week before, "
                f"{len(last7) - falling} of {len(last7)} higher. One week is not a floor."
            )
        else:
            parts.append(
                f"The last week was flat, median {med7:+.1f}% against the week before. That is "
                f"the first sign of a floor, not proof of one."
            )

    if len(bands) >= 3:
        cheap, dear = bands[0], bands[-1]
        if (
            cheap["off_peak"] is not None
            and dear["off_peak"] is not None
            and cheap["off_peak"] < dear["off_peak"] - 15
        ):
            parts.append(
                f"The fall is graded by what a card was worth at release: {cheap['label']} is "
                f"down a median {cheap['off_peak']:+.1f}% while {dear['label']} is "
                f"{dear['off_peak']:+.1f}%. Supply arrives at the cheap end first; the genuine "
                f"chase cards hold."
            )

    parts.append(
        "This describes the last six weeks, not the next six. A card down 70% can go lower, "
        "and nothing here shows a floor."
    )
    return " ".join(parts)


# --------------------------------------------------------------------------
# Rendering. Same visual language as the hold screen -- this is the same
# project asking a different question, not a different product.
# --------------------------------------------------------------------------
def _spark(px: Sequence[float], last7: float | None, *, w: int = 120, h: int = 26) -> str:
    """The post-release path, coloured by whether it is STILL falling.

    Colouring by last-versus-first would introduce a third signal next to the
    two columns beside it and contradict them: Domon Kasshu opened at $0.72 and
    sits at $0.84, so last-vs-first says green while the card is 56% off its
    $1.92 peak. Colouring by the last-7-day direction makes the line answer the
    same question as the rest of the report -- has it stopped.
    """
    if len(px) < 3:
        return ""
    lo, hi = min(px), max(px)
    rng = (hi - lo) or 1
    step = w / (len(px) - 1)
    pts = " ".join(
        f"{i * step:.1f},{h - 1 - (v - lo) / rng * (h - 2):.1f}" for i, v in enumerate(px)
    )
    stroke = "var(--text-muted)" if last7 is None else (
        "var(--down)" if last7 < 0 else "var(--up)"
    )
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="1.4"/></svg>'
    )


def render(
    summary: dict,
    *,
    set_name: str,
    set_code: str,
    released: str,
    as_of: str,
    notes: Sequence[str] = (),
    heat: dict | None = None,
) -> str:
    from .dashboard import CSS, _esc

    def money(v):
        return "—" if v is None else f"${v:,.2f}"

    def pct(v, *, bold=False):
        if v is None:
            return '<span class="flat">—</span>'
        cls = "cool" if v > 0 else ("hot" if v < 0 else "flat")
        w = ";font-weight:700" if bold else ""
        return f'<span class="{cls}" style="white-space:nowrap{w}">{v:+.1f}%</span>'

    days = ""
    try:
        from datetime import date as _d

        days = f" · {(_d.fromisoformat(as_of) - _d.fromisoformat(released)).days} days old"
    except (ValueError, TypeError):
        pass

    band_rows = "".join(
        f'<tr><td>{_esc(b["label"])}</td><td class="num">{b["n"]}</td>'
        f'<td class="num">{pct(b["off_peak"], bold=True)}</td>'
        f'<td class="num">{pct(b["since_release"])}</td>'
        f'<td class="num">{pct(b["last7"], bold=True)}</td>'
        f'<td class="num">{b["falling"]} of {b["n7"]}</td></tr>'
        for b in summary["bands"]
    )
    rarity_rows = "".join(
        f'<tr><td>{_esc(r["rarity"])}</td><td class="num">{r["n"]}</td>'
        f'<td class="num">{pct(r["off_peak"])}</td></tr>'
        for r in summary["rarity"]
    )

    body = []
    for i, r in enumerate(summary["rows"], 1):
        url = (
            f'https://www.tcgplayer.com/product/{r["tcgplayer_id"]}?Language=English'
            if r.get("tcgplayer_id") else None
        )
        nm = (
            f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(r["name"])}</a>'
            if url else _esc(r["name"])
        )
        meta = " · ".join(filter(None, [
            r.get("number"),
            r.get("printing") if r.get("printing") not in (None, "Normal") else None,
            "sealed" if r.get("product_type") == "Sealed Products" else None,
        ]))
        body.append(
            f'<tr><td class="rank">{i}</td>'
            f'<td><div class="nm">{nm}<span class="rar">{_esc(r.get("rarity") or "—")}</span></div>'
            f'<div class="meta">{_esc(meta)}</div></td>'
            f'<td class="num">{money(r["release_price"])}</td>'
            f'<td class="num">{money(r["peak"])}</td>'
            f'<td class="num">{money(r["now"])}</td>'
            f'<td class="num">{pct(r["off_peak_pct"], bold=True)}</td>'
            f'<td class="num">{pct(r["last7_pct"])}</td>'
            f'<td>{_spark(r["path"], r["last7_pct"])}</td>'
            f'<td class="num">{money(r.get("entry"))}</td>'
            f'<td class="num">{"—" if r.get("copies") is None else r["copies"]}</td>'
            f'<td class="num">{"—" if r.get("listings") is None else r["listings"]}</td>'
            f"</tr>"
        )

    notes_html = ""
    if notes:
        notes_html = (
            '<div class="panel"><h4>How to read this</h4><ul class="notes">'
            + "".join(f"<li>{_esc(x)}</li>" for x in notes)
            + "</ul></div>"
        )

    heat_html = ""
    if heat:
        s = next((x for x in (heat.get("sets") or []) if x.get("set_code") == set_code), None)
        if s:
            heat_html = f"""
<div class="panel">
  <h4>The attention data said this first</h4>
  <p class="lead">Search interest in {_esc(s["name"].title())} peaked
  <b>{_esc(s["peak_date"])}</b> &mdash; the week <i>before</i> release &mdash; and was already at
  <b>{s["pct_of_peak"]}%</b> of that peak when captured on {_esc(heat.get("captured_at"))},
  {s["weeks_since_peak"]} weeks in. Every set so far has done this: Steel Requiem sits at 7% of
  its peak, Newtype Rising at 4%. The table below is what that looks like once it reaches the
  singles.</p>
</div>"""

    def _sign(v):
        if v is None:
            return "neutral"
        return "down" if v < 0 else ("up" if v > 0 else "neutral")

    mo = summary["median_off_peak"]
    m7 = summary["median_last7"]
    return f"""<!doctype html>
<html lang="en" class="viz-root" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Haro · {_esc(set_code)} {_esc(set_name)} — {_esc(as_of)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap">
<style>{CSS}
.lead{{font-size:13px;line-height:1.7;color:var(--text);margin:0}}
.verdict{{padding:14px 16px;margin:14px 0;border-left:2px solid var(--down);
  background:var(--surface);font-size:14px;line-height:1.75}}
.panel h4{{margin:0 0 10px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--accent)}}
.panel{{padding:14px 16px;margin:14px 0}}
.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}
table.mini{{width:100%;border-collapse:collapse;font-size:12px}}
table.mini th{{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);
  text-align:left;padding:5px 6px;border-bottom:1px solid var(--border);font-weight:400}}
table.mini td{{padding:6px;border-bottom:1px dotted var(--border)}}
table.mini td.num,table.mini th.num{{text-align:right}}
.notes{{margin:0;padding-left:18px;font-size:12px;line-height:1.85;color:var(--text-muted)}}
.nm{{font-weight:700}}
.rar{{font-size:9px;letter-spacing:.08em;padding:1px 5px;margin-left:8px;
  border:1px solid var(--border);border-radius:2px;color:var(--accent)}}
.meta{{font-size:10px;color:var(--text-muted);letter-spacing:.06em;text-transform:uppercase}}
.spark{{display:block;width:120px;height:26px}}
/* The hold screen colours tiles by position; here every headline number is
   signed, so position would say green for a 21% fall. Sign wins. */
.tile:nth-child(n) .value{{color:var(--accent)}}
.tile .value.down{{color:var(--down)}}
.tile .value.up{{color:var(--up)}}
.tile .value.neutral{{color:var(--cyan)}}
</style>
</head>
<body class="viz-root">
<div class="wrap">
<header>
  <div>
    <div class="brand"><span class="brand-from">Market Haro · from</span> GUNDECK.AI</div>
    <h1>{_esc(set_code)} {_esc(set_name)}</h1>
    <p class="mission">What one set has done since it launched, and whether the fall has
      stopped. This is not the hold screen &mdash; a set this new has no 90-day trend to
      judge, so the only honest question is whether it has found a floor.</p>
    <p class="stamp">Released {_esc(released)}{days} · priced through {_esc(as_of)} ·
      {summary["n"]} products with {MIN_POINTS}+ post-release closes ·
      English printings only · source: tcgapi.dev</p>
  </div>
</header>

<div class="tiles">
  <div class="tile"><div class="label">Off post-release peak</div>
    <div class="value {_sign(mo)}">{mo:+.1f}%</div>
    <div class="foot">median of {summary["n"]} products</div></div>
  <div class="tile"><div class="label">Since release</div>
    <div class="value {_sign(summary["median_since_release"])}">{summary["median_since_release"]:+.1f}%</div>
    <div class="foot">median, first close to now</div></div>
  <div class="tile"><div class="label">Last 7 days</div>
    <div class="value {_sign(m7)}">{"—" if m7 is None else f"{m7:+.1f}%"}</div>
    <div class="foot">vs the 7 before</div></div>
  <div class="tile"><div class="label">Still falling</div>
    <div class="value {"down" if summary["still_falling"] > summary["n_last7"] / 2 else ""}">{summary["still_falling"]}</div>
    <div class="foot">of {summary["n_last7"]} measurable</div></div>
  <div class="tile"><div class="label">Singles</div>
    <div class="value {_sign(summary["median_singles"])}">{summary["median_singles"]:+.1f}%</div>
    <div class="foot">off peak, {summary["n_singles"]} products</div></div>
  <div class="tile"><div class="label">Sealed</div>
    <div class="value {_sign(summary["median_sealed"])}">{"—" if summary["median_sealed"] is None
      else f"{summary['median_sealed']:+.1f}%"}</div>
    <div class="foot">off peak, {summary["n_sealed"]} products</div></div>
</div>

<div class="verdict">{_esc(summary["verdict"])}</div>
{heat_html}

<div class="two">
  <div class="panel">
    <h4>Graded by what it was worth at release</h4>
    <table class="mini"><thead><tr><th>Price at release</th><th class="num">n</th>
      <th class="num">Off peak</th><th class="num">Since release</th>
      <th class="num">Last 7d</th><th class="num">Falling</th></tr></thead>
      <tbody>{band_rows}</tbody></table>
    <p class="sub2" style="margin-top:10px">Banded by opening price, not by today's price &mdash;
      a card that opened at $40 and now sits at $8 belongs with the tier it was priced into.
      Bucketing on today's price would hide the whole effect.</p>
  </div>
  <div class="panel">
    <h4>By rarity (singles only)</h4>
    <table class="mini"><thead><tr><th>Rarity</th><th class="num">n</th>
      <th class="num">Off peak</th></tr></thead><tbody>{rarity_rows}</tbody></table>
    <p class="sub2" style="margin-top:10px">Rarity and price are not the same thing. The LR++
      chase cards hold because they are genuinely scarce; an R+ at $20 is not scarce, it is
      just rarer than a common.</p>
  </div>
</div>

{notes_html}

<div class="panel tablewrap"><table><thead><tr>
  <th class="rank">#</th><th>Product</th>
  <th class="num">At release</th><th class="num">Peak</th><th class="num">Now</th>
  <th class="num">Off peak</th><th class="num">Last 7d</th>
  <th>Path since release</th>
  <th class="num">Entry</th><th class="num">NM copies</th><th class="num">Listings</th>
</tr></thead><tbody>{"".join(body)}</tbody></table></div>

<footer>
  <p><b>Market Haro</b> is published by GUNDECK.AI for its subscribers. Every number here
  describes what has already happened. &ldquo;Still falling&rdquo; is a statement about the last
  fortnight, not the next one &mdash; a card down 70% can go lower, and nothing on this page
  shows a floor. Nothing here is a forecast, a recommendation, or financial advice, and nothing
  knows about bans, reprints or tournament results. Trading cards can lose value.</p>
  <p>Prices from tcgapi.dev under commercial licence · English Near Mint printings only ·
  &copy; GUNDECK.AI</p>
</footer>
</div>
</body></html>"""
