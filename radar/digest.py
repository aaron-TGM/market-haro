"""The stored rankings, and the diff between two of them.

Each run writes `data/rankings/YYYY-MM-DD.json` -- the scored rows, minus the
series, which the archive already holds. The page reads the previous ranking
for rank movement; the track record scores every stored ranking later. `diff`
computes what changed between two issues (entries, exits, climbers, fallers,
asks that ran ahead of sales) and is kept for that purpose; nothing is mailed.
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
    # From 2026-10-08 (radar/horizon.py): the hold score behind `rank`, what a
    # round trip costs, and the under-30-days ranking beside it.
    "hold_score", "set_age_days", "sells_for", "break_even", "hurdle_pct",
)
METHOD = "horizons-2026-10"


def _key(r: dict) -> tuple[str, str]:
    return (str(r.get("card_id")), r.get("printing") or "Normal")


def snapshot(ranked: Sequence[dict], *, obs_date: str, market: dict | None) -> dict[str, Any]:
    """Today's ranking, trimmed to what a diff needs."""
    rows = []
    rank = 0
    for r in ranked:
        if not r.get("disqualified"):
            rank += 1
        row = {**{k: r.get(k) for k in KEEP}, "rank": rank if not r.get("disqualified") else None}
        hz = r.get("horizons")
        if hz:
            row["rank_short"] = (hz.get("short") or {}).get("rank")
        rows.append(row)
    m = market or {}
    priced = m.get("priced") or 0
    return {
        "obs_date": obs_date,
        # Which ranking `rank` is: absent on issues before 2026-10-08 (the
        # retired score), "horizons-2026-10" after (the hold score).
        **({"method": METHOD} if any(r.get("horizons") for r in ranked) else {}),
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


def latest_floors(root: str | Path) -> dict[tuple[str, str], dict]:
    """The live shelf the newest stored issue carried, for an offline rebuild:
    the database is rebuilt from the archive on every run and the shelf is
    not in the archive, so this is the last one anybody saw."""
    d = Path(root) / "rankings"
    for p in sorted(d.glob("*.json"), reverse=True) if d.exists() else []:
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out = {_key(r): {"floor_low": r.get("floor_low"), "shelf_med": r.get("shelf_med"),
                         "copies": r.get("copies"), "language": None}
               for r in snap.get("rows") or [] if r.get("floor_low")}
        if out:
            return out
    return {}


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

    score = lambda r: r.get("hold_score") if r.get("hold_score") is not None else r.get("invest_score")  # noqa: E731
    both = [(k, t_rows[k], p_rows[k]) for k in t_rows.keys() & p_rows.keys()
            if score(t_rows[k]) is not None and score(p_rows[k]) is not None
            and not t_rows[k].get("disqualified") and not p_rows[k].get("disqualified")]
    moves = []
    for k, t, p in both:
        d = round(score(t) - score(p), 1)
        if d:
            moves.append({**t, "score_delta": d, "prev_score": score(p), "prev_rank": p.get("rank")})
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
