"""Pull the whole Gundam Card Game catalogue + prices into SQLite.

Request cost per full sync is tiny: ~22 sets x (1 price call + 1-2 card pages)
= roughly 60 requests against a 10,000/day Pro budget. The expensive part is the
optional one-time history backfill, which is capped by config.

Field mapping note: the API returns `price_change_24h/7d/30d`; internally we
store them as `change_24h/7d/30d`. A `market_price` of 0 means "no market data"
(usually pre-release), not "free" -- it is normalised to NULL so it can't drag
averages or breakout baselines down.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from .client import RateLimitExhausted, TCGClient
from .config import Config
from .db import Database, today

log = logging.getLogger("radar.ingest")

SEALED_TYPES = {"Sealed Products"}


def _price(v: Any) -> float | None:
    """Normalise a price: 0 and negatives mean 'no data' for TCG market prices."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _norm_price_row(
    row: dict,
    *,
    obs_date: str,
    source: str,
    listings: dict[tuple[str, str], int] | None = None,
) -> dict | None:
    card_id = row.get("card_id") or row.get("id")
    if card_id is None:
        return None
    printing = row.get("printing") or "Normal"
    key = (str(card_id), printing)
    return {
        "card_id": str(card_id),
        "printing": printing,
        "obs_date": obs_date,
        "market_price": _price(row.get("market_price")),
        "low_price": _price(row.get("low_price")),
        "median_price": _price(row.get("median_price")),
        "buylist_price": _price(row.get("buylist_price")),
        "lowest_with_shipping": _price(
            row.get("lowest_with_shipping") or row.get("lowest_price_with_shipping")
        ),
        "total_listings": (listings or {}).get(key, row.get("total_listings")),
        "sales_volume": row.get("sales_volume"),
        "avg_sales_price": _price(row.get("avg_sales_price")),
        "change_24h": row.get("price_change_24h", row.get("change_24h")),
        "change_7d": row.get("price_change_7d", row.get("change_7d")),
        "change_30d": row.get("price_change_30d", row.get("change_30d")),
        "source": source,
    }


def _norm_card(row: dict, set_id: Any, set_name: str | None) -> dict:
    return {
        "id": row.get("id") or row.get("card_id"),
        "tcgplayer_id": row.get("tcgplayer_id"),
        "name": row.get("name") or row.get("card_name") or "",
        "clean_name": row.get("clean_name"),
        "number": row.get("number"),
        "rarity": row.get("rarity"),
        "image_url": row.get("image_url"),
        # ?Language=English so the page you open is filtered the same way the
        # screen is -- otherwise you land on a listing set that includes
        # printings the entry price was never measured against.
        "tcgplayer_url": (
            f"https://www.tcgplayer.com/product/{row['tcgplayer_id']}?Language=English"
            if row.get("tcgplayer_id")
            else row.get("tcgplayer_url")
        ),
        "product_type": row.get("product_type"),
        "foil_only": row.get("foil_only"),
        "set_id": set_id,
        "set_name": set_name,
        "game_name": row.get("game_name"),
    }


def sync(
    cfg: Config,
    db: Database,
    client: TCGClient,
    *,
    obs_date: str | None = None,
    skip_history: bool = False,
) -> dict[str, Any]:
    obs_date = obs_date or today()
    include_sealed = bool(cfg.ingest.get("include_sealed", True))
    keep_printings = set(cfg.ingest.get("printings") or [])

    run_id = db.start_run(note=f"sync {obs_date}")
    sets_seen = cards_seen = prices_written = 0
    status = "ok"
    error: str | None = None

    try:
        sets = client.sets(cfg.game_slug)
        if not sets:
            raise RuntimeError(
                f"No sets returned for game slug '{cfg.game_slug}'. "
                f"Run `python -m radar games` to list valid slugs."
            )
        db.upsert_sets(sets, cfg.game_slug)
        sets_seen = len(sets)
        log.info("Found %d sets for %s", sets_seen, cfg.game_slug)

        for s in sets:
            set_id, set_name = s.get("id"), s.get("name")

            # 1. Card metadata: rarity + listing counts live here, not in /prices.
            listings: dict[tuple[str, str], int] = {}
            card_rows = client.set_cards(set_id)
            cards: list[dict] = []
            for row in card_rows:
                if not include_sealed and row.get("product_type") in SEALED_TYPES:
                    continue
                cards.append(_norm_card(row, set_id, set_name))
                if row.get("total_listings") is not None and row.get("id") is not None:
                    listings[(str(row["id"]), row.get("printing") or "Normal")] = row[
                        "total_listings"
                    ]
            if cards:
                cards_seen += db.upsert_cards(cards)

            # 2. Prices with the change_% fields -- one request for the whole set.
            price_rows = client.set_prices(set_id)
            price_cards: list[dict] = []
            points: list[dict] = []
            for row in price_rows:
                if not include_sealed and row.get("product_type") in SEALED_TYPES:
                    continue
                if keep_printings and (row.get("printing") or "Normal") not in keep_printings:
                    continue
                # /sets/:id/prices carries name + image, so it can create cards
                # that the /cards page missed (rare, but keeps the join honest).
                price_cards.append(_norm_card(row, set_id, set_name))
                pt = _norm_price_row(
                    row, obs_date=obs_date, source="snapshot", listings=listings
                )
                if pt:
                    points.append(pt)
            if price_cards:
                db.upsert_cards(price_cards)
            if points:
                prices_written += db.upsert_price_points(points)

            log.info(
                "  %-42s %4d cards  %4d price rows", (set_name or set_id), len(cards), len(points)
            )

        # 3. One-time-ish history backfill so breakout has a baseline on day one.
        if not skip_history:
            prices_written += backfill_history(cfg, db, client)

    except RateLimitExhausted as exc:
        status, error = "rate_limited", str(exc)
        log.warning("Stopped early: %s", exc)
    except Exception as exc:  # noqa: BLE001 - record then re-raise
        status, error = "error", str(exc)
        db.finish_run(
            run_id,
            requests_used=client.requests_made,
            sets_seen=sets_seen,
            cards_seen=cards_seen,
            prices_written=prices_written,
            status=status,
            note=error,
        )
        raise

    db.finish_run(
        run_id,
        requests_used=client.requests_made,
        sets_seen=sets_seen,
        cards_seen=cards_seen,
        prices_written=prices_written,
        status=status,
        note=error or "",
    )
    return {
        "run_id": run_id,
        "obs_date": obs_date,
        "sets": sets_seen,
        "cards": cards_seen,
        "prices": prices_written,
        "requests": client.requests_made,
        "status": status,
    }


def backfill_history(
    cfg: Config,
    db: Database,
    client: TCGClient,
    *,
    range_: str | None = None,
    min_price: float | None = None,
    limit: int | None = None,
) -> int:
    """Fetch price history for the priciest cards that don't have any yet.

    Ranges differ in granularity, not just length: month/quarter are daily,
    year/all are weekly. `quarter` gives daily resolution across the breakout
    window; `all` reaches back to April 2025 at weekly resolution.
    """
    if min_price is None:
        min_price = float(cfg.ingest.get("history_backfill_min_price", 3.0))
    if limit is None:
        limit = int(cfg.ingest.get("history_requests_per_run", 400))
    if range_ is None:
        range_ = cfg.ingest.get("history_backfill_range", "quarter")

    targets = db.cards_needing_history(min_price, limit)
    if not targets:
        log.info("History backfill: nothing to do")
        return 0

    log.info("History backfill: %d cards (range=%s)", len(targets), range_)
    written = 0
    for i, row in enumerate(targets, 1):
        if client.budget_left <= 0:
            log.warning("History backfill stopped at %d/%d -- budget", i, len(targets))
            break
        try:
            hist = client.card_history(row["card_id"], range_)
        except RateLimitExhausted:
            log.warning("History backfill stopped at %d/%d -- rate limit", i, len(targets))
            break
        points = []
        for h in hist:
            date_ = h.get("date") or h.get("obs_date")
            if not date_:
                continue
            points.append(
                {
                    "card_id": row["card_id"],
                    "printing": h.get("printing") or "Normal",
                    "obs_date": str(date_)[:10],
                    "market_price": _price(h.get("market_price")),
                    "low_price": _price(h.get("low_price")),
                    "avg_sales_price": _price(h.get("avg_sales_price")),
                    "sales_volume": h.get("sales_volume"),
                    "source": "history",
                }
            )
        # Drop leading all-zero weeks (pre-release) -- they carry no information.
        points = [p for p in points if p["market_price"] is not None]
        if points:
            written += db.upsert_price_points(points)
        if i % 25 == 0:
            log.info("  ...%d/%d (%d requests left)", i, len(targets), client.budget_left)
    return written


def enrich_flagged(
    cfg: Config,
    db: Database,
    client: TCGClient,
    obs_date: str,
    *,
    limit: int = 200,
) -> int:
    """Pull real sales data for the cards that got flagged.

    `/sets/:id/prices` is cheap but carries no sales figures. `/cards/:id/prices`
    does -- `sales_volume` and `avg_sales_price` are actual transactions rather
    than listings, which is a much better liquidity check before you act on a
    signal. Only flagged cards are worth a request each.
    """
    card_ids = db.flagged_card_ids(obs_date, limit)
    if not card_ids:
        log.info("Enrich: nothing flagged for %s", obs_date)
        return 0

    log.info("Enrich: %d flagged cards", len(card_ids))
    points: list[dict] = []
    for i, cid in enumerate(card_ids, 1):
        if client.budget_left <= 0:
            log.warning("Enrich stopped at %d/%d -- budget", i, len(card_ids))
            break
        try:
            rows = client.get(f"/cards/{cid}/prices")
        except RateLimitExhausted:
            log.warning("Enrich stopped at %d/%d -- rate limit", i, len(card_ids))
            break
        if not rows:
            continue
        for row in rows if isinstance(rows, list) else [rows]:
            pt = _norm_price_row(row, obs_date=obs_date, source="snapshot")
            if pt:
                pt["card_id"] = str(cid)
                points.append(pt)
    if points:
        return db.upsert_price_points(points)
    return 0


def resolve_watchlist(cfg: Config, db: Database, client: TCGClient) -> list[dict]:
    """Map watchlist TCGplayer product IDs to internal card ids, caching in the DB."""
    resolved = []
    for tid in cfg.watchlist_tcgplayer_ids:
        row = db.card_by_tcgplayer_id(tid)
        if row:
            resolved.append({"tcgplayer_id": tid, "card_id": row["id"], "name": row["name"]})
            continue
        card = client.card_by_tcgplayer_id(tid)
        if not card:
            log.warning("Watchlist: TCGplayer id %s not found", tid)
            continue
        db.upsert_cards([_norm_card(card, card.get("set_id"), card.get("set_name"))])
        resolved.append(
            {"tcgplayer_id": tid, "card_id": str(card["id"]), "name": card.get("name")}
        )
    return resolved
