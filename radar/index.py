"""The GUNDECK 50: one number for the market.

WHAT IT IS

An equal-weight index of the fifty most-traded English singles priced $5
and up, base 100.
Equal weight, not value weight, because a value-weighted index of this market
is three chase cards wearing a trench coat; equal weight says what the typical
liquid card did. "Most traded" is copies sold over the last 90 days, which is
the one liquidity measure the API records per day.

HOW IT IS BUILT

  - Constituents are fixed for a calendar month and rebalanced on the first
    run of each month (data/index_members.json records who is in and since
    when). Reselecting every day would let survivorship drift the number.
  - The level is chain-linked: each step is the mean price relative of the
    members observed that day (see `compute`). A card that enters mid-year
    joins at the current level; one that stops trading stops counting.
  - The base is 100 on the first date at least half the members are priced.
    The level is stored daily in data/index.ndjson, one JSON object per
    line, rewritten whole and deterministically like the rest of the archive.

The index is descriptive. It is the market's own average, not a forecast.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date as _date
from datetime import timedelta
from pathlib import Path
from typing import Any, Sequence

from .invest import _change_over

SIZE = 50
MIN_PRICE = 5.0
COVERAGE = 0.50
LOOKBACK_DAYS = 400
NAME = "GUNDECK 50"

Series = dict[tuple[str, str], list[tuple[str, float, float, Any]]]


def _volume_90d(pts: Sequence[Sequence[Any]], as_of: str) -> float:
    cut = (_date.fromisoformat(as_of) - timedelta(days=90)).isoformat()
    return sum(float(p[2] or 0) for p in pts if str(p[0])[:10] >= cut)


def select(series: Series, cards: dict[str, dict], as_of: str, *, size: int = SIZE) -> list[dict]:
    """The `size` most-traded singles priced at least MIN_PRICE on the last close."""
    ranked = []
    for (cid, printing), pts in series.items():
        c = cards.get(str(cid)) or {}
        if c.get("product_type") == "Sealed Products" or not pts:
            continue
        last = pts[-1]
        if not last[1] or last[1] < MIN_PRICE:
            continue
        vol = _volume_90d(pts, as_of)
        if vol <= 0:
            continue
        ranked.append({"card_id": str(cid), "printing": printing, "name": c.get("name"),
                       "set_name": c.get("set_name"), "volume_90d": round(vol)})
    ranked.sort(key=lambda r: (-r["volume_90d"], r["card_id"], r["printing"]))
    return ranked[:size]


def members(path: Path, series: Series, cards: dict[str, dict], as_of: str) -> dict:
    """Load this month's constituents, or select and record them."""
    month = as_of[:7]
    if path.exists():
        try:
            cur = json.loads(path.read_text(encoding="utf-8"))
            if cur.get("month") == month and cur.get("members"):
                return cur
        except (ValueError, OSError):
            pass
    cur = {"name": NAME, "month": month, "selected_on": as_of,
           "members": select(series, cards, as_of)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cur, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return cur


def compute(series: Series, mem: Sequence[dict], as_of: str, *, lookback: int = LOOKBACK_DAYS) -> list[dict]:
    """Daily index levels [{date, value, priced}] from the members' series.

    Chain-linked: each date's level is the previous level times the mean
    price relative of the members that were actually observed that day, so a
    card that enters the market mid-year (a new set's chase card) joins at the
    current level rather than distorting the base, and a card that stops
    trading simply stops contributing. Members carry their last price forward
    between observations; a member counts toward a date only when it has a
    real observation there. Before daily history begins the grid is weekly, so
    the mean on those dates is a mean of weekly relatives -- the level is
    still a level, only its steps are coarser.
    """
    cut = (_date.fromisoformat(as_of) - timedelta(days=lookback)).isoformat()
    per: dict[tuple[str, str], dict[str, float]] = {}
    dates: set[str] = set()
    for m in mem:
        k = (m["card_id"], m["printing"])
        px = {str(p[0])[:10]: float(p[1]) for p in series.get(k, []) if p[1] and str(p[0])[:10] >= cut}
        if px:
            per[k] = px
            dates.update(px)
    if not per:
        return []
    need = max(1, int(round(len(mem) * COVERAGE)))
    out = []
    last: dict[tuple[str, str], float] = {}
    level = None
    for d in sorted(dates):
        rels = []
        for k, px in per.items():
            if d in px:
                prev = last.get(k)
                if prev and prev > 0 and level is not None:
                    rels.append(px[d] / prev)
                last[k] = px[d]
        if level is None:
            if len(last) >= need:
                level = 100.0
                out.append({"date": d, "value": 100.0, "priced": len(last)})
            continue
        if len(rels) < max(2, need // 3):
            continue  # too few real observations to call it a step
        level = level * (sum(rels) / len(rels))
        out.append({"date": d, "value": round(level, 2), "priced": len(rels)})
    return out


def summarise(levels: Sequence[dict], series: Series, mem: Sequence[dict]) -> dict[str, Any]:
    if not levels:
        return {"name": NAME, "levels": [], "members": len(mem)}
    pts = [(lv["date"], lv["value"]) for lv in levels]
    as_of = pts[-1][0]
    # Breadth within the index: members up over 7 days.
    up = tot = 0
    for m in mem:
        s = series.get((m["card_id"], m["printing"]), [])
        c = _change_over(s, 7) if s else None
        if c is not None:
            tot += 1
            up += 1 if c > 0 else 0
    return {
        "name": NAME, "as_of": as_of, "value": pts[-1][1], "members": len(mem),
        "base_date": pts[0][0],
        "change_1d": _change_over(pts, 1), "change_7d": _change_over(pts, 7),
        "change_30d": _change_over(pts, 30), "change_90d": _change_over(pts, 90),
        "change_1y": _change_over(pts, 365, tolerance=10),
        "high": max(p[1] for p in pts), "high_date": max(pts, key=lambda p: p[1])[0],
        "up_7d": up, "measured_7d": tot,
        "levels": pts,
    }


def write_levels(levels: Sequence[dict], path: Path) -> bool:
    body = "".join(json.dumps(lv, sort_keys=True, separators=(",", ":")) + "\n" for lv in levels)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == body:
        return False
    path.write_text(body, encoding="utf-8")
    return True


def build(root: Path, series: Series, cards: dict[str, dict], as_of: str) -> dict[str, Any]:
    mem = members(root / "index_members.json", series, cards, as_of)
    levels = compute(series, mem["members"], as_of)
    write_levels(levels, root / "index.ndjson")
    out = summarise(levels, series, mem["members"])
    out["month"] = mem["month"]
    out["constituents"] = mem["members"]
    return out
