"""Command line interface: python -m radar <command>"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date
from pathlib import Path

from . import dashboard, ingest, invest as invest_mod, signals, snipe as snipe_mod
from .client import TCGClient
from .config import ConfigError, load_config
from .db import Database


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )


def _client(cfg) -> TCGClient:
    return TCGClient(
        cfg.api_key,
        cfg.base_url,
        timeout=int(cfg.api.get("timeout_seconds", 30)),
        max_retries=int(cfg.api.get("max_retries", 4)),
        daily_budget=int(cfg.api.get("daily_request_budget", 10000)),
        reserve=int(cfg.api.get("reserve_requests", 500)),
    )


# --- commands ------------------------------------------------------------------
def cmd_doctor(cfg, args) -> int:
    """Verify the key, the game slug, and that every endpoint we rely on works."""
    client = _client(cfg)
    ok = True

    print("Checking API key and endpoints...\n")

    games = client.games()
    print(f"  games                    {len(games)} games returned")
    match = [g for g in games if g.get("slug") == cfg.game_slug]
    if match:
        g = match[0]
        print(
            f"  game slug '{cfg.game_slug}'  OK -> {g.get('name')} "
            f"({g.get('set_count')} sets, {g.get('card_count')} cards)"
        )
    else:
        ok = False
        print(f"  game slug '{cfg.game_slug}'  NOT FOUND")
        near = [g for g in games if "gundam" in json.dumps(g).lower()]
        for g in near:
            print(f"      did you mean: {g.get('slug')}  ({g.get('name')})")

    sets = client.sets(cfg.game_slug)
    print(f"  /sets                    {len(sets)} sets")
    if not sets:
        return 1

    sid = sets[0]["id"]
    cards = client.set_cards(sid)
    print(f"  /sets/{sid}/cards      {len(cards)} rows "
          f"(fields: {', '.join(sorted(cards[0].keys())[:6])}...)" if cards else "  no cards")

    prices = client.set_prices(sid)
    print(f"  /sets/{sid}/prices     {len(prices)} rows")
    if prices:
        needed = {"market_price", "price_change_24h", "price_change_7d", "price_change_30d"}
        missing = needed - set(prices[0].keys())
        if missing:
            ok = False
            print(f"      MISSING EXPECTED FIELDS: {sorted(missing)}")
            print(f"      actual fields: {sorted(prices[0].keys())}")
        else:
            print("      price change fields present")

    if cards:
        hist = client.card_history(cards[0]["id"], "month")
        print(f"  /cards/:id/history       {len(hist)} points "
              f"({'Pro tier OK' if hist else 'empty - check plan tier'})")

    movers = client.top_movers(cfg.game_slug, period="7d", limit=5)
    print(f"  /prices/top-movers       {len(movers)} rows")

    for tid in cfg.watchlist_tcgplayer_ids:
        card = client.card_by_tcgplayer_id(tid)
        print(f"  watchlist {tid:<8}       {'-> ' + card['name'] if card else 'NOT FOUND'}")

    print(f"\n  requests used: {client.requests_made}   remaining today: {client.daily_remaining}")
    print("\n" + ("All good." if ok else "Problems found -- see above."))
    return 0 if ok else 1


def cmd_games(cfg, args) -> int:
    client = _client(cfg)
    for g in sorted(client.games(), key=lambda x: (x.get("name") or "")):
        print(f"{str(g.get('slug')):<32} {g.get('name')}  "
              f"({g.get('set_count')} sets, {g.get('card_count')} cards)")
    return 0


def cmd_sync(cfg, args) -> int:
    db = Database(cfg.db_path)
    client = _client(cfg)
    try:
        ingest.resolve_watchlist(cfg, db, client)
        result = ingest.sync(cfg, db, client, skip_history=args.no_history)
    finally:
        db.close()
    print(
        f"\nSync {result['status']}: {result['sets']} sets, {result['cards']} cards, "
        f"{result['prices']} price points, {result['requests']} API requests."
    )
    return 0 if result["status"] == "ok" else 1


def cmd_backfill(cfg, args) -> int:
    db = Database(cfg.db_path)
    client = _client(cfg)
    try:
        n = ingest.backfill_history(
            cfg, db, client, range_=args.range, min_price=args.min_price, limit=args.limit
        )
    finally:
        db.close()
    print(f"\nBackfilled {n} history points using {client.requests_made} requests.")
    return 0


def cmd_invest(cfg, args) -> int:
    """The hold screen: score every candidate and write the dashboard."""
    icfg = cfg.raw.get("invest", {}) or {}
    db = Database(cfg.db_path)
    client = _client(cfg)
    try:
        obs = args.date or db.latest_obs_date()
        if not obs:
            print("No snapshots yet. Run `python -m radar sync` first.")
            return 1

        min_price = float(icfg.get("min_price", 10.0))
        rows = [dict(r) for r in db.latest_prices(obs)]
        candidates = [
            r for r in rows
            if r.get("product_type") != "Sealed Products"
            and (r.get("market_price") or 0) >= min_price
            and (r.get("change_30d") or 0) > 0
        ]
        print(f"{len(candidates)} cards at ${min_price:,.0f}+ and up over 30d.")

        # 1. Make sure each candidate has daily history with sales volume.
        series = db.all_series_with_volume()
        need = [
            r for r in candidates
            if len(series.get((r["card_id"], r.get("printing") or "Normal"), [])) < 45
        ]
        if need and not args.no_fetch:
            print(f"Fetching 90-day history for {len(need)} of them...")
            points = []
            for i, r in enumerate(need, 1):
                if client.budget_left <= 0:
                    print(f"  stopped at {i}/{len(need)} -- request budget")
                    break
                try:
                    hist = client.card_history(r["card_id"], "quarter")
                except Exception:
                    continue
                for h in hist:
                    d = h.get("date")
                    if not d:
                        continue
                    points.append({
                        "card_id": r["card_id"],
                        "printing": h.get("printing") or r.get("printing") or "Normal",
                        "obs_date": str(d)[:10],
                        "market_price": h.get("market_price") or None,
                        "sales_volume": h.get("sales_volume"),
                        "avg_sales_price": h.get("avg_sales_price") or None,
                        "source": "history",
                    })
            points = [p for p in points if p["market_price"]]
            if points:
                db.upsert_price_points(points)
            series = db.all_series_with_volume()

        # 2. Measure.
        measured = []
        for r in candidates:
            key = (r["card_id"], r.get("printing") or "Normal")
            hist = series.get(key, [])
            feats = invest_mod.features(hist) or {}
            rec = {**r, **feats, "series": [(d, p) for d, p, _ in hist[-90:]]}
            measured.append(rec)

        # 3. Live entry price for the strongest ones only.
        preliminary = invest_mod.evaluate(measured, icfg)
        alive = [r for r in preliminary if not r.get("disqualified")]
        n_entry = args.entries or int(icfg.get("entry_lookups", 40))
        targets = [(r["card_id"], r.get("printing") or "Normal") for r in alive[:n_entry]]
        if targets and not args.no_fetch:
            print(f"Pulling live entry prices for the top {len(targets)}...")
            floors = snipe_mod.fetch_floors(
                client, targets, limit=n_entry, language=icfg.get("language", "English")
            )
            if floors:
                db.save_floors(floors.values())
            for r in preliminary:
                f = floors.get((r["card_id"], r.get("printing") or "Normal"))
                if f:
                    r["floor_low"] = f.get("floor_low")
                    r["shelf_med"] = f.get("shelf_med")
                    r["copies"] = f.get("copies")
                    r["floor_language"] = f.get("language")
        else:
            for r in preliminary:
                f = db.latest_floors().get((r["card_id"], r.get("printing") or "Normal"))
                if f:
                    r["floor_low"] = f.get("floor_low")
                    r["copies"] = f.get("copies")

        # 4. Score for real (scarcity uses copies) and render.
        ranked = invest_mod.evaluate(preliminary, icfg)
        html = dashboard.render(
            ranked,
            obs_date=obs,
            stats=db.stats(),
            market=db.market_breadth(obs),
            plan_cfg=cfg.raw.get("plan") or {},
        )
        out = cfg.path(args.out or cfg.report.get("output_path", "out/dashboard.html"))
        dashboard.write(html, out)
        print(f"\nDashboard -> {out}")

        keep = [r for r in ranked if not r.get("disqualified")]
        drop = [r for r in ranked if r.get("disqualified")]
        if cfg.report.get("write_csv", True):
            cp = out.with_suffix(".csv")
            cols = ["invest_score", "name", "set_name", "number", "rarity", "printing",
                    "market_price", "change_30d", "change_90d", "consistency_pct",
                    "volatility_pct", "drawdown_pct", "avg_daily_sales", "days_traded_pct",
                    "floor_low", "shelf_med", "copies", "tcgplayer_url"]
            with cp.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                for r in keep:
                    w.writerow([r.get(c) for c in cols])
            print(f"CSV       -> {cp}")

        print(f"\n{len(keep)} candidates, {len(drop)} screened out.")
        print(f"{'':2}{'SCORE':>5}  {'CARD':<40} {'RARITY':<12} {'PRICE':>9} "
              f"{'90D':>6} {'WKUP':>5} {'SALES':>6}  ENTRY")
        for r in keep[: args.top]:
            print(
                f"  {r['invest_score']:5.1f}  {str(r.get('name'))[:40]:<40} "
                f"{str(r.get('rarity') or '-')[:12]:<12} ${(r.get('market_price') or 0):8.2f} "
                f"{(r.get('change_90d') or 0):+5.0f}% {(r.get('consistency_pct') or 0):4.0f}% "
                f"{(r.get('avg_daily_sales') or 0):5.1f}  "
                f"{('$%.2f' % r['floor_low']) if r.get('floor_low') else '-'}"
            )
        if drop:
            from collections import Counter
            for reason, n in Counter(r["disqualified"] for r in drop).most_common():
                print(f"  screened out: {n:>3}  {reason}")
        print(f"\n  {client.requests_made} API requests used.")
    finally:
        db.close()
    return 0


def cmd_snipe(cfg, args) -> int:
    """Pull live listing floors for the cards that are moving, and rank buys."""
    db = Database(cfg.db_path)
    client = _client(cfg)
    scfg = cfg.raw.get("snipe", {}) or {}
    try:
        obs = args.date or db.latest_obs_date()
        if not obs:
            print("No snapshots yet -- run `python -m radar run` first.")
            return 1

        rows = [dict(r) for r in db.latest_prices(obs)]
        min_price = float(scfg.get("min_market_price", 2.0))
        min_c7 = float(scfg.get("min_change_7d", 10.0))
        include_sealed = bool(scfg.get("include_sealed", False))

        movers = [
            r for r in rows
            if (r.get("market_price") or 0) >= min_price
            and (include_sealed or r.get("product_type") != "Sealed Products")
            and ((r.get("change_7d") or 0) >= min_c7 or (r.get("change_24h") or 0) >= min_c7)
        ]
        movers.sort(key=lambda r: (r.get("change_7d") or 0), reverse=True)
        n = args.targets or int(scfg.get("targets", 60))
        movers = movers[:n]
        if not movers:
            print("Nothing is moving enough to be worth a live look right now.")
            return 0

        print(f"Fetching live listing floors for {len(movers)} movers...")
        floors = snipe_mod.fetch_floors(
            client, [(r["card_id"], r.get("printing") or "Normal") for r in movers],
            limit=n, language=scfg.get("language", "English"),
        )
        if floors:
            db.save_floors(floors.values())

        ranked = snipe_mod.score(movers, floors, scfg)
        # The board is driven by live listing data, so a stale batch listing count
        # shouldn't hide a row -- only the price floor filter applies here.
        board = [
            r for r in ranked
            if r.get("snipe_mode") and r.get("filter_reason") != "below price floor"
        ][: args.top]

        thin = int(scfg.get("thin_supply", 12))
        print(f"\n{'':2}{'SCORE':>6}  {'CARD':<40} {'MARKET':>9} {'FLOOR':>9} "
              f"{'SHIPPED':>9} {'COPIES':>7} {'GAP':>7}  SETUP")
        for r in board:
            mark = "*" if (r.get("copies") or 999) <= thin else " "
            print(
                f"{mark} {r['snipe_score']:6.1f}  {r['name'][:40]:<40} "
                f"${(r.get('market_price') or 0):8.2f} ${(r.get('floor_low') or 0):8.2f} "
                f"${(r.get('floor_ship') or 0):8.2f} {str(r.get('copies') or '?'):>7} "
                f"{(r.get('gap_pct') or 0):+6.0f}%  {r.get('snipe_mode')}"
            )
        if not board:
            print("  no setups cleared the gap threshold.")
        print(f"\n  * = {thin} copies or fewer at Near Mint")
        print(f"  {client.requests_made} requests used. "
              f"Floors are live as of this run; market prices are the daily batch.")
        print("  Re-run `python -m radar report` to fold these into the dashboard.")
    finally:
        db.close()
    return 0


def cmd_run(cfg, args) -> int:
    """Daily pass: refresh prices, then rebuild the hold screen."""
    rc = cmd_sync(cfg, args)
    if rc != 0:
        print("Sync did not complete cleanly; screening on what we have.")
    return cmd_invest(cfg, args)


def cmd_stats(cfg, args) -> int:
    db = Database(cfg.db_path)
    try:
        for k, v in db.stats().items():
            print(f"{k:>16}: {v}")
        print(f"{'db':>16}: {cfg.db_path}")
    finally:
        db.close()
    return 0


# --- entrypoint ----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="radar",
        description="Track Gundam Card Game prices and surface cards that are rising.",
    )
    p.add_argument("-c", "--config", help="path to config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="verify API key, game slug and every endpoint used")
    sub.add_parser("games", help="list every game slug the API knows about")
    sub.add_parser("stats", help="what's in the local database")

    s = sub.add_parser("sync", help="pull the catalogue and today's prices")
    s.add_argument("--no-history", action="store_true", help="skip the history backfill")

    b = sub.add_parser("backfill", help="pull price history for cards that lack it")
    b.add_argument(
        "--range",
        default=None,
        choices=["month", "quarter", "year", "all"],
        help="month/quarter = daily points, year/all = weekly (all reaches back to 2025-04)",
    )
    b.add_argument("--min-price", type=float, default=None)
    b.add_argument("--limit", type=int, default=None, help="max cards this run")

    n = sub.add_parser("snipe", help="live listing floors + copy counts for the movers")
    n.add_argument("--date", help="observation date (YYYY-MM-DD), default = latest")
    n.add_argument("--targets", type=int, default=None, help="how many movers to look up")
    n.add_argument("--top", type=int, default=20, help="rows to print")

    r = sub.add_parser("invest", help="the hold screen: rank cards worth buying and sitting on")
    r.add_argument("--date", help="observation date (YYYY-MM-DD), default = latest")
    r.add_argument("--out", help="output html path")
    r.add_argument("--top", type=int, default=25, help="rows to print to the terminal")
    r.add_argument("--entries", type=int, default=None,
                   help="how many candidates to pull a live entry price for")
    r.add_argument("--no-fetch", action="store_true",
                   help="score from what's already in the database, no API calls")

    a = sub.add_parser("run", help="sync then rebuild the hold screen (use this in cron)")
    a.add_argument("--no-history", action="store_true")
    a.add_argument("--date")
    a.add_argument("--out")
    a.add_argument("--top", type=int, default=25)
    a.add_argument("--entries", type=int, default=None)
    a.add_argument("--no-fetch", action="store_true")
    return p


COMMANDS = {
    "doctor": cmd_doctor,
    "games": cmd_games,
    "sync": cmd_sync,
    "backfill": cmd_backfill,
    "snipe": cmd_snipe,
    "invest": cmd_invest,
    "run": cmd_run,
    "stats": cmd_stats,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    return COMMANDS[args.cmd](cfg, args)
