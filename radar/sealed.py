"""The sealed screen: booster boxes, starter decks, deck build boxes.

WHY IT IS SEPARATE

The hold screen scores singles on liquidity, trend, stability and scarcity,
calibrated on singles. A booster box is a different animal: its price is a
function of print waves and time since release, it trades in units not
copies, and "scarcity" means allocation, not rarity. Scoring it with the
singles model would be a number that means nothing. So sealed gets its own
screen with the questions a sealed investor actually asks:

  - where is it against release: the earliest price we have for it, and how
    far it has come since
  - how old is it: days since the set released (the API's own date)
  - is it still rising or has it rolled: 7d / 30d / 90d, and the drawdown
    from its 90-day high
  - does it move: units sold a day, and ask vs sold like the singles

No score, no sizing. Sorted by 30-day change by default, because for sealed
the question is "what is moving now", not "what is worth holding".
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any, Sequence

from .invest import _window, features, weekly_points

KIND = "sealed"

CHECKLIST = [
    "Confirm it is the English print run and factory sealed — resealed and Japanese product are "
    "different markets and both list under the same name.",
    "Check for a reprint or a new wave. Bandai reprints readily; sealed prices are print waves and "
    "time, and a reprint announcement ends a run the same day.",
    "Compare the price to the retail price at release. A box below retail is a different bet from a "
    "box at three times retail.",
    "Weigh shipping. A booster box ships heavy; the cheapest listing is not always the cheapest landed.",
    "Decide the exit before you buy: at this rate of units sold a day, how long does it take to sell "
    "what you are holding?",
]


def _kind_word(name: str) -> str:
    n = (name or "").lower()
    if "case" in n:
        return "case"
    if "booster box" in n:
        return "booster box"
    if "pack" in n:
        return "booster pack"
    if "deck build box" in n:
        return "deck build box"
    if "starter deck" in n or "deck" in n:
        return "starter deck"
    return "sealed product"


def thesis(r: dict) -> str:
    """One sentence a person would say about a box, from the numbers."""
    what = _kind_word(r.get("name") or "")
    age = r.get("days_since_release")
    first = r.get("first_price")
    since = r.get("change_since_first")
    parts = [f"A {what} at ${r['market_price']:,.2f}"]
    if age is not None:
        parts[0] += f", {age} days after release" if age >= 0 else f", {-age} days before release"
    s = parts[0] + "."
    if since is not None and first:
        s += (f" Against the earliest price we hold (${first:,.2f} on {r.get('first_date')}) it is "
              f"{'up' if since >= 0 else 'down'} {abs(since)}%.")
    if r.get("h30d") is not None:
        s += f" Over 30 days it is {r['h30d']:+.0f}%"
        if r.get("h7d") is not None:
            s += f", the last week {r['h7d']:+.0f}%"
        s += "."
    if r.get("avg_daily_sales") is not None:
        s += f" It sells about {r['avg_daily_sales']} units a day."
    return s


def watch(r: dict) -> str:
    """What would break it, for sealed: reprints, a rolling trend, and a thin market."""
    notes = []
    dd = r.get("drawdown_pct")
    if dd is not None and dd >= 10:
        notes.append(f"it is already {dd:.0f}% off its 90-day high")
    if r.get("h7d") is not None and r["h7d"] <= -10:
        notes.append(f"the last week gave back {abs(r['h7d']):.0f}%")
    if (r.get("consistency_pct") or 100) < 50:
        notes.append(f"only {r['consistency_pct']}% of weeks closed up")
    if r.get("avg_daily_sales") is not None and r["avg_daily_sales"] < 1:
        notes.append(f"at {r['avg_daily_sales']} units a day, exiting more than a few takes time")
    if r.get("ask_premium_pct") is not None and r["ask_premium_pct"] > 5:
        notes.append(f"the listed price is running {r['ask_premium_pct']:.0f}% above what units have sold for")
    lead = "Watch: " + ("; ".join(notes) if notes else "nothing in the numbers is flashing yet")
    return lead + ". A reprint or a new wave is the thing that ends a sealed run, and it is not visible in price data."


def _days_between(a: str | None, b: str | None) -> int | None:
    try:
        return (_date.fromisoformat(str(b)[:10]) - _date.fromisoformat(str(a)[:10])).days
    except (ValueError, TypeError):
        return None


def evaluate(rows: Sequence[dict], series: dict, sets: Sequence[dict], as_of: str,
             shelves: dict | None = None) -> list[dict]:
    """rows: latest price rows for sealed products; series: all_series_with_volume;
    shelves: db.listings_series(), for the supply measure."""
    from .invest import shelf_math, supply

    release = {str(s["id"]): s.get("release_date") for s in sets}
    out = []
    for r in rows:
        key = (str(r["card_id"]), r.get("printing") or "Normal")
        pts = series.get(key, [])
        feats = features(pts) or {}
        feats.update(supply((shelves or {}).get(key, []), as_of=as_of))
        feats.update(shelf_math({**r, **feats}))
        price = r.get("market_price")
        if not price:
            continue
        first = next(((str(p[0])[:10], float(p[1])) for p in pts if p[1]), None)
        rel = release.get(str(r.get("set_id")))
        rec = {
            **{k: r.get(k) for k in ("card_id", "printing", "name", "set_name", "set_id", "number",
                                    "tcgplayer_id", "tcgplayer_url", "image_url", "product_type",
                                    "market_price", "low_price", "median_price", "total_listings")},
            **feats,
            "kind": KIND,
            "rarity": None,
            "release_date": rel,
            "days_since_release": _days_between(rel, as_of) if rel else None,
            "first_date": first[0] if first else None,
            "first_price": first[1] if first else None,
            "change_since_first": round((price / first[1] - 1) * 100) if first and first[1] else None,
            "series": [(str(p[0])[:10], float(p[1])) for p in _window(pts, 90) if p[1]],
            "series_long": weekly_points(pts, 400),
        }
        rec["change_7d"] = feats.get("h7d")
        rec["change_30d"] = feats.get("h30d")
        rec["change_3d"] = feats.get("h3d")
        rec["thesis"] = thesis(rec)
        rec["watch"] = watch(rec)
        out.append(rec)
    out.sort(key=lambda x: (-(x.get("change_30d") if x.get("change_30d") is not None else -1e9),
                            -(x.get("market_price") or 0)))
    for i, rec in enumerate(out, 1):
        rec["rank"] = i
    return out


def summary(rows: Sequence[dict]) -> dict[str, Any]:
    priced = [r for r in rows if r.get("change_30d") is not None]
    up = sum(1 for r in priced if r["change_30d"] > 0)
    return {"count": len(rows), "measured": len(priced), "up_30d": up,
            "breadth_30d": round(100 * up / len(priced)) if priced else None}
