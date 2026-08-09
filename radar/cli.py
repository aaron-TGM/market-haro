"""Command line interface: python -m radar <command>"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date
from pathlib import Path

from . import dashboard, ingest, signals
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
            top_n=int(cfg.report.get("top_n", 60)),
            fallers=fallers,
            watchlist=watchlist,
        )
        out = cfg.path(args.out or cfg.report.get("output_path", "out/dashboard.html"))
        dashboard.write(html, out)
        print(f"Dashboard -> {out}")

        flagged = [r for r in ranked if r.get("signals")]
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


def cmd_run(cfg, args) -> int:
    rc = cmd_sync(cfg, args)
    if rc != 0:
        print("Sync did not complete cleanly; reporting on what we have.")
    return cmd_report(cfg, args)


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

    r = sub.add_parser("report", help="score the latest snapshot and build the dashboard")
    r.add_argument("--date", help="observation date (YYYY-MM-DD), default = latest")
    r.add_argument("--out", help="output html path")
    r.add_argument("--top", type=int, default=25, help="rows to print to the terminal")

    a = sub.add_parser("run", help="sync then report (use this in cron)")
    a.add_argument("--no-history", action="store_true")
    a.add_argument("--date")
    a.add_argument("--out")
    a.add_argument("--top", type=int, default=25)
    return p


COMMANDS = {
    "doctor": cmd_doctor,
    "games": cmd_games,
    "sync": cmd_sync,
    "backfill": cmd_backfill,
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
