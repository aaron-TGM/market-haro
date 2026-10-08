"""What a round trip costs: the number every holding has to clear before it makes money.

THE PROBLEM THIS FIXES

The page used to show percentage moves as if a card that rose 8% put 8% in
the reader's pocket. It does not. To get money back out of a card it has to
be sold, and selling on TCGplayer costs a commission and payment processing.
Measured on the issues of September 2026, the median top-20 call was down 5%
on the market price and down 21% once it was bought at the cheapest listing
and sold at the market less costs (docs/METHOD.md, "Costs"). That gap is the
single most important fact for a buyer, so it is on every row now.

THE MODEL, IN FULL

    proceeds(sale)       sale x (1 - sell_fee_pct) - sell_fee_fixed
    break_even(entry)    (entry + sell_fee_fixed) / (1 - sell_fee_pct)
    hurdle(entry, ref)   break_even(entry) / ref - 1

`entry` is what you pay: the cheapest Near Mint English copy, shipping
included (radar/snipe.py). `ref` is what the card sells for now: the 14-day
volume-weighted average of real sales when there are enough of them, the
market price when there are not. The hurdle is the move the card needs,
from where it trades today, before selling it gives back what it cost.

The defaults are TCGplayer's marketplace fees for a standard seller: a 10.75%
commission plus 2.5% + $0.30 payment processing. eBay's trading-card fee is
within a point of that. Shipping is assumed to be charged to the buyer, and
the fixed fee is applied per card, which is conservative for a seller who
bundles. Change them in config.yaml under `costs:`; nothing else needs to.

This is arithmetic on the reader's own exit, not a view on the card.
"""

from __future__ import annotations

from typing import Any

DEFAULTS = {"sell_fee_pct": 0.1325, "sell_fee_fixed": 0.30}


def settings(cfg: dict | None) -> dict[str, float]:
    """The cost settings with defaults filled in. Out-of-range values fall back."""
    cfg = cfg or {}
    out = dict(DEFAULTS)
    try:
        pct = float(cfg.get("sell_fee_pct", DEFAULTS["sell_fee_pct"]))
        if 0 <= pct < 1:
            out["sell_fee_pct"] = pct
    except (TypeError, ValueError):
        pass
    try:
        fixed = float(cfg.get("sell_fee_fixed", DEFAULTS["sell_fee_fixed"]))
        if fixed >= 0:
            out["sell_fee_fixed"] = fixed
    except (TypeError, ValueError):
        pass
    return out


def _pos(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def proceeds(sale: Any, cfg: dict | None = None) -> float | None:
    """What a sale at `sale` puts back in your pocket."""
    s, c = _pos(sale), settings(cfg)
    if s is None:
        return None
    return round(s * (1 - c["sell_fee_pct"]) - c["sell_fee_fixed"], 2)


def break_even(entry: Any, cfg: dict | None = None) -> float | None:
    """The sale price that gives back exactly what `entry` cost."""
    e, c = _pos(entry), settings(cfg)
    if e is None:
        return None
    return round((e + c["sell_fee_fixed"]) / (1 - c["sell_fee_pct"]), 2)


def hurdle_pct(entry: Any, ref: Any, cfg: dict | None = None) -> float | None:
    """The move from `ref` (where it trades now) a card bought at `entry` needs to break even."""
    be, r = break_even(entry, cfg), _pos(ref)
    if be is None or r is None:
        return None
    return round((be / r - 1) * 100, 1)


def net_return_pct(entry: Any, sale: Any, cfg: dict | None = None) -> float | None:
    """Bought at `entry`, sold at `sale`, after selling costs."""
    e, p = _pos(entry), proceeds(sale, cfg)
    if e is None or p is None:
        return None
    return round((p / e - 1) * 100, 1)


def sells_for(row: dict) -> tuple[float | None, str]:
    """Where a card trades now, and which number that is."""
    s = _pos(row.get("settled_price"))
    if s is not None:
        return s, "sold"
    m = _pos(row.get("market_price"))
    return (m, "market") if m is not None else (None, "")


def annotate(row: dict, cfg: dict | None = None) -> dict[str, Any]:
    """The cost fields every row carries. `entry` is the live Near Mint shelf
    when it was pulled; without it the break-even is quoted from the market
    price and says so, because it is then a floor on the real hurdle."""
    ref, ref_kind = sells_for(row)
    entry = _pos(row.get("floor_low"))
    basis = "entry" if entry is not None else "market"
    if entry is None:
        entry = _pos(row.get("market_price"))
    return {
        "sells_for": ref,
        "sells_for_basis": ref_kind,
        "break_even": break_even(entry, cfg),
        "break_even_basis": basis,
        "hurdle_pct": hurdle_pct(entry, ref, cfg),
        "entry_vs_sold_pct": (round((entry / ref - 1) * 100, 1)
                              if basis == "entry" and entry and ref else None),
    }
