"""Snipe mode: is one copy priced below the rest of the shelf, and how deep is it?

WHICH FIELD IS THE FLOOR (verified 2026-08-09 against TCGplayer itself)

`/cards/:id/prices/conditions` returns both `low_price` and
`lowest_with_shipping` per condition. They are not two views of the same number:

    Gundam Barbatos Adapt (673480)  low_price $2.81   lowest_with_shipping $8.00
      tcgplayer.com/product/673480  ->  "As low as $8.00", 26 listings

    Gundam (LR+) (641452)           low_price $49.99  lowest_with_shipping $49.99
      tcgplayer.com/product/641452  ->  "As low as $49.99", next copy $161.94

`lowest_with_shipping` matched the site exactly on both. `low_price` did not, and
using it produced fake 70%+ "discounts" on cards you could not actually buy at
that price. **Treat `lowest_with_shipping` as the floor. `low_price` is kept only
as `low_ex_ship` and is not used for any signal.**

WHAT THE SIGNAL IS NOW

The old signal compared the live floor against `market_price`, which comes from a
daily batch and runs up to two days behind. Half of every "gap" was just the two
feeds being out of step.

The comparison that holds up is **lowest shipped vs. median shipped**, because
both come from the same live call at the same instant:

  undercut -- the cheapest copy sits well below the rest of the shelf. That is a
              mispriced listing, and it is true regardless of what any batch
              price says. Gundam (LR+): $49.99 with the next copy at $161.94.

  squeeze  -- the whole shelf, cheapest copy included, sits above the recorded
              market on thin supply. The cheap copies are gone and the batch
              price has not caught up.

An undercut says one listing is out of line with its neighbours. It does not say
the card is going up, and neither detector knows why anything is moving.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Sequence

from .client import RateLimitExhausted, TCGClient

log = logging.getLogger("radar.snipe")

NM = "Near Mint"
DEFAULT_LANGUAGE = "English"

# Word-boundary matching on purpose: a loose substring test flags "Saikoro
# Gundam" as Korean and "Improved Technique" as Japanese.
NON_ENGLISH = re.compile(
    r"\b(japan|japanese|jpn|jp|nihongo|chinese|china|chn|korean|korea|kor|"
    r"german|french|spanish|italian|portuguese|thai|russian)\b"
    r"|[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]",
    re.I,
)


def is_english_product(*fields: Any) -> bool:
    """False if any of name/set/edition looks like a non-English printing."""
    for f in fields:
        if f and NON_ENGLISH.search(str(f)):
            return False
    return True


def _f(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def fetch_floor(
    client: TCGClient,
    card_id: Any,
    printing: str | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> dict | None:
    """Live Near Mint shelf for one card: cheapest, median, and how many. One request.

    English only, enforced twice: the endpoint is asked for the language, and
    every row is checked again on the way back. Measured across 60 Gundam cards
    on 2026-08-10 the API returned English for all 92 condition rows, so today
    this is a guard rather than a filter -- but a Japanese listing priced in a
    different market must never become the entry price for an English card.
    """
    rows = client.get(f"/cards/{card_id}/prices/conditions", language=language)
    if not rows:
        return None
    rows = rows if isinstance(rows, list) else [rows]

    before = len(rows)
    rows = [r for r in rows if (r.get("language") or language) == language]
    if len(rows) != before:
        log.debug("card %s: dropped %d non-%s rows", card_id, before - len(rows), language)
    if not rows:
        return None

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
        # Sealed and token products often list in a single condition only.
        candidates = [r for r in rows if not printing or r.get("printing") == printing]
        nm = candidates[0] if candidates else None
    if not nm:
        return None

    return {
        "card_id": str(card_id),
        "printing": nm.get("printing") or printing or "Normal",
        "condition": nm.get("condition"),
        "language": nm.get("language") or language,
        # The floor: matches TCGplayer's displayed "As low as".
        "floor_low": _f(nm.get("lowest_with_shipping")),
        # The rest of the shelf, same call, same instant.
        "shelf_med": _f(nm.get("median_with_shipping")),
        # Kept for reference only -- see the module docstring for why it is not
        # the floor and is never used in a signal.
        "low_ex_ship": _f(nm.get("low_price")),
        "copies": nm.get("sample_count"),
        "as_of": nm.get("last_updated_at"),
        "conditions": [
            {
                "condition": r.get("condition"),
                "printing": r.get("printing"),
                "low_shipped": _f(r.get("lowest_with_shipping")),
                "median_shipped": _f(r.get("median_with_shipping")),
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
    language: str = DEFAULT_LANGUAGE,
) -> dict[tuple[str, str], dict]:
    """One request per card. Stops cleanly on budget or rate limit."""
    out: dict[tuple[str, str], dict] = {}
    for i, (card_id, printing) in enumerate(targets[:limit], 1):
        if client.budget_left <= 0:
            log.warning("Floor fetch stopped at %d/%d -- budget", i, len(targets[:limit]))
            break
        try:
            floor = fetch_floor(client, card_id, printing, language=language)
        except RateLimitExhausted:
            log.warning("Floor fetch stopped at %d/%d -- rate limit", i, len(targets[:limit]))
            break
        except Exception as exc:  # one bad card shouldn't kill the run
            log.debug("Floor fetch failed for %s: %s", card_id, exc)
            continue
        if floor:
            out[(str(card_id), printing)] = floor
        if i % 20 == 0:
            log.info("  ...%d floors (%d requests left)", i, client.budget_left)
    return out


def score(rows: Iterable[dict], floors: dict[tuple[str, str], dict], cfg: dict) -> list[dict]:
    """Attach the live shelf and a 0-100 snipe score. Best first."""
    max_copies = int(cfg.get("max_copies", 40))
    min_undercut = float(cfg.get("min_undercut_pct", 40.0))
    min_squeeze = float(cfg.get("min_squeeze_pct", 8.0))
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
        rec["undercut_pct"] = None
        rec["gap_pct"] = None

        if not floor or not floor.get("floor_low"):
            out.append(rec)
            continue

        low = floor["floor_low"]
        shelf = floor.get("shelf_med")
        copies = floor.get("copies")
        rec["floor_low"] = low
        rec["shelf_med"] = shelf
        rec["low_ex_ship"] = floor.get("low_ex_ship")
        rec["copies"] = copies
        rec["floor_as_of"] = floor.get("as_of")
        rec["floor_condition"] = floor.get("condition")

        # --- the live signal: cheapest copy vs. the rest of the shelf ----------
        undercut = None
        if shelf and shelf > 0:
            undercut = (shelf - low) / shelf * 100.0
            rec["undercut_pct"] = round(undercut, 1)

        # --- context only: the batch price is up to two days old --------------
        market = _f(row.get("market_price"))
        if market:
            rec["gap_pct"] = round((market - low) / market * 100.0, 1)
            rec["floor_multiple"] = round(low / market, 2)

        c7 = float(row.get("change_7d") or 0.0)
        c24 = float(row.get("change_24h") or 0.0)
        momentum = 100.0 * _clamp(max(c7 / 60.0, c24 / 30.0))

        cnum = copies if isinstance(copies, (int, float)) else max_copies
        scarcity = 100.0 * _clamp(1.0 - (cnum / max_copies))

        gap_component = 0.0
        if undercut is not None and undercut >= min_undercut:
            rec["snipe_mode"] = "undercut"
            gap_component = 100.0 * _clamp(undercut / 60.0)
        elif market and rec.get("gap_pct") is not None and rec["gap_pct"] <= -min_squeeze:
            rec["snipe_mode"] = "squeeze"
            gap_component = 100.0 * _clamp(-rec["gap_pct"] / 100.0)

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
    """One line saying what the setup actually is."""
    mode = rec.get("snipe_mode")
    low, shelf = rec.get("floor_low"), rec.get("shelf_med")
    copies, under = rec.get("copies"), rec.get("undercut_pct")

    if mode == "undercut" and low and shelf:
        s = f"Cheapest copy ${low:,.2f} vs ${shelf:,.2f} for the rest — {under:.0f}% below the shelf"
        if copies is not None:
            s += f", {copies} listed"
        return s
    if mode == "squeeze":
        mult = rec.get("floor_multiple")
        s = f"Whole shelf starts at ${low:,.2f}"
        if mult:
            s += f", {mult:.1f}x the recorded price"
        if copies is not None:
            s += f" — {copies} listed"
        return s
    if low and shelf:
        return f"Cheapest ${low:,.2f}, shelf median ${shelf:,.2f} — nothing out of line."
    if low:
        return f"Cheapest copy ${low:,.2f}."
    return ""


def risk(rec: dict) -> str:
    """The specific way this particular setup goes wrong."""
    mode = rec.get("snipe_mode")
    if mode == "undercut":
        return (
            "A copy priced far below its neighbours is usually priced that way for a "
            "reason: wrong printing or language, a condition mismatch, a seller with "
            "bad feedback, or a listing that is already sold and not yet removed. "
            "Check the listing itself before assuming it is free money."
        )
    if mode == "squeeze":
        return (
            "You would be paying above the last recorded trade on the assumption the "
            "batch price catches up. If those listings are one optimistic seller "
            "rather than real scarcity, nothing catches up and you own the top."
        )
    return "No setup here — the cheapest copy is in line with the rest of the shelf."


CHECKLIST = [
    "Open the listing and confirm printing, language and condition match this row — "
    "an outlier price usually has an outlier reason.",
    "Check the seller's feedback and how long the listing has been up.",
    "Compare against the second-cheapest copy, not the market price. If the gap to "
    "number two is small, there is no snipe.",
    "Look for a cause. Nothing here knows about bans, reprints or tournament results.",
    "Remember the market price is up to two days old and the shelf is from your last "
    "`radar snipe`, cached after the first call.",
]
