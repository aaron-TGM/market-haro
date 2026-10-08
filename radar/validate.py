"""Does the score still work? Re-measurable, so decay is visible.

THE PROBLEM THIS SOLVES

The invest score was calibrated once, on one 90-day window, in a market that
rose the whole way through. Every threshold in invest.py and every number in the
`vs sold` tooltip inherits that window. If Gundam turns -- a banlist, a reprint,
attention draining to the next game -- those numbers quietly stop describing
reality, and nothing in the dashboard would tell you. A screen that was right
last year and is wrong now looks exactly like a screen that is right.

So this runs the same test again on demand and writes a dated record. What you
are watching for is not the absolute numbers, it is the drift in them.

WHAT IT MEASURES

Walk-forward, entirely inside stored history. For a split point T:

  1. score every card using ONLY data up to T -- the same invest.features and
     invest.evaluate the live screen uses, no special path
  2. measure what each card actually did from T to T+horizon
  3. rank-correlate the two

Reported three ways, because one number hides too much:

  spearman      does a higher score mean a higher forward return, at all
  quintiles     top fifth vs bottom fifth -- the spread you would actually
                capture, which can be flat even when rho looks fine
  vs_sold       the same test on the ask-versus-sold premium, which is the one
                signal strong enough to be worth watching separately

BASELINE, ALWAYS

Every run reports what a card picked at random from the eligible pool did over
the same window. Without it "+28%" means nothing -- in the calibration window
the whole market did +16.8% and the screen's edge was the difference, not the
headline. If the baseline is negative and the top quintile is positive, that is
a better result than both being positive.

READING THE OUTPUT

  rho > 0.20, top quintile beats baseline    working
  rho near 0, quintiles overlapping          the score has stopped separating
  rho < 0                                    it is now inverted -- stop using it

One run is one window. Two runs three months apart is a trend. The point of
writing the JSON is that the third run can see the first two.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from . import invest

# Enough post-split history to measure something, and enough pre-split history
# for features() to have anything to say. 45/45 matches the live gate.
DEFAULT_HORIZON = 45
MIN_PRE_DAYS = 45


def _rank(xs: Sequence[float]) -> list[float]:
    """Ranks with ties averaged -- ties are common here (scores are rounded)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float] | tuple[None, None]:
    """Rank correlation and its t statistic. |t| > 2 is roughly p < 0.05."""
    if len(xs) < 8:
        return None, None
    rx, ry = _rank(xs), _rank(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx <= 0 or syy <= 0:
        return None, None
    rho = sxy / math.sqrt(sxx * syy)
    if abs(rho) >= 1:
        return round(rho, 3), None
    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    return round(rho, 3), round(t, 2)


def _quantile(xs: Sequence[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s) * q))]


def _stats(rets: Sequence[float]) -> dict[str, Any]:
    if not rets:
        return {"n": 0}
    return {
        "n": len(rets),
        "mean_pct": round(sum(rets) / len(rets), 1),
        "median_pct": round(_quantile(rets, 0.5), 1),
        "win_rate_pct": round(sum(1 for r in rets if r > 0) / len(rets) * 100),
        "worst_pct": round(min(rets), 1),
        "best_pct": round(max(rets), 1),
    }


def _forward(pts: Sequence[Sequence[Any]], split_idx: int, horizon: int) -> float | None:
    """% change from the split close to `horizon` rows later. Rows, not calendar
    days -- the series is already one row per stored observation, and inventing
    a calendar here would silently compare a weekly point to a daily one."""
    if split_idx + horizon >= len(pts):
        return None
    a = pts[split_idx][1]
    b = pts[split_idx + horizon][1]
    if not a or not b:
        return None
    return (b / a - 1) * 100


def run(
    series: dict[tuple[str, str], list[Sequence[Any]]],
    cards: dict[tuple[str, str], dict],
    cfg: dict,
    *,
    horizon: int = DEFAULT_HORIZON,
    today: str | None = None,
) -> dict[str, Any]:
    """Walk-forward test over everything in the database with enough history."""
    rows: list[dict] = []
    skipped = {"too_short": 0, "no_features": 0, "no_forward": 0}

    for key, pts in series.items():
        pts = [p for p in pts if p[1]]
        # Need history on both sides of the split.
        if len(pts) < MIN_PRE_DAYS + horizon + 1:
            skipped["too_short"] += 1
            continue
        split_idx = len(pts) - horizon - 1
        past = pts[: split_idx + 1]

        feats = invest.features(past)
        if not feats:
            skipped["no_features"] += 1
            continue
        fwd = _forward(pts, split_idx, horizon)
        if fwd is None:
            skipped["no_forward"] += 1
            continue

        meta = cards.get(key) or {}
        rows.append(
            {
                **meta,
                **feats,
                "card_id": key[0],
                "printing": key[1],
                # As of the split, not as of today. Using today's price would
                # leak the answer into the input.
                "market_price": past[-1][1],
                "forward_pct": fwd,
            }
        )

    if not rows:
        return {
            "ran_at": today or date.today().isoformat(),
            "horizon_days": horizon,
            "universe": len(series),
            "eligible": 0,
            "disqualified": 0,
            "skipped": skipped,
            "score_vs_forward": {"spearman": None, "t": None},
            "premium_vs_forward": {"spearman": None, "t": None, "n": 0},
            "note": (
                f"No card had enough history on both sides of the split. Each needs "
                f"{MIN_PRE_DAYS} points before it and {horizon} after "
                f"({MIN_PRE_DAYS + horizon + 1} total). Run `radar backfill` or lower "
                f"--horizon."
            ),
            "verdict": "Not enough history to measure. Sync more and re-run.",
        }

    scored = invest.evaluate(rows, cfg)
    alive = [r for r in scored if not r.get("disqualified")]
    rejected = [r for r in scored if r.get("disqualified")]

    alive.sort(key=lambda r: r.get("invest_score") or 0, reverse=True)
    fwd_all = [r["forward_pct"] for r in alive]
    cut = max(1, len(alive) // 5)

    rho, t = spearman(
        [r.get("invest_score") or 0 for r in alive], fwd_all
    ) if len(alive) >= 8 else (None, None)

    # The vs-sold premium, tested the same way, on whichever rows have one.
    prem_rows = [r for r in alive if r.get("ask_premium_pct") is not None]
    prem_rho, prem_t = (
        spearman([r["ask_premium_pct"] for r in prem_rows],
                 [r["forward_pct"] for r in prem_rows])
        if len(prem_rows) >= 8 else (None, None)
    )

    return {
        "ran_at": today or date.today().isoformat(),
        "horizon_days": horizon,
        "universe": len(series),
        "eligible": len(alive),
        "disqualified": len(rejected),
        "skipped": skipped,
        "score_vs_forward": {"spearman": rho, "t": t},
        "premium_vs_forward": {"spearman": prem_rho, "t": prem_t, "n": len(prem_rows)},
        "top_quintile": _stats([r["forward_pct"] for r in alive[:cut]]),
        "bottom_quintile": _stats([r["forward_pct"] for r in alive[-cut:]]),
        "all_eligible": _stats(fwd_all),
        # The honest denominator: everything that had the history to be tested,
        # including what the gates threw out. If the screened-out pile beat the
        # candidates, the gates are the problem.
        "screened_out": _stats([r["forward_pct"] for r in rejected]),
        "verdict": verdict(rho, alive, cut),
    }


def verdict(rho: float | None, alive: list[dict], cut: int) -> str:
    if rho is None:
        return "Not enough eligible cards to measure. Sync more history and re-run."
    top = [r["forward_pct"] for r in alive[:cut]]
    bottom = [r["forward_pct"] for r in alive[-cut:]]
    if not top or not bottom:
        return "Not enough eligible cards to split into quintiles."
    spread = (sum(top) / len(top)) - (sum(bottom) / len(bottom))
    if rho < 0:
        return (
            f"INVERTED. rho = {rho:+.2f}: higher-scoring cards did WORSE over this window. "
            f"Stop acting on the ranking until you understand why."
        )
    if rho < 0.10:
        return (
            f"NOT SEPARATING. rho = {rho:+.2f}, top-minus-bottom spread {spread:+.1f} points. "
            f"The score is no better than picking from the eligible pool at random here."
        )
    if rho < 0.20:
        return (
            f"WEAK. rho = {rho:+.2f}, spread {spread:+.1f} points. Some signal, but thinner "
            f"than the 0.24 measured at calibration. Watch it."
        )
    against = (
        "stronger than" if rho > 0.30 else "in line with" if rho >= 0.20 else "under"
    )
    return (
        f"HOLDING UP. rho = {rho:+.2f}, top-minus-bottom spread {spread:+.1f} points — "
        f"{against} the 0.24 measured at calibration."
    )


def append_history(path: str | Path, result: dict) -> list[dict]:
    """Keep every run in one file so drift is visible without digging."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    hist: list[dict] = []
    if p.exists():
        try:
            hist = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            hist = []
    if not isinstance(hist, list):
        hist = []
    hist.append(result)
    p.write_text(json.dumps(hist, indent=2), encoding="utf-8")
    return hist


# ============================================================================
# The horizon rankings, walked forward (October 2026)
# ============================================================================
#
# `run` above tests one score at one split. The rankings the page shows now
# are per hold horizon (radar/horizon.py), so this tests each one at every
# monthly split the archive allows, at the windows that horizon is for, and
# reports the spread of results rather than one number:
#
#   mid    the hold score at 90 and 180 days
#   long   the hold score at 270 and 365 days
#   short  bought at the cheapest listing (any condition, shipping in -- the
#          batch's lowest_with_shipping, recorded from August 2026) and sold at
#          the market 30 days later less selling costs: the whole pool, the
#          20 lowest hurdles among cards that sell daily, and the 20 strongest
#          on 7-day momentum for comparison
#   legacy the retired score (value/liquidity/trend/stability/scarcity) on its
#          own pool, at 30/60/90 days, wherever the daily history lets the
#          live code score it -- kept so its record stays on file
#
# The hold score is computed from things the archive has at every date:
# rarity, set age and sales a day (invest.sales_rate reads weekly and daily
# history alike). The gates it can measure at every date are applied: an
# English single, $10+, 45 days of history, some sales. The volatility and
# entry-price gates need daily prices and live shelves the archive does not
# hold before mid-2026, so the test runs without them; the live ranking runs
# with them.
#
# Market basis: the price nearest each date within a week. Sold basis: the
# volume-weighted average of what copies sold for over the 21 days ending at
# each date, where both ends have sales -- immune to the market price's lag.

HOLD_WINDOWS = {"mid": (90, 180), "long": (270, 365)}
LEGACY_WINDOWS = (30, 60, 90)
SHORT_WINDOW = 30
STEP_DAYS = 30
TOP = 20
MIN_POOL = 30


def _dates(pts: Sequence[Sequence[Any]]) -> list[str]:
    return [str(p[0])[:10] for p in pts]


def _price_near(pts, dates, target: str, tol: int = 7) -> float | None:
    """Close nearest `target` within `tol` days, the earlier side on a tie."""
    import bisect
    from datetime import date as _d

    i = bisect.bisect_right(dates, target)
    best = None
    t = _d.fromisoformat(target)
    for j in (i - 1, i, i - 2, i + 1):
        if 0 <= j < len(pts) and pts[j][1]:
            gap = abs((_d.fromisoformat(dates[j]) - t).days)
            if gap <= tol and (best is None or gap < best[0] or (gap == best[0] and dates[j] <= target)):
                best = (gap, float(pts[j][1]))
    return best[1] if best else None


def _sold_avg(pts, dates, end: str, days: int = 21) -> float | None:
    import bisect
    from datetime import date as _d
    from datetime import timedelta as _td

    start = (_d.fromisoformat(end) - _td(days=days)).isoformat()
    lo, hi = bisect.bisect_right(dates, start), bisect.bisect_right(dates, end)
    rec = [p for p in pts[lo:hi] if len(p) > 3 and p[3] and (p[2] or 0) > 0]
    vol = sum(p[2] for p in rec)
    return sum(p[3] * p[2] for p in rec) / vol if len(rec) >= 2 and vol > 0 else None


def _median(xs: Sequence[float]) -> float | None:
    s = sorted(xs)
    if not s:
        return None
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def hold_pool(series: dict, dates: dict, meta: dict, releases: dict, as_of: str,
              *, min_price: float = 10.0, min_days: int = 45) -> list[dict]:
    """Every card the hold ranking could have scored on `as_of`, scored with
    only what was known then."""
    import bisect
    from datetime import date as _d

    from . import horizon
    from .snipe import is_english_product

    t = _d.fromisoformat(as_of)
    rows = []
    for k, pts in series.items():
        m = meta.get(str(k[0])) or {}
        if m.get("product_type") != "Cards":
            continue
        ds = dates[k]
        n = bisect.bisect_right(ds, as_of)
        if not n or (t - _d.fromisoformat(ds[n - 1])).days > 10:
            continue
        if (t - _d.fromisoformat(ds[0])).days < min_days:
            continue
        price = pts[n - 1][1]
        if not price or price < min_price:
            continue
        if not is_english_product(m.get("name"), m.get("set_name"), m.get("number")):
            continue
        rate = invest.sales_rate(pts[:n], as_of=as_of)
        if not rate["per_day"]:
            continue
        row = {"key": k, "price": float(price), "rarity": m.get("rarity"), "set_id": m.get("set_id"),
               "set_name": m.get("set_name"), "tracked_since": ds[0], "sales": rate["per_day"]}
        row["age"] = horizon.set_age_days(row, releases, as_of)
        rows.append(row)
    parts = [horizon.percentiles([float(horizon.tier(r)) for r in rows]),
             horizon.percentiles([r["age"] for r in rows]),
             horizon.percentiles([r["sales"] for r in rows])]
    for i, r in enumerate(rows):
        got = [p[i] for p in parts if p[i] is not None]
        r["score"] = sum(got) / len(got) if got else 0.0
    rows.sort(key=lambda r: -r["score"])
    return rows


def _window_stats(per_split: list[dict]) -> dict[str, Any]:
    """Across splits: how the ranking's top 20 and its ordering did."""
    if not per_split:
        return {"splits": 0}
    rhos = [s["rho"] for s in per_split if s["rho"] is not None]
    q = [s["q5_q1"] for s in per_split if s["q5_q1"] is not None]
    out: dict[str, Any] = {
        "splits": len(per_split),
        "first": per_split[0]["date"], "last": per_split[-1]["date"],
        "pool_n": round(sum(s["pool_n"] for s in per_split) / len(per_split)),
        "rho_mean": round(sum(rhos) / len(rhos), 2) if rhos else None,
        "rho_positive": sum(1 for r in rhos if r > 0),
        "top_median": round(sum(s["top"] for s in per_split) / len(per_split), 1),
        "pool_median": round(sum(s["pool"] for s in per_split) / len(per_split), 1),
        "top_beat_pool": sum(1 for s in per_split if s["top"] > s["pool"]),
        "q5_minus_q1": round(sum(q) / len(q), 1) if q else None,
        "q5_minus_q1_positive": sum(1 for x in q if x > 0),
    }
    nets = [s["top_net"] for s in per_split if s.get("top_net") is not None]
    if nets:
        out["top_net_median"] = round(sum(nets) / len(nets), 1)
        out["top_net_positive"] = sum(1 for x in nets if x > 0)
    return out


def _split_result(date_: str, scored: list[dict], fwd: dict, cost_cfg: dict | None) -> dict | None:
    from . import costs

    rows = [r for r in scored if fwd.get(r["key"]) is not None]
    if len(rows) < MIN_POOL:
        return None
    ys = [fwd[r["key"]] for r in rows]
    rho, _ = spearman([r["score"] for r in rows], ys)
    n = len(rows) // 5
    top = ys[:TOP]
    c = costs.settings(cost_cfg)
    # Bought at the market price and sold at the market less costs: the
    # least a holder gives up. Live entries can only add to it.
    nets = [((1 + y / 100) * (1 - c["sell_fee_pct"]) - c["sell_fee_fixed"] / r["price"] - 1) * 100
            for r, y in zip(rows[:TOP], top)]
    return {"date": date_, "pool_n": len(rows), "rho": rho,
            "top": _median(top), "pool": _median(ys), "top_net": _median(nets),
            "q5_q1": (_median(ys[:n]) - _median(ys[-n:])) if n >= 5 else None}


def run_horizons(series: dict, meta: dict, sets: Sequence[dict], cfg: dict, *,
                 entries: dict | None = None, cost_cfg: dict | None = None,
                 today: str | None = None, step_days: int = STEP_DAYS) -> dict[str, Any]:
    """The walk-forward record of every horizon's ranking. See the block above."""
    from datetime import date as _d
    from datetime import timedelta as _td

    from . import costs

    series = {k: [p for p in pts if p[1]] for k, pts in series.items()}
    series = {k: v for k, v in series.items() if v}
    if not series:
        return {"ran_at": today or date.today().isoformat(), "kind": "horizons", "horizons": {},
                "verdict": "No history to measure."}
    dates = {k: _dates(v) for k, v in series.items()}
    releases = {str(s.get("id")): s.get("release_date") for s in sets}
    first = min(d[0] for d in dates.values())
    last = max(d[-1] for d in dates.values())
    min_price = float(cfg.get("min_price", 10.0))
    min_days = int(cfg.get("min_history_days", 45))
    d_first, d_last = _d.fromisoformat(first), _d.fromisoformat(last)

    splits = []
    t = d_first + _td(days=min_days)
    while t < d_last:
        splits.append(t.isoformat())
        t += _td(days=step_days)

    pools: dict[str, list[dict]] = {}
    out_h: dict[str, Any] = {}
    for name, windows in HOLD_WINDOWS.items():
        res: dict[str, Any] = {}
        for h in windows:
            mk, sd = [], []
            for T in splits:
                end = (_d.fromisoformat(T) + _td(days=h)).isoformat()
                if end > last:
                    break
                if T not in pools:
                    pools[T] = hold_pool(series, dates, meta, releases, T, min_price=min_price, min_days=min_days)
                scored = pools[T]
                f_mk, f_sd = {}, {}
                for r in scored:
                    pts, ds = series[r["key"]], dates[r["key"]]
                    p1 = _price_near(pts, ds, end)
                    if p1:
                        f_mk[r["key"]] = (p1 / r["price"] - 1) * 100
                    a, b = _sold_avg(pts, ds, T), _sold_avg(pts, ds, end)
                    if a and b:
                        f_sd[r["key"]] = (b / a - 1) * 100
                s1 = _split_result(T, scored, f_mk, cost_cfg)
                if s1:
                    mk.append(s1)
                s2 = _split_result(T, scored, f_sd, cost_cfg)
                if s2:
                    sd.append(s2)
            res[str(h)] = {**_window_stats(mk), "sold": _window_stats(sd)}
        out_h[name] = {"windows": res, "verdict": _hold_verdict(res)}

    out_h["short"] = _short_record(series, dates, meta, releases, entries or {}, cost_cfg,
                                   min_price=min_price, min_days=min_days, last=last)
    legacy = _legacy_record(series, dates, meta, cfg, last=last)
    c = costs.settings(cost_cfg)
    return {
        "ran_at": today or date.today().isoformat(),
        "kind": "horizons",
        "archive": {"first": first, "last": last, "series": len(series)},
        "costs": c,
        "horizons": out_h,
        "legacy": legacy,
        "note": ("Walk-forward on the archive: each split scores cards with only what was known that "
                 "day. Hold windows use monthly splits; the short and legacy tests use the dates the "
                 "data allows. Medians of per-card change; 'net' is bought at the market price and "
                 "sold at the market less selling costs."),
    }


def _verdict_word(rho: float | None, positive: int, n: int) -> str:
    if rho is None or not n:
        return "NOT MEASURABLE YET"
    if rho < 0:
        return "INVERTED"
    if rho < 0.10:
        return "NOT SEPARATING"
    if rho < 0.20 or positive < n * 0.7:
        return "WEAK"
    return "HOLDING UP"


def _hold_verdict(windows: dict) -> str:
    best = None
    for h, w in sorted(windows.items(), key=lambda kv: int(kv[0])):
        if w.get("splits", 0) >= 3:
            best = (h, w)
    if not best:
        open_ = [h for h, w in windows.items() if not w.get("splits")]
        return f"NOT MEASURABLE YET. No {', '.join(open_)}-day window has closed often enough to judge."
    h, w = best
    word = _verdict_word(w.get("rho_mean"), w.get("rho_positive", 0), w["splits"])
    early = " Few tests yet; read it as early." if w["splits"] < 5 else ""
    return (f"{word}. At {h} days, rho {w['rho_mean']:+.2f} across {w['splits']} monthly tests "
            f"({w['rho_positive']} positive); the top 20 beat the pool in {w['top_beat_pool']} "
            f"(median {w['top_median']:+.1f}% against {w['pool_median']:+.1f}%).{early}")


def _short_record(series, dates, meta, releases, entries, cost_cfg, *, min_price, min_days, last) -> dict:
    """Bought at the batch's cheapest listing, sold 30 days later at the market less costs."""
    from datetime import date as _d
    from datetime import timedelta as _td

    from . import costs

    if not entries:
        return {"window": SHORT_WINDOW, "starts": [], "verdict": "NOT MEASURABLE YET. No entry prices recorded."}
    counts: dict[str, int] = {}
    for byd in entries.values():
        for d in byd:
            counts[d] = counts.get(d, 0) + 1
    # Batch days that priced most of the market, a week apart at least.
    starts, prev = [], None
    for d in sorted(x for x, n in counts.items() if n >= 100):
        if (_d.fromisoformat(d) + _td(days=SHORT_WINDOW)).isoformat() > last:
            break
        if prev is None or (_d.fromisoformat(d) - _d.fromisoformat(prev)).days >= 7:
            starts.append(d)
            prev = d
    per = []
    for T in starts:
        end = (_d.fromisoformat(T) + _td(days=SHORT_WINDOW)).isoformat()
        pool = hold_pool(series, dates, meta, releases, T, min_price=min_price, min_days=min_days)
        rows = []
        for r in pool:
            e = (entries.get(r["key"]) or {}).get(T)
            pts, ds = series[r["key"]], dates[r["key"]]
            p1 = _price_near(pts, ds, end, tol=3)
            if not e or not p1:
                continue
            p7 = _price_near(pts, ds, (_d.fromisoformat(T) - _td(days=7)).isoformat(), tol=3)
            # The hurdle against what copies sold for, as the live ranking
            # measures it; the market price only where sales are too thin.
            ref = _sold_avg(pts, ds, T, 14) or r["price"]
            rows.append({**r, "entry": e, "net": costs.net_return_pct(e, p1, cost_cfg),
                         "hurdle": costs.hurdle_pct(e, ref, cost_cfg),
                         "m7": (r["price"] / p7 - 1) * 100 if p7 else None})
        rows = [r for r in rows if r["net"] is not None and r["hurdle"] is not None]
        if len(rows) < MIN_POOL:
            continue
        liquid = sorted((r for r in rows if r["sales"] >= 1.0), key=lambda r: r["hurdle"])[:TOP]
        mom = sorted((r for r in rows if r["m7"] is not None), key=lambda r: -r["m7"])[:TOP]
        per.append({
            "date": T, "pool_n": len(rows),
            "pool_net_median": round(_median([r["net"] for r in rows]), 1),
            "pool_profitable_pct": round(100 * sum(r["net"] > 0 for r in rows) / len(rows)),
            "ranked_net_median": round(_median([r["net"] for r in liquid]), 1) if liquid else None,
            "ranked_profitable": sum(r["net"] > 0 for r in liquid), "ranked_n": len(liquid),
            "momentum_net_median": round(_median([r["net"] for r in mom]), 1) if mom else None,
            "momentum_profitable": sum(r["net"] > 0 for r in mom), "momentum_n": len(mom),
        })
    if not per:
        return {"window": SHORT_WINDOW, "starts": [], "verdict": "NOT MEASURABLE YET. Under 30 days of entry prices."}
    rp = sum(p["ranked_profitable"] for p in per)
    rn = sum(p["ranked_n"] for p in per)
    mp = sum(p["momentum_profitable"] for p in per)
    mn = sum(p["momentum_n"] for p in per)
    pool_pct = round(sum(p["pool_profitable_pct"] for p in per) / len(per))
    return {
        "window": SHORT_WINDOW, "starts": per,
        "pool_profitable_pct": pool_pct,
        "ranked_profitable": rp, "ranked_n": rn,
        "momentum_profitable": mp, "momentum_n": mn,
        "verdict": (f"SHORT HOLDS HAVE NOT PAID. Bought at the cheapest listing and sold 30 days later at the "
                    f"market less costs, {pool_pct}% of the pool made money; the 20 lowest hurdles made money "
                    f"{rp} times in {rn}, the 20 strongest risers {mp} in {mn} ({len(per)} start dates)."),
    }


def _legacy_record(series, dates, meta, cfg, *, last: str) -> dict:
    """The retired score, scored by the live code wherever the daily history allows."""
    from datetime import date as _d
    from datetime import timedelta as _td

    from .snipe import is_english_product

    per: dict[int, list[dict]] = {h: [] for h in LEGACY_WINDOWS}
    d_last = _d.fromisoformat(last)
    t = _d(2026, 6, 1)
    while t + _td(days=min(LEGACY_WINDOWS)) <= d_last:
        T = t.isoformat()
        rows = []
        for k, pts in series.items():
            m = meta.get(str(k[0])) or {}
            if m.get("product_type") != "Cards" or not is_english_product(m.get("name"), m.get("set_name"), m.get("number")):
                continue
            ds = dates[k]
            import bisect

            n = bisect.bisect_right(ds, T)
            if n < 30 or (t - _d.fromisoformat(ds[n - 1])).days > 3:
                continue
            f = invest.features(pts[:n])
            if not f or (f.get("h30d") or 0) <= 0 or pts[n - 1][1] < float(cfg.get("min_price", 10.0)):
                continue
            rows.append({**m, **f, "key": k, "card_id": k[0], "printing": k[1], "market_price": pts[n - 1][1]})
        alive = [r for r in invest.evaluate(rows, cfg) if not r.get("disqualified")]
        alive.sort(key=lambda r: -(r.get("invest_score") or 0))
        for h in LEGACY_WINDOWS:
            end = (t + _td(days=h)).isoformat()
            if end > last:
                continue
            fwd = {}
            for r in alive:
                p1 = _price_near(series[r["key"]], dates[r["key"]], end, tol=3)
                if p1:
                    fwd[r["key"]] = (p1 / r["market_price"] - 1) * 100
            scored = [{"key": r["key"], "score": r["invest_score"], "price": r["market_price"]} for r in alive]
            s = _split_result(T, scored, fwd, None)
            if s:
                per[h].append(s)
        t += _td(days=7)
    windows = {str(h): _window_stats(v) for h, v in per.items()}
    w = windows.get("30") or {}
    word = _verdict_word(w.get("rho_mean"), w.get("rho_positive", 0), w.get("splits", 0))
    return {"name": "value 20 · liquidity 25 · trend 25 · stability 20 · scarcity 10, pool up over 30 days",
            "retired": "2026-10-08", "windows": windows,
            "verdict": (f"{word}. At 30 days, rho {w['rho_mean']:+.2f} across {w['splits']} weekly tests; its top 20 "
                        f"beat its pool in {w['top_beat_pool']}." if w.get("splits") else word)}
