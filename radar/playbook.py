"""The release playbook: what past releases did to prices, from our own data.

THE QUESTION IT ANSWERS

A new set is the one scheduled event in this market, and everyone has a
story about what it does to prices -- the previous set's chase cards fall as
attention moves on; the new set's chase cards open high and settle. Stories
are cheap. We hold daily history for the liquid part of the game and the
API's own release dates, so the honest thing is to measure it and show the
count next to every number.

For each past release with at least 30 days of aftermath:

  prior set     the most recent booster set released before it: its top
                cards by price the day before release, followed 30/60/90
                days out
  the new set   the released set's own top cards by price a week after
                release (the first week is listing chaos, not a price),
                followed the same distances
  whole market  every single priced the day before, as the baseline the
                other two should be read against

"Top cards" is the top TOP_N by price, so the sample is the part of a set an
investor would actually hold. Every figure is a median of per-card changes,
because one card doubling should not carry the group. When a release is too
recent for a window, that cell is blank rather than extrapolated.

This is descriptive. Two releases is two data points, and the panel says so.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from statistics import median
from typing import Any, Sequence

TOP_N = 20
HORIZONS = (30, 60, 90)
SETTLE_DAYS = 7          # the new set is measured from a week after release
TOLERANCE = 5            # days a price may be off the target date


def _price_at(pts: Sequence[Sequence[Any]], target: str, tol: int = TOLERANCE, *, before: bool = True) -> float | None:
    """Price nearest `target`, within `tol` days, preferring the side asked for."""
    best = None
    t = _date.fromisoformat(target)
    for d, p, *_ in pts:
        if not p:
            continue
        try:
            cur = _date.fromisoformat(str(d)[:10])
        except (ValueError, TypeError):
            continue
        gap = (cur - t).days
        if abs(gap) > tol:
            continue
        rank = (abs(gap), 0 if (gap <= 0) == before else 1)
        if best is None or rank < best[0]:
            best = (rank, float(p))
    return best[1] if best else None


def _group_changes(keys: Sequence[tuple[str, str]], series: dict, start: str, horizons=HORIZONS) -> dict[str, Any]:
    """Median % change from `start` to each horizon across the keys."""
    out: dict[str, Any] = {"n": 0}
    base: dict[tuple[str, str], float] = {}
    for k in keys:
        p0 = _price_at(series.get(k, []), start)
        if p0:
            base[k] = p0
    out["n"] = len(base)
    s = _date.fromisoformat(start)
    for h in horizons:
        target = (s + timedelta(days=h)).isoformat()
        ch = []
        for k, p0 in base.items():
            p1 = _price_at(series.get(k, []), target, before=False)
            if p1:
                ch.append((p1 / p0 - 1) * 100)
        out[f"d{h}"] = round(median(ch)) if len(ch) >= 5 else None
        out[f"n{h}"] = len(ch)
    return out


def _top_by_price(keys: Sequence[tuple[str, str]], series: dict, on: str, n: int = TOP_N) -> list[tuple[str, str]]:
    priced = []
    for k in keys:
        p = _price_at(series.get(k, []), on)
        if p:
            priced.append((p, k))
    priced.sort(reverse=True)
    return [k for _, k in priced[:n]]


def build(sets: Sequence[dict], cards: Sequence[dict], series: dict, as_of: str, *, calendar: Sequence[dict]) -> dict[str, Any]:
    """sets: db.sets(); cards: rows with id, set_id, product_type, printing-agnostic;
    series: all_series_with_volume; calendar: releases.calendar() output."""
    from .releases import kind_of

    by_set: dict[str, list[tuple[str, str]]] = {}
    keys_by_card: dict[str, list[tuple[str, str]]] = {}
    for k in series:
        keys_by_card.setdefault(str(k[0]), []).append(k)
    for c in cards:
        if c.get("product_type") == "Sealed Products" or c.get("set_id") is None:
            continue
        by_set.setdefault(str(c["set_id"]), []).extend(keys_by_card.get(str(c["id"]), []))
    all_singles = [k for ks in by_set.values() for k in ks]

    boosters = sorted(
        [s for s in sets if kind_of(s.get("name") or "") == "booster" and s.get("release_date")],
        key=lambda s: s["release_date"])
    today = _date.fromisoformat(as_of)
    events = []
    for m in calendar:
        d = _date.fromisoformat(m["date"])
        if (today - d).days < HORIZONS[0]:
            continue
        released = [s for s in sets if (s.get("release_date") or "")[:10] == m["date"]]
        rel_keys = [k for s in released for k in by_set.get(str(s["id"]), [])]
        prior = [s for s in boosters if s["release_date"][:10] < m["date"]]
        prior_set = prior[-1] if prior else None
        prior_keys = by_set.get(str(prior_set["id"]), []) if prior_set else []
        day_before = (d - timedelta(days=1)).isoformat()
        settled = (d + timedelta(days=SETTLE_DAYS)).isoformat()
        ev = {
            "date": m["date"], "label": m["label"], "kind": m.get("kind"), "names": m.get("names") or [],
            "prior_set": prior_set["name"] if prior_set else None,
            "prior": _group_changes(_top_by_price(prior_keys, series, day_before), series, day_before),
            "new": _group_changes(_top_by_price(rel_keys, series, settled), series, settled),
            "market": _group_changes(all_singles, series, day_before),
        }
        if ev["prior"]["n"] or ev["new"]["n"] or ev["market"]["n"]:
            events.append(ev)

    # One line across all measured releases, for the panel header.
    def _agg(group: str, h: int):
        vals = [e[group].get(f"d{h}") for e in events if e[group].get(f"d{h}") is not None]
        return (round(median(vals)), len(vals)) if vals else (None, 0)

    summary = {g: {f"d{h}": _agg(g, h) for h in HORIZONS} for g in ("prior", "new", "market")}
    return {"as_of": as_of, "events": events, "summary": summary, "top_n": TOP_N,
            "settle_days": SETTLE_DAYS}
