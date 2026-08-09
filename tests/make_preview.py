"""Build a preview dashboard from a real snapshot of live tcgapi.dev data.

The rows below were pulled from the live API on 2026-08-09 (1,685 Gundam products
scanned, 45 cleared the thresholds). Kept in the repo as a fixture so the
dashboard can be regenerated and eyeballed without burning API calls.

    python tests/make_preview.py [output.html]
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TCGAPI_KEY", "preview-not-used")

from radar import dashboard, signals  # noqa: E402

OBS = "2026-08-09"

# name, set, number, printing, market, c24, c7, c30, tcgplayer_id, listings, rarity
LIVE = [
    ("Argama", "Dual Impact", "GD02-129", "Holofoil", 7.75, 54.4, 438.2, 1362.3, 655173, 26, "Rare"),
    ("Zaku II", "Edition Beta", "ST03-008", "Normal", 8.93, 0.0, 121.6, 286.6, 616619, 5, "Common"),
    ("Zaku II", "Starter Deck 03: Zeon's Rush", "ST03-008", "Normal", 6.95, 0.0, 115.8, 504.4, 641507, 25, "Common"),
    ("Silver Bullet", "Phantom Aria", "GD04-068", "Holofoil", 4.58, 0.0, 115.0, 249.6, 689710, 11, "Rare"),
    ("Gundam Barbatos Adapt", "Steel Requiem", "GD03-056", "Holofoil", 9.46, -2.1, 114.0, 201.3, 673480, 18, "Rare"),
    ("Gundam Barbatos Lupus", "Steel Requiem", "GD03-050", "Holofoil", 8.30, 0.0, 112.3, 351.1, 670514, 21, "Rare"),
    ("Gundam NT-1", "Steel Requiem", "GD03-001", "Holofoil", 3.84, 1.3, 72.2, 161.2, 670488, 30, "Rare"),
    ("Argama (R+)", "Dual Impact", "GD02-129", "Holofoil", 74.15, 0.0, 71.7, 411.0, 659358, 14, "R+"),
    ("Corsica Base", "Starter Deck 02: Wings of Advance", "ST02-016", "Normal", 1.79, 14.7, 62.7, 123.8, 641483, 53, "Common"),
    ("GQuuuuuuX (Omega Psycommu) (C+)", "Starter Deck 06: Clan Unity", "ST06-002", "Holofoil", 7.89, 0.0, 40.6, 60.7, 659096, 22, "C+"),
    ("Mikazuki Augus (C+)", "Starter Deck 05: Iron Bloom", "ST05-010", "Holofoil", 13.78, 2.5, 38.1, 43.5, 653646, 17, "C+"),
    ("Zeong", "Phantom Aria", "GD04-017", "Holofoil", 5.27, 0.0, 37.6, 279.1, 684548, 19, "Rare"),
    ("Wire-Guided Arm", "Phantom Aria", "T-022", "Normal", 1.39, 28.7, 32.4, 162.3, 689774, 40, "Common"),
    ("Resource (R-002) (C+)", "Newtype Rising", "R-002", "Holofoil", 11.25, 0.0, 30.2, 46.1, 645345, 12, "C+"),
    ("Parts", "Phantom Aria", "T-021", "Normal", 1.05, 0.0, 29.1, 58.0, 689773, 44, "Common"),
    ("Gundam (GD01-001) (LR++)", "Newtype Rising", "GD01-001", "Holofoil", 1850.85, 0.0, 28.7, 94.1, 645375, 6, "LR++"),
    ("Gundam Ez8 High Mobility Custom", "Eternal Nexus", "EB01-032", "Normal", 1.83, 9.3, 27.5, 82.1, 700940, 35, "Common"),
    ("Unicorn Gundam 02 Banshee (Destroy Mode)", "Newtype Rising", "GD01-003", "Holofoil", 8.51, 0.0, 26.6, 245.9, 643152, 16, "Rare"),
    ("Improved Technique", "Steel Requiem", "GD03-109", "Holofoil", 5.23, 0.0, 26.3, 67.6, 673508, 23, "Rare"),
    ("Giant Killing", "Starter Deck 09: Destiny Ignition", "ST09-009", "Normal", 4.44, 0.0, 24.4, 162.7, 684008, 20, "Common"),
]

# Real quarter-range history (daily, downsampled) for the cards we pulled it for.
SERIES = {
    655173: [("2026-05-14", 0.91), ("2026-05-25", 0.81), ("2026-06-06", 0.68), ("2026-06-17", 0.57),
             ("2026-06-29", 0.62), ("2026-07-04", 0.56), ("2026-07-07", 0.55), ("2026-07-09", 0.53),
             ("2026-07-11", 0.56), ("2026-07-14", 0.55), ("2026-07-16", 0.58), ("2026-07-19", 0.68),
             ("2026-07-21", 0.72), ("2026-07-23", 0.78), ("2026-07-26", 0.67), ("2026-07-28", 0.73),
             ("2026-07-30", 1.00), ("2026-08-01", 1.44), ("2026-08-04", 5.02), ("2026-08-07", 7.75)],
    659358: [("2026-05-14", 16.61), ("2026-05-23", 16.04), ("2026-05-27", 15.97), ("2026-05-31", 16.08),
             ("2026-06-04", 16.16), ("2026-06-08", 15.97), ("2026-06-12", 15.97), ("2026-06-16", 15.34),
             ("2026-06-20", 14.89), ("2026-06-25", 14.54), ("2026-06-30", 14.40), ("2026-07-05", 13.53),
             ("2026-07-10", 15.55), ("2026-07-15", 22.27), ("2026-07-20", 27.41), ("2026-07-25", 31.71),
             ("2026-07-30", 39.45), ("2026-08-04", 63.73), ("2026-08-07", 74.15)],
    616619: [("2026-05-14", 4.57), ("2026-05-22", 4.60), ("2026-05-26", 4.58), ("2026-05-30", 4.18),
             ("2026-06-03", 4.19), ("2026-06-07", 4.25), ("2026-06-11", 4.15), ("2026-06-15", 4.08),
             ("2026-06-19", 3.69), ("2026-06-23", 3.01), ("2026-06-27", 2.89), ("2026-07-01", 2.78),
             ("2026-07-05", 2.53), ("2026-07-09", 2.31), ("2026-07-13", 1.69), ("2026-07-17", 1.63),
             ("2026-07-21", 1.68), ("2026-07-25", 1.74), ("2026-07-29", 1.73), ("2026-08-02", 5.29),
             ("2026-08-06", 6.50), ("2026-08-07", 8.93)],
    641483: [("2026-05-14", 1.24), ("2026-05-22", 1.51), ("2026-05-26", 1.53), ("2026-05-30", 1.52),
             ("2026-06-03", 1.54), ("2026-06-07", 1.59), ("2026-06-11", 1.39), ("2026-06-15", 1.75),
             ("2026-06-19", 1.69), ("2026-06-23", 1.42), ("2026-06-27", 1.45), ("2026-07-01", 1.12),
             ("2026-07-05", 0.76), ("2026-07-09", 0.80), ("2026-07-13", 0.83), ("2026-07-17", 0.78),
             ("2026-07-21", 0.91), ("2026-07-25", 0.94), ("2026-07-29", 1.00), ("2026-08-02", 1.19),
             ("2026-08-07", 1.79)],
}

FALLERS = [
    ("Freedom Ascension Booster Box", "Freedom Ascension", None, "Normal", 233.06, -0.4, -6.2, -29.9, 693621, 48, None),
    ("Char Aznable (LR)", "Newtype Rising", "GD01-047", "Holofoil", 38.40, -1.1, -9.4, -18.2, 645372, 31, "LR"),
    ("Freedom Ascension Booster Pack", "Freedom Ascension", None, "Normal", 8.40, 0.1, -4.8, -29.9, 693620, 120, None),
]

CFG = {
    "min_market_price": 1.0,
    "min_listings": 2,
    "sustained": {"min_change_7d": 8.0, "min_change_30d": 15.0},
    "spike": {"min_change_24h": 12.0, "min_change_7d": 0.0},
    "breakout": {"lookback_days": 90, "exclude_recent_days": 7, "margin_pct": 3.0, "min_history_points": 5},
    "scoring": {
        "weight_sustained": 0.45, "weight_spike": 0.25, "weight_breakout": 0.30,
        "price_bonus_ceiling": 50.0, "price_bonus_max": 8.0, "volume_bonus_max": 6.0,
    },
}


def _rows(spec):
    out = []
    for name, sname, num, printing, mp, c24, c7, c30, tid, listings, rarity in spec:
        out.append(
            dict(
                card_id=str(tid), printing=printing, name=name, set_name=sname, number=num,
                rarity=rarity, market_price=mp, change_24h=c24, change_7d=c7, change_30d=c30,
                total_listings=listings, sales_volume=0, tcgplayer_id=tid,
                tcgplayer_url=f"https://www.tcgplayer.com/product/{tid}",
                image_url=f"https://product-images.tcgplayer.com/fit-in/400x400/{tid}.jpg",
            )
        )
    return out


def main(out_path: str = "out/preview.html") -> Path:
    series = {(str(tid), p): SERIES[tid]
              for tid in SERIES
              for p in ("Normal", "Holofoil")}
    ranked = signals.evaluate(_rows(LIVE), series, CFG, as_of=date.fromisoformat(OBS))
    fallers = signals.evaluate(_rows(FALLERS), {}, CFG, as_of=date.fromisoformat(OBS))
    watch = [r for r in ranked if r["card_id"] == "684008"]

    html = dashboard.render(
        ranked, obs_date=OBS,
        stats={"cards": 1685, "snapshot_dates": 1},
        top_n=60, fallers=fallers, watchlist=watch,
    )
    p = dashboard.write(html, out_path)
    flagged = [r for r in ranked if r["signals"]]
    print(f"{len(flagged)} flagged of {len(ranked)} rows -> {p}")
    for r in flagged[:8]:
        print(f"  {r['score']:5.1f}  {r['name'][:40]:<40} {','.join(r['signals'])}")
    return p


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/preview.html")
