"""Build the GD05 Freedom Ascension set report from a captured TSV pull.

The sandbox this was built in cannot reach api.tcgapi.dev, so the pull is routed
through a browser and written out as a TSV (same format as scripts/load_snapshot.py,
plus F rows for the live English condition shelf). Load that first:

    python scripts/load_snapshot.py /path/to/gd05_full.tsv
    python scripts/build_set_report.py

On a machine that can reach the API, `radar sync` + `radar backfill` fill the same
database and only the F-row handling below is browser-specific.
"""
import sys, csv, collections; sys.path.insert(0,'.')
from radar import setreport as SR, heat as H, snipe as S
from radar.config import load_config
from radar.db import Database

SRC='/mnt/user-data/uploads/Downloads/gd05_full.tsv'
RELEASED='2026-07-24'; AS_OF='2026-09-03'

# Metadata the DB loader doesn't carry: rarity + total_listings live on the
# C rows, and the F rows are the live English condition shelf.
meta={}; floors=collections.defaultdict(list)
for line in open(SRC, encoding='utf-8'):
    p=line.rstrip('\n').split('\t')
    if p[0]=='C':
        meta[p[1]]={"rarity":p[5] or None,
                    "listings":int(p[10]) if len(p)>10 and p[10] else None}
    elif p[0]=='F':
        f=lambda i:(float(p[i]) if len(p)>i and p[i] else None)
        floors[p[1]].append({"card_id":p[1],"printing":p[2],"condition":p[3],
            "language":p[4],"low_price":f(5),"lowest_with_shipping":f(6),
            "median_with_shipping":f(7),
            "sample_count":int(p[8]) if len(p)>8 and p[8] else None,
            "last_updated_at":p[9] if len(p)>9 else None})

class Stub:
    """Replays the captured conditions rows through the real fetch_floor path."""
    budget_left=10**6; requests_made=0
    def get(self,path,**kw):
        self.requests_made+=1
        return floors.get(path.split('/')[2], [])

cfg=load_config(None); db=Database(cfg.db_path)
series=db.all_series_with_volume()
rows=[dict(r) for r in db.latest_prices()]
fa=[r for r in rows if (r["set_name"] or '').endswith('Freedom Ascension')]

targets=[(r["card_id"], r["printing"]) for r in fa if (r["market_price"] or 0)>=5]
fl=S.fetch_floors(Stub(), targets, limit=len(targets), language="English")

recs=[]
for r in fa:
    key=(r["card_id"], r["printing"])
    m=meta.get(r["card_id"], {})
    f=fl.get(key) or {}
    recs.append({
        "name": r["name"], "number": r["number"],
        "rarity": m.get("rarity") or r["rarity"],
        "printing": r["printing"], "product_type": r["product_type"],
        "tcgplayer_id": r["tcgplayer_id"], "set_name": r["set_name"],
        "listings": m.get("listings"),
        "entry": f.get("floor_low"), "shelf_med": f.get("shelf_med"),
        "copies": f.get("copies"),
        "series": series.get(key, []),
    })

summary=SR.compare(recs, RELEASED)
heat=H.evaluate(H.load(cfg.path("data/market_heat.json")), AS_OF)

NOTES=[
    "“Off peak” is measured against each product's own highest close SINCE RELEASE, not against "
    "its preorder price. Several products have listings back to 2026-06-06; those are dropped.",
    "“Last 7d” compares the mean of the last seven closes with the mean of the seven before. "
    "It is the only column that answers “has it stopped”, and it is deliberately a mean rather "
    "than a point reading — a single quiet day should not read as a turn.",
    "“Entry” is the cheapest Near Mint ENGLISH listing including shipping — what you would "
    "actually pay, matching TCGplayer's “As low as”. It is a live figure from the conditions "
    "endpoint, not the daily batch, so it can sit either side of the market price.",
    "Products with fewer than 10 post-release closes are excluded entirely — there is no path "
    "to read, only noise. That is why the table is shorter than the 257-product set.",
    "Market price comes from a daily batch and is dated by the API's own last_updated_at. "
    f"Latest across this set is {AS_OF}.",
]

html=SR.render(summary, set_name="Freedom Ascension", set_code="GD05",
               released=RELEASED, as_of=AS_OF, notes=NOTES, heat=heat)
open("out/gd05_freedom_ascension.html","w",encoding="utf-8").write(html)

with open("out/gd05_freedom_ascension.csv","w",newline="") as fh:
    w=csv.writer(fh)
    w.writerow(["name","number","rarity","printing","product_type","release_price","peak",
                "peak_date","now","off_peak_pct","since_release_pct","last7_pct","entry",
                "shelf_med","nm_copies","listings","points","tcgplayer_id"])
    for r in summary["rows"]:
        w.writerow([r["name"],r["number"],r["rarity"],r["printing"],r["product_type"],
            r["release_price"],r["peak"],r["peak_date"],r["now"],r["off_peak_pct"],
            r["since_release_pct"],r["last7_pct"],r.get("entry"),r.get("shelf_med"),
            r.get("copies"),r.get("listings"),r["points"],r["tcgplayer_id"]])

print(summary["verdict"]); print()
print(f"{summary['n']} products | off peak {summary['median_off_peak']:+.1f}% | "
      f"since release {summary['median_since_release']:+.1f}% | "
      f"last7 {summary['median_last7']:+.1f}% | still falling "
      f"{summary['still_falling']}/{summary['n_last7']}")
print(f"entry prices resolved: {sum(1 for r in summary['rows'] if r.get('entry'))}")
print()
print(f"  {'band':<10}{'n':>4}{'off peak':>10}{'since rel':>11}{'last 7d':>9}{'falling':>9}")
for b in summary["bands"]:
    print(f"  {b['label']:<10}{b['n']:>4}{b['off_peak']:>9.1f}%{b['since_release']:>10.1f}%"
          f"{b['last7']:>8.1f}%{b['falling']:>5}/{b['n7']}")
print()
print("held best (least off peak):")
for r in summary["rows"][-8:][::-1]:
    e = f"${r['entry']:,.2f}" if r.get("entry") else "-"
    print(f"  {r['name'][:40]:<40} {str(r['rarity'] or '-'):<12} ${r['release_price']:>8.2f} -> "
          f"${r['now']:>8.2f}  {r['off_peak_pct']:>6.1f}%  entry {e}")
db.close()
