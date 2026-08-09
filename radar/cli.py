"""Command line interface: python -m radar <command>"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date
from pathlib import Path

from . import dashboard, ingest, signals, snipe as snipe_mod
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


def cmd_report(cfg, args) -> int:
    db = Database(cfg.db_path)
    try:
        obs = args.date or db.latest_obs_date()
        if not obs:
            print("No snapshots in the database yet. Run `python -m radar sync` first.")
            return 1

        rows = [dict(r) for r in db.latest_prices(obs)]
        series = db.all_series()
        ranked = signals.evaluate(rows, series, cfg.signals, as_of=date.fromisoformat(obs))

        # Fold in any live listing floors we've pulled (radar snipe).
        scfg = cfg.raw.get("snipe", {}) or {}
        floors = db.latest_floors()
        if floors:
            ranked = snipe_mod.score(ranked, floors, scfg)
            ranked.sort(key=lambda r: (bool(r.get("signals")), r.get("score", 0)), reverse=True)
        # The board is driven by live listing data, so a stale batch listing count
        # shouldn't hide a row -- only the price floor filter applies here.
        board = [
            r for r in ranked
            if r.get("snipe_mode") and r.get("filter_reason") != "below price floor"
        ]
        board.sort(key=lambda r: r.get("snipe_score", 0), reverse=True)
        board = board[: int(scfg.get("board_size", 15))]

        watch_ids = set()
        for tid in cfg.watchlist_tcgplayer_ids:
            row = db.card_by_tcgplayer_id(tid)
            if row:
                watch_ids.add(str(row["id"]))
        watchlist = [r for r in ranked if r["card_id"] in watch_ids]

        n_fall = int(cfg.report.get("include_fallers", 15))
        fallers = sorted(
            (r for r in ranked if not r.get("filtered") and (r.get("change_7d") or 0) < 0),
            key=lambda r: r.get("change_7d") or 0,
        )[:n_fall]

        stats = db.stats()
        html = dashboard.render(
            ranked,
            obs_date=obs,
            stats=stats,
            top_n=int(cfg.report.get("top_n", 400)),
            fallers=fallers,
            watchlist=watchlist,
            market=db.market_breadth(obs),
            snipe_board=board,
            thin_supply=int(scfg.get("thin_supply", 12)),
        )
        out = cfg.path(args.out or cfg.report.get("output_path", "out/dashboard.html"))
        dashboard.write(html, out)
        print(f"Dashboard -> {out}")

        flagged = [r for r in ranked if r.get("signals")]

        # Persist the calls so you can ask later "what did the radar say on the 9th,
        # and was it right?" -- and so `enrich` knows which cards to spend requests on.
        db.record_alerts(0, obs, flagged)

        if cfg.report.get("write_json", True):
            jp = out.with_suffix(".json")
            jp.write_text(
                json.dumps(
                    {
                        "obs_date": obs,
                        "generated_from": stats,
                        "flagged": [
                            {
                                k: v
                                for k, v in r.items()
                                if k not in ("series", "raw", "components")
                            }
                            for r in flagged
                        ],
                    },
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            print(f"JSON      -> {jp}")
        if cfg.report.get("write_csv", True):
            cp = out.with_suffix(".csv")
            cols = [
                "score", "name", "set_name", "number", "rarity", "printing",
                "market_price", "change_24h", "change_7d", "change_30d",
                "total_listings", "sales_volume", "trailing_high",
                "breakout_excess_pct", "tcgplayer_url",
            ]
            with cp.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(cols + ["signals"])
                for r in flagged:
                    w.writerow([r.get(c) for c in cols] + ["|".join(r.get("signals", []))])
            print(f"CSV       -> {cp}")

        # Terminal summary so a cron run says something useful in the log.
        print(f"\nTop movers for {obs}:")
        for r in flagged[: args.top]:
            print(
                f"  {r['score']:5.1f}  {r['name'][:38]:<38} {r.get('set_name', '')[:22]:<22} "
                f"${(r.get('market_price') or 0):7.2f}  "
                f"24h {(r.get('change_24h') or 0):+6.1f}%  "
                f"7d {(r.get('change_7d') or 0):+7.1f}%  "
                f"30d {(r.get('change_30d') or 0):+8.1f}%  "
                f"[{','.join(r['signals'])}]"
            )
        if not flagged:
            print("  nothing cleared the thresholds today.")
    finally:
        db.close()
    return 0


def cmd_enrich(cfg, args) -> int:
    """Pull real sales figures for flagged cards (one request each)."""
    db = Database(cfg.db_path)
    client = _client(cfg)
    try:
        obs = args.date or db.latest_obs_date()
        if not obs:
            print("Nothing to enrich -- run `python -m radar run` first.")
            return 1
        n = ingest.enrich_flagged(cfg, db, client, obs, limit=args.limit)
    finally:
        db.close()
    print(f"\nEnriched {n} price rows with sales data using {client.requests_made} requests.")
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
            client, [(r["card_id"], r.get("printing") or "Normal") for r in movers], limit=n
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
    rc = cmd_sync(cfg, args)
    if rc != 0:
        print("Sync did not complete cleanly; reporting on what we have.")
    rc = cmd_report(cfg, args)
    if getattr(args, "enrich", False):
        cmd_enrich(cfg, args)
        # Sales volume feeds the score, so re-report once it's in.
        rc = cmd_report(cfg, args)
    if getattr(args, "snipe", False):
        args.targets = None
        args.top = 15
        cmd_snipe(cfg, args)
        rc = cmd_report(cfg, args)
    return rc


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

    e = sub.add_parser("enrich", help="pull real sales figures for flagged cards")
    e.add_argument("--date", help="observation date (YYYY-MM-DD), default = latest")
    e.add_argument("--limit", type=int, default=200, help="max flagged cards to enrich")

    r = sub.add_parser("report", help="score the latest snapshot and build the dashboard")
    r.add_argument("--date", help="observation date (YYYY-MM-DD), default = latest")
    r.add_argument("--out", help="output html path")
    r.add_argument("--top", type=int, default=25, help="rows to print to the terminal")

    a = sub.add_parser("run", help="sync then report (use this in cron)")
    a.add_argument("--no-history", action="store_true")
    a.add_argument("--enrich", action="store_true",
                   help="also pull sales volume for flagged cards, then re-score")
    a.add_argument("--snipe", action="store_true",
                   help="also pull live listing floors for the movers")
    a.add_argument("--limit", type=int, default=200)
    a.add_argument("--date")
    a.add_argument("--out")
    a.add_argument("--top", type=int, default=25)
    return p


COMMANDS = {
    "doctor": cmd_doctor,
    "games": cmd_games,
    "sync": cmd_sync,
    "backfill": cmd_backfill,
    "enrich": cmd_enrich,
    "snipe": cmd_snipe,
    "report": cmd_report,
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
