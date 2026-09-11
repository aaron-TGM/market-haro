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
        # The API's change_30d is the cheap pre-filter. When it is missing --
        # an older archive, or a product the batch has not repriced -- fall
        # back to the stored series rather than silently dropping the card.
        series_30 = db.change_over_days(30)
        def _up_30d(r: dict) -> bool:
            c = r.get("change_30d")
            if c is None:
                c = series_30.get((r["card_id"], r.get("printing") or "Normal"))
            return (c or 0) > 0
        candidates = [
            r for r in rows
            if r.get("product_type") != "Sealed Products"
            and (r.get("market_price") or 0) >= min_price
            and _up_30d(r)
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
        shelves = db.listings_series()
        measured = []
        for r in candidates:
            key = (r["card_id"], r.get("printing") or "Normal")
            hist = series.get(key, [])
            feats = invest_mod.features(hist) or {}
            feats.update(invest_mod.supply(shelves.get(key, []), as_of=obs))
            feats.update(invest_mod.shelf_math({**r, **feats}))
            rec = {**r, **feats,
                   "series": [(pt[0], pt[1]) for pt in invest_mod._window(hist, 90)],
                   "series_long": invest_mod.weekly_points(hist, 400)}
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
            # Offline: the most recent stored shelf per card. Same fields as the
            # live path so the detail panel renders identically.
            stored = db.latest_floors()
            for r in preliminary:
                f = stored.get((r["card_id"], r.get("printing") or "Normal"))
                if f:
                    r["floor_low"] = f.get("floor_low")
                    r["shelf_med"] = f.get("shelf_med")
                    r["copies"] = f.get("copies")
                    r["floor_language"] = f.get("language")

        # 4. Score for real (scarcity uses copies) and render.
        ranked = invest_mod.evaluate(preliminary, icfg)
        from . import digest as digest_mod
        from . import heat as heat_mod

        heat = None if getattr(args, "no_heat", False) else heat_mod.evaluate(
            heat_mod.load(cfg.path("data/market_heat.json"))
        )
        market = db.market_breadth(obs)

        # Today's ranking is kept (data/rankings) so tomorrow can show rank
        # movement and the track record can score it later.
        today = getattr(args, "today", None) or _today()
        snap = digest_mod.snapshot(ranked, obs_date=obs, market=market)
        digest_mod.save(snap, cfg.path("data"))

        from . import haro

        prev = digest_mod.previous(cfg.path("data"), obs)
        prev_ranks = (
            {f"{r['card_id']}|{r.get('printing') or 'Normal'}": r["rank"]
             for r in prev["rows"] if r.get("rank")}
            if prev else None
        )
        # The release calendar, drawn on every chart. Read from the sets table
        # the sync (or the archive) filled; nothing is hand-maintained.
        from . import releases as releases_mod
        from . import sealed as sealed_mod

        all_sets = db.sets()
        calendar = releases_mod.calendar(
            all_sets, [dict(x) for x in db.conn.execute("SELECT number, set_id FROM cards")])

        sealed_rows = sealed_mod.evaluate(
            [r for r in rows if r.get("product_type") == "Sealed Products"], series, all_sets, obs,
            shelves=shelves)
        from . import playbook as playbook_mod
        from . import track as track_mod

        pbook = playbook_mod.build(
            all_sets, [dict(x) for x in db.conn.execute("SELECT id, set_id, product_type FROM cards")],
            series, obs, calendar=calendar)
        # What is under each box: the set's singles, and the money through both.
        from . import depth as depth_mod

        depth = depth_mod.build(rows, series, all_sets, as_of=obs)
        for sr in sealed_rows:
            sr["set_depth"] = depth_mod.for_set(depth, sr.get("set_id"))
        print(f"sealed screen: {len(sealed_rows)} products")
        # The public track record, rebuilt every issue from the stored rankings,
        # and its one-sentence summary, which the page carries.
        pub_cfg = cfg.raw.get("publish") or {}
        site_url = (pub_cfg.get("site_url") or "").rstrip("/")
        report_url = (site_url + "/") if site_url else None
        track_html, track_recs = track_mod.build(cfg.path("data"), series, obs, report_url=report_url or "")
        track_sm = track_mod.summary(track_recs)
        track_sm["headline"] = track_mod.headline(track_sm)
        if track_sm["headline"]:
            print("Record: " + track_sm["headline"])
        html = haro.render(
            ranked,
            obs_date=obs,
            stats=db.stats(),
            market=market,
            plan_cfg=cfg.raw.get("plan") or {},
            today=today,
            prev_ranks=prev_ranks,
            releases=calendar,
            sealed=sealed_rows,
            playbook=pbook,
            depth=depth,
            sync_on=bool(site_url),
            record=track_sm,
            art_cache=cfg.path("data/images"),
            fetch_art=not getattr(args, "no_art_fetch", False),
        )
        out = cfg.path(args.out or cfg.report.get("output_path", "out/dashboard.html"))
        haro.write(html, out)
        (out.parent / "track-record.html").write_text(track_html, encoding="utf-8")
        (out.parent / "track.json").write_text(json.dumps(track_sm, indent=1), encoding="utf-8")
        # The front door: the same tiles, the top ten as the report draws
        # them, then the plans. The Worker adds identity when it serves it.
        from . import preview as preview_mod

        (out.parent / "preview.html").write_text(preview_mod.render(
            ranked, obs_date=obs, market=market, releases=calendar, today=today,
            record=track_sm, art_cache=cfg.path("data/images"),
            fetch_art=not getattr(args, "no_art_fetch", False)), encoding="utf-8")
        print(f"Preview   -> {out.parent / 'preview.html'}")
        print(f"\nDashboard -> {out}")

        (out.parent / "playbook.json").write_text(json.dumps(pbook.get("summary"), sort_keys=True), encoding="utf-8")

        keep = [r for r in ranked if not r.get("disqualified")]
        drop = [r for r in ranked if r.get("disqualified")]
        if cfg.report.get("write_csv", True):
            cp = out.with_suffix(".csv")
            cols = ["invest_score", "name", "set_name", "number", "rarity", "printing",
                    "market_price", "settled_price", "ask_premium_pct",
                    "change_30d", "change_90d", "consistency_pct",
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


def _today() -> str:
    from datetime import date as _d

    return _d.today().isoformat()


def cmd_publish(cfg, args) -> int:
    """Push today's report and the public preview to the Worker at marketharo.io.

    Reads what `radar invest` wrote to out/ rather than rebuilding, so what
    is served is byte-for-byte what was tested. The Worker's URL is config
    (`publish.site_url`); the shared secret is the environment's
    HARO_ADMIN_SECRET, never config. Two PUTs; nothing else leaves.
    """
    import os

    pcfg = cfg.raw.get("publish") or {}
    site = (pcfg.get("site_url") or "").rstrip("/")
    secret = os.getenv("HARO_ADMIN_SECRET")
    if not site or not secret:
        print("publish.site_url (config) and HARO_ADMIN_SECRET (environment) must both be set. Nothing published.")
        return 2
    # The report is whatever `radar invest --out` wrote (the workflow uses
    # out/index.html); the track record sits beside it.
    report = cfg.path(args.out or cfg.report.get("output_path", "out/dashboard.html"))
    pages = [("report", report), ("preview", report.parent / "preview.html")]
    for _, p in pages:
        if not p.exists():
            print(f"Missing {p} -- run `radar invest` first.")
            return 1
    if args.dry_run:
        for key, p in pages:
            print(f"Would PUT {site}/admin/{key}  ({p.stat().st_size:,} bytes)")
        return 0
    import requests

    for key, p in pages:
        r = requests.put(f"{site}/admin/{key}", data=p.read_bytes(),
                         headers={"X-Admin-Secret": secret, "Content-Type": "text/html; charset=utf-8"}, timeout=60)
        print(f"{key:<6} -> {site}/admin/{key}  ({r.status_code}, {p.stat().st_size:,} bytes)")
        if not r.ok:
            print(r.text[:300])
            return 1
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


def cmd_export(cfg, args) -> int:
    """Database -> data/history/*.ndjson, the durable append-only archive."""
    from . import archive

    db = Database(cfg.db_path)
    try:
        res = archive.export(db, cfg.path(args.root or "data"))
    finally:
        db.close()
    print(f"Archive -> {res['root']}/history/")
    print(f"  {res['points']:,} price points across {res['months']} months, "
          f"{res['cards']:,} cards")
    if res["changed"]:
        print(f"  changed: {', '.join(res['changed'][:8])}"
              + (f" (+{len(res['changed']) - 8} more)" if len(res["changed"]) > 8 else ""))
    else:
        print("  nothing changed")
    return 0


def cmd_restore(cfg, args) -> int:
    """data/history/*.ndjson -> database. Rebuilds from the archive."""
    from . import archive

    db = Database(cfg.db_path)
    try:
        res = archive.restore(db, cfg.path(args.root or "data"))
        stats = db.stats()
    finally:
        db.close()
    print(f"Restored from {res['root']}/history/ -> {cfg.db_path}")
    print(f"  {res['points']:,} price points from {res['months']} months, "
          f"{res['cards']:,} cards")
    print(f"  database now holds {stats['price_points']:,} points across "
          f"{stats['snapshot_dates']} snapshot dates")
    return 0


def cmd_validate(cfg, args) -> int:
    """Re-run the walk-forward test and record the result.

    Worth running monthly. The number to watch is not this run's rho, it is the
    difference between this run's rho and the last one's.
    """
    from . import validate as validate_mod

    db = Database(cfg.db_path)
    try:
        series = db.all_series_with_volume()
        cards = {}
        for r in db.latest_prices(db.latest_obs_date() or ""):
            cards[(r["card_id"], r["printing"])] = {
                "name": r["name"], "set_name": r["set_name"],
                "number": r["number"], "rarity": r["rarity"],
            }
        result = validate_mod.run(
            series, cards, cfg.raw.get("invest") or {},
            horizon=args.horizon,
        )
    finally:
        db.close()

    print(f"Walk-forward test, {result['horizon_days']}-day horizon, run {result['ran_at']}")
    print(f"  {result.get('universe', 0)} series in the database, "
          f"{result.get('eligible', 0)} eligible, {result.get('disqualified', 0)} screened out")
    sk = result.get("skipped") or {}
    if sk:
        print(f"  skipped: {sk.get('too_short', 0)} too short, "
              f"{sk.get('no_features', 0)} no features, {sk.get('no_forward', 0)} no forward window")
    if not result.get("eligible"):
        print(f"\n  {result.get('note') or 'Nothing to measure.'}")
        return 1

    sv = result["score_vs_forward"]
    pv = result["premium_vs_forward"]
    print(f"\n  score vs forward return   rho = {sv['spearman']}  (t = {sv['t']})")
    if pv["spearman"] is not None:
        print(f"  vs-sold vs forward return rho = {pv['spearman']}  (t = {pv['t']}, "
              f"n = {pv['n']})   negative is the expected direction")
    print(f"\n  {'':16} {'n':>4} {'mean':>8} {'median':>8} {'win':>5} {'worst':>8} {'best':>8}")
    for label, key in [("top quintile", "top_quintile"), ("all eligible", "all_eligible"),
                       ("bottom quintile", "bottom_quintile"), ("screened out", "screened_out")]:
        b = result[key]
        if not b.get("n"):
            continue
        print(f"  {label:16} {b['n']:>4} {b['mean_pct']:>7.1f}% {b['median_pct']:>7.1f}% "
              f"{b['win_rate_pct']:>4}% {b['worst_pct']:>7.1f}% {b['best_pct']:>7.1f}%")
    print(f"\n  {result['verdict']}")

    out = cfg.path(args.out or "data/validation_history.json")
    hist = validate_mod.append_history(out, result)
    print(f"\nRecorded -> {out}  ({len(hist)} run{'s' if len(hist) != 1 else ''} on file)")
    if len(hist) > 1:
        print("  history:")
        for h in hist[-6:]:
            r = (h.get("score_vs_forward") or {}).get("spearman")
            print(f"    {h.get('ran_at')}  rho = {r if r is not None else '--':>6}  "
                  f"n = {h.get('eligible', 0)}")
    return 0


def cmd_heat(cfg, args) -> int:
    """Show the attention capture, or print how to refresh it."""
    from . import heat as heat_mod

    if args.template:
        print(heat_mod.TEMPLATE)
        return 0

    raw = heat_mod.load(cfg.path(args.file or "data/market_heat.json"))
    h = heat_mod.evaluate(raw)
    if not h:
        print("No attention data. Run `radar heat --template` for how to capture it.")
        return 1

    age = f"{h['age_days']} day{'s' if h['age_days'] != 1 else ''} old"
    warn = "  <-- STALE, refresh it" if h["stale"] else ""
    print(f"Attention, captured {h['captured_at']} ({age}){warn}\n")

    for label, group in [("web search", h["web"]), ("youtube", h["youtube"])]:
        for name, s in group.items():
            if not s.get("enough"):
                print(f"  {label:11} {name:20} not enough history captured")
                continue
            print(f"  {label:11} {name:20} now {s['latest']:>3}  "
                  f"{s['pct_of_peak']:>3}% of peak ({s['peak_date']})  "
                  f"{s['vs_trough_pct']:+}% off the trough  "
                  f"quarter {s['quarter_change_pct']:+}%")

    if h.get("daily"):
        from . import heat as _h

        wins = _h.MOMENTUM_WINDOWS
        print("\n  demand momentum, same windows as the price columns:")
        print(f"    {'term':28}{'res':8}{'cov':>5}  " + "".join(f"{str(w) + 'd':>8}" for w in wins))
        for dser in h["daily"]:
            cells = "".join(
                f"{dser['windows'][f'{w}d']:+7.0f}%" if dser["windows"].get(f"{w}d") is not None
                else f"{'--':>8}"
                for w in wins
            )
            tag = "buy" if dser.get("intent") == "transactional" else "aware"
            print(f"    {dser['name'] + ' (' + tag + ')':28}"
                  f"{dser.get('resolution', ''):8}{dser['coverage_pct']:>4}%  {cells}")
        print("    blank = Google publishes no data at that resolution for that term")

    if h.get("sets"):
        print("\n  set attention (one query, so these ARE comparable to each other):")
        for st in h["sets"]:
            age = "evergreen" if st["evergreen"] else f"{st['weeks_since_peak']}w past peak"
            code = f" [{st['set_code']}]" if st.get("set_code") else ""
            print(f"    {st['name'] + code:34} {st['pct_of_peak']:>3}% of peak   "
                  f"{age:16} {st['phase']}")

    if h.get("intent"):
        print("\n  buying intent (monthly US searches):")
        for k in h["intent"]:
            if k.get("intent") == "transactional":
                print(f"    {k['keyword']:32} {k['volume']:>9,}")
        for k in h["intent"]:
            if str(k.get("intent", "")).startswith("set"):
                print(f"    {k['keyword']:32} {k['volume']:>9,}  ({k['intent']})")
        if h.get("zero_volume"):
            print(f"    no measurable volume: {', '.join(h['zero_volume'])}")

    if h["semrush"]:
        print("\n  monthly US search volume (absolute, comparable):")
        for k in h["semrush"]:
            print(f"    {k['keyword']:28} {k['volume']:>9,}")

    if h["rank_series"]:
        print("\n  TCGplayer sales rank: " +
              "  ".join(f"{r['period']} #{r['rank']}" for r in h["rank_series"]))

    if h["rising_queries"]:
        print("\n  rising searches:")
        for q, v in h["rising_queries"][:5]:
            print(f"    {v:>7.1f}  {q}")

    if h["catalysts"]:
        print("\n  catalysts the price screen cannot see:")
        for c in h["catalysts"]:
            print(f"    {c['date']}  {c['kind']:8} {c['label']}")

    print(f"\n  {h['verdict']}")
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
    r.add_argument("--no-heat", action="store_true",
                   help="leave the market-heat (search attention) panel off the page")
    r.add_argument("--today", help="override the run date (for reproducing a past issue)")
    r.add_argument("--no-art-fetch", action="store_true",
                   help="embed only card art already cached under data/images; never call the image CDN")

    pb = sub.add_parser("publish", help="push today's report and the track record to the site Worker")
    pb.add_argument("--out", help="where radar invest wrote the dashboard")
    pb.add_argument("--dry-run", action="store_true", help="show what would be published")
    r.add_argument("--date", help="observation date (YYYY-MM-DD), default = latest")
    r.add_argument("--out", help="output html path")
    r.add_argument("--top", type=int, default=25, help="rows to print to the terminal")
    r.add_argument("--entries", type=int, default=None,
                   help="how many candidates to pull a live entry price for")
    r.add_argument("--no-fetch", action="store_true",
                   help="score from what's already in the database, no API calls")

    e = sub.add_parser(
        "export", help="write the price history to data/history/*.ndjson (the durable archive)"
    )
    e.add_argument("--root", help="archive directory (default data/)")

    rs = sub.add_parser("restore", help="rebuild the database from data/history/*.ndjson")
    rs.add_argument("--root", help="archive directory (default data/)")

    v = sub.add_parser(
        "validate",
        help="re-run the walk-forward test -- does the score still separate winners?",
    )
    v.add_argument("--horizon", type=int, default=45,
                   help="rows of history to measure forward (default 45)")
    v.add_argument("--out", help="where to append the run record")

    hh = sub.add_parser("heat", help="attention outside the price data: search, YouTube, rank")
    hh.add_argument("--template", action="store_true",
                    help="print how to refresh the capture instead of showing it")
    hh.add_argument("--file", help="path to market_heat.json")

    a = sub.add_parser("run", help="sync then rebuild the hold screen (use this in cron)")
    a.add_argument("--no-history", action="store_true")
    a.add_argument("--date")
    a.add_argument("--out")
    a.add_argument("--top", type=int, default=25)
    a.add_argument("--entries", type=int, default=None)
    a.add_argument("--no-fetch", action="store_true")
    a.add_argument("--no-art-fetch", action="store_true")
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
    "export": cmd_export,
    "restore": cmd_restore,
    "validate": cmd_validate,
    "publish": cmd_publish,
    "heat": cmd_heat,
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
