"""Build a preview dashboard from a real captured snapshot of live tcgapi.dev data.

Captured 2026-08-09 from the live API: 1,685 Gundam products scanned, 1,657 with a
market price, 657 at or above $1. The slice embedded below is a complete,
well-defined subset of those — every product >= $1 that moved >= 40% on any of the
24h / 7d / 30d windows (118 rows, 20 sets, 13 rarities, both product types).

Kept in the repo so the dashboard can be regenerated and eyeballed without
burning API calls.

    python tests/make_preview.py [output.html]
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TCGAPI_KEY", "preview-not-used")

from radar import dashboard, signals, snipe  # noqa: E402

OBS = "2026-08-09"

SETS = [
    "Dual Impact", "Edition Beta", "Starter Deck 03: Zeon's Rush", "Phantom Aria",
    "Steel Requiem", "Starter Deck 02: Wings of Advance", "Starter Deck 06: Clan Unity",
    "Starter Deck 05: Iron Bloom", "Newtype Rising", "Eternal Nexus",
    "Starter Deck 09: Destiny Ignition", "Gundam Promotional Cards",
    "Starter Deck 08: Flash of Radiance", "Starter Deck 01: Heroic Beginnings",
    "Promotional Resource Tokens", "Starter Deck 04: SEED Strike",
    "Starter Deck 10: Generation Pulse", "Promotional EX Resource Tokens",
    "Promotional EX Base Tokens", "Freedom Ascension",
]
RARITIES = ["Rare", "Common", "Legend Rare", "R+", "C+", "LR++", "LR+", "Uncommon",
            "", "Promo", "U+", "None", "C++"]
PRINTINGS = ["Holofoil", "Normal"]
TYPES = ["Cards", "Sealed Products"]

# name|set|number|printing|type|rarity|market|24h|7d|30d|tcgplayer_id|listings
CAPTURE = """
Argama|0|GD02-129|0|0|0|7.75|54|438|1362|655173|26
Zaku II|1|ST03-008|1|0|1|8.93|0|122|287|616619|5
Zaku II|2|ST03-008|1|0|1|6.95|0|116|504|641507|25
Silver Bullet|3|GD04-068|0|0|0|4.58|0|115|250|689710|22
Gundam Barbatos Adapt|4|GD03-056|0|0|0|9.46|-2|114|201|673480|20
Gundam Barbatos Lupus|4|GD03-050|0|0|2|8.3|0|112|351|670514|23
Gundam NT-1|4|GD03-001|0|0|2|3.84|1|72|161|670488|85
Argama (R+)|0|GD02-129|0|0|3|74.15|0|72|411|659358|14
Corsica Base|5|ST02-016|1|0|1|1.79|15|63|124|641483|53
GQuuuuuuX (Omega Psycommu) (C+)|6|ST06-002|0|0|4|7.89|0|41|61|659096|5
Mikazuki Augus (C+)|7|ST05-010|0|0|4|13.78|2|38|44|653646|11
Zeong|3|GD04-017|0|0|2|5.27|0|38|279|684548|62
Wire-Guided Arm|3|T-022|1|0|1|1.39|29|32|162|689774|20
Resource (R-002) (C+)|8|R-002|0|0|4|11.25|0|30|46|645345|7
Parts|3|T-021|1|0|1|1.05|0|29|58|689773|33
Gundam (GD01-001) (LR++)|8|GD01-001|0|0|5|1850.85|0|29|94|645375|5
Gundam Ez8 High Mobility Custom|9|EB01-032|1|0|1|1.83|9|28|82|700940|2
Unicorn Gundam 02 Banshee (Destroy Mode)|8|GD01-003|0|0|2|8.51|0|27|246|643152|36
Improved Technique|4|GD03-109|0|0|0|5.23|0|26|68|673508|45
Giant Killing|10|ST09-009|1|0|1|4.44|0|24|163|684008|20
Char's Gelgoog|8|GD01-023|0|0|2|8.04|0|24|136|643172|44
Momentary Respite (Store Tournament Winner Pack 02)|11|GD02-112|0|0|3|14.16|0|23|74|659408|20
Shenlong Gundam (GD01-029) (R+)|8|GD01-029|0|0|3|107.3|0|22|49|645360|12
Freedom Gundam (LR+)|10|ST09-004|0|0|6|82.16|0|21|68|684029|10
Wing Gundam|1|GD01-040|1|0|1|3.56|0|20|275|616646|0
Lady Luck (C+)|12|ST08-013|0|0|4|25.99|0|20|45|671976|10
Char's Gelgoog (LR+)|8|GD01-023|0|0|6|27.82|0|19|62|645369|23
Tieria Erde (Store Tournament Winner Pack 03)|11|ST07-010|0|0|4|8.63|0|17|54|670574|13
Victory Gundam (GD04-003)|3|GD04-003|0|0|2|7.99|0|16|607|689647|57
Gundam (LR+)|13|ST01-001|0|0|6|159.88|0|15|45|641452|14
Kshatriya (GD01-044)|8|GD01-044|0|0|2|23.8|0|14|46|643193|27
Overflowing Affection|1|GD01-118|1|0|7|6.45|0|14|47|616668|3
Resource (RP-001) (Edition Beta BANDAI TCG+ Store Trial Event)|14|RP-001|1|0|8|38.49|8|14|67|641564|
Simultaneous Fire (C+)|5|ST02-012|0|0|4|10.49|0|13|44|641495|11
Unicorn Gundam 02 Banshee (Destroy Mode) (LR+)|8|GD01-003|0|0|6|70.51|0|13|139|645343|14
Striker Pack|15|ST04-012|1|0|1|2.82|0|12|124|641543|40
Zaku II FZ (R+)|4|GD03-020|0|0|3|34.39|0|12|66|675723|7
Resource (RP-031) (Premium Accessory Set - Mobile Suit Gundam Wing)|14|RP-031|0|0|9|9.39|0|12|61|681978|16
Zaku I (C+)|2|ST03-007|0|0|4|8.84|0|11|216|641522|16
Gundam Mk-II (Titans) (Store Tournament Winner Pack 02)|11|GD02-003|0|0|3|8.13|0|10|74|659394|18
Gundam Barbatos 1st Form|0|GD02-054|0|0|2|40.17|0|10|117|659290|27
Overflowing Affection (Newtype Challenge 2025 Mission 1)|11|GD01-118|0|0|7|34.58|0|10|88|643465|39
Unlocking the Development Diagram|16|ST10-014|1|0|1|1.76|0|9|252|701016|9
Resource (RP-029) (Premium Accessory Set - Mobile Suit Gundam Wing)|14|RP-029|0|0|9|17.58|0|9|82|681976|22
Awakened Potential (Newtype Challenge 2026 Mission 1)|11|GD03-118|0|0|0|2.16|0|9|71|675729|30
Shuji Ito (Store Tournament Winner Pack 02)|11|ST06-010|0|0|4|16.48|0|9|47|659392|10
Resource (R-004) (C+)|8|R-004|0|0|4|14.3|0|8|49|645347|15
Resource (RP-027) (Premium Accessory Set - Mobile Suit Gundam Wing)|14|RP-027|0|0|9|20.34|0|7|92|681973|15
Quattro Bajeena (Store Tournament Winner Pack 02)|11|GD02-098|0|0|10|21.01|0|7|76|659403|12
EX Resource (EXRP-001) (Mobile Suit Gundam Wing)|17|EXRP-001|0|0|9|74.45|0|6|121|634344|22
The Magic Bullet of Dusk (C+)|15|ST04-014|0|0|4|3.5|0|6|67|641561|17
Newtype Rising Booster Pack|8||1|1|11|18.02|0|6|51|619067|9
Gaplant TR-5 "Hrairoo" Unit 1|9|EB01-054|1|0|1|2.37|0|5|45|700962|44
Resource (RP-022) (Mobile Suit Gundam 00)|14|RP-022|0|0|9|22.93|0|5|79|679243|30
Resource (RP-021) (Mobile Suit Gundam: Hathaway's Flash)|14|RP-021|0|0|9|91.12|0|5|66|679242|13
Freedom Gundam|10|ST09-004|0|0|2|3.58|0|5|120|684003|33
Freedom Gundam (Newtype Challenge 2026 Mission 1)|11|GD01-065|0|0|2|1917.1|0|5|45|675727|9
EX Base (EXBP-005) (Bandai Card Games Fest 25-26)|18|EXBP-005|0|0|9|49.29|0|4|146|641568|31
Z Gundam (Biosensor) (R+)|4|GD03-071|0|0|3|15.08|0|4|47|675722|28
Maganac (C+)|5|ST02-005|0|0|4|5.56|0|3|65|641488|18
Zaku II (Championship Participation Pack 01)|11|ST03-008|0|0|1|72.12|0|3|46|654578|3
Resource (RP-024) (Premium Accessory Set - Mobile Suit Gundam Wing)|14|RP-024|0|0|9|9.51|0|3|45|681970|25
Kshatriya (GD01-051) (Store Tournament Winner Pack 01)|11|GD01-051|0|0|10|42.25|0|3|43|646538|30
GQuuuuuuX (Omega Psycommu) (LR+)|0|GD02-038|0|0|6|24.2|0|2|54|659278|20
Leo (C+)|5|ST02-007|0|0|4|3.99|0|2|43|641490|7
Gundam Epyon (LR+)|0|GD02-002|0|0|6|156.25|0|2|55|659248|23
Gundam Deathscythe Hell (Store Tournament Winner Pack 03)|11|GD03-021|0|0|3|47.83|0|2|144|670580|24
Tallgeese (R+)|0|GD02-005|0|0|3|66.98|0|2|96|659252|25
Resource (RP-033) (Premium Accessory Set - Mobile Suit Gundam Wing)|14|RP-033|0|0|9|8.06|0|2|49|681980|26
First Contact (SP) (U+)|4|GD01-107|0|0|10|56.41|0|1|55|675686|26
Dramatic Turnabout (R+)|0|GD02-100|0|0|3|5|0|1|71|659335|41
Sayla Mass (R+)|8|GD01-087|0|0|3|86.56|0|1|163|645355|25
Full Armor Unicorn Gundam (Destroy Mode) (Store Tournament Winner Pack 03)|11|GD03-010|0|0|10|35.57|0|1|178|670578|34
Tactical Visionary (Store Tournament Winner Pack 03)|11|ST07-014|0|0|4|18.63|0|1|48|670576|11
Zeta Gundam (LR+)|0|GD02-069|0|0|6|28.5|0|0|89|659307|27
Cagalli Yula Athha (R+)|8|GD01-096|0|0|3|59.81|0|0|57|645357|29
Gundam AGE-1 Normal (Store Tournament Winner Pack 02)|11|GD02-029|0|0|1|20.88|0|0|40|659397|22
EX Base (EXBP-003) (Gundam Base Pop-Up World Tour)|18|EXBP-003|1|0|9|19.73|0|0|57|646555|15
Jegan (Store Tournament Winner Pack 01)|11|GD01-016|0|0|4|20.04|0|0|59|646536|13
Dra-C (Sleeves) (C+)|2|ST03-005|0|0|4|2.78|0|0|136|641520|15
Sayla Mass (Store Tournament Winner Pack 01)|11|GD01-087|0|0|3|65.66|0|0|338|646544|40
Cagalli Yula Athha (Championship Participation Pack 01)|11|GD01-096|0|0|0|165.93|0|0|70|654583|11
Resource (RP-006) (Resource Pack)|14|RP-006|0|0|9|46.39|0|0|60|646550|6
Resource (RP-025) (Premium Accessory Set - Mobile Suit Gundam Wing)|14|RP-025|0|0|9|45.92|0|0|206|681971|25
Guncannon (R+)|1|GD01-004|1|0|3|862.5|0|0|46|616631|3
Char Aznable (C+)|1|ST03-011|0|0|4|1500|0|0|88|616621|6
Providence Gundam (LR+)|4|GD03-033|0|0|6|33.98|0|0|70|675708|35
Resource (RP-001) (Edition Beta BANDAI TCG+ Store Trial Event) (Holo)|14|RP-001|0|0|9|65.93||0|50|641564|30
Aile Strike Gundam (Store Tournament Winner Pack 03)|11|GD03-072|0|0|3|28.84|0|0|114|670582|23
Gundam Aerial (Store Tournament Winner Pack 01)|11|GD01-070|0|0|3|43.59|0|0|64|646541|21
Resource (R-002) (C++)|8|R-002|0|0|12|100.42|0|0|50|645374|24
Wing Gundam (Bird Mode)|1|ST02-002|1|0|1|1.45|0|-1|61|616612|11
Gundam Exia (GD04-038)|3|GD04-038|0|0|0|1.19|0|-1|43|689681|118
Gundam Aerial Rebuild (LR+)|8|GD01-067|0|0|6|158.32|0|-1|90|645372|26
Gundam Deathscythe (GD01-025) (LR+)|8|GD01-025|0|0|6|90.07|0|-1|43|645367|27
Garrod Ran & Tiffa Adill (R+)|0|GD02-094|0|0|3|37.11|0|-2|48|659330|26
Wing Gundam (Bird Mode) (Store Tournament Winner Pack 01)|11|ST02-002|0|0|4|53.99|0|-3|63|646531|25
Wing Gundam Zero (LR+)|8|GD01-024|0|0|6|333.16|0|-3|53|645344|36
The-O (LR+)|4|GD03-002|0|0|6|34.74|0|-3|67|675721|29
Amate Yuzuriha (Machu) (ST06 Release Event)|11|ST06-009|0|0|1|5.24|0|-3|-42|660144|41
EX Base (EXBP-006) (G Generation Eternal Collaboration Pack)|18|EXBP-006|0|0|9|1.25|0|-4|-54|653358|41
Freedom Ascension Deck Build Box|19||1|1|11|63.54|-6|-4|-49|693625|35
Gundam (GD01-001) (LR+)|8|GD01-001|0|0|6|102.56|0|-5|192|645356|47
Aile Strike Gundam|1|ST04-001|0|0|2|38.66|0|-5|89|616623|24
Gundam Epyon|0|GD02-002|0|0|2|1.85|0|-6|-42|655155|122
Rick Dom|1|GD01-030|1|0|7|2.42|0|-6|-40|616643|13
Marida Cruz|8|GD01-093|0|0|0|2.28|0|-8|-56|643242|106
Neo Zeong|3|GD04-033|0|0|2|2.37|0|-8|103|689676|125
Wing Gundam (ST02-001)|1|ST02-001|0|0|2|36.06|0|-8|63|616610|21
Gundam X (GD02-056) (Store Tournament Winner Pack 02)|11|GD02-056|0|0|3|42.53|0|-9|292|659401|20
Awakened Potential (Store Tournament Winner Pack 03)|11|GD03-118|0|0|3|13.87|0|-12|85|670589|36
Gundam Lfrith|8|GD01-086|1|0|1|1.88|0|-13|-51|643235|140
Mikazuki Augus (Event Promo)|11|ST05-010|0|0|1|13.08|0|-14|67|661901|43
Gundam Exia (EX)|9|EB01-022|0|0|2|1.95|0|-21|-46|700930|99
Zeta Gundam (EX)|16|ST10-001|0|0|2|1.56|0|-22|-63|701003|63
Build Strike Gundam (Full Package) (EX)|9|EB01-021|0|0|2|1.11|0|-24|-75|700929|101
Gundam AGE-1 Normal|0|GD02-021|0|0|2|5.52|-2|-26|667|651156|71
Phoenix Gundam (Power Unleashed) (EX)|16|ST10-006|0|0|2|1.56|0|-31|-63|701008|72
""".strip()

# Real /cards/:id/history?range=quarter series (daily, downsampled) for the cards
# history was pulled for. Keyed by TCGplayer id.
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

# Population figures over all 1,657 priced products, for the breadth tile.
MARKET = {"priced": 1657, "up_7d": 625}


# Cards that showed up in the live snipe sweep but sit outside the >=40% slice
# above. Same capture, 2026-08-09.
# (name, set, number, printing, market, 24h, 7d, 30d, tcgplayer_id, rarity)
EXTRA = [
    ("Gundam Aerial (Permet Score Six) (LR+)", "Starter Deck 01: Heroic Beginnings", "ST01-006", "Holofoil", 38.49, 0, 16, 39, 641457, "LR+"),
    ("Resource (R-039) (C+)", "Phantom Aria", "R-039", "Holofoil", 2.03, 0, 20, 13, 689795, "C+"),
    ("Resource (R-015) (C++)", "Dual Impact", "R-015", "Holofoil", 30.17, 0, 21, 31, 659373, "C++"),
    ("Char's Zaku II", "Edition Beta", "GD01-026", "Holofoil", 4.45, 0, 20, -16, 616640, "Rare"),
    ("Strike Gundam (C+)", "Starter Deck 04: SEED Strike", "ST04-002", "Holofoil", 12.86, 0, 20, 28, 641549, "C+"),
    ("Resource (R-008) (C+)", "Newtype Rising", "R-008", "Holofoil", 8.52, 0, 19, 20, 645351, "C+"),
    ("GFreD", "Steel Requiem", "GD03-035", "Holofoil", 6.25, 0, 16, 6, 670506, "Rare"),
    ("A Show of Resolve", "Edition Beta", "GD01-100", "Normal", 8.55, 0, 16, 17, 616662, "Common"),
    ("Aegis Gundam (LR+)", "Starter Deck 04: SEED Strike", "ST04-006", "Holofoil", 52.63, 0, 15, 26, 641553, "LR+"),
    ("Gundam Barbatos 2nd Form (C+)", "Starter Deck 05: Iron Bloom", "ST05-002", "Holofoil", 9.52, 0, 23, 14, 653638, "C+"),
    ("Gundam Exia (ST07-002) (C+)", "Starter Deck 07: Celestial Drive", "ST07-002", "Holofoil", 5.95, 0, 19, 16, 671987, "C+"),
    ("Gundam Barbatos Lupus (LR+)", "Steel Requiem", "GD03-050", "Holofoil", 48.63, 0, 15, 29, 675695, "LR+"),
    ("Zechs Merquise (C+)", "Starter Deck 02: Wings of Advance", "ST02-011", "Holofoil", 19.19, 0, 19, 22, 641494, "C+"),
    ("Unforeseen Incident (C+)", "Starter Deck 01: Heroic Beginnings", "ST01-014", "Holofoil", 30.84, 0, 20, 36, 641465, "C+"),
    ("McGillis Fareed (C+)", "Starter Deck 05: Iron Bloom", "ST05-012", "Holofoil", 7.50, 0, 12, 16, 653648, "C+"),
    ("Shamblo (Championship Participation Pack 01)", "Gundam Promotional Cards", "GD01-047", "Holofoil", 11.80, 0, 14, 18, 654581, "Promo"),
    ("Heero Yuy (C+)", "Starter Deck 02: Wings of Advance", "ST02-010", "Holofoil", 20.35, 0, 8, -3, 641493, "C+"),
    ("Force Impulse Gundam (LR+)", "Starter Deck 09: Destiny Ignition", "ST09-002", "Holofoil", 52.17, 0, 5, 3, 684027, "LR+"),
    ("GQuuuuuuX (Omega Psycommu)", "Dual Impact", "GD02-038", "Holofoil", 2.18, 0, 5, 6, 659277, "Rare"),
]

# Live Near Mint shelf from /cards/:id/prices/conditions, 2026-08-09.
#   floor  = lowest_with_shipping  (verified against TCGplayer's "As low as" on
#            products 673480 -> $8.00 and 641452 -> $49.99)
#   shelf  = median_with_shipping, or None where it wasn't pulled for that card.
#            None means no undercut is computed -- an absent number is left absent
#            rather than guessed.
#   copies = sample_count
# `low_price` from the same endpoint does NOT match the site and is never used.
# {tcgplayer_id: (floor, shelf_median_or_None, copies)}
FLOORS = {
    # --- floor, shelf and copies all pulled ---
    645345: (6.29, 31.47, 8),    641452: (49.99, 180.75, 16),  653648: (6.72, 19.99, 3),
    641457: (16.66, 47.47, 15),  645360: (49.99, 134.36, 10),  659373: (17.77, 40.99, 22),
    659408: (21.99, 50.00, 22),  645351: (6.00, 12.99, 7),     654581: (16.39, 35.00, 9),
    641522: (8.89, 14.99, 15),   681976: (17.46, 29.44, 19),   659392: (19.56, 32.99, 3),
    616662: (7.45, 12.41, 11),   643172: (8.20, 13.45, 37),    659277: (2.74, 4.49, 48),
    641543: (3.99, 6.38, 35),    641493: (35.80, 56.80, 4),    684027: (44.38, 69.50, 14),
    673480: (8.00, 10.87, 27),   689710: (5.00, 6.00, 29),     684008: (5.37, 6.51, 21),
    655173: (8.39, 9.90, 24),

    # --- floor and copies pulled, median not fetched for these ---
    670488: (5.15, None, 44),    689795: (3.07, None, 48),     643152: (7.98, None, 40),
    684548: (5.43, None, 45),    616640: (5.00, None, 22),     641549: (8.94, None, 17),
    670506: (7.26, None, 45),    641553: (49.00, None, 11),    653638: (10.50, None, 12),
    689647: (7.12, None, 50),    684029: (74.99, None, 11),    673508: (5.99, None, 34),
    641507: (7.33, None, 26),    671987: (8.00, None, 14),     659358: (75.98, None, 19),
    670514: (10.77, None, 18),   616619: (11.99, None, 7),     671976: (35.00, None, 11),
    675695: (71.49, None, 19),   645369: (44.49, None, 22),    641494: (29.99, None, 13),
    670574: (18.89, None, 18),   653646: (25.00, None, 8),     645375: (3800.00, None, 6),
    641465: (74.99, None, 7),    659096: (20.86, None, 4),     616646: (22.98, None, 1),
}

SNIPE_CFG = {
    "min_undercut_pct": 40.0, "min_squeeze_pct": 8.0, "max_copies": 40, "thin_supply": 12,
    "weight_gap": 0.55, "weight_scarcity": 0.25, "weight_momentum": 0.20,
}

CFG = {
    "min_market_price": 1.0,
    "min_listings": 2,
    "sustained": {"min_change_7d": 8.0, "min_change_30d": 15.0},
    "spike": {"min_change_24h": 12.0, "min_change_7d": 0.0},
    "breakout": {"lookback_days": 90, "exclude_recent_days": 7, "margin_pct": 3.0,
                 "min_history_points": 5},
    "scoring": {
        "weight_sustained": 0.45, "weight_spike": 0.25, "weight_breakout": 0.30,
        "price_bonus_ceiling": 50.0, "price_bonus_max": 8.0, "volume_bonus_max": 6.0,
    },
}


def _num(s: str):
    s = s.strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_capture() -> list[dict]:
    rows = []
    for line in CAPTURE.splitlines():
        if not line.strip():
            continue
        f = line.split("|")
        name, si, num, pi, ti, ri = f[0], int(f[1]), f[2], int(f[3]), int(f[4]), int(f[5])
        market, c24, c7, c30 = (_num(f[6]), _num(f[7]), _num(f[8]), _num(f[9]))
        tid, listings = int(f[10]), _num(f[11])
        rarity = RARITIES[ri]
        rows.append(
            dict(
                card_id=str(tid),
                printing=PRINTINGS[pi],
                product_type=TYPES[ti],
                name=name,
                set_name=SETS[si],
                number=num or None,
                rarity=rarity if rarity not in ("", "None") else None,
                market_price=market,
                change_24h=c24,
                change_7d=c7,
                change_30d=c30,
                total_listings=int(listings) if listings is not None else None,
                sales_volume=0,
                tcgplayer_id=tid,
                tcgplayer_url=f"https://www.tcgplayer.com/product/{tid}",
                image_url=f"https://product-images.tcgplayer.com/fit-in/400x400/{tid}.jpg",
            )
        )
    return rows


def _extra_rows() -> list[dict]:
    out = []
    for name, sname, num, printing, mkt, c24, c7, c30, tid, rarity in EXTRA:
        out.append(dict(
            card_id=str(tid), printing=printing, product_type="Cards", name=name,
            set_name=sname, number=num, rarity=rarity, market_price=mkt,
            change_24h=c24, change_7d=c7, change_30d=c30, total_listings=None,
            sales_volume=0, tcgplayer_id=tid,
            tcgplayer_url=f"https://www.tcgplayer.com/product/{tid}",
            image_url=f"https://product-images.tcgplayer.com/fit-in/400x400/{tid}.jpg",
        ))
    return out


def main(out_path: str = "out/preview.html") -> Path:
    rows = parse_capture() + _extra_rows()
    series = {(str(tid), p): SERIES[tid] for tid in SERIES for p in PRINTINGS}
    as_of = date.fromisoformat(OBS)

    ranked = signals.evaluate(rows, series, CFG, as_of=as_of)

    floors = {}
    for r in rows:
        f = FLOORS.get(r["tcgplayer_id"])
        if f:
            floors[(r["card_id"], r["printing"])] = {
                "card_id": r["card_id"], "printing": r["printing"], "condition": "Near Mint",
                "floor_low": f[0], "shelf_med": f[1], "copies": f[2],
            }
    ranked = snipe.score(ranked, floors, SNIPE_CFG)
    ranked.sort(key=lambda r: (bool(r.get("signals")), r.get("score", 0)), reverse=True)
    board = sorted(
        (r for r in ranked
         if r.get("snipe_mode") and r.get("filter_reason") != "below price floor"),
        key=lambda r: r.get("snipe_score", 0), reverse=True,
    )[:15]
    watch = [r for r in ranked if r["card_id"] in {"684008", "655173"}]
    fallers = sorted(
        (r for r in ranked if not r.get("filtered") and (r.get("change_7d") or 0) < 0),
        key=lambda r: r.get("change_7d") or 0,
    )[:12]

    html = dashboard.render(
        ranked,
        obs_date=OBS,
        stats={"cards": 1685, "snapshot_dates": 1},
        top_n=400,
        fallers=fallers,
        watchlist=watch,
        market=MARKET,
        snipe_board=board,
        thin_supply=12,
        plan_cfg={"max_position_pct": 0.25, "squeeze_haircut": 0.5, "fee_pct": 0.0},
        scope_note="preview slice: 118 of 657 products ≥$1 that moved ≥40% on a window",
    )
    p = dashboard.write(html, out_path)

    flagged = [r for r in ranked if r["signals"]]
    print(f"{len(rows)} rows · {len(flagged)} flagged · {len(board)} on the snipe board -> {p}")
    for r in board[:6]:
        print(f"  snipe {r['snipe_score']:5.1f}  {r['name'][:36]:<36} "
              f"floor ${r.get('floor_low') or 0:8.2f} vs shelf "
              f"{('$%8.2f' % r['shelf_med']) if r.get('shelf_med') else '       —'} "
              f"x{r.get('copies'):<3} "
              f"{(('%+5.0f%%' % r['undercut_pct']) if r.get('undercut_pct') is not None else '    —')}"
              f"  {r.get('snipe_mode')}")
    for r in flagged[:8]:
        print(f"  {r['score']:5.1f}  {r['name'][:44]:<44} {','.join(r['signals'])}")
    return p


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/preview.html")
