"""Turn price rows into ranked "this is rising" calls.

Three independent detectors, then one composite score:

  sustained  -- up over BOTH 7d and 30d. The trend signal. Slow but honest.
  spike      -- big 24h jump that hasn't already round-tripped. Early but noisy.
  breakout   -- price clears its own trailing high by a margin. Catches a card
                leaving the range it has traded in for months, which is usually
                what a real demand shift looks like before the % windows notice.

Anything under `min_market_price` or `min_listings` is dropped before scoring,
because a 300% move on a $0.12 common with one listing is an artifact, not a
market.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Sequence

Series = Sequence[tuple[str, float]]


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _parse(d: str) -> date:
    return datetime.strptime(d[:10], "%Y-%m-%d").date()


def trailing_high(
    series: Series,
    *,
    as_of: date,
    lookback_days: int,
    exclude_recent_days: int = 7,
) -> tuple[float | None, int]:
    """Highest price in the card's established range, and how many points it saw.

    The recent window is excluded deliberately. Comparing today against
    yesterday makes every day of a climb a "new high", which is noise; comparing
    today against the range the card held *before* the run is the question that
    matters -- has it left the band it used to trade in?
    """
    start = as_of - timedelta(days=lookback_days)
    end = as_of - timedelta(days=max(0, exclude_recent_days))
    vals = [px for d, px in series if px and px > 0 and start <= _parse(d) < end]
    return (max(vals) if vals else None, len(vals))


def trough_since(
    series: Series, *, as_of: date, lookback_days: int
) -> tuple[str, float] | None:
    """The low point of the current run: cheapest price in the lookback window."""
    start = as_of - timedelta(days=lookback_days)
    pts = [(d, px) for d, px in series if px and px > 0 and start <= _parse(d) <= as_of]
    if len(pts) < 3:
        return None
    d, px = min(pts, key=lambda t: t[1])
    return (d, px)


def price_days_ago(series: Series, *, as_of: date, days: int) -> float | None:
    """Closest observed price at or before `days` ago (history is weekly)."""
    target = as_of - timedelta(days=days)
    best: tuple[int, float] | None = None
    for d, px in series:
        if not px or px <= 0:
            continue
        delta = abs((_parse(d) - target).days)
        if delta > 14:
            continue
        if best is None or delta < best[0]:
            best = (delta, px)
    return best[1] if best else None


def evaluate(
    rows: Iterable[dict],
    series_by_key: dict[tuple[str, str], list[tuple[str, float]]],
    cfg_signals: dict[str, Any],
    *,
    as_of: date | None = None,
) -> list[dict]:
    """Score every row. Returns all rows, sorted by score desc."""
    as_of = as_of or date.today()

    min_price = float(cfg_signals.get("min_market_price", 1.0))
    min_listings = int(cfg_signals.get("min_listings", 0))
    sus = cfg_signals.get("sustained", {})
    spk = cfg_signals.get("spike", {})
    brk = cfg_signals.get("breakout", {})
    sc = cfg_signals.get("scoring", {})

    w_sus = float(sc.get("weight_sustained", 0.45))
    w_spk = float(sc.get("weight_spike", 0.25))
    w_brk = float(sc.get("weight_breakout", 0.30))
    w_total = (w_sus + w_spk + w_brk) or 1.0
    price_ceiling = float(sc.get("price_bonus_ceiling", 50.0))
    price_bonus_max = float(sc.get("price_bonus_max", 8.0))
    volume_bonus_max = float(sc.get("volume_bonus_max", 6.0))

    out: list[dict] = []

    for row in rows:
        market = _f(row.get("market_price"))
        listings = row.get("total_listings")
        card_id = str(row.get("card_id"))
        printing = row.get("printing") or "Normal"

        rec: dict[str, Any] = dict(row)
        rec["card_id"] = card_id
        rec["printing"] = printing
        rec["signals"] = []
        rec["score"] = 0.0
        rec["filtered"] = False

        if market is None or market < min_price:
            rec["filtered"] = True
            rec["filter_reason"] = "below price floor"
            out.append(rec)
            continue
        if min_listings and listings is not None and int(listings) < min_listings:
            rec["filtered"] = True
            rec["filter_reason"] = "too few listings"
            out.append(rec)
            continue

        c24 = _f(row.get("change_24h")) or 0.0
        c7 = _f(row.get("change_7d")) or 0.0
        c30 = _f(row.get("change_30d")) or 0.0

        series = series_by_key.get((card_id, printing), [])
        high, n_points = trailing_high(
            series,
            as_of=as_of,
            lookback_days=int(brk.get("lookback_days", 90)),
            exclude_recent_days=int(brk.get("exclude_recent_days", 7)),
        )

        # --- sustained ---------------------------------------------------------
        sustained_hit = c7 >= float(sus.get("min_change_7d", 8.0)) and c30 >= float(
            sus.get("min_change_30d", 15.0)
        )
        sustained_component = 100.0 * (
            0.5 * _clamp(c7 / 40.0) + 0.5 * _clamp(c30 / 100.0)
        )

        # --- spike -------------------------------------------------------------
        spike_hit = c24 >= float(spk.get("min_change_24h", 12.0)) and c7 >= float(
            spk.get("min_change_7d", 0.0)
        )
        spike_component = 100.0 * _clamp(c24 / 50.0)

        # --- breakout ----------------------------------------------------------
        margin = float(brk.get("margin_pct", 3.0))
        min_pts = int(brk.get("min_history_points", 5))
        breakout_hit = False
        breakout_component = 0.0
        excess = None
        if high and n_points >= min_pts:
            excess = (market / high - 1.0) * 100.0
            if excess >= margin:
                breakout_hit = True
            breakout_component = 100.0 * _clamp(excess / 25.0)
        rec["trailing_high"] = high
        rec["history_points"] = n_points
        rec["breakout_excess_pct"] = excess

        # --- composite ---------------------------------------------------------
        base = (
            w_sus * sustained_component
            + w_spk * spike_component
            + w_brk * breakout_component
        ) / w_total

        price_bonus = price_bonus_max * _clamp(market / price_ceiling)
        vol = row.get("sales_volume") or 0
        try:
            vol = int(vol)
        except (TypeError, ValueError):
            vol = 0
        volume_bonus = volume_bonus_max * _clamp(vol / 20.0)

        score = _clamp(base + price_bonus + volume_bonus, 0.0, 100.0)

        if sustained_hit:
            rec["signals"].append("sustained")
        if spike_hit:
            rec["signals"].append("spike")
        if breakout_hit:
            rec["signals"].append("breakout")

        # No detector fired -> not a call, just context. Keep the score for
        # ranking within the "also moving" tail but mark it clearly.
        rec["score"] = round(score, 1) if rec["signals"] else round(score * 0.5, 1)
        rec["components"] = {
            "sustained": round(sustained_component, 1),
            "spike": round(spike_component, 1),
            "breakout": round(breakout_component, 1),
            "price_bonus": round(price_bonus, 1),
            "volume_bonus": round(volume_bonus, 1),
        }
        rec["price_7d_ago"] = price_days_ago(series, as_of=as_of, days=7)
        rec["price_30d_ago"] = price_days_ago(series, as_of=as_of, days=30)
        rec["trough"] = trough_since(
            series, as_of=as_of, lookback_days=int(brk.get("lookback_days", 90))
        )
        rec["series"] = series[-60:]
        out.append(rec)

    out.sort(key=lambda r: (len(r["signals"]) > 0, r["score"]), reverse=True)
    return out


def explain(rec: dict) -> str:
    """Short note that adds what the % columns and badges don't already say."""
    sig = rec.get("signals") or []
    if not sig:
        return ""
    if "breakout" in sig and rec.get("trailing_high"):
        return f"Cleared its ${rec['trailing_high']:.2f} 90-day ceiling"
    trough = rec.get("trough")
    if trough:
        d, px = trough
        try:
            when = _parse(d).strftime("%b %-d")
        except ValueError:
            when = _parse(d).strftime("%b %d")
        mp = rec.get("market_price")
        if mp and px and mp / px >= 1.15:
            return f"Up from ${px:.2f} on {when}"
    if "sustained" in sig and "spike" in sig:
        return "Established trend, fresh 24h leg"
    if "sustained" in sig:
        return "Steady climb, not a one-day pop"
    if "spike" in sig:
        c7 = rec.get("change_7d")
        return f"One-day move; 7d still {c7:+.0f}%" if c7 is not None else "One-day move"
    return ""
