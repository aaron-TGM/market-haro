"""Alert rules, and the compact issue file the alert service reads.

WHY THIS FILE EXISTS TWICE

Alerts are sent by a small Cloudflare Worker (worker/src/index.js) that
knows each subscriber's holdings. The rules that decide what is worth an
email are written here, in Python, with tests -- and mirrored line for line
in the Worker's `evaluate()`. If the two ever disagree, this file wins and
the Worker is wrong. Keep them the same shape on purpose: one function, one
list of rules, one output record per alert.

THE RULES

  trend_broke      a card you hold or watch broke trend today and had not
                   in the previous issue (weeks-up under 50%, or a 7-day fall
                   past 10%)
  ask_below_sold   a card you watch is now listed below what it has been
                   selling for, and was not yesterday -- the entry read
  left_top_20      a card you hold or watch left the top 20
  entered_top_20   a card you watch entered the top 20
  release_soon     a set releases in exactly seven days (everyone gets this)

Alerts are about change. A card that is broken every day is not news every
day; the previous issue's state is part of the input so nothing repeats.

THE ISSUE FILE

`issue()` reduces a rendered ranking to the dozen fields these rules need,
keyed like the page keys its rows (card_id|printing), so the Worker never
has to parse the dashboard. The pipeline pushes it once a day.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from typing import Any, Sequence

TOP = 20
RELEASE_LEAD_DAYS = 7


def _trend_broke(r: dict) -> bool:
    c, w = r.get("consistency_pct"), r.get("change_7d")
    return (c is not None and c < 50) or (w is not None and w <= -10)


def issue(rows: Sequence[dict], *, obs_date: str, prev_rows: Sequence[dict] | None,
          releases: Sequence[dict], sealed: Sequence[dict] = (), report_url: str = "") -> dict[str, Any]:
    """The compact per-card state the alert rules need, for today and the previous issue."""
    prev = {f"{r['card_id']}|{r.get('printing') or 'Normal'}": r for r in (prev_rows or [])}
    cards = {}
    for r in list(rows) + list(sealed):
        k = f"{r['card_id']}|{r.get('printing') or 'Normal'}"
        p = prev.get(k) or {}
        cards[k] = {
            "name": r.get("name"), "set": r.get("set_name"),
            "price": r.get("market_price"), "entry": r.get("floor_low"),
            # Sealed has its own ordering (by 30-day change); it is not the ranking.
            "rank": None if r.get("kind") == "sealed" else r.get("rank"),
            "prev_rank": None if r.get("kind") == "sealed" else p.get("rank"),
            "trend_broke": _trend_broke(r), "prev_trend_broke": _trend_broke(p) if p else None,
            "prem": r.get("ask_premium_pct"), "prev_prem": p.get("ask_premium_pct"),
            "sealed": r.get("kind") == "sealed",
        }
    nxt = [m for m in releases if m["date"] > obs_date]
    return {"date": obs_date, "report_url": report_url, "top": TOP,
            "next_release": nxt[0] if nxt else None, "cards": cards}


def evaluate(iss: dict, positions: dict[str, dict], *, today: str | None = None) -> list[dict]:
    """positions: {card_key: {qty, cost, since}} -- watched (qty None) or held.

    Returns alert records [{kind, key, name, text}], most urgent first.
    Mirrored in worker/src/index.js::evaluate. Change both.
    """
    out: list[dict] = []
    cards = iss.get("cards") or {}
    top = iss.get("top") or TOP
    for k, pos in positions.items():
        c = cards.get(k)
        if not c:
            continue
        held = bool(pos.get("qty"))
        name = c.get("name") or k
        if c.get("trend_broke") and not c.get("prev_trend_broke"):
            out.append({"kind": "trend_broke", "key": k, "name": name,
                        "text": f"{name} broke trend today" + (" — you hold it." if held else ".")})
        if (c.get("prem") is not None and c["prem"] < -2
                and (c.get("prev_prem") is None or c["prev_prem"] >= -2) and not c.get("sealed")):
            out.append({"kind": "ask_below_sold", "key": k, "name": name,
                        "text": f"{name} is now listed {abs(c['prem']):.0f}% below what it has been selling for."})
        r, pr = c.get("rank"), c.get("prev_rank")
        if pr is not None and pr <= top and (r is None or r > top):
            out.append({"kind": "left_top_20", "key": k, "name": name,
                        "text": f"{name} left the top {top}" + (f" (now #{r})." if r else " (screened out).")})
        if r is not None and r <= top and (pr is None or pr > top) and not held:
            out.append({"kind": "entered_top_20", "key": k, "name": name,
                        "text": f"{name} entered the top {top} at #{r}."})
    nxt = iss.get("next_release")
    today = today or iss.get("date")
    if nxt and today:
        try:
            lead = (_date.fromisoformat(nxt["date"]) - _date.fromisoformat(today)).days
        except (ValueError, TypeError):
            lead = None
        if lead == RELEASE_LEAD_DAYS:
            names = ", ".join(nxt.get("names") or [nxt.get("label", "")])
            out.append({"kind": "release_soon", "key": None, "name": nxt.get("label"),
                        "text": f"{names} releases in {RELEASE_LEAD_DAYS} days ({nxt['date']}). "
                                f"On record, the previous set's top cards fell into a release; see the playbook."})
    order = {"trend_broke": 0, "left_top_20": 1, "ask_below_sold": 2, "entered_top_20": 3, "release_soon": 4}
    out.sort(key=lambda a: (order.get(a["kind"], 9), a["name"] or ""))
    return out


def pnl(iss: dict, positions: dict[str, dict]) -> dict[str, Any] | None:
    """Unrealised P&L across held positions at today's market price."""
    basis = value = 0.0
    n = 0
    for k, pos in positions.items():
        q, c = pos.get("qty"), pos.get("cost")
        px = (iss.get("cards") or {}).get(k, {}).get("price")
        if not q or not c or not px:
            continue
        n += 1
        basis += q * c
        value += q * px
    if not n:
        return None
    return {"positions": n, "basis": round(basis, 2), "value": round(value, 2),
            "pnl": round(value - basis, 2), "pct": round((value / basis - 1) * 100, 1) if basis else None}


def next_lead(today: str, days: int = RELEASE_LEAD_DAYS) -> str:
    return (_date.fromisoformat(today) + timedelta(days=days)).isoformat()
