"""Attention: is anyone outside this dashboard paying attention to the game?

WHY THIS EXISTS

Everything else in the project measures price, and price is a lagging, circular
signal -- a card is "rising" because people bought it, and you learn that after
they did. Demand shows up in search and in marketplace share before it shows up
in a 90-day trend, and it disappears the same way. This module holds the part of
the picture that tcgapi.dev cannot see.

It is also the honest counterweight. A screen that only reads price will always
find something rising, because something is always rising. Attention data is how
you tell "this game is growing" apart from "this game's remaining buyers are
bidding against each other".

WHERE THE DATA COMES FROM, AND WHY IT IS A FILE

Google Trends, Semrush and the TCGplayer seller blog are not one API with one
key, and none of them are on tcgapi.dev. Rather than pretend the CLI can fetch
them, `data/market_heat.json` is a dated capture with the source recorded next
to every number, and this module refuses to present it as current once it ages.
`radar heat --template` prints the exact queries to re-run.

WHAT THE NUMBERS MEAN, AND WHAT THEY DON'T

Google Trends values are relative to the peak *within one query*. "gundam tcg"
at 50 and "gundam card game" at 16 does not mean the first is three times the
second -- they are separately scaled. Compare a series to its own history, never
to another series. Semrush volumes ARE absolute and comparable; that is what
they are here for.

None of this is a forecast either. It says how much attention the game has now
versus its own past. It does not say what price does next.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# Past this, the panel is shown greyed out with the age on it. Search interest
# moves on a scale of weeks; a two-month-old capture describes a different market.
STALE_AFTER_DAYS = 30

# Trend readings. A window of 12 weeks matches the 90-day price window the rest
# of the screen uses, so "attention over the last quarter" and "price over the
# last quarter" are the same quarter.
RECENT_WEEKS = 12


def load(path: str | Path) -> dict[str, Any] | None:
    """Read the capture. Missing or unparseable file is not an error -- the rest
    of the dashboard works without it, and the panel simply doesn't render."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _dates(start: str, n: int) -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(weeks=i)).isoformat() for i in range(n)]


def summarise_series(name: str, spec: dict) -> dict[str, Any]:
    """One Google Trends series -> where it stands against its own history.

    Nulls are gaps in the source, not zeros, and are dropped rather than
    interpolated. Reported against three reference points:

      peak     the all-time high in the captured window -- for this game that
               is the launch spike, which is the number worth being honest about
      trough   the low since the peak
      recent   the last 12 weeks versus the 12 before them
    """
    vals = spec.get("values") or []
    dates = _dates(spec.get("start", "1970-01-01"), len(vals))
    pts = [(d, v) for d, v in zip(dates, vals) if isinstance(v, (int, float))]
    if len(pts) < RECENT_WEEKS * 2:
        return {"name": name, "points": len(pts), "enough": False}

    latest_d, latest = pts[-1]
    peak_d, peak = max(pts[1:], key=lambda p: p[1])
    after_peak = [p for p in pts if p[0] > peak_d]
    trough_d, trough = min(after_peak, key=lambda p: p[1]) if after_peak else (peak_d, peak)

    recent = [v for _, v in pts[-RECENT_WEEKS:]]
    prior = [v for _, v in pts[-RECENT_WEEKS * 2 : -RECENT_WEEKS]]
    avg_recent = sum(recent) / len(recent)
    avg_prior = sum(prior) / len(prior)

    return {
        "name": name,
        "enough": True,
        "points": len(pts),
        "latest": latest,
        "latest_date": latest_d,
        "peak": peak,
        "peak_date": peak_d,
        "trough": trough,
        "trough_date": trough_d,
        "pct_of_peak": round(latest / peak * 100) if peak else None,
        "vs_trough_pct": round((latest / trough - 1) * 100) if trough else None,
        "avg_recent": round(avg_recent, 1),
        "avg_prior": round(avg_prior, 1),
        "quarter_change_pct": round((avg_recent / avg_prior - 1) * 100) if avg_prior else None,
        "series": [v for _, v in pts],
        "dates": [d for d, _ in pts],
    }


def summarise_sets(spec: dict) -> list[dict[str, Any]]:
    """Per-expansion release-decay curves, on one shared scale.

    These four terms were queried together on purpose, so unlike the headline
    series they ARE comparable to each other. That is what makes the pattern
    visible: every set so far spikes at launch and gives most of it back inside
    two quarters. Knowing where the newest set sits on that curve is the
    difference between buying into rising attention and buying the decay.

    `weeks_since_peak` and `pct_of_peak` are the two numbers that matter. A set
    three weeks past its peak at 43% of it is not the same purchase as a set
    still climbing, whatever the price chart says.
    """
    start = spec.get("start", "1970-01-01")
    out: list[dict[str, Any]] = []
    for name, entry in (spec.get("series") or {}).items():
        vals = entry.get("values") or []
        dates = _dates(start, len(vals))
        pts = [(d, v) for d, v in zip(dates, vals) if isinstance(v, (int, float))]
        if len(pts) < 4:
            continue
        peak_d, peak = max(pts, key=lambda p: p[1])
        latest_d, latest = pts[-1]
        weeks_since = (date.fromisoformat(latest_d) - date.fromisoformat(peak_d)).days // 7
        out.append({
            "name": name,
            "set_code": entry.get("set_code"),
            "released": entry.get("released"),
            "evergreen": bool(entry.get("evergreen")),
            "latest": latest,
            "peak": peak,
            "peak_date": peak_d,
            "weeks_since_peak": weeks_since,
            "pct_of_peak": round(latest / peak * 100) if peak else None,
            "series": [v for _, v in pts],
            # Live = still inside the first quarter after its peak. After that a
            # set's search interest has never recovered in the captured history.
            "phase": (
                "evergreen" if entry.get("evergreen")
                else "peaking" if weeks_since <= 1
                else "cooling" if weeks_since <= 13
                else "faded"
            ),
        })
    # Newest peak first -- the set you are most likely to be buying into.
    out.sort(key=lambda s: s["peak_date"], reverse=True)
    return out


# The same windows the price screen uses, so a demand move and a price move can
# be put side by side without mental arithmetic.
MOMENTUM_WINDOWS = (1, 3, 7, 14, 30, 60, 90)

# A single day of Trends is noisy and, on smaller terms, frequently missing. Each
# window is therefore a trailing MEAN, not a point reading -- except the 1-day
# window, which has nothing to average and is reported as-is.
SMOOTH = {1: 1, 3: 3, 7: 7, 14: 7, 30: 14, 60: 14, 90: 14}

# Below this share of days present, a daily series is too gappy to difference and
# the shorter windows are reported as unavailable rather than guessed at.
MIN_DAILY_COVERAGE = 0.60


def momentum(values: Sequence[float | None], start: str) -> dict[str, Any]:
    """Demand momentum over the price screen's own windows: 1/3/7/14/30/60/90d.

    THE POINT
    A price screen tells you a card already moved. If commercial-intent search is
    climbing, that is buyers forming before they transact -- the only genuinely
    leading number in this whole project. So it is measured on exactly the same
    windows as price, which is what makes the two comparable.

    THE CATCH, AND IT IS A REAL ONE
    Google only reports daily resolution for terms with enough volume to clear
    its threshold. Measured 2026-08-10 over 151 days:

      "gundam card game"    123/151 days present (81%)  -- usable
      "gundam booster box"   17/151 days present (11%)  -- not usable daily

    The commercial-intent terms are exactly the ones too small to survive daily
    resolution, which is the opposite of convenient. So short windows come back
    None for those, and the honest read for them is the weekly series at 7d and
    longer. Reporting a 1d change computed off two observations three weeks apart
    would be a fabricated number wearing a real label.
    """
    pts = [(i, v) for i, v in enumerate(values) if isinstance(v, (int, float))]
    n = len(values)
    coverage = len(pts) / n if n else 0.0
    out: dict[str, Any] = {
        "coverage_pct": round(coverage * 100),
        "days": n,
        "start": start,
        "usable_daily": coverage >= MIN_DAILY_COVERAGE,
        "windows": {},
    }
    if not pts:
        return out

    by_idx = {i: v for i, v in pts}
    last = pts[-1][0]

    def mean_at(end_idx: int, width: int) -> float | None:
        vals = [by_idx[i] for i in range(end_idx - width + 1, end_idx + 1) if i in by_idx]
        # Need at least half the window actually present, else it is an average
        # of whatever happened to be reported, which is not the same thing.
        if len(vals) < max(1, width // 2):
            return None
        return sum(vals) / len(vals)

    for w in MOMENTUM_WINDOWS:
        width = SMOOTH[w]
        if not out["usable_daily"] and w < 7:
            out["windows"][f"{w}d"] = None
            continue
        now = mean_at(last, width)
        then = mean_at(last - w, width)
        if now is None or then is None or then <= 0:
            out["windows"][f"{w}d"] = None
            continue
        out["windows"][f"{w}d"] = round((now / then - 1) * 100, 1)
    return out


def _weekly_pool(raw_trends: dict) -> dict[str, list]:
    """Every weekly series in the capture, keyed by term, for daily fallback."""
    pool: dict[str, list] = {}
    for group in ("web", "youtube"):
        for name, spec in (raw_trends.get(group) or {}).items():
            pool.setdefault(name, spec.get("values") or [])
    for name, entry in ((raw_trends.get("sets") or {}).get("series") or {}).items():
        pool.setdefault(name, entry.get("values") or [])
    return pool


def summarise_daily(spec: dict, weekly_pool: dict[str, list] | None = None) -> list[dict[str, Any]]:
    """Every daily series -> its momentum table, falling back to weekly where needed.

    A term too small for daily resolution still has a weekly series, and a weekly
    series supports every window from 7d up. So instead of a row of blanks for
    exactly the commercial-intent terms that matter most, those rows are filled
    from weekly data and labelled `weekly` -- 1d and 3d stay empty, because at
    weekly resolution they genuinely do not exist.
    """
    start = spec.get("start", "1970-01-01")
    pool = weekly_pool or {}
    out = []
    for name, entry in (spec.get("series") or {}).items():
        m = momentum(entry.get("values") or [], start)
        m["name"] = name
        m["intent"] = entry.get("intent")
        m["resolution"] = "daily"
        m["series"] = [v for v in (entry.get("values") or []) if isinstance(v, (int, float))]

        if not m["usable_daily"] and name in pool:
            wk = momentum_weekly(pool[name])
            m["resolution"] = "weekly"
            m["weekly_coverage_pct"] = wk["coverage_pct"]
            # Daily wins wherever it produced a number; weekly fills the rest.
            for k, v in wk["windows"].items():
                if m["windows"].get(k) is None:
                    m["windows"][k] = v
            m["series"] = wk["series"] or m["series"]
        out.append(m)
    # Commercial-intent terms first: they are the leading ones.
    out.sort(key=lambda x: (x.get("intent") != "transactional", x["name"]))
    return out


def momentum_weekly(values: Sequence[float | None]) -> dict[str, Any]:
    """Momentum over the same windows, from weekly points.

    Windows under 7 days are left None rather than interpolated -- a weekly
    series has no opinion about yesterday, and pretending otherwise is how you
    end up with a column that looks precise and is not.
    """
    pts = [(i, v) for i, v in enumerate(values) if isinstance(v, (int, float))]
    out: dict[str, Any] = {
        "coverage_pct": round(len(pts) / len(values) * 100) if values else 0,
        "windows": {f"{w}d": None for w in MOMENTUM_WINDOWS},
        "series": [v for _, v in pts],
    }
    if len(pts) < 4:
        return out
    by_idx = {i: v for i, v in pts}
    last = pts[-1][0]

    def mean_at(end_idx: int, weeks: int) -> float | None:
        vals = [by_idx[i] for i in range(end_idx - weeks + 1, end_idx + 1) if i in by_idx]
        return sum(vals) / len(vals) if vals else None

    # 7d -> 1 week back, 14d -> 2, 30d -> 4, 60d -> 9, 90d -> 13.
    for w, back, width in ((7, 1, 2), (14, 2, 2), (30, 4, 3), (60, 9, 3), (90, 13, 3)):
        now, then = mean_at(last, width), mean_at(last - back, width)
        if now is not None and then and then > 0:
            out["windows"][f"{w}d"] = round((now / then - 1) * 100, 1)
    return out


def _direction(pct: float | None) -> str:
    """Deliberately coarse. A 6% shift in a relative index is not a trend, and
    naming it one would be inventing precision the source doesn't have."""
    if pct is None:
        return "flat"
    if pct >= 15:
        return "rising"
    if pct <= -15:
        return "falling"
    return "flat"


def evaluate(raw: dict | None, today: str | None = None) -> dict[str, Any] | None:
    """The capture -> what the panel shows, including how stale it is."""
    if not raw:
        return None
    today = today or date.today().isoformat()
    captured = raw.get("captured_at") or "1970-01-01"
    try:
        age = (date.fromisoformat(today) - date.fromisoformat(captured)).days
    except ValueError:
        age = 9999

    trends = raw.get("trends") or {}
    web = {k: summarise_series(k, v) for k, v in (trends.get("web") or {}).items()}
    yt = {k: summarise_series(k, v) for k, v in (trends.get("youtube") or {}).items()}
    sets = summarise_sets(trends.get("sets") or {})
    daily = summarise_daily(trends.get("daily") or {}, _weekly_pool(trends))

    # The headline series is whichever web term has the most usable history --
    # on this game that is "gundam tcg", which carries roughly three times the
    # search volume of "gundam card game" per Semrush.
    usable = [s for s in web.values() if s.get("enough")]
    lead = max(usable, key=lambda s: s["points"]) if usable else None

    ranks = (raw.get("marketplace_rank") or {}).get("series") or []
    rank_now = ranks[-1] if ranks else None
    rank_prev = ranks[-2] if len(ranks) > 1 else None

    return {
        "captured_at": captured,
        "age_days": age,
        "stale": age > STALE_AFTER_DAYS,
        "web": web,
        "youtube": yt,
        "lead": lead,
        "direction": _direction(lead["quarter_change_pct"]) if lead else "flat",
        "rising_queries": (trends.get("rising_related_queries") or {}).get("values") or [],
        "sets": sets,
        "daily": daily,
        "daily_note": (trends.get("daily") or {}).get("note"),
        "sets_note": (trends.get("sets") or {}).get("note"),
        "semrush": (raw.get("semrush") or {}).get("keywords") or [],
        "intent": ((raw.get("semrush") or {}).get("intent_keywords") or {}).get("keywords") or [],
        "intent_note": ((raw.get("semrush") or {}).get("intent_keywords") or {}).get("note"),
        "zero_volume": ((raw.get("semrush") or {}).get("intent_keywords") or {}).get("zero_volume") or [],
        "semrush_source": (raw.get("semrush") or {}).get("source"),
        "trends_source": trends.get("source"),
        "rank_now": rank_now,
        "rank_prev": rank_prev,
        "rank_series": ranks,
        "rank_source": (raw.get("marketplace_rank") or {}).get("source"),
        "catalysts": raw.get("catalysts") or [],
        "banlist": raw.get("banlist_price_impact") or {},
        "verdict": verdict(lead, rank_now, rank_prev, sets),
    }


def verdict(
    lead: dict | None,
    rank_now: dict | None,
    rank_prev: dict | None,
    sets: list[dict] | None = None,
) -> str:
    """One sentence, and it is allowed to disagree with the price screen.

    The interesting case is exactly the one this market is in: prices climbing
    while attention sits well under its launch peak. That is not a contradiction
    to explain away -- it is a smaller pool of buyers bidding against each other,
    which is a real thing that happens and a real risk to a hold.
    """
    if not lead:
        return "Not enough attention data captured to say anything."

    pct_peak = lead.get("pct_of_peak")
    direction = _direction(lead.get("quarter_change_pct"))
    bits = []

    if pct_peak is not None:
        if pct_peak >= 90:
            bits.append("Search interest is at or near its all-time high")
        elif pct_peak >= 60:
            bits.append(f"Search interest is at {pct_peak}% of its launch peak")
        else:
            bits.append(f"Search interest is at {pct_peak}% of its launch peak — well below it")

    if direction == "rising":
        bits.append(f"and up {lead['quarter_change_pct']:+.0f}% over the last quarter")
    elif direction == "falling":
        bits.append(f"and down {lead['quarter_change_pct']:+.0f}% over the last quarter")
    else:
        bits.append("and roughly flat over the last quarter")

    if rank_now and rank_prev:
        move = rank_prev["rank"] - rank_now["rank"]
        if move > 0:
            bits.append(
                f"TCGplayer sales rank improved to #{rank_now['rank']} in {rank_now['period']}"
            )
        elif move < 0:
            bits.append(
                f"TCGplayer sales rank slipped to #{rank_now['rank']} in {rank_now['period']}"
            )
        else:
            bits.append(f"TCGplayer sales rank held at #{rank_now['rank']}")

    tail = ""
    if pct_peak is not None and pct_peak < 60:
        tail = (
            " Prices can rise on flat or falling attention — that is a smaller pool of "
            "buyers bidding against each other, and it unwinds faster than it built."
        )
    # First two clauses are one sentence ("interest is at X, and up Y"); anything
    # after that is its own.
    newest = next((s for s in (sets or []) if not s["evergreen"]), None)
    if newest:
        code = f" ({newest['set_code']})" if newest.get("set_code") else ""
        label = f"{newest['name'].title()}{code}"
        if newest["phase"] in ("cooling", "faded"):
            tail += (
                f" The newest set, {label}, peaked {newest['weeks_since_peak']} weeks ago and is "
                f"at {newest['pct_of_peak']}% of that peak — singles from it are being bought "
                f"into falling attention, not rising."
            )
        elif newest["phase"] == "peaking":
            tail += (
                f" The newest set, {label}, is at or just past its attention peak right now, "
                f"which is when its singles are most expensive."
            )

    head = " ".join(bits[:2])
    rest = bits[2:]
    return ". ".join([head, *rest]) + "." + tail


TEMPLATE = """\
How to refresh data/market_heat.json
====================================
Nothing here is on tcgapi.dev, so this is a manual capture. Update
`captured_at` to the day you run it, and keep every source string.

1. GOOGLE TRENDS -- weekly interest, US
   Trends connector, report InterestOverTime, country US.
     search_type ""        -> trends.web
     search_type "youtube" -> trends.youtube
   Terms: "gundam tcg", "gundam card game". Start 2025-03-30 so the launch
   spike stays in frame -- it is the reference point for everything else.
   IMPORTANT: query the Gundam terms ALONE. Put "pokemon cards" in the same
   query and every Gundam value is crushed to 1, because Trends scales to the
   largest term in the request.

2. GOOGLE TRENDS -- rising related queries
   Same connector, report RelatedQueries, result_type "rising",
   term "gundam card game", trailing 6 months. This is the early warning: a
   set code or "ban list" climbing here shows up before it shows up in price.

3. SEMRUSH -- absolute volume
   phrase_these, database us. Keep the peer rows (one piece card game,
   tcgplayer) -- they are the scale check that makes the Gundam rows mean
   something.

4. TCGPLAYER MARKETPLACE RANK
   seller.tcgplayer.com/blog, quarterly "best-selling trading card games".
   Append the new quarter; keep the history.

5. CATALYSTS
   gundam-gcg.com/en/news -- set releases and banlist updates, with dates.
   These are the events the price screen is blind to, so they are worth the
   two minutes it takes to log them.
"""
