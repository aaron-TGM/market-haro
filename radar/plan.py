"""Position sizing: turn a budget into "how many, at what cost".

This is arithmetic on numbers you supplied, not a recommendation. It answers a
narrow question -- *given this budget and these caps, what would a position in
this card cost and how much of the shelf would it take* -- and nothing else. It
has no view on whether the card is worth owning, and no knowledge of why the
price is moving.

The rules, in full:

  unit cost      = lowest Near Mint listing WITH shipping (falls back to the
                   bare floor when shipped isn't known). Shipping is the number
                   you actually pay, and on a $2 card it can double the cost.
  position cap   = budget x max_position_pct. Halved for a `squeeze`, because
                   there you are paying above the last recorded trade rather
                   than below it.
  quantity       = min(copies listed, floor(cap / unit), floor(remaining / unit))
  allocation     = greedy down the board by snipe score until the budget runs out.

Greedy is the honest choice here: it is transparent, it never quietly
reallocates away from the row you were looking at, and every line can be
checked by hand.

IMPORTANT: `radar/dashboard.py` carries a JavaScript twin of `allocate()` so the
budget box can recompute live in the page. If you change the rules here, change
them there too. `test_plan_allocates_greedily_within_caps` and
`test_plan_runs_out_of_budget_gracefully` in tests/test_pipeline.py pin this
side; the twin was checked against the same fixture in a browser and agrees on
quantity, cost and the limiting constraint for every row.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence


def unit_cost(row: dict) -> float | None:
    """What one copy actually costs, shipping included where we know it."""
    for key in ("floor_ship", "floor_low"):
        v = row.get(key)
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f
    return None


def allocate(
    rows: Sequence[dict],
    budget: float,
    *,
    max_position_pct: float = 0.25,
    squeeze_haircut: float = 0.5,
    fee_pct: float = 0.0,
) -> list[dict]:
    """Walk the board in order and size each row against what's left.

    Returns one plan dict per input row, in the same order. Rows that don't fit
    still get a plan explaining why.
    """
    remaining = float(budget)
    plans: list[dict] = []

    for row in rows:
        unit = unit_cost(row)
        copies = row.get("copies")
        try:
            copies = int(copies)
        except (TypeError, ValueError):
            copies = None

        plan: dict[str, Any] = {
            "unit": unit,
            "qty": 0,
            "cost": 0.0,
            "affordable": False,
            "clears_shelf": False,
            "reason": "",
            "budget_pct": 0.0,
            "breakeven": None,
        }

        if unit is None:
            plan["reason"] = "No live floor yet — run `radar snipe` to price it."
            plans.append(plan)
            continue

        cap = float(budget) * float(max_position_pct)
        if row.get("snipe_mode") == "squeeze":
            cap *= float(squeeze_haircut)

        by_cap = math.floor(cap / unit)
        by_remaining = math.floor(remaining / unit)
        by_supply = copies if copies is not None else by_cap
        qty = max(0, min(by_cap, by_remaining, by_supply))

        if qty < 1:
            # Report the cap before the running total: the cap is a fixed
            # property of this card and your budget, while "what's left"
            # depends on how far down the list it happens to sit.
            if by_cap < 1:
                pct = unit / float(budget) * 100 if budget else 0
                plan["reason"] = (
                    f"One copy is {pct:.0f}% of the budget, over the "
                    f"{max_position_pct * 100:.0f}% per-position cap."
                )
            elif by_remaining < 1:
                plan["reason"] = f"${remaining:,.2f} left — one copy costs ${unit:,.2f}."
            else:
                plan["reason"] = "No copies listed."
            plans.append(plan)
            continue

        cost = qty * unit
        remaining -= cost

        limit = "the per-position cap"
        if by_supply <= by_cap and by_supply <= by_remaining:
            limit = "the number of copies listed"
        elif by_remaining < by_cap:
            limit = "what's left of the budget"

        plan.update(
            {
                "qty": qty,
                "cost": round(cost, 2),
                "affordable": True,
                "clears_shelf": copies is not None and qty >= copies,
                "budget_pct": round(cost / float(budget) * 100, 1) if budget else 0.0,
                "limited_by": limit,
                "remaining_after": round(remaining, 2),
                # Only meaningful once a fee rate is set; at 0 it just restates the cost.
                "breakeven": round(unit / (1 - fee_pct), 2) if 0 < fee_pct < 1 else None,
            }
        )
        plans.append(plan)

    return plans


def read(row: dict) -> str:
    """One paragraph: what this row is actually saying."""
    mode = row.get("snipe_mode")
    market, low = row.get("market_price"), row.get("floor_low")
    ship, copies = row.get("floor_ship"), row.get("copies")
    gap, mult = row.get("gap_pct"), row.get("floor_multiple")

    if mode == "discount" and market and low:
        s = (
            f"The cheapest Near Mint copy is ${low:,.2f}"
            + (f" (${ship:,.2f} shipped)" if ship else "")
            + f", {gap:.0f}% under the ${market:,.2f} the daily batch last recorded."
        )
        if copies is not None:
            s += f" There are {copies} listed at Near Mint."
        return s
    if mode == "squeeze" and market and low:
        s = (
            f"The cheapest Near Mint copy is already ${low:,.2f}"
            + (f" (${ship:,.2f} shipped)" if ship else "")
            + f" — {mult:.1f}x the ${market:,.2f} the batch still records."
        )
        if copies is not None:
            s += f" Only {copies} listed at Near Mint."
        return s
    if low:
        return f"Floor ${low:,.2f}, in line with the recorded market price."
    return "No live floor pulled for this row yet."


def risk(row: dict) -> str:
    """The specific way this particular setup goes wrong."""
    mode = row.get("snipe_mode")
    if mode == "discount":
        return (
            "The market price is up to two days old. A big discount can mean the "
            "recorded price is stale-high from a spike that has already reversed — "
            "in which case the floor is the real price and there is no gap."
        )
    if mode == "squeeze":
        return (
            "You would be paying above the last recorded trade on the assumption the "
            "batch price catches up. If the remaining listings are one optimistic "
            "seller rather than genuine scarcity, nothing catches up and you own the top."
        )
    return "No setup here — the floor and the recorded price agree."


CHECKLIST = [
    "Confirm the listing is the same printing and language as this row — Holofoil, "
    "Foil and Normal are different products at different prices.",
    "Compare the shipped price, not the floor. On cheap cards shipping can more than "
    "double what you pay.",
    "Check how many sellers those copies come from. One seller holding all of them can "
    "relist at a higher price the moment you clear it.",
    "Look for a reason. Nothing here knows about bans, reprints, or tournament results — "
    "a move with a public cause behaves very differently from one without.",
    "Check the date on the numbers. Market prices lag by up to two days; the floor is "
    "from your last `radar snipe` and is cached after the first call.",
]
