"""Hold screen: cards with real value, a steady uptrend, and a way out.

This is the opposite question from sniping. A flipper wants a mispriced listing
today. A holder wants a card that is already worth something, has been climbing
for months rather than days, and trades often enough that the position can be
exited. Those are different measurements, and a card can score well on one and
badly on the other -- Sayla Mass (Store Tournament Winner Pack 01) was up 338%
in 30 days and is disqualified here for 9.2% daily volatility.

FIVE COMPONENTS, each 0-100, then weighted

  value      Is there value to preserve? Log-scaled price: $10 scores 0,
             $200 scores 100. A 50% move on a $3 card is not an investment
             outcome, it is noise with a percentage sign on it.
  liquidity  Can you get out? Average daily sales and the share of days with
             any sale at all, both from 90 days of history.
  trend      Is it actually rising? The share of weeks that closed above the
             previous week, plus the 90-day change. Weekly closes rather than
             daily so a single bad day doesn't read as a reversal.
  stability  Is the rise orderly? Daily volatility and drawdown from the
             90-day high. A card that triples and halves is not a hold.
  scarcity   Is supply structurally limited? Rarity tier and copies listed.

THRESHOLDS COME FROM THE DISTRIBUTION, NOT FROM TASTE

Measured across 212 Gundam singles at $10+ that were up over 30 days
(2026-08-09, 90 days of daily history each):

  weeks closing up   min 8%   Q1 50%   median 67%   Q3 92%   max 100%
  daily volatility   min 0%   Q1 1.1%  median 1.9%  Q3 3.1%  max 84.9%
  avg daily sales    min 0    Q1 0.6   median 1.3   Q3 1.8   max 16
  days with a sale   min 0%   Q1 29%   median 47%   Q3 57%   max 89%
  drawdown from high min 0%   Q1 0%    median 0%    Q3 4.9%  max 57.8%

The component curves are anchored to those quartiles so a "good" score means
"in the top quarter of this actual market", not "above a number someone liked".

DISQUALIFIERS ARE SHOWN, NEVER HIDDEN

A card that fails a gate is excluded from the ranking and listed with the
reason. 60 of those 212 failed: 39 down over 90 days, 11 with no recorded sales
at all, 8 too erratic, 2 too new. The most expensive card in the pool --
Overflowing Affection (U+) Foil at $4,798 -- has not sold once in 90 days.

None of this is a forecast, and none of it knows *why* a card is moving. It
describes what a card has done and whether it can be exited.
"""

from __future__ import annotations

import math
from datetime import date as _date, timedelta as _timedelta
from typing import Any, Iterable, Sequence

# Rarity as a proxy for structural scarcity. Alt-art and parallel treatments
# (the +/++ suffixes) are printed at a fraction of the base rate.
RARITY_TIER = {
    "LR++": 100, "LR+": 90, "R+": 80, "C++": 75, "C+": 70, "U+": 65,
    "Promo": 60, "Legend Rare": 55, "Rare": 40, "Uncommon": 20,
    "Common": 10, "None": 5, "": 5,
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _f(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


# --------------------------------------------------------------------------
# Features: everything the score needs, measured from 90 days of history.
# --------------------------------------------------------------------------
WINDOW_DAYS = 90


def _window(pts: Sequence[Sequence[Any]], days: int) -> list:
    """The points dated within `days` of the last point."""
    if not pts:
        return []
    try:
        last_d = _date.fromisoformat(str(pts[-1][0])[:10])
    except (ValueError, TypeError):
        return list(pts)
    cut = (last_d - _timedelta(days=days)).isoformat()
    return [p for p in pts if str(p[0])[:10] >= cut]


def _change_over(pts: Sequence[Sequence[Any]], days: int, *, tolerance: int = 3) -> float | None:
    """% change from the last close back to the close `days` calendar days earlier.

    Indexed by date, not by list position, because the daily series has gaps --
    the most recent point sits anywhere from today to three days back depending
    on the card. Falls back to the nearest earlier close within a 3-day window
    so one missing day doesn't blank the column; returns None past that.
    """
    if len(pts) < 2:
        return None
    try:
        last_d = _date.fromisoformat(pts[-1][0][:10])
    except (ValueError, TypeError):
        return None
    target = last_d - _timedelta(days=days)
    best: tuple[int, float] | None = None
    for row in pts[:-1]:
        d, price = row[0], row[1]
        try:
            cur = _date.fromisoformat(str(d)[:10])
        except (ValueError, TypeError):
            continue
        if cur > target:
            continue
        gap = (target - cur).days
        if gap > tolerance:
            continue
        if best is None or gap < best[0]:
            best = (gap, price)
    if best is None or not best[1]:
        return None
    return round((pts[-1][1] / best[1] - 1) * 100, 1)


def supply(listings: Sequence[tuple[str, int]], *, as_of: str | None = None) -> dict[str, Any]:
    """The shelf over time: how many copies are listed now against 7 and 30 days ago.

    A shelf that shrinks while copies keep selling is demand eating supply --
    the one thing a price chart cannot show, and the signal sealed buyers care
    about most. Uses the same date-indexed lookback as _change_over (a 3-day
    tolerance), so a card that did not update on the exact day still measures.
    Returns {} until the shelf has been recorded long enough to compare.
    """
    if not listings:
        return {}
    pts = [(d, float(n)) for d, n in listings if n is not None]
    if as_of:
        pts = [p for p in pts if p[0] <= as_of]
    if not pts:
        return {}
    out: dict[str, Any] = {"listings_now": int(pts[-1][1]), "listings_as_of": pts[-1][0],
                           "listings_first": int(pts[0][1]), "listings_first_date": pts[0][0]}
    for days in (7, 30):
        ch = _change_over(pts, days) if pts[-1][1] else None
        if ch is not None:
            out[f"listings_change_{days}d"] = ch
    return out


def shelf_math(row: dict) -> dict[str, Any]:
    """Two numbers a shelf implies, given what is listed and how fast it sells.

    days_of_shelf: listings / sales a day -- how long the current shelf lasts
    at the current pace (341 days is a box going nowhere; 12 is a box that is
    about to be scarce). dollars_to_clear: listings x price -- what it would
    cost to buy the shelf out, i.e. how much money it takes to move this.
    """
    n = row.get("total_listings")
    price = _f(row.get("market_price"))
    sales = _f(row.get("avg_daily_sales"))
    out: dict[str, Any] = {}
    if n is None or price is None:
        return out
    n = int(n)
    out["dollars_to_clear"] = round(n * price)
    if sales and sales > 0:
        out["days_of_shelf"] = round(n / sales)
    return out


def settled(pts: Sequence[tuple[str, float, float, float | None]], window: int = 14) -> dict:
    """Where copies are actually changing hands, versus what they are listed at.

    `market_price` is derived from listings. `avg_sales_price` on days with
    volume is what buyers really paid. The volume-weighted average of the latter
    over the last two weeks is the settled price, and `ask_premium_pct` is how
    far the listed price has run ahead of it.

    WHY THIS IS HERE AND A FORECAST IS NOT
    --------------------------------------
    Aaron asked for a predicted settling price built from sales velocity, the
    size of the run, supply and rarity. I tested those four directly on 90 days
    of daily Gundam history and they do not support a forecast:

      run size vs next 30d       r = -0.13   (n=47 run-ups of 25%+)
      sales velocity vs next 30d r = -0.15
      run speed vs next 30d      r = -0.06
      rarity                     largest bucket n=7 -- not measurable
      listings vs next 30d       rho = -0.20, but listing counts are only
                                 available as of today, so testing them against
                                 the past is lookahead bias. Unusable.

    There was also nothing to settle *back* to. After a 25%+ run, the median
    card was **up another 24% thirty days later** and 77% were above the peak.
    The whole market rose over this window; a model fitted here would predict
    perpetual gains, which is not a settling price, it is a bull market.

    The ask-versus-sold gap is the one thing that did hold up, and it holds up
    because both sides are measured at the same moment from history alone:

      premium vs next 30d      rho = -0.307   (n = 1,201 over 290 cards)
      first half of window     rho = -0.318
      second half of window    rho = -0.284
      after removing momentum  rho = -0.227
      at 14 days instead of 30 rho = -0.384   -- the correction lands fast

    Sorted into fifths by premium, the cheapest fifth (asking 7% BELOW recent
    sales) returned +10.3% over the next 30 days; the priciest fifth (asking
    9% above) returned -4.0%. As a point estimate the sold-average beat today's
    listed price: median absolute error 8.0% versus 9.5%.

    That is worth showing. It is still not a forecast, and it is not labelled
    as one -- it is the price copies have been trading at.
    """
    recent = [p for p in pts[-window:] if len(p) > 3 and p[3] and p[2] > 0]
    volume = sum(p[2] for p in recent)
    if len(recent) < 3 or volume <= 0:
        # Under three days of real sales the average is one or two transactions
        # wearing a decimal point. Say nothing rather than something thin.
        return {"settled_price": None, "ask_premium_pct": None, "settled_days": len(recent)}
    price = sum(p[3] * p[2] for p in recent) / volume
    ask = pts[-1][1]
    return {
        "settled_price": round(price, 2),
        "ask_premium_pct": round((ask / price - 1) * 100, 1) if price else None,
        "settled_days": len(recent),
        "settled_volume": round(volume),
    }


def weekly_points(pts: Sequence[Sequence[Any]], days: int) -> list[tuple[str, float]]:
    """One point a week over the last `days`, for the long chart.

    Keeps the first point of every ISO week plus the very last point, so the
    line ends where today's price is. Daily and weekly stretches both come out
    at weekly spacing.
    """
    out: list[tuple[str, float]] = []
    seen = set()
    for d, p, *_ in _window(pts, days):
        if not p:
            continue
        try:
            wk = _date.fromisoformat(str(d)[:10]).isocalendar()[:2]
        except (ValueError, TypeError):
            continue
        if wk in seen:
            continue
        seen.add(wk)
        out.append((str(d)[:10], round(float(p), 2)))
    if pts and out and out[-1][0] != str(pts[-1][0])[:10] and pts[-1][1]:
        out.append((str(pts[-1][0])[:10], round(float(pts[-1][1]), 2)))
    return out


def features(series: Sequence[Sequence[Any]]) -> dict[str, Any] | None:
    """From [(date, market_price, sales_volume, avg_sales_price), ...] -> measurements.

    The fourth element is optional; without it the settled price is simply
    absent rather than estimated.

    Returns None when there isn't enough history to say anything.
    """
    full: list[tuple[str, float, float, float | None]] = []
    for row in series:
        date = row[0]
        price = _f(row[1]) if len(row) > 1 else None
        volume = _f(row[2]) if len(row) > 2 else 0.0
        sold = _f(row[3]) if len(row) > 3 else None
        if price and price > 0:
            full.append((date, price, volume or 0.0, sold if sold and sold > 0 else None))
    if not full:
        return None
    # The measurements are 90-day measurements. The stored series can run back
    # a year at weekly resolution (the 1y chart), and feeding that in would
    # turn "change over 90 days" into "change since launch" and break the
    # weekly sampling below. Everything here is cut to the window by date; the
    # long series contributes only the long-window changes.
    pts = _window(full, WINDOW_DAYS)
    if len(pts) < 30:
        return None

    px = [p[1] for p in pts]
    vol = [p[2] for p in pts]
    last, first, high = px[-1], px[0], max(px)

    # Weekly closes, walking back from today so the most recent week is whole.
    weekly = [px[i] for i in range(len(px) - 1, -1, -7)][::-1]
    ups = sum(1 for i in range(1, len(weekly)) if weekly[i] >= weekly[i - 1])
    consistency = round(ups / (len(weekly) - 1) * 100) if len(weekly) > 1 else None

    rets = [(px[i] - px[i - 1]) / px[i - 1] for i in range(1, len(px)) if px[i - 1] > 0]
    mean = sum(rets) / len(rets) if rets else 0.0
    var = sum((r - mean) ** 2 for r in rets) / len(rets) if rets else 0.0
    volatility = round(math.sqrt(var) * 100, 1)

    days = len(vol)
    # Money through the product: copies sold x what they sold for (the market
    # price when no sale price is recorded), over the last 30 days. Grayson's
    # "dollar absorption": how much of the market this card actually is.
    last30 = _window(pts, 30)
    dollars_30d = round(sum(p[2] * (p[3] or p[1]) for p in last30))
    # The high since we have tracked it -- the whole stored series, not the
    # window -- and the day it was set. "This was $1,000 once" is context a
    # 90-day high cannot give.
    hi_pt = max(full, key=lambda p: p[1])
    return {
        "dollars_30d": dollars_30d,
        "tracked_high": round(hi_pt[1], 2),
        "tracked_high_date": str(hi_pt[0])[:10],
        "tracked_since": str(full[0][0])[:10],
        "off_tracked_high_pct": round((1 - last / hi_pt[1]) * 100, 1) if hi_pt[1] else 0.0,
        # Short-window changes computed from the stored daily series rather than
        # taken from the API's price_change_24h field. That field is unreliable:
        # measured 2026-08-09 across 1,701 Gundam products it was non-zero on
        # 3.2% of rows, and on a spot check of 129 cards it reported 0 for 8 of
        # the 9 that had actually moved >=1% day over day. The daily history
        # moves on 37% of days, so the data exists -- only the field is wrong.
        "h1d": _change_over(pts, 1),
        "h3d": _change_over(pts, 3),
        "h7d": _change_over(pts, 7),
        "h30d": _change_over(pts, 30),
        "as_of": pts[-1][0],
        **settled(pts),
        "change_90d": round((last / first - 1) * 100) if first else None,
        "change_180d": _change_over(full, 180, tolerance=10),
        "change_1y": _change_over(full, 365, tolerance=10),
        "drawdown_pct": round((1 - last / high) * 100, 1) if high else 0.0,
        "consistency_pct": consistency,
        "volatility_pct": volatility,
        "avg_daily_sales": round(sum(vol) / days, 1),
        "days_traded_pct": round(sum(1 for v in vol if v > 0) / days * 100),
        "history_points": days,
    }


# --------------------------------------------------------------------------
# Gates: reasons a card is not a hold candidate at all.
# --------------------------------------------------------------------------
def disqualify(row: dict, cfg: dict) -> str | None:
    from .snipe import is_english_product

    if not is_english_product(row.get("name"), row.get("set_name"), row.get("number")):
        return "Not an English printing — different market, excluded"
    if row.get("floor_language") and row["floor_language"] != cfg.get("language", "English"):
        return f"Entry price is a {row['floor_language']} listing — excluded"

    price = _f(row.get("market_price")) or 0.0
    if price < float(cfg.get("min_price", 10.0)):
        return f"Under ${float(cfg.get('min_price', 10.0)):,.0f} — too little value to preserve"
    if row.get("history_points") is None:
        return "No price history pulled yet — run `radar invest`"
    if int(row.get("history_points") or 0) < int(cfg.get("min_history_days", 45)):
        return "Too new — under 45 days of price history to judge"
    if (_f(row.get("avg_daily_sales")) or 0.0) <= 0:
        return "No recorded sales in 90 days — no way out of the position"
    if (_f(row.get("change_90d")) or 0.0) < 0:
        return "Down over 90 days — not on the rise"
    if (_f(row.get("volatility_pct")) or 0.0) > float(cfg.get("max_volatility_pct", 8.0)):
        return "Too erratic — daily swings too large to sit on"
    return None


# --------------------------------------------------------------------------
# The score.
# --------------------------------------------------------------------------
def components(row: dict, cfg: dict) -> dict[str, float]:
    price = _f(row.get("market_price")) or 0.0
    floor = float(cfg.get("min_price", 10.0))
    ceiling = float(cfg.get("value_ceiling", 200.0))

    value = 100.0 * _clamp(
        math.log10(max(price, floor) / floor) / math.log10(ceiling / floor)
    )

    sales = _f(row.get("avg_daily_sales")) or 0.0
    traded = _f(row.get("days_traded_pct")) or 0.0
    liquidity = 60.0 * _clamp(sales / 2.0) + 40.0 * _clamp(traded / 60.0)

    cons = _f(row.get("consistency_pct")) or 0.0
    q90 = _f(row.get("change_90d")) or 0.0
    trend = 60.0 * _clamp((cons - 40.0) / 50.0) + 40.0 * _clamp(q90 / 60.0)

    vola = _f(row.get("volatility_pct")) or 0.0
    dd = _f(row.get("drawdown_pct")) or 0.0
    stability = 55.0 * _clamp(1.0 - (vola - 1.0) / 4.0) + 45.0 * _clamp(1.0 - dd / 25.0)

    tier = RARITY_TIER.get(row.get("rarity") or "", 20)
    copies = row.get("copies")
    copies = float(copies) if isinstance(copies, (int, float)) else 20.0
    scarcity = 0.6 * tier + 40.0 * _clamp(1.0 - copies / 40.0)

    return {
        "value": round(value, 1),
        "liquidity": round(liquidity, 1),
        "trend": round(trend, 1),
        "stability": round(stability, 1),
        "scarcity": round(scarcity, 1),
    }


def evaluate(rows: Iterable[dict], cfg: dict) -> list[dict]:
    """Score every row. Disqualified rows are kept, marked, and sorted last."""
    w = {
        "value": float(cfg.get("weight_value", 0.20)),
        "liquidity": float(cfg.get("weight_liquidity", 0.25)),
        "trend": float(cfg.get("weight_trend", 0.25)),
        "stability": float(cfg.get("weight_stability", 0.20)),
        "scarcity": float(cfg.get("weight_scarcity", 0.10)),
    }
    total = sum(w.values()) or 1.0

    out: list[dict] = []
    for row in rows:
        rec = dict(row)
        reason = disqualify(rec, cfg)
        rec["disqualified"] = reason
        comp = components(rec, cfg)
        rec["components"] = comp
        rec["invest_score"] = (
            0.0 if reason else round(sum(w[k] * comp[k] for k in w) / total, 1)
        )

        # Entry quality is a bonus, not part of the thesis: it says something
        # about today's listing, not about the card.
        entry, shelf = _f(rec.get("floor_low")), _f(rec.get("shelf_med"))
        if entry and shelf and shelf > 0:
            rec["entry_vs_shelf_pct"] = round((shelf - entry) / shelf * 100, 1)
        else:
            rec["entry_vs_shelf_pct"] = None
        if entry and (_f(rec.get("market_price")) or 0) > 0:
            rec["entry_vs_market_pct"] = round(
                (float(rec["market_price"]) - entry) / float(rec["market_price"]) * 100, 1
            )
        else:
            rec["entry_vs_market_pct"] = None

        out.append(rec)

    out.sort(key=lambda r: (r["disqualified"] is None, r["invest_score"]), reverse=True)
    return out


# --------------------------------------------------------------------------
# Words.
# --------------------------------------------------------------------------
def thesis(row: dict) -> str:
    """What the numbers say about holding this, in one paragraph."""
    if row.get("disqualified"):
        return row["disqualified"] + "."

    price = _f(row.get("market_price")) or 0.0
    q90 = _f(row.get("change_90d"))
    cons = _f(row.get("consistency_pct"))
    sales = _f(row.get("avg_daily_sales"))
    traded = _f(row.get("days_traded_pct"))
    vola = _f(row.get("volatility_pct"))
    rarity = row.get("rarity") or "—"

    bits = [f"A ${price:,.2f} {rarity}"]
    if q90 is not None and cons is not None:
        bits.append(
            f"up {q90:.0f}% over 90 days, with {cons:.0f}% of weeks closing above the one before"
        )
    if vola is not None:
        bits.append(f"moving {vola:.1f}% a day")
    s = ", ".join(bits) + "."
    if sales is not None and traded is not None:
        s += (
            f" It sells about {sales:.1f} copies a day and traded on {traded:.0f}% of the "
            f"last 90 days, so the position can be exited."
        )
    return s


def watch_for(row: dict) -> str:
    """What would break the case for holding it."""
    if row.get("disqualified"):
        return "Not a candidate while that stays true."
    dd = _f(row.get("drawdown_pct")) or 0.0
    cons = _f(row.get("consistency_pct")) or 0.0
    sales = _f(row.get("avg_daily_sales")) or 0.0
    parts = []
    if dd > 5:
        parts.append(f"it is already {dd:.0f}% off its 90-day high")
    if cons < 70:
        parts.append(f"only {cons:.0f}% of weeks closed up, so the trend is not clean")
    if sales < 1:
        parts.append(f"at {sales:.1f} sales a day, exiting more than a few copies takes time")
    # A stretched ask is a timing problem, not a reason to drop the card. It says
    # wait, not no -- so it belongs here rather than in the score or the gates.
    prem = _f(row.get("ask_premium_pct"))
    if prem is not None and prem > 5:
        parts.append(
            f"the listed price is running {prem:.0f}% above what copies have actually "
            f"been selling for (${row.get('settled_price'):,.2f}), which historically "
            f"drifted back rather than held"
        )
    if not parts:
        parts.append("nothing in the numbers is flashing yet")
    return (
        "Watch: " + "; ".join(parts) + ". Reprints, ban-list changes and rotation are "
        "the things that end a run, and none of them are visible here."
    )


CHECKLIST = [
    "Confirm printing and language on the listing — the alt-art parallels carry the value, "
    "and the base printing of the same card is a different product.",
    "Check the second-cheapest copy. If the entry price is far below it, ask why before "
    "assuming it's a bargain.",
    "Sanity-check the sales figure against the TCGplayer sales history on the page.",
    "Decide the exit before you buy: at this sales rate, how long does it take to sell "
    "the quantity you're holding?",
    "Compare the entry price to what copies have actually sold for, not just to the other "
    "listings. Listings are what sellers hope for; the sale price is what buyers agreed to.",
    "Look for a reason the card is moving. Nothing here knows about bans, reprints, "
    "rotation or tournament results.",
]
