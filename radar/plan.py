"""Position sizing: turn a budget into "how many, at what cost".

This is arithmetic on numbers you supplied, not a recommendation. It answers a
narrow question -- *given this budget and these caps, what would a position in
this card cost and how much of the shelf would it take* -- and nothing else. It
has no view on whether the card is worth owning, and no knowledge of why the
price is moving.

The rules, in full:

  unit cost      = the live Near Mint floor, which is already shipping-inclusive
                   (`lowest_with_shipping`; see radar/snipe.py for why that is
                   the field that matches TCGplayer and `low_price` is not).
  position cap   = budget x max_position_pct. Halved for a `squeeze`, because
                   there you are paying above the last recorded trade rather
                   than below it.
  set cap        = budget x max_set_pct, across every card of one set: a new
                   set's supply or a reprint hits all of a set's cards at once,
                   and the hold ranking leans to older sets, so without it a
                   budget can land in one set entirely.
  quantity       = min(copies listed, floor(cap / unit), floor(remaining / unit),
                       floor(what is left of the set cap / unit))
  allocation     = greedy down the board in the order given (the page passes
                   the ranking of the hold horizon the reader picked) until the
                   budget runs out.

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
    for key in ("floor_low", "floor_ship"):
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
    max_set_pct: float = 1.0,
    squeeze_haircut: float = 0.5,
    fee_pct: float = 0.0,
) -> list[dict]:
    """Walk the board in order and size each row against what's left.

    Returns one plan dict per input row, in the same order. Rows that don't fit
    still get a plan explaining why. `max_set_pct` 1.0 means no set cap.
    """
    remaining = float(budget)
    by_set_spent: dict[str, float] = {}
    set_cap = float(budget) * float(max_set_pct)
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

        set_key = str(row.get("set_name") or row.get("set_id") or "")
        by_cap = math.floor(cap / unit)
        by_remaining = math.floor(remaining / unit)
        by_supply = copies if copies is not None else by_cap
        # A hair of tolerance: 0.1 x 3 is not quite 0.3 in floating point.
        by_set = math.floor((set_cap - by_set_spent.get(set_key, 0.0)) / unit + 1e-9)
        qty = max(0, min(by_cap, by_remaining, by_supply, by_set))

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
            elif by_set < 1:
                plan["reason"] = (
                    f"{set_key or 'Its set'} already holds the {max_set_pct * 100:.0f}% of the "
                    f"budget one set may take."
                )
            else:
                plan["reason"] = "No copies listed."
            plans.append(plan)
            continue

        cost = qty * unit
        remaining -= cost
        by_set_spent[set_key] = by_set_spent.get(set_key, 0.0) + cost

        limit = "the per-position cap"
        if by_supply <= by_cap and by_supply <= by_remaining and by_supply <= by_set:
            limit = "the number of copies listed"
        elif by_set < by_cap and by_set <= by_remaining:
            limit = "the per-set cap"
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


# The plain-English read, the setup-specific risk and the pre-buy checklist all
# live in radar/snipe.py, next to the data they describe.
from .snipe import CHECKLIST, explain as read, risk  # noqa: E402,F401
