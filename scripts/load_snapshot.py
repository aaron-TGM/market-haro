"""Load a TSV snapshot pulled from tcgapi.dev into the database.

WHY THIS EXISTS

The sandbox this project was built in cannot reach api.tcgapi.dev, so the live
pull was routed through a browser on the user's machine and written out as a TSV.
This loader replays that file through the *same* normalisers the live sync uses
-- `ingest._norm_card` and `ingest._norm_price_row` -- so the rows that land in
SQLite are byte-for-byte what `radar sync` would have written. Nothing is
recomputed or cleaned up on the way in.

On a machine that can reach the API this script is unnecessary: run
`radar sync` and `radar backfill` instead.

FORMAT (tab-separated, one record per line)

  #OBS <date>                                       observation date
  C  id tcgplayer_id name number rarity product_type set_id set_name image_url
  P  card_id printing market low median lowest_with_shipping total_listings
     sales_volume avg_sales_price c24 c7 c30 product_type tcgplayer_id name
     number set_id set_name image_url [last_updated_at]
  H  card_id printing date market low avg_sales_price sales_volume

Empty string means absent, which `_price` and `_int_or_none` already turn into
NULL. A market price of 0 means "no market data", not "free" -- that rule lives
in ingest._price and is not duplicated here.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from radar.config import load_config  # noqa: E402
from radar.db import Database  # noqa: E402
from radar.ingest import _norm_card, _norm_price_row  # noqa: E402


def _v(parts: list[str], i: int) -> str | None:
    return parts[i] if i < len(parts) and parts[i] != "" else None


def _updated_map(path: Path | None) -> dict[tuple[str, str], str]:
    """Optional sidecar: card_id<TAB>printing<TAB>last_updated_at."""
    if not path or not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        if len(p) >= 3 and p[2]:
            out[(p[0], p[1] or "Normal")] = p[2][:10]
    return out


def load(path: Path, cfg, updated: Path | None = None) -> dict:
    db = Database(cfg.db_path)
    upd = _updated_map(updated)
    obs = None
    cards: list[dict] = []
    points: list[dict] = []
    hist: list[dict] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        p = line.split("\t")
        tag = p[0]

        if tag == "#OBS":
            obs = p[1]

        elif tag == "C":
            cards.append(
                _norm_card(
                    {
                        "id": p[1],
                        "tcgplayer_id": _v(p, 2),
                        "name": _v(p, 3) or "",
                        "number": _v(p, 4),
                        "rarity": _v(p, 5),
                        "product_type": _v(p, 6),
                        "image_url": _v(p, 9),
                    },
                    _v(p, 7),
                    _v(p, 8),
                )
            )

        elif tag == "P":
            points.append(
                {
                    "card_id": p[1],
                    "printing": p[2],
                    "market_price": _v(p, 3),
                    "low_price": _v(p, 4),
                    "median_price": _v(p, 5),
                    "lowest_with_shipping": _v(p, 6),
                    "total_listings": _v(p, 7),
                    "sales_volume": _v(p, 8),
                    "avg_sales_price": _v(p, 9),
                    "price_change_24h": _v(p, 10),
                    "price_change_7d": _v(p, 11),
                    "price_change_30d": _v(p, 12),
                    "product_type": _v(p, 13),
                    "tcgplayer_id": _v(p, 14),
                    "name": _v(p, 15) or "",
                    "number": _v(p, 16),
                    "image_url": _v(p, 19),
                    # Dates the row by when the price changed, not by the fetch.
                    # Supplied out of band by --updated when the snapshot TSV
                    # predates this column.
                    "last_updated_at": _v(p, 20),
                    "_set_id": _v(p, 17),
                    "_set_name": _v(p, 18),
                }
            )

        elif tag == "H":
            hist.append(
                {
                    "card_id": p[1],
                    "printing": p[2],
                    "obs_date": p[3][:10],
                    "market_price": _v(p, 4),
                    "low_price": _v(p, 5),
                    "avg_sales_price": _v(p, 6),
                    "sales_volume": _v(p, 7),
                    "source": "history",
                }
            )

    if not obs:
        raise SystemExit("Snapshot has no #OBS line -- refusing to guess the date.")

    for r in points:
        if not r.get("last_updated_at"):
            r["last_updated_at"] = upd.get((str(r["card_id"]), r["printing"]))

    # /sets/:id/prices carries name and image, so it can create cards the
    # /cards page missed. Same order as ingest.sync: metadata first.
    n_cards = db.upsert_cards(cards)
    n_cards += db.upsert_cards(
        [_norm_card(r, r.pop("_set_id"), r.pop("_set_name")) for r in list(points)]
    )

    norm = [_norm_price_row(r, obs_date=obs, source="snapshot") for r in points]
    n_snap = db.upsert_price_points([r for r in norm if r])

    # History rows are floats/ints as strings; _price is applied by the DB layer
    # via _float_or_none, and a market price of 0 was already dropped upstream.
    hist = [h for h in hist if h["market_price"] not in (None, "0", "0.0")]
    n_hist = db.upsert_price_points(hist)

    stats = db.stats()
    db.close()
    return {
        "obs_date": obs,
        "cards": n_cards,
        "snapshot_points": n_snap,
        "history_points": n_hist,
        "stats": stats,
    }


if __name__ == "__main__":
    src = Path(sys.argv[1])
    upd = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    cfg = load_config(None)
    res = load(src, cfg, upd)
    print(f"Loaded {src.name}  (obs {res['obs_date']})")
    print(f"  {res['cards']:,} card upserts")
    print(f"  {res['snapshot_points']:,} snapshot points, {res['history_points']:,} history points")
    for k, v in res["stats"].items():
        print(f"  {k:>16}: {v}")
