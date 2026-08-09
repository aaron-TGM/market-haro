"""Snipe mode: what can I actually buy right now, and is the supply thin?

The daily `market_price` from `/sets/:id/prices` is a *batch* figure -- measured
against live data on 2026-08-09 it was stamped 2026-08-07, i.e. up to two days
behind. That is fine for spotting which cards are moving, and useless for
deciding what to buy.

`/cards/:id/prices/conditions` is different: it is fetched on demand and the
response carries `meta.cached` plus an `as_of` stamp, so a cold call returns the
listing floor as it stands right now. It also carries `sample_count` -- how many
copies are actually listed at that condition. That is the number that decides
whether buying the shelf moves the price.

Comparing the live floor against the stale market price splits into two setups:

  discount -- floor sits BELOW the recorded market. Copies are listed under what
              the card last traded at. Straight arbitrage, if the market price
              isn't simply stale-high from a spike that already reversed.

  squeeze  -- floor sits ABOVE the recorded market, on few copies. The cheap
              copies are gone and the batch price hasn't caught up yet. This is
              what a card looks like just before the printed price moves.

Neither is advice, and both can be wrong for the same reason: the market price
is old. `copies` is the honest part of the row -- it's live, and it's what
decides how much supply you'd have to clear.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

from .client import RateLimitExhausted, TCGClient

log = logging.getLogger("radar.snipe")

NM = "Near Mint"


def _f(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def fetch_floor(client: TCGClient, card_id: Any, printing: str | None = None) -> dict | None:
    """Live Near Mint floor + copy count for one card. One request."""
    rows = client.get(f"/cards/{card_id}/prices/conditions")
    if not rows:
        return None
    rows = rows if isinstance(rows, list) else [rows]

    def pick(cond: str) -> dict | None:
        exact = [
            r
            for r in rows
            if r.get("condition") == cond and (not printing or r.get("printing") == printing)
        ]
        if exact:
            return exact[0]
        loose = [r for r in rows if r.get("condition") == cond]
        return loose[0] if loose else None

    nm = pick(NM)
    if not nm:
        # Some products only ever list in one condition (sealed, tokens).
        candidates = [r for r in rows if not printing or r.get("printing") == printing]
        nm = candidates[0] if candidates else None
    if not nm:
        return None

    return {
        "card_id": str(card_id),
        "printing": nm.get("printing") or printing or "Normal",
        "condition": nm.get("condition"),
        "floor_low": _f(nm.get("low_price")),
        "floor_ship": _f(nm.get("lowest_with_shipping")),
        "copies": nm.get("sample_count"),
        "as_of": nm.get("last_updated_at"),
        "conditions": [
            {
                "condition": r.get("condition"),
                "printing": r.get("printing"),
                "low": _f(r.get("low_price")),
                "copies": r.get("sample_count"),
            }
            for r in rows
        ],
    }


def fetch_floors(
    client: TCGClient,
    targets: Sequence[tuple[Any, str]],
    *,
    limit: int = 60,
) -> dict[tuple[str, str], dict]:
    """One request per card. Stops cleanly on budget or rate limit."""
    out: dict[tuple[str, str], dict] = {}
    for i, (card_id, printing) in enumerate(targets[:limit], 1):
        if client.budget_left <= 0:
            log.warning("Floor fetch stopped at %d/%d -- budget", i, len(targets[:limit]))
            break
        try:
            floor = fetch_floor(client, card_id, printing)
        except RateLimitExhausted:
            log.warning("Floor fetch stopped at %d/%d -- rate limit", i, len(targets[:limit]))
            break
        except Exception as exc:  # a single bad card shouldn't kill the run
            log.debug("Floor fetch failed for %s: %s", card_id, exc)
            continue
        if floor:
            out[(str(card_id), printing)] = floor
        if i % 20 == 0:
            log.info("  ...%d floors (%d requests left)", i, client.budget_left)
    return out


def score(rows: Iterable[dict], floors: dict[tuple[str, str], dict], cfg: dict) -> list[dict]:
    """Attach floor data and a 0-100 snipe score. Returns rows sorted best first."""
    max_copies = int(cfg.get("max_copies", 40))
    min_gap = float(cfg.get("min_gap_pct", 8.0))
    w_gap = float(cfg.get("weight_gap", 0.55))
    w_scarcity = float(cfg.get("weight_scarcity", 0.25))
    w_momentum = float(cfg.get("weight_momentum", 0.20))
    w_total = (w_gap + w_scarcity + w_momentum) or 1.0

    out: list[dict] = []
    for row in rows:
        rec = dict(row)
        key = (str(row.get("card_id")), row.get("printing") or "Normal")
        floor = floors.get(key)
        rec["snipe_score"] = 0.0
        rec["snipe_mode"] = None
        rec["gap_pct"] = None

        if not floor or not floor.get("floor_low"):
            out.append(rec)
            continue

        market = _f(row.get("market_price"))
        low = floor["floor_low"]
        copies = floor.get("copies")
        rec["floor_low"] = low
        rec["floor_ship"] = floor.get("floor_ship")
        rec["copies"] = copies
        rec["floor_as_of"] = floor.get("as_of")
        rec["floor_condition"] = floor.get("condition")
        if not market:
            out.append(rec)
            continue

        gap = (market - low) / market * 100.0  # positive = floor under market
        rec["gap_pct"] = round(gap, 1)
        # For a squeeze, "-462%" is arithmetically right and unreadable. The
        # multiple is the number that means something: the shelf is 5.6x the
        # price the batch still thinks this card trades at.
        rec["floor_multiple"] = round(low / market, 2)

        c7 = float(row.get("change_7d") or 0.0)
        c24 = float(row.get("change_24h") or 0.0)
        momentum = 100.0 * _clamp(max(c7 / 60.0, c24 / 30.0))

        # Scarcity: 40+ copies is deep supply, a handful is thin.
        cnum = copies if isinstance(copies, (int, float)) else max_copies
        scarcity = 100.0 * _clamp(1.0 - (cnum / max_copies))

        if gap >= min_gap:
            rec["snipe_mode"] = "discount"
            gap_component = 100.0 * _clamp(gap / 50.0)
        elif gap <= -min_gap:
            rec["snipe_mode"] = "squeeze"
            gap_component = 100.0 * _clamp(-gap / 100.0)
        else:
            gap_component = 0.0

        rec["snipe_score"] = round(
            _clamp(
                (w_gap * gap_component + w_scarcity * scarcity + w_momentum * momentum) / w_total,
                0.0,
                100.0,
            ),
            1,
        )
        out.append(rec)

    out.sort(key=lambda r: (r.get("snipe_mode") is not None, r.get("snipe_score", 0)), reverse=True)
    return out


def explain(rec: dict) -> str:
    """One line telling you what the setup actually is."""
    mode, gap, copies = rec.get("snipe_mode"), rec.get("gap_pct"), rec.get("copies")
    low, ship = rec.get("floor_low"), rec.get("floor_ship")
    if mode == "discount":
        s = f"{gap:.0f}% under market at ${low:.2f}"
        if ship and low and ship > low * 1.05:
            s += f" (${ship:.2f} shipped)"
        if copies is not None:
            s += f", {copies} listed"
        return s
    if mode == "squeeze":
        mult = rec.get("floor_multiple")
        s = (f"Floor already ${low:.2f}, {mult:.1f}x the recorded price"
             if mult else f"Floor already ${low:.2f}")
        if copies is not None:
            s += f" — {copies} left"
        return s
    if low is not None:
        return f"Floor ${low:.2f}, in line with market"
    return ""
