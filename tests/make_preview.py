"""Build the hold-screen dashboard from a real captured snapshot.

Captured 2026-08-09 from the live API. 1,701 Gundam products scanned; 1,595
singles with a market price; 315 at $10 or more; 212 of those up over 30 days.
Each of the 212 had 90 days of daily price + sales-volume history pulled and the
features below measured from it. Live entry prices came from
/cards/:id/prices/conditions for the top 30.

Every number here was measured. Nothing is interpolated or guessed -- where a
figure wasn't pulled for a card, it is None and the dashboard shows a dash.

    python tests/make_preview.py [output.html]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TCGAPI_KEY", "preview-not-used")

from radar import dashboard, invest  # noqa: E402

OBS = "2026-08-09"

# name|set|number|printing|rarity|market|30d|90d|weeks_up%|volatility%|drawdown%|
# avg_daily_sales|days_traded%|history_pts|entry|shelf_median|copies|tcgplayer_id
CANDIDATES = """
Gundam Epyon (LR+)|Dual Impact|GD02-002|Holofoil|LR+|156.25|55|60|92|2.1|0|1.6|60|89|167.99|197.49|24|659248
Freedom Gundam (LR+)|Newtype Rising|GD01-065|Holofoil|LR+|66.64|38|85|92|1.5|0|2|62|89|81.98|94.99|23|646004
Wing Gundam Zero (LR+)|Newtype Rising|GD01-024|Holofoil|LR+|333.16|53|128|83|2.7|2.9|1.8|57|89|279.99|449.99|21|645344
Kshatriya (GD01-044) (LR+)|Newtype Rising|GD01-044|Holofoil|LR+|106.92|14|47|92|1.1|0|1.5|58|89|105.98|119.79|24|645373
Shenlong Gundam (GD01-029) (R+)|Newtype Rising|GD01-029|Holofoil|R+|107.3|49|84|83|2.4|0|2|53|89|49.99|134.36|10|645360
Altron Gundam (LR+)|Steel Requiem|GD03-018|Holofoil|LR+|55.04|39|49|100|1.2|0.8|1.7|62|89|50|58|26|675680
Gundam Deathscythe (GD01-025) (LR+)|Newtype Rising|GD01-025|Holofoil|LR+|90.07|43|103|75|2.2|5.1|2|58|89|87.99|94.99|31|645367
Resource (R-002) (C++)|Newtype Rising|R-002|Holofoil|C++|100.42|50|82|83|3|0.4|1.8|56|89|94.99|106.48|9|645374
Gundam|Edition Beta|ST01-001|Holofoil|Legend Rare|63.83|31|90|83|2.1|0|2.4|54|90|57.95|84.99|29|616528
Resource (C+)|Edition Beta|R-001|Holofoil|C+|92.34|15|65|92|1.7|0|1.7|26|90|85.92|100|23|616677
Nyaan (Store Tournament Winner Pack 03)|Gundam Promotional Cards|GD03-092|Holofoil|U+|32.49|28|71|100|1.9|0|2.1|54|90|29.99|36.39|32|670587
Marida Cruz (R+)|Newtype Rising|GD01-093|Holofoil|R+|129.87|2|41|75|0.9|4.3|1.5|54|89|112.99|127.93|28|645363
Tallgeese (R+)|Dual Impact|GD02-005|Holofoil|R+|66.98|96|111|83|2.7|0|1.6|65|89|54.98|66.01|26|659252
EX Resource (EXRP-014) (Mobile Suit Gundam 00)|Promotional EX Resource Tokens|EXRP-014|Holofoil|Promo|92.17|39|95|75|3.4|0|3.4|66|89|78.99|87|28|681981
Gundam Aerial Rebuild (LR+)|Newtype Rising|GD01-067|Holofoil|LR+|158.32|90|97|58|2.4|1.7|1.6|61|89|129.58|161.49|24|645372
Cagalli Yula Athha (R+)|Newtype Rising|GD01-096|Holofoil|R+|59.81|57|151|92|2.9|0.5|1.5|55|89|57|66.86|34|645357
Gundam (LR+)|Starter Deck 01: Heroic Beginnings|ST01-001|Holofoil|LR+|159.88|45|38|75|1.6|0|1.3|41|90|49.99|180.75|16|641452
Char's Zaku II (LR+)|Starter Deck 03: Zeon's Rush|ST03-006|Holofoil|LR+|118.98|10|76|83|1.4|2.5|0.9|31|90|109.99|121.95|18|641521
Sayla Mass (R+)|Newtype Rising|GD01-087|Holofoil|R+|86.56|163|235|92|7.2|10|2.3|58|89|85.17|100.63|22|645355
Overflowing Affection (SP) (U+)|Steel Requiem|GD01-118|Holofoil|U+|135.57|5|21|75|1|0|1.3|51|89|135.24|160.35|18|675706
Resource (RP-009) (Gen Con 2025)|Promotional Resource Tokens|RP-009|Holofoil|Promo|74.76|36|107|100|1.5|0|1|30|90|78.99|84.49|16|641571
GFreD (LR+)|Steel Requiem|GD03-035|Holofoil|LR+|41.77|14|29|75|0.8|0|1.7|57|89|41.88|62.91|20|675688
Duo Maxwell (R+)|Newtype Rising|GD01-090|Holofoil|R+|39.71|4|64|83|1.9|16.2|1.9|54|89|35.48|49.99|34|645366
Gundam (Premium Card Collection)|Gundam Promotional Cards|ST01-001|Holofoil|Legend Rare|282.25|39|52|100|1.4|0|0.4|17|90|501.29|674.25|4|670590
Full Armor Unicorn Gundam (Destroy Mode) (Store Tournament Winner Pack 03)|Gundam Promotional Cards|GD03-010|Holofoil|U+|35.57|178|329|100|4.9|0.3|2.8|71|90|25.49|34.07|40|670578
Gundam Deathscythe Hell (Store Tournament Winner Pack 03)|Gundam Promotional Cards|GD03-021|Holofoil|R+|47.83|144|240|83|4.8|3.3|2.8|62|90|34.43|47.68|30|670580
Gundam Exia (Trans-Am) (LR+)|Steel Requiem|GD03-049|Holofoil|LR+|46.52|30|33|67|1.1|0|1.7|55|89|49.99|56.96|19|675696
Resource (R-004) (C+)|Newtype Rising|R-004|Holofoil|C+|14.3|49|108|75|1.7|0|2.1|69|89|16.88|19.99|12|645347
Strike Rouge (R+)|Newtype Rising|GD01-069|Holofoil|R+|35.11|12|115|83|4.5|0|2|52|89|36.46|42.11|39|645358
Unicorn Gundam 02 Banshee (Destroy Mode) (LR+)|Newtype Rising|GD01-003|Holofoil|LR+|70.51|139|107|67|3.8|1.4|1.6|58|89|60.97|77|14|645343
""".strip()

# Cards that failed a gate. Same capture, same measurements -- these are the ones
# worth seeing precisely because they look tempting on a momentum screen.
REJECTED = """
Overflowing Affection (U+)|Edition Beta|GD01-118|Foil|U+|4798.34|10|10|100|1.4|0|0|0|58|616669
Heero Yuy (Championship Finalist Card 01)|Gundam Promotional Cards|ST02-010|Holofoil|Common|1630|12|10|92|1.3|0|0|1|90|654138
Fatal Strike (SP) (C+)|Steel Requiem|ST05-014|Holofoil|C+|81.15|3|-19|42|0.9|18.7|1.3|44|89|675685
Aegis Gundam (LR+)|Starter Deck 04: SEED Strike|ST04-006|Holofoil|LR+|52.63|26|-26|50|2.1|25.5|1|38|90|641553
Resource (RP-001) (Edition Beta BANDAI TCG+ Store Trial Event)|Promotional Resource Tokens|RP-001|Holofoil|Promo|65.93|50|260|48|84.9|40.6|1.8|47|164|641564
Sayla Mass (Store Tournament Winner Pack 01)|Gundam Promotional Cards|GD01-087|Holofoil|R+|65.66|338|531|58|9.2|0|1.6|42|90|646544
EX Base (EXBP-023) (Starter Deck Battle Event)|Promotional EX Base Tokens|EXBP-023|Holofoil|Promo|70.25|37|65|100|3.3|0|1.9|44|41|691178
""".strip()

# Real /cards/:id/history?range=quarter series, downsampled to 14 points for the
# sparkline. Only the cards it was actually pulled for. A card without an entry
# here gets no sparkline -- an absent series is left absent, never interpolated.
SERIES = {
    659248: [("2026-05-14", 97.88), ("2026-05-25", 89.49), ("2026-05-30", 84.98), ("2026-06-05", 87.22),
             ("2026-06-10", 87.24), ("2026-06-16", 87.60), ("2026-06-22", 90.38), ("2026-06-29", 94.56),
             ("2026-07-06", 95.88), ("2026-07-13", 102.98), ("2026-07-20", 128.03), ("2026-07-27", 149.98),
             ("2026-08-03", 153.30), ("2026-08-07", 156.25)],
    646004: [("2026-05-14", 36.03), ("2026-05-25", 34.32), ("2026-05-30", 33.75), ("2026-06-05", 34.01),
             ("2026-06-10", 34.76), ("2026-06-16", 35.79), ("2026-06-22", 41.20), ("2026-06-29", 43.93),
             ("2026-07-06", 44.69), ("2026-07-13", 51.98), ("2026-07-20", 59.55), ("2026-07-27", 59.98),
             ("2026-08-03", 63.64), ("2026-08-07", 66.64)],
    645344: [("2026-05-14", 146.26), ("2026-05-25", 144.94), ("2026-05-30", 148.41), ("2026-06-05", 178.51),
             ("2026-06-10", 187.34), ("2026-06-16", 207.93), ("2026-06-22", 213.44), ("2026-06-29", 214.04),
             ("2026-07-06", 215.89), ("2026-07-13", 220.63), ("2026-07-20", 300.91), ("2026-07-27", 343.15),
             ("2026-08-03", 336.34), ("2026-08-07", 333.16)],
    645373: [("2026-05-14", 72.49), ("2026-05-25", 72.96), ("2026-05-30", 73.37), ("2026-06-05", 73.98),
             ("2026-06-10", 73.01), ("2026-06-16", 74.00), ("2026-06-22", 80.17), ("2026-06-29", 89.03),
             ("2026-07-06", 92.39), ("2026-07-13", 94.85), ("2026-07-20", 95.60), ("2026-07-27", 101.42),
             ("2026-08-03", 105.44), ("2026-08-07", 106.92)],
}

CFG = {
    "min_price": 10.0, "value_ceiling": 200.0, "min_history_days": 45,
    "max_volatility_pct": 8.0,
    "weight_value": 0.20, "weight_liquidity": 0.25, "weight_trend": 0.25,
    "weight_stability": 0.20, "weight_scarcity": 0.10,
}

MARKET = {"priced": 1657, "up_7d": 625}


def _num(s: str):
    s = s.strip()
    if s == "":
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f == int(f) and abs(f) < 1e9 and "." not in s else f


def _row(fields: list[str], with_entry: bool) -> dict:
    name, sname, num, printing, rarity = fields[0], fields[1], fields[2], fields[3], fields[4]
    mkt, c30, c90, cons, vola, dd, sales, traded, pts = (_num(x) for x in fields[5:14])
    if with_entry:
        entry, shelf, copies, tid = (_num(x) for x in fields[14:18])
    else:
        entry = shelf = copies = None
        tid = _num(fields[14])
    return dict(
        card_id=str(tid), tcgplayer_id=tid, printing=printing, product_type="Cards",
        name=name, set_name=sname, number=num or None, rarity=rarity,
        market_price=mkt, change_30d=c30, change_90d=c90,
        consistency_pct=cons, volatility_pct=vola, drawdown_pct=dd,
        avg_daily_sales=sales, days_traded_pct=traded, history_points=pts,
        floor_low=entry, shelf_med=shelf, copies=copies,
        tcgplayer_url=f"https://www.tcgplayer.com/product/{tid}",
        image_url=f"https://product-images.tcgplayer.com/fit-in/400x400/{tid}.jpg",
        series=SERIES.get(tid, []),
    )


def parse() -> list[dict]:
    rows = [_row(l.split("|"), True) for l in CANDIDATES.splitlines() if l.strip()]
    rows += [_row(l.split("|"), False) for l in REJECTED.splitlines() if l.strip()]
    return rows


def main(out_path: str = "out/dashboard.html") -> Path:
    ranked = invest.evaluate(parse(), CFG)
    html = dashboard.render(
        ranked, obs_date=OBS, market=MARKET,
        plan_cfg={"max_position_pct": 0.25},
        scope_note="captured slice: 30 of 212 candidates, plus 7 screened out",
    )
    p = dashboard.write(html, out_path)

    keep = [r for r in ranked if not r.get("disqualified")]
    drop = [r for r in ranked if r.get("disqualified")]
    print(f"{len(keep)} candidates, {len(drop)} screened out -> {p}")
    for r in keep[:8]:
        print(f"  {r['invest_score']:5.1f}  {r['name'][:42]:<42} {str(r['rarity']):<12} "
              f"${r['market_price']:8.2f}  90d {r['change_90d']:+4.0f}%  "
              f"wk {r['consistency_pct']:3.0f}%  {r['avg_daily_sales']:.1f}/day")
    for r in drop:
        print(f"     --  {r['name'][:42]:<42} {r['disqualified']}")
    return p


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/dashboard.html")
