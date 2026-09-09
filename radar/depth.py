"""Set depth: what is under a box.

A booster box sells six a day or none a day because of the cards inside it,
not because of the box. Freedom Ascension has a dozen cards over $1,000 and
its commons-with-a-plus are $60; Dual Impact has two chase cards and nothing
behind them. That is the whole reason one moves and the other does not, and
it is invisible on a page that prices boxes and singles in separate lists.

For every set on record this measures the singles beneath it: how many are
worth $50, $100 and $500 or more, what the top ten are worth together and
how that changed over 30 days, and how much money moved through the set's
singles and its sealed product in the last 30 days (copies sold x what they
sold for). The table is a panel on the page; the row for a box's own set is
handed to the writer with every sealed case.
"""

from __future__ import annotations

from typing import Any, Sequence

from .invest import _change_over, _f, _window

TIERS = (50, 100, 500)
TOP_N = 10
MIN_CARDS = 5          # a "set" with fewer priced singles is a promo bucket, not a set


def _dollars_30d(pts: Sequence[Sequence[Any]]) -> float:
    return sum((_f(p[2]) or 0.0) * ((_f(p[3]) if len(p) > 3 else None) or _f(p[1]) or 0.0)
               for p in _window(list(pts), 30) if _f(p[1]))


def build(rows: Sequence[dict], series: dict, sets: Sequence[dict], *, as_of: str) -> list[dict[str, Any]]:
    """rows: db.latest_prices(); series: db.all_series_with_volume(); sets: db.sets()."""
    release = {str(s["id"]): s.get("release_date") for s in sets}
    by_set: dict[str, dict[str, Any]] = {}
    for r in rows:
        sid = str(r.get("set_id") or "")
        if not sid:
            continue
        rec = by_set.setdefault(sid, {"set_id": sid, "set_name": r.get("set_name"),
                                      "release_date": release.get(sid), "singles": [], "sealed": []})
        key = (str(r["card_id"]), r.get("printing") or "Normal")
        price = _f(r.get("market_price"))
        if not price:
            continue
        pts = series.get(key, [])
        item = {"name": r.get("name"), "price": price, "printing": key[1],
                "price_30d_ago": None, "dollars_30d": round(_dollars_30d(pts))}
        ch = _change_over(pts, 30) if pts else None
        if ch is not None:
            item["price_30d_ago"] = price / (1 + ch / 100)
        (rec["sealed"] if r.get("product_type") == "Sealed Products" else rec["singles"]).append(item)

    out = []
    for rec in by_set.values():
        singles = sorted(rec["singles"], key=lambda x: -x["price"])
        if len(singles) < MIN_CARDS:
            continue
        top = singles[:TOP_N]
        top_now = sum(x["price"] for x in top)
        top_then = [x["price_30d_ago"] for x in top if x["price_30d_ago"]]
        top_now_measured = sum(x["price"] for x in top if x["price_30d_ago"])
        row = {
            "set_id": rec["set_id"], "set_name": rec["set_name"], "release_date": rec["release_date"],
            "singles_priced": len(singles),
            **{f"over_{t}": sum(1 for x in singles if x["price"] >= t) for t in TIERS},
            "top10_value": round(top_now),
            "top10_change_30d": (round((top_now_measured / sum(top_then) - 1) * 100)
                                 if top_then and sum(top_then) else None),
            "top_card": top[0]["name"] if top else None,
            "top_card_price": round(top[0]["price"], 2) if top else None,
            "dollars_30d_singles": round(sum(x["dollars_30d"] for x in singles)),
            "dollars_30d_sealed": round(sum(x["dollars_30d"] for x in rec["sealed"])),
        }
        row["dollars_30d"] = row["dollars_30d_singles"] + row["dollars_30d_sealed"]
        out.append(row)
    out.sort(key=lambda x: -(x["dollars_30d"] or 0))
    return out


def for_set(table: Sequence[dict], set_id: Any) -> dict | None:
    """The writer's slice: one set's row, keys that read as facts."""
    row = next((r for r in table if str(r["set_id"]) == str(set_id)), None)
    if not row:
        return None
    keep = ("set_name", "singles_priced", "over_50", "over_100", "over_500", "top10_value",
            "top10_change_30d", "top_card", "top_card_price", "dollars_30d_singles", "dollars_30d_sealed")
    return {k: row[k] for k in keep if row.get(k) is not None}


def facts_for_lead(table: Sequence[dict], n: int = 3) -> list[dict]:
    """The three sets money is moving through, for the email's opening."""
    return [{"set_name": r["set_name"], "dollars_30d": r["dollars_30d"], "over_100": r["over_100"],
             "top10_change_30d": r["top10_change_30d"]} for r in table[:n]]
