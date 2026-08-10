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
