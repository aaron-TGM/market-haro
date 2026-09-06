"""The release calendar: what gets drawn on every price chart.

WHY RELEASES AND NOT "CATALYSTS"

The first attempt at annotating price data was a hand-kept list of events
(a banlist, a release) attached to cards as a "catalyst" flag. It needed a
person to maintain it, it explained nothing on the chart itself, and a reader
could not tell what the flag meant without a tooltip. It is gone.

What a reader actually wants is what a trading terminal gives them: marks on
the chart where something happened, so they can see how price responded. For
a card game the one event that always matters and is always on record is a
set release -- a new booster set, a wave of starter decks, a deck build box.
tcgapi.dev carries every set's release date, so this needs no upkeep: the
calendar is read from the database on every run and drawn on every chart,
past and upcoming.

Each release gets a short code the way players say it -- GD05, ST11 -- taken
from the card numbers in that set (GD05-001 -> GD05), not from a table
somebody has to update. Same-day releases (four starter decks on one Friday)
are one mark with one combined label, because four dashed lines an inch apart
say nothing.

Price anomalies -- a single day that moved more than a threshold -- are the
second mark, computed from the series itself in the page (see haro.py); no
data or upkeep needed either.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

_PREFIX = re.compile(r"^([A-Za-z]+\d*)-")

# Sets that are not events: token and promo pools trickle out all year.
_SKIP = ("promotional", "promo ", "token", "edition beta")


def kind_of(name: str) -> str | None:
    n = (name or "").lower()
    if any(k in n for k in _SKIP):
        return None
    if n.startswith("starter deck"):
        return "starter"
    if "deck build box" in n:
        return "deckbox"
    return "booster"


def set_codes(cards: list[dict]) -> dict[str, str]:
    """set_id -> the most common card-number prefix in that set (GD05, ST11, EXBP)."""
    seen: dict[str, Counter] = defaultdict(Counter)
    for c in cards:
        m = _PREFIX.match(c.get("number") or "")
        if m and c.get("set_id") is not None:
            seen[str(c["set_id"])][m.group(1).upper()] += 1
    return {sid: cnt.most_common(1)[0][0] for sid, cnt in seen.items()}


def _fallback_code(name: str) -> str:
    """No card numbers yet (an upcoming set): ST11 from the name, else the name itself."""
    m = re.search(r"starter deck\s*(\d+)", name or "", re.I)
    if m:
        return f"ST{int(m.group(1)):02d}"
    return (name or "").strip()


def calendar(sets: list[dict], cards: list[dict]) -> list[dict[str, Any]]:
    """Group sets by release date into chart marks.

    Returns [{date, kind, label, names}] oldest first. `label` is what the
    chart prints (GD05, or ST11–14 for a wave); `names` is the full list for
    the tooltip.
    """
    codes = set_codes(cards)
    by_date: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for s in sets:
        d = (s.get("release_date") or "")[:10]
        k = kind_of(s.get("name") or "")
        if not d or not k:
            continue
        # A deck build box reprints another set's cards, so its numbers would
        # mislabel it; it rides on the booster released the same day.
        code = "" if k == "deckbox" else (codes.get(str(s.get("id"))) or _fallback_code(s.get("name") or ""))
        by_date[d].append((k, code, s.get("name") or ""))

    out = []
    for d in sorted(by_date):
        items = sorted(by_date[d], key=lambda x: x[1])
        # A wave of starter decks on one day is one mark: ST11–14.
        st = [c for k, c, _ in items if k == "starter" and re.fullmatch(r"ST\d+", c)]
        others = [c for k, c, _ in items if c and not (k == "starter" and re.fullmatch(r"ST\d+", c))]
        label_parts = list(dict.fromkeys(others))  # boosters first, deduped, order kept
        if len(st) > 1:
            nums = sorted(int(c[2:]) for c in st)
            label_parts.append(f"ST{nums[0]:02d}–{nums[-1]:02d}")
        elif st:
            label_parts.append(st[0])
        if not label_parts:
            label_parts.append("Deck build box")
        kind = "booster" if any(k == "booster" for k, _, _ in items) else items[0][0]
        out.append({"date": d, "kind": kind, "label": " + ".join(label_parts),
                    "names": [n for _, _, n in items]})
    return out


def next_after(cal: list[dict], today: str) -> dict | None:
    for m in cal:
        if m["date"] > today:
            return m
    return None
