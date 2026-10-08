"""How long will you hold? The ranking depends on the answer.

WHAT REPLACED WHAT, AND WHY (October 2026)

Until 8 October 2026 every card was ranked by one score: value, liquidity,
trend, stability and scarcity, weighted 20/25/25/20/10, over a pool of cards
that were up over 30 days. Walked forward across every week the archive can
score (June to September 2026), that score did worse than picking from its
own pool at random, at every horizon measured: rank correlation with what
came next -0.13 at 30 days, -0.19 at 60, -0.11 at 90 (radar validate, run
2026-10-08), and about -0.20 on what copies actually sold for. Its top 20
trailed the pool in 9 of 12 weekly tests at 30 days and in all 7 at 60.
The trend component (a steady 90-day climb) was the worst part of it: the
climbs reversed. docs/METHOD.md has the tables.

The archive then answered a different question -- what DID predict the
next 3, 6 and 9 months -- and the answer depends on how long the hold is.

  Under 30 days.  Nothing ranked cards into a profit once they were bought
  at the cheapest listing and sold at the market less selling costs: the
  whole pool made money about one time in nine, the 20 strongest 7-day
  risers 3 times in 40. The one thing that helped was paying less than the
  card sells for (the 20 lowest hurdles: 17 in 40). So this horizon is
  sorted by the break-even hurdle -- the move the card needs before selling
  gives your money back -- among cards that sell at least once a day and
  have recent sales to measure it against, and it shows the record above
  the list.

  3-6 months and 1 year+.  Three facts about a card, none of them a
  price trend, ordered the next 90 to 270 days, on market price and on what
  copies sold for, in the $10-100 band and in the pool as a whole, in every
  month the archive can test from October 2025:

    rarity tier    the print rate of the treatment: LR++ over LR+ over R+ ...
    set age        days since its set released; new supply weighs on a new
                   set's cards for months (the playbook panel), so older is
                   better. Promotional pools trickle out all year, so their
                   cards are aged from the day the archive first priced them.
    sales a day    copies actually sold, 90 days; the deeper the market, the
                   better it held

  The hold score is the average of the three as percentiles of today's
  pool, 0-100. Walked forward monthly from October 2025 (radar validate,
  run 2026-10-08), its top 20 rose a median 37.6% over 90 days against
  6.9% for the field and beat it in 9 of 9 tests; over 180 days, 60.1%
  against 25.2%, 6 of 6; over 270 days, 110% against 53%, 3 of 3. After
  selling costs, bought at the market price: +18% at 90 days (positive in
  5 of 9), +38% at 180 (6 of 6). On what copies actually sold for the
  ordering holds too (rank correlation +0.22 at 90 days, +0.26 at 180).
  The 3-6 month and 1 year+ views rank the same way, because the archive
  cannot tell them apart yet: the first full year closes in October 2026,
  and `radar validate` will say when a difference appears. They differ in
  the record they show and the window it is measured over.

  Momentum hurt the long view: requiring a card to be up over 30 days cut
  the 90-day result of the hold ranking from +24% to +10%. So the pool is
  every English single at $10+ that the gates pass, not only the risers.

THE GATES, FOR EVERY HORIZON

A card is not ranked if it is not English, under $10, under 45 days of
history, has no sales (or no sales figures), swings more than 8% a day, or
its cheapest copy costs more than 30% over what it sells for -- at that
point the quoted price is not one anyone can buy at (cards over $500 sat a
median 68% above their market price in September). Under 30 days also needs
a sale a day (the exit has to happen inside the window) and a live Near Mint
price (the hurdle is computed from it).

None of this is a forecast. It is the ordering that has held up, measured
again every month, with the record on the page.
"""

from __future__ import annotations

from datetime import date as _date
from statistics import median
from typing import Any, Sequence

from . import costs as costs_mod
from .invest import RARITY_TIER, _f

HORIZONS = ("short", "mid", "long")
DEFAULT = "mid"
LABELS = {"short": "Under 30 days", "mid": "3–6 months", "long": "1 year+"}
# The windows each horizon's record is measured over (radar validate).
WINDOWS = {"short": (30,), "mid": (90, 180), "long": (270, 365)}

HOLD_PARTS = (
    ("tier", "Rarity", "Print rate of the treatment: LR++ over LR+ over R+ and down. Percentile of today’s pool."),
    ("age", "Set age", "Days since the card’s set released (promos: since first priced). Older sets held up better. Percentile of today’s pool."),
    ("sales", "Sales a day", "Copies actually sold a day over 90 days. Deeper markets held up better. Percentile of today’s pool."),
)

SHORT_MIN_SALES = 1.0
DEFAULTS = {"max_entry_premium_pct": 30.0, "min_price": 10.0, "min_history_days": 45,
            "max_volatility_pct": 8.0}
_TRICKLE = ("promotional", "promo ", "token")


def _cfg(cfg: dict | None) -> dict:
    out = dict(DEFAULTS)
    for k in DEFAULTS:
        v = _f((cfg or {}).get(k))
        if v is not None:
            out[k] = v
    return out


def tier(row: dict) -> int:
    return RARITY_TIER.get(row.get("rarity") or "", 20)


def set_age_days(row: dict, releases: dict[str, str | None], as_of: str) -> int | None:
    """Days since the card's supply started arriving. A set's release date for
    booster and starter sets; the first day the archive priced it for promo
    and token pools, whose cards arrive all year."""
    try:
        today = _date.fromisoformat(as_of[:10])
    except (TypeError, ValueError):
        return None
    name = (row.get("set_name") or "").lower()
    start = row.get("tracked_since") if any(t in name for t in _TRICKLE) else releases.get(str(row.get("set_id")))
    try:
        return max(0, (today - _date.fromisoformat(str(start)[:10])).days)
    except (TypeError, ValueError):
        return None


def percentiles(values: Sequence[float | None]) -> list[float | None]:
    """0-100 rank of each value among the others, ties averaged. None stays None."""
    idx = [i for i, v in enumerate(values) if v is not None]
    out: list[float | None] = [None] * len(values)
    if not idx:
        return out
    order = sorted(idx, key=lambda i: values[i])
    n = len(order)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        pct = 100.0 * ((i + j) / 2) / (n - 1) if n > 1 else 50.0
        for k in range(i, j + 1):
            out[order[k]] = round(pct, 1)
        i = j + 1
    return out


def gate(row: dict, cfg: dict | None = None) -> str | None:
    """Why a card is not ranked for any horizon, or None."""
    from .snipe import is_english_product

    c = _cfg(cfg)
    if not is_english_product(row.get("name"), row.get("set_name"), row.get("number")):
        return "Not an English printing — different market, excluded"
    if row.get("floor_language") and row["floor_language"] != (cfg or {}).get("language", "English"):
        return f"Entry price is a {row['floor_language']} listing — excluded"
    price = _f(row.get("market_price")) or 0.0
    if price < c["min_price"]:
        return f"Under ${c['min_price']:,.0f} — too little value to preserve"
    if row.get("history_points") is None:
        return "No price history pulled yet — run `radar invest`"
    if int(row.get("history_points") or 0) < int(c["min_history_days"]):
        return f"Too new — under {int(c['min_history_days'])} days of price history to judge"
    if row.get("avg_daily_sales") is None:
        return "No sales figures for this card yet — the exit can't be judged"
    if (_f(row.get("avg_daily_sales")) or 0.0) <= 0:
        return "No recorded sales in 90 days — no way out of the position"
    if (_f(row.get("volatility_pct")) or 0.0) > c["max_volatility_pct"]:
        return "Too erratic — daily swings too large to sit on"
    return unbuyable(row, cfg)


def unbuyable(row: dict, cfg: dict | None = None) -> str | None:
    """The cheapest copy costs so much more than the card sells for that the
    quoted price is fiction. Uses the live Near Mint English floor when it was
    pulled; otherwise the batch's cheapest listing of any condition, which is
    a lower bound -- if even that is too far over, Near Mint is too."""
    limit = _cfg(cfg)["max_entry_premium_pct"]
    ref, kind = costs_mod.sells_for(row)
    entry = _f(row.get("floor_low")) or _f(row.get("lowest_with_shipping"))
    if not entry or not ref:
        return None
    prem = (entry / ref - 1) * 100
    if prem > limit:
        what = "sells for" if kind == "sold" else "is priced at"
        return (f"Cheapest copy costs {prem:.0f}% more than it {what} — the quoted price is not "
                f"one you can buy at")
    return None


def short_reason(row: dict) -> str | None:
    """Why a card that passes the gates is still not ranked for a hold under 30 days."""
    if (_f(row.get("avg_daily_sales")) or 0.0) < SHORT_MIN_SALES:
        return f"Sells under {SHORT_MIN_SALES:.0f} a day — too slow to exit inside 30 days"
    if not _f(row.get("floor_low")):
        return "No live Near Mint price pulled today — the hurdle can't be computed"
    # Against the market price the hurdle invents bargains: the market price
    # lags sales, so a copy listed under a stale market price looks like a
    # profit that the next sale would not pay. Real sales or nothing.
    if row.get("sells_for_basis") != "sold":
        return "Too few recent sales to measure the hurdle against"
    if row.get("hurdle_pct") is None:
        return "No price to measure the hurdle against"
    return None


def rank(rows: Sequence[dict], *, releases: dict[str, str | None], as_of: str,
         cfg: dict | None = None, cost_cfg: dict | None = None, regate: bool = True) -> list[dict]:
    """Annotate every row with costs, gates, the hold score and a rank per horizon.

    Returns new dicts, ordered by the default horizon (ranked rows first,
    then the screened-out ones). Each row gets:

      gate          why it is not ranked anywhere, or None
      hold_score    0-100, the mid and long ordering; None when gated
      hold_parts    {tier, age, sales} percentiles behind it
      set_age_days  the age that went in
      horizons      {short|mid|long: {"rank": n or None, "why": reason or None}}
      sells_for, break_even, hurdle_pct, ...   (radar/costs.py)

    `regate=False` keeps each row's existing `disqualified` verdict instead of
    running the gates -- for a renderer handed rows someone else screened.
    """
    out = []
    for r in rows:
        rec = dict(r)
        rec.update(costs_mod.annotate(rec, cost_cfg))
        rec["set_age_days"] = set_age_days(rec, releases, as_of)
        rec["gate"] = gate(rec, cfg) if regate else (rec.get("disqualified") or None)
        # The name the rest of the pipeline (page, front door, stored issue)
        # has always read the screen's verdict under.
        rec["disqualified"] = rec["gate"]
        entry, shelf, mkt = _f(rec.get("floor_low")), _f(rec.get("shelf_med")), _f(rec.get("market_price"))
        rec["entry_vs_shelf_pct"] = round((shelf - entry) / shelf * 100, 1) if entry and shelf else None
        rec["entry_vs_market_pct"] = round((mkt - entry) / mkt * 100, 1) if entry and mkt else None
        out.append(rec)

    alive = [r for r in out if not r["gate"]]
    parts = {
        "tier": percentiles([float(tier(r)) for r in alive]),
        "age": percentiles([r["set_age_days"] for r in alive]),
        "sales": percentiles([_f(r.get("avg_daily_sales")) for r in alive]),
    }
    for i, r in enumerate(alive):
        p = {k: parts[k][i] for k in parts}
        r["hold_parts"] = p
        got = [v for v in p.values() if v is not None]
        r["hold_score"] = round(sum(got) / len(got), 1) if got else None
    for r in out:
        r.setdefault("hold_parts", None)
        r.setdefault("hold_score", None)

    hold = sorted((r for r in alive if r["hold_score"] is not None),
                  key=lambda r: (-r["hold_score"], -(_f(r.get("market_price")) or 0)))
    short_ok = [r for r in alive if not short_reason(r)]
    short = sorted(short_ok, key=lambda r: (r["hurdle_pct"], -(_f(r.get("avg_daily_sales")) or 0)))
    hold_rank = {id(r): i for i, r in enumerate(hold, 1)}
    short_rank = {id(r): i for i, r in enumerate(short, 1)}
    for r in out:
        g = r["gate"]
        r["horizons"] = {
            "short": {"rank": short_rank.get(id(r)), "why": g or (short_reason(r) if id(r) not in short_rank else None)},
            "mid": {"rank": hold_rank.get(id(r)), "why": g},
            "long": {"rank": hold_rank.get(id(r)), "why": g},
        }
    big = 10 ** 9
    out.sort(key=lambda r: (r["gate"] is not None, r["horizons"][DEFAULT]["rank"] or big,
                            -(_f(r.get("market_price")) or 0)))
    return out


def lookup_targets(rows: Sequence[dict], *, hold_n: int, short_n: int) -> list[tuple[str, str]]:
    """Which cards get a live Near Mint price today: the top of the hold
    ranking, and the liquid cards whose batch listing sits furthest under what
    they sell for -- the short view's candidates. One request each."""
    key = lambda r: (str(r["card_id"]), r.get("printing") or "Normal")  # noqa: E731
    picks: list[tuple[str, str]] = []
    hold = [r for r in rows if r.get("hold_score") is not None]
    hold.sort(key=lambda r: -r["hold_score"])
    for r in hold[:hold_n]:
        picks.append(key(r))
    liquid = []
    for r in rows:
        if r.get("gate") or (_f(r.get("avg_daily_sales")) or 0) < SHORT_MIN_SALES:
            continue
        ref, _ = costs_mod.sells_for(r)
        lws = _f(r.get("lowest_with_shipping"))
        if ref and lws:
            liquid.append((lws / ref, r))
    liquid.sort(key=lambda t: t[0])
    for _, r in liquid[:short_n]:
        if key(r) not in picks:
            picks.append(key(r))
    return picks


# ---------------------------------------------------------------- the record
def evidence(validations: Sequence[dict]) -> dict[str, Any] | None:
    """The newest horizon validation, trimmed to what the page shows."""
    rec = next((v for v in reversed(list(validations or [])) if v.get("kind") == "horizons"), None)
    if not rec:
        return None
    return {"ran_at": rec.get("ran_at"), "horizons": rec.get("horizons") or {},
            "legacy": rec.get("legacy"), "costs": rec.get("costs")}


def calendar_read(playbook: dict | None, releases: Sequence[dict], today: str) -> dict[str, Any]:
    """The next release and what past releases did, for the horizon panel."""
    nxt = next((m for m in releases if m.get("date", "") > today and m.get("kind") == "booster"), None)
    out: dict[str, Any] = {}
    if nxt:
        try:
            days = (_date.fromisoformat(nxt["date"]) - _date.fromisoformat(today)).days
        except (TypeError, ValueError):
            days = None
        out["next"] = {"label": nxt.get("label"), "date": nxt["date"], "days": days,
                       "names": nxt.get("names") or []}
    sm = (playbook or {}).get("summary") or {}
    for group in ("prior", "new", "market"):
        for h in (30, 60, 90):
            v = (sm.get(group) or {}).get(f"d{h}")
            if v and v[0] is not None:
                out[f"{group}_d{h}"] = {"median": v[0], "n": v[1]}
    return out


def summary_line(rows: Sequence[dict]) -> dict[str, Any]:
    """Counts for the header: ranked per horizon, and the median hurdle of the ranked."""
    out: dict[str, Any] = {}
    for h in HORIZONS:
        ranked = [r for r in rows if r["horizons"][h]["rank"]]
        hs = [r["hurdle_pct"] for r in ranked if r.get("hurdle_pct") is not None]
        out[h] = {"ranked": len(ranked), "median_hurdle_pct": round(median(hs), 1) if hs else None}
    return out


# ---------------------------------------------------------------- words
def thesis(row: dict) -> str:
    """What the numbers say about holding it, in plain words. Facts only:
    what it is, how old its set is, how it trades, what a round trip takes."""
    if row.get("gate"):
        return row["gate"] + "."
    price = _f(row.get("market_price")) or 0.0
    bits = [f"A ${price:,.2f} {row.get('rarity') or 'card'}"]
    if row.get("set_name"):
        bits.append(f"from {row['set_name']}")
    s = " ".join(bits)
    age = row.get("set_age_days")
    if age is not None:
        s += f", {age // 30} months after its set released" if age >= 60 else f", {age} days after its set released"
    s += "."
    sales = _f(row.get("avg_daily_sales"))
    if sales is not None:
        s += f" It sells about {sales:.1f} copies a day."
    entry, ref, h = _f(row.get("floor_low")), _f(row.get("sells_for")), _f(row.get("hurdle_pct"))
    if entry and ref and h is not None:
        what = "selling for" if row.get("sells_for_basis") == "sold" else "priced at"
        s += (f" The cheapest Near Mint English copy is ${entry:,.2f} shipped and copies have been {what} "
              f"${ref:,.2f}, so it needs {h:+.0f}% before selling it gives back what it cost.")
    elif h is not None:
        s += f" No live Near Mint price was pulled today; from the market price it needs at least {h:+.0f}% to break even."
    return s


def watch(row: dict) -> str:
    """What would break the case for holding it."""
    if row.get("gate"):
        return "Not a candidate while that stays true."
    parts = []
    age = row.get("set_age_days")
    if age is not None and age < 120:
        parts.append(f"its set is {age} days old, and a new set's top cards fell in their first two months "
                     f"after every release measured")
    h = _f(row.get("hurdle_pct"))
    if h is not None and h > 25:
        parts.append(f"it needs {h:+.0f}% before selling it gives back what it cost")
    ev = _f(row.get("entry_vs_sold_pct"))
    if ev is not None and ev > 5:
        parts.append(f"the cheapest copy costs {ev:.0f}% more than copies have been selling for")
    sales = _f(row.get("avg_daily_sales"))
    if sales is not None and sales < 1:
        parts.append(f"at {sales:.1f} sales a day, exiting more than a few copies takes weeks")
    dd = _f(row.get("drawdown_pct"))
    if dd is not None and dd > 15:
        parts.append(f"it is already {dd:.0f}% off its 90-day high")
    if not parts:
        parts.append("nothing in the numbers is flashing yet")
    return ("Watch: " + "; ".join(parts) + ". Reprints, ban-list changes and rotation are the things "
            "that end a run, and none of them are visible here.")
