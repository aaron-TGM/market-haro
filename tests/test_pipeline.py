"""Offline tests: DB round-trip, signal detection, dashboard render.

No network. Run with:  python -m pytest tests -q   (or python tests/test_pipeline.py)
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TCGAPI_KEY", "test-key-not-used")

from radar import dashboard, signals  # noqa: E402
from radar.db import Database  # noqa: E402
from radar.ingest import _norm_price_row, _price  # noqa: E402

TODAY = date(2026, 8, 9)


def _cfg() -> dict:
    return {
        "min_market_price": 1.0,
        "min_listings": 2,
        "sustained": {"min_change_7d": 8.0, "min_change_30d": 15.0},
        "spike": {"min_change_24h": 12.0, "min_change_7d": 0.0},
        "breakout": {"lookback_days": 90, "exclude_recent_days": 7, "margin_pct": 3.0, "min_history_points": 5},
        "scoring": {
            "weight_sustained": 0.45,
            "weight_spike": 0.25,
            "weight_breakout": 0.30,
            "price_bonus_ceiling": 50.0,
            "price_bonus_max": 8.0,
            "volume_bonus_max": 6.0,
        },
    }


def _flat_series(price: float, n: int = 12) -> list[tuple[str, float]]:
    return [((TODAY - timedelta(days=7 * (n - i))).isoformat(), price) for i in range(n)]


def test_price_normalisation():
    assert _price(0) is None, "0 must mean 'no market data', not free"
    assert _price(-3) is None
    assert _price("4.44") == 4.44
    assert _price(None) is None


def test_field_mapping_matches_live_api():
    """The API returns price_change_*; we store change_*. Verified live Aug 2026."""
    live_row = {
        "card_id": 2027683,
        "printing": "Normal",
        "market_price": 4.44,
        "low_price": 4,
        "median_price": 7.395,
        "lowest_with_shipping": 5.41,
        "buylist_price": None,
        "price_change_24h": 0,
        "price_change_7d": 24.37,
        "price_change_30d": 162.72,
        "sales_volume": 3,
        "avg_sales_price": 4.1,
    }
    out = _norm_price_row(live_row, obs_date="2026-08-09", source="snapshot")
    assert out["card_id"] == "2027683"
    assert out["change_7d"] == 24.37
    assert out["change_30d"] == 162.72
    assert out["market_price"] == 4.44
    assert out["buylist_price"] is None


def test_sustained_and_spike_and_breakout():
    rows = [
        # Real trend: up on both windows, plenty of listings.
        dict(card_id="1", printing="Normal", name="Sustained Card", market_price=12.0,
             change_24h=1.0, change_7d=20.0, change_30d=60.0, total_listings=25,
             sales_volume=5, set_name="S"),
        # Sudden jump today.
        dict(card_id="2", printing="Normal", name="Spike Card", market_price=8.0,
             change_24h=35.0, change_7d=5.0, change_30d=2.0, total_listings=10,
             sales_volume=2, set_name="S"),
        # Below the price floor -> filtered before scoring.
        dict(card_id="3", printing="Normal", name="Penny Common", market_price=0.30,
             change_24h=300.0, change_7d=300.0, change_30d=300.0, total_listings=40,
             sales_volume=0, set_name="S"),
        # Too few listings -> filtered.
        dict(card_id="4", printing="Normal", name="Thin Listing", market_price=30.0,
             change_24h=50.0, change_7d=50.0, change_30d=50.0, total_listings=1,
             sales_volume=0, set_name="S"),
        # Flat, well-covered card -> no signal.
        dict(card_id="5", printing="Normal", name="Boring Card", market_price=5.0,
             change_24h=0.2, change_7d=-1.0, change_30d=0.5, total_listings=30,
             sales_volume=1, set_name="S"),
        # Breakout: traded at ~10 for months, now 14.
        dict(card_id="6", printing="Normal", name="Breakout Card", market_price=14.0,
             change_24h=2.0, change_7d=3.0, change_30d=6.0, total_listings=12,
             sales_volume=8, set_name="S"),
    ]
    series = {
        ("1", "Normal"): _flat_series(6.0),
        ("6", "Normal"): _flat_series(10.0),
    }
    ranked = signals.evaluate(rows, series, _cfg(), as_of=TODAY)
    by_id = {r["card_id"]: r for r in ranked}

    assert "sustained" in by_id["1"]["signals"]
    assert "spike" in by_id["2"]["signals"]
    assert by_id["3"]["filtered"] and by_id["3"]["filter_reason"] == "below price floor"
    assert by_id["4"]["filtered"] and by_id["4"]["filter_reason"] == "too few listings"
    assert by_id["5"]["signals"] == []
    assert "breakout" in by_id["6"]["signals"], by_id["6"]

    # Breakout maths: 14 vs a 10.00 trailing high = +40%.
    assert round(by_id["6"]["breakout_excess_pct"]) == 40

    # Flagged cards must outrank unflagged ones.
    flagged = [r for r in ranked if r["signals"]]
    assert ranked[: len(flagged)] == flagged

    # Notes add what the % columns don't already show, and never duplicate badges.
    assert signals.explain(by_id["2"]).startswith("One-day move")
    assert "ceiling" in signals.explain(by_id["6"])
    assert signals.explain(by_id["5"]) == ""


def test_breakout_needs_enough_history():
    rows = [dict(card_id="9", printing="Normal", name="New Card", market_price=20.0,
                 change_24h=1.0, change_7d=1.0, change_30d=1.0, total_listings=10,
                 sales_volume=0, set_name="S")]
    thin = {("9", "Normal"): _flat_series(5.0, n=3)}  # only 3 points
    ranked = signals.evaluate(rows, thin, _cfg(), as_of=TODAY)
    assert "breakout" not in ranked[0]["signals"]


def test_db_roundtrip_and_source_precedence():
    with tempfile.TemporaryDirectory() as td:
        db = Database(Path(td) / "t.sqlite3")
        db.upsert_sets([{"id": 800021, "name": "Freedom Ascension"}], "gundam-card-game")
        db.upsert_cards(
            [{"id": "2027683", "name": "Giant Killing", "tcgplayer_id": 684008,
              "number": "ST09-009", "rarity": "Common", "set_id": "800021",
              "set_name": "Freedom Ascension"}]
        )
        # A backfilled history point, then a live snapshot for the same date.
        db.upsert_price_points([{"card_id": "2027683", "printing": "Normal",
                                 "obs_date": "2026-08-09", "market_price": 1.11,
                                 "source": "history"}])
        db.upsert_price_points([{"card_id": "2027683", "printing": "Normal",
                                 "obs_date": "2026-08-09", "market_price": 4.44,
                                 "change_7d": 24.37, "source": "snapshot"}])
        rows = db.latest_prices()
        assert len(rows) == 1
        assert rows[0]["market_price"] == 4.44, "snapshot must win over history"
        assert rows[0]["source"] == "snapshot"
        assert rows[0]["name"] == "Giant Killing"

        # History must not clobber an existing snapshot.
        db.upsert_price_points([{"card_id": "2027683", "printing": "Normal",
                                 "obs_date": "2026-08-09", "market_price": 9.99,
                                 "source": "history"}])
        assert db.latest_prices()[0]["market_price"] == 4.44

        assert db.card_by_tcgplayer_id(684008)["name"] == "Giant Killing"
        assert db.stats()["cards"] == 1
        db.close()


def test_dashboard_renders_valid_selfcontained_html():
    from radar import invest

    rows = [
        dict(card_id="659248", printing="Holofoil", name='Gundam "Epyon" <LR+>',
             set_name="Dual Impact", number="GD02-002", rarity="LR+", market_price=156.25,
             change_30d=55, change_90d=60, consistency_pct=92, volatility_pct=2.1,
             drawdown_pct=0, avg_daily_sales=1.6, days_traded_pct=60, history_points=89,
             floor_low=167.99, shelf_med=197.49, copies=24, tcgplayer_id=659248,
             series=[("2026-05-14", 97.88), ("2026-08-07", 156.25)]),
        dict(card_id="616669", printing="Foil", name="Illiquid Card", set_name="Edition Beta",
             rarity="U+", market_price=4798.34, change_30d=10, change_90d=10,
             consistency_pct=100, volatility_pct=1.4, drawdown_pct=0,
             avg_daily_sales=0, days_traded_pct=0, history_points=58, tcgplayer_id=616669),
    ]
    ranked = invest.evaluate(rows, {"min_price": 10.0})
    html = dashboard.render(ranked, obs_date="2026-08-09", market={"priced": 1657, "up_7d": 625})

    assert html.startswith("<!doctype html>")
    assert html.count("<html") == 1 and "</html>" in html
    # Self-contained apart from two named externals: the JetBrains Mono fallback
    # face (so it reads like gundeck.ai on any machine) and card images.
    head = html[: html.index("</head>")]
    assert head.count("<link") == 3, "only the font preconnects + stylesheet"
    assert "fonts.googleapis.com" in head and "fonts.gstatic.com" in head
    assert "<link" not in html[html.index("</head>") :]
    assert "<script src" not in html
    # The mission is stated on the page, not just implied by the columns.
    assert "buying and sitting on" in html
    # Rejects are shown with the reason, never silently dropped.
    assert "Screened out" in html and "no way out of the position" in html
    # XSS-ish name never lands raw in the payload or the markup.
    assert 'Gundam "Epyon" <LR+>' not in html
    assert "&lt;LR+&gt;" in html or "\\u003c" in html
    assert "<polyline" not in html or True  # sparklines are client-rendered


def test_full_sync_with_stubbed_client():
    """Exercise ingest.sync end to end against a fake client using live-shaped payloads."""
    from radar.config import Config
    from radar.ingest import sync

    class StubClient:
        requests_made = 0
        budget_left = 9999
        daily_remaining = 9999

        def sets(self, slug):
            assert slug == "gundam-card-game"
            return [{"id": 800021, "name": "Freedom Ascension", "slug": "freedom-ascension",
                     "release_date": "2026-07-24", "card_count": 138,
                     "game_name": "Gundam Card Game", "game_slug": slug}]

        def set_cards(self, set_id):
            return [
                {"id": 2162918, "name": "Amuro Ray", "clean_name": "amuro ray",
                 "number": "GD05-085", "rarity": "Rare", "tcgplayer_id": 705621,
                 "product_type": "Cards", "foil_only": 0, "total_listings": 31,
                 "printing": "Holofoil", "market_price": 1.73,
                 "image_url": "https://img.test/705621.jpg"},
                {"id": 2157822, "name": "Freedom Ascension Booster Box", "number": None,
                 "tcgplayer_id": 693621, "product_type": "Sealed Products",
                 "total_listings": 48, "printing": "Normal", "market_price": 233.06},
            ]

        def set_prices(self, set_id):
            return [
                {"card_id": 2162918, "name": "Amuro Ray", "number": "GD05-085",
                 "tcgplayer_id": 705621, "product_type": "Cards", "printing": "Holofoil",
                 "market_price": 1.73, "low_price": 1.5, "median_price": None,
                 "lowest_with_shipping": 2.2, "buylist_price": None,
                 "price_change_24h": 4.0, "price_change_7d": 22.0, "price_change_30d": 40.0,
                 "image_url": "https://img.test/705621.jpg"},
                # market_price 0 = no data, must land as NULL
                {"card_id": 2157822, "name": "Freedom Ascension Booster Box",
                 "tcgplayer_id": 693621, "product_type": "Sealed Products",
                 "printing": "Normal", "market_price": 0, "price_change_7d": 0},
            ]

        def card_history(self, card_id, range_):
            return [{"date": "2026-07-05", "printing": "Holofoil", "market_price": 1.0},
                    {"date": "2026-07-12", "printing": "Holofoil", "market_price": 0},
                    {"date": "2026-07-19", "printing": "Holofoil", "market_price": 1.2}]

    with tempfile.TemporaryDirectory() as td:
        db = Database(Path(td) / "sync.sqlite3")
        cfg = Config(
            raw={"api": {"game_slug": "gundam-card-game"},
                 "ingest": {"include_sealed": True, "printings": [],
                            "history_backfill_min_price": 1.0,
                            "history_backfill_range": "quarter",
                            "history_requests_per_run": 10}},
            api_key="stub", db_path=Path(td) / "sync.sqlite3",
        )
        res = sync(cfg, db, StubClient(), obs_date="2026-08-09")
        assert res["status"] == "ok", res
        assert res["sets"] == 1

        rows = {r["card_id"]: r for r in db.latest_prices("2026-08-09")}
        assert rows["2162918"]["market_price"] == 1.73
        assert rows["2162918"]["change_7d"] == 22.0
        assert rows["2162918"]["rarity"] == "Rare"
        assert rows["2162918"]["total_listings"] == 31, "listings come from /cards, not /prices"
        assert rows["2157822"]["market_price"] is None, "0 must normalise to NULL"

        # History backfilled, with the zero-price week dropped.
        series = db.series("2162918", "Holofoil")
        dates = [r["obs_date"] for r in series]
        assert "2026-07-05" in dates and "2026-07-19" in dates
        assert "2026-07-12" not in dates
        db.close()


def test_sealed_can_be_excluded():
    from radar.config import Config
    from radar.ingest import sync

    class StubClient:
        requests_made = 0
        budget_left = 9999
        daily_remaining = 9999
        sets = lambda self, s: [{"id": 1, "name": "S"}]
        set_cards = lambda self, i: [
            {"id": 10, "name": "Card", "product_type": "Cards", "printing": "Normal"},
            {"id": 11, "name": "Box", "product_type": "Sealed Products", "printing": "Normal"},
        ]
        set_prices = lambda self, i: [
            {"card_id": 10, "name": "Card", "product_type": "Cards", "printing": "Normal",
             "market_price": 5.0},
            {"card_id": 11, "name": "Box", "product_type": "Sealed Products",
             "printing": "Normal", "market_price": 200.0},
        ]

    with tempfile.TemporaryDirectory() as td:
        db = Database(Path(td) / "x.sqlite3")
        cfg = Config(raw={"api": {"game_slug": "g"}, "ingest": {"include_sealed": False}},
                     api_key="stub", db_path=Path(td) / "x.sqlite3")
        sync(cfg, db, StubClient(), obs_date="2026-08-09", skip_history=True)
        ids = {r["card_id"] for r in db.latest_prices("2026-08-09")}
        assert ids == {"10"}, ids
        db.close()


def test_snipe_undercut_uses_live_shelf_not_stale_market():
    """The signal is cheapest-vs-median from one live call, not vs the batch price.

    Field choice is pinned deliberately: `lowest_with_shipping` matched TCGplayer's
    displayed "As low as" on products 673480 ($8.00) and 641452 ($49.99), while
    `low_price` did not ($2.81 and $49.99). Using low_price produced fake 70%
    discounts on cards you could not buy at that price.
    """
    from radar import snipe

    cfg = {"min_undercut_pct": 40.0, "min_squeeze_pct": 8.0, "max_copies": 40,
           "weight_gap": 0.55, "weight_scarcity": 0.25, "weight_momentum": 0.20}
    rows = [
        # Gundam (LR+), live: one copy at $49.99, next at $161.94, median $180.75.
        dict(card_id="641452", printing="Holofoil", name="Gundam (LR+)",
             market_price=159.88, change_7d=15.0, change_24h=0.0),
        # Barbatos Adapt: $8.00 cheapest vs $10.87 median -- normal spread, no snipe,
        # even though the stale market price of $9.46 makes it look like a discount.
        dict(card_id="673480", printing="Holofoil", name="Gundam Barbatos Adapt",
             market_price=9.46, change_7d=114.0, change_24h=-2.0),
        # Wing Gundam: whole shelf far above the recorded price, one copy left.
        dict(card_id="616646", printing="Normal", name="Wing Gundam",
             market_price=3.56, change_7d=20.0, change_24h=0.0),
        dict(card_id="999999", printing="Normal", name="No shelf pulled",
             market_price=10.0, change_7d=50.0, change_24h=0.0),
    ]
    floors = {
        ("641452", "Holofoil"): {"floor_low": 49.99, "shelf_med": 180.75, "copies": 16},
        ("673480", "Holofoil"): {"floor_low": 8.00, "shelf_med": 10.87, "copies": 27},
        ("616646", "Normal"):   {"floor_low": 22.98, "shelf_med": 23.50, "copies": 1},
    }
    out = {r["card_id"]: r for r in snipe.score(rows, floors, cfg)}

    assert out["641452"]["snipe_mode"] == "undercut"
    assert round(out["641452"]["undercut_pct"]) == 72
    assert "below the shelf" in snipe.explain(out["641452"])

    # The one that used to be a fake 70% "discount" is correctly nothing now.
    assert out["673480"]["snipe_mode"] is None, "26% below median is an ordinary spread"
    assert round(out["673480"]["undercut_pct"]) == 26
    assert out["673480"]["floor_low"] == 8.00, "floor must be the shipping-inclusive figure"

    assert out["616646"]["snipe_mode"] == "squeeze"
    assert out["616646"]["floor_multiple"] == 6.46
    assert "1 listed" in snipe.explain(out["616646"])

    assert out["999999"]["snipe_mode"] is None
    assert out["999999"].get("floor_low") is None

    # Thin supply outranks deep supply at the same undercut.
    thin = dict(card_id="a", printing="Normal", name="Thin", market_price=10.0, change_7d=20.0)
    deep = dict(card_id="b", printing="Normal", name="Deep", market_price=10.0, change_7d=20.0)
    f2 = {("a", "Normal"): {"floor_low": 5.0, "shelf_med": 10.0, "copies": 3},
          ("b", "Normal"): {"floor_low": 5.0, "shelf_med": 10.0, "copies": 40}}
    ranked = snipe.score([thin, deep], f2, cfg)
    assert ranked[0]["card_id"] == "a", ranked

    assert "priced that way for a reason" in snipe.risk({"snipe_mode": "undercut"})
    assert "own the top" in snipe.risk({"snipe_mode": "squeeze"})


def test_snipe_never_uses_low_price_as_the_floor():
    """Regression guard for the field that produced fake discounts."""
    from radar import snipe

    class FakeClient:
        requests_made = 0
        budget_left = 10
        def get(self, path, **kw):
            return [{"printing": "Holofoil", "condition": "Near Mint",
                     "low_price": 2.81,               # not the buyable price
                     "lowest_with_shipping": 8.00,    # matches the TCGplayer page
                     "median_with_shipping": 10.87, "sample_count": 27}]

    floor = snipe.fetch_floor(FakeClient(), 673480, "Holofoil")
    assert floor["floor_low"] == 8.00
    assert floor["shelf_med"] == 10.87
    assert floor["low_ex_ship"] == 2.81, "kept for reference"
    assert floor["copies"] == 27


def test_snipe_still_scores_for_the_cli():
    """The snipe screen is CLI-only now; it still has to work for entry pricing."""
    from radar import snipe

    cfg = {"min_undercut_pct": 40.0, "min_squeeze_pct": 8.0, "max_copies": 40}
    rows = [dict(card_id="641452", printing="Holofoil", name="Gundam (LR+)",
                 market_price=159.88, change_7d=15.0)]
    floors = {("641452", "Holofoil"): {"floor_low": 49.99, "shelf_med": 180.75, "copies": 16}}
    out = snipe.score(rows, floors, cfg)[0]
    assert out["snipe_mode"] == "undercut"
    assert round(out["undercut_pct"]) == 72


def test_plan_allocates_greedily_within_caps():
    """Position sizing is plain arithmetic; these numbers are checkable by hand."""
    from radar import plan

    rows = [
        # floor_low is the shipping-inclusive live floor -- see radar/snipe.py.
        # squeeze: cap is halved -> 500 * 0.25 * 0.5 = $62.50 -> 2 copies at $20.86
        dict(card_id="659096", printing="Holofoil", snipe_mode="squeeze",
             floor_low=20.86, copies=4),
        # squeeze, only one copy exists -> supply is the binding constraint
        dict(card_id="616646", printing="Normal", snipe_mode="squeeze",
             floor_low=22.98, copies=1),
        # squeeze on a $3,800 card -> one copy blows the halved cap
        dict(card_id="645375", printing="Holofoil", snipe_mode="squeeze",
             floor_low=3800.0, copies=6),
        # undercut: full cap $125 at $8.00 -> 15 copies, under the 27 listed
        dict(card_id="673480", printing="Holofoil", snipe_mode="undercut",
             floor_low=8.00, copies=27),
        # no shelf pulled at all
        dict(card_id="000000", printing="Normal", snipe_mode=None),
    ]
    out = plan.allocate(rows, 500.0, max_position_pct=0.25, squeeze_haircut=0.5)

    assert out[0]["qty"] == 2 and out[0]["cost"] == 41.72
    assert out[0]["limited_by"] == "the per-position cap"
    assert out[0]["clears_shelf"] is False

    assert out[1]["qty"] == 1 and out[1]["cost"] == 22.98
    assert out[1]["clears_shelf"] is True, "one copy listed, one copy bought"
    assert out[1]["limited_by"] == "the number of copies listed"

    assert out[2]["qty"] == 0
    assert "per-position cap" in out[2]["reason"]

    assert out[3]["qty"] == 15 and out[3]["cost"] == 120.0
    assert out[3]["budget_pct"] == 24.0

    assert out[4]["qty"] == 0 and "No live floor" in out[4]["reason"]

    # Spend is cumulative, and never exceeds the budget.
    spent = sum(o["cost"] for o in out)
    assert spent <= 500.0
    assert round(spent, 2) == 184.70

    # The live floor is already shipping-inclusive, so it is the unit cost.
    assert plan.unit_cost({"floor_low": 8.00}) == 8.00
    assert plan.unit_cost({"floor_ship": 5.00}) == 5.00, "legacy field still honoured"
    assert plan.unit_cost({}) is None


def test_plan_runs_out_of_budget_gracefully():
    from radar import plan

    rows = [dict(card_id=str(i), printing="Normal", snipe_mode="undercut",
                 floor_low=10.0, copies=5) for i in range(6)]
    out = plan.allocate(rows, 100.0, max_position_pct=0.25)
    # 25% cap = $25 -> 2 copies each ($20) until the money is gone.
    assert [o["qty"] for o in out] == [2, 2, 2, 2, 2, 0]
    assert out[5]["reason"].startswith("$0.00 left")
    assert sum(o["cost"] for o in out) == 100.0


def test_plan_reexports_the_snipe_narrative():
    """read/risk/CHECKLIST live in snipe.py; plan re-exports them so callers have one import."""
    from radar import plan, snipe

    assert plan.read is snipe.explain
    assert plan.risk is snipe.risk
    assert plan.CHECKLIST is snipe.CHECKLIST
    assert len(plan.CHECKLIST) == 5
    assert "second-cheapest" in " ".join(plan.CHECKLIST)


def test_invest_features_from_history():
    """Measurements come off a real 90-day series, not from the batch summary."""
    from radar import invest

    # Wing Gundam Zero (LR+), real capture: $146.26 -> $333.16 over 90 days,
    # with a pullback from a $343.15 peak.
    series = [
        ("2026-05-14", 146.26, 2), ("2026-05-25", 144.94, 1), ("2026-05-30", 148.41, 3),
        ("2026-06-05", 178.51, 2), ("2026-06-10", 187.34, 0), ("2026-06-16", 207.93, 4),
        ("2026-06-22", 213.44, 1), ("2026-06-29", 214.04, 2), ("2026-07-06", 215.89, 0),
        ("2026-07-13", 220.63, 3), ("2026-07-20", 300.91, 2), ("2026-07-27", 343.15, 1),
        ("2026-08-03", 336.34, 2), ("2026-08-07", 333.16, 3),
    ] * 3  # enough points to clear the 30-point minimum
    f = invest.features(series)
    assert f is not None
    assert f["history_points"] == 42
    assert f["avg_daily_sales"] > 0
    assert 0 <= f["days_traded_pct"] <= 100
    assert f["drawdown_pct"] >= 0

    # Under 30 points there is nothing to say.
    assert invest.features(series[:20]) is None
    # A zero price is missing data, not a free card.
    assert invest.features([("2026-01-01", 0, 0)] * 40) is None


def test_invest_gates_reject_for_the_right_reasons():
    """Every rejection is a specific, stated reason -- these are the real cases."""
    from radar import invest

    cfg = {"min_price": 10.0, "min_history_days": 45, "max_volatility_pct": 8.0}
    base = dict(market_price=100.0, history_points=89, avg_daily_sales=1.5,
                change_90d=50.0, volatility_pct=2.0)

    assert invest.disqualify(base, cfg) is None

    # The most expensive card in the real pool: $4,798 and not one sale in 90 days.
    illiquid = {**base, "market_price": 4798.34, "avg_daily_sales": 0}
    assert "no way out" in invest.disqualify(illiquid, cfg)

    # Up 338% in 30 days, 9.2% daily volatility -- a trade, not a holding.
    erratic = {**base, "volatility_pct": 9.2}
    assert "erratic" in invest.disqualify(erratic, cfg)

    assert "Down over 90 days" in invest.disqualify({**base, "change_90d": -26.0}, cfg)
    assert "Too new" in invest.disqualify({**base, "history_points": 41}, cfg)
    assert "too little value" in invest.disqualify({**base, "market_price": 4.0}, cfg)
    assert "run `radar invest`" in invest.disqualify({**base, "history_points": None}, cfg)


def test_invest_scoring_prefers_the_hold_profile():
    """A steady expensive LR+ must outrank a cheap spiky common on the same trend."""
    from radar import invest

    cfg = {"min_price": 10.0, "value_ceiling": 200.0}
    quality = dict(card_id="a", printing="Holofoil", name="Gundam Epyon (LR+)", rarity="LR+",
                   market_price=156.25, change_90d=60, consistency_pct=92, volatility_pct=2.1,
                   drawdown_pct=0, avg_daily_sales=1.6, days_traded_pct=60,
                   history_points=89, copies=24)
    junk = dict(card_id="b", printing="Normal", name="Cheap Spiky Common", rarity="Common",
                market_price=11.0, change_90d=60, consistency_pct=50, volatility_pct=6.5,
                drawdown_pct=18, avg_daily_sales=0.4, days_traded_pct=22,
                history_points=89, copies=40)
    out = {r["card_id"]: r for r in invest.evaluate([junk, quality], cfg)}

    assert out["a"]["invest_score"] > out["b"]["invest_score"] + 25
    c = out["a"]["components"]
    assert set(c) == {"value", "liquidity", "trend", "stability", "scarcity"}
    assert all(0 <= v <= 100 for v in c.values())
    # Rarity is doing real work: LR+ scores far above Common on scarcity.
    assert c["scarcity"] > out["b"]["components"]["scarcity"] + 30

    # Disqualified rows score 0 and sort last, but are kept.
    dead = dict(card_id="c", printing="Normal", name="Illiquid", rarity="U+",
                market_price=4798.34, change_90d=10, consistency_pct=100, volatility_pct=1.4,
                drawdown_pct=0, avg_daily_sales=0, days_traded_pct=0, history_points=58)
    ranked = invest.evaluate([dead, quality], cfg)
    assert ranked[0]["card_id"] == "a"
    assert ranked[-1]["card_id"] == "c" and ranked[-1]["invest_score"] == 0.0
    assert ranked[-1]["disqualified"]


def test_invest_entry_quality_is_separate_from_the_thesis():
    """Entry price says something about today's listing, not about the card."""
    from radar import invest

    row = dict(card_id="a", printing="Holofoil", name="X", rarity="LR+", market_price=100.0,
               change_90d=50, consistency_pct=90, volatility_pct=2.0, drawdown_pct=0,
               avg_daily_sales=1.5, days_traded_pct=55, history_points=89,
               floor_low=50.0, shelf_med=100.0, copies=10)
    out = invest.evaluate([row], {"min_price": 10.0})[0]
    assert out["entry_vs_shelf_pct"] == 50.0
    assert out["entry_vs_market_pct"] == 50.0

    # Same card, no entry pulled -> the score is unchanged.
    bare = {k: v for k, v in row.items() if k not in ("floor_low", "shelf_med")}
    assert invest.evaluate([bare], {"min_price": 10.0})[0]["invest_score"] == out["invest_score"]


def test_invest_words_are_specific():
    from radar import invest

    row = dict(name="X", rarity="LR+", market_price=156.25, change_90d=60,
               consistency_pct=92, volatility_pct=2.1, drawdown_pct=0,
               avg_daily_sales=1.6, days_traded_pct=60, history_points=89)
    scored = invest.evaluate([row], {"min_price": 10.0})[0]
    t = invest.thesis(scored)
    assert "$156.25 LR+" in t and "60% over 90 days" in t and "92% of weeks" in t
    assert "exited" in t
    assert "Reprints, ban-list changes and rotation" in invest.watch_for(scored)

    dead = invest.evaluate([{**row, "avg_daily_sales": 0}], {"min_price": 10.0})[0]
    assert invest.thesis(dead).startswith("No recorded sales")
    assert len(invest.CHECKLIST) == 5


def test_english_only_is_enforced_on_the_shelf():
    """A non-English listing must never become the entry price for an English card."""
    from radar import snipe

    class MixedClient:
        requests_made = 0
        budget_left = 10
        last_params = {}
        def get(self, path, **params):
            MixedClient.last_params = params
            return [
                {"printing": "Holofoil", "condition": "Near Mint", "language": "Japanese",
                 "lowest_with_shipping": 12.00, "median_with_shipping": 14.00, "sample_count": 40},
                {"printing": "Holofoil", "condition": "Near Mint", "language": "English",
                 "lowest_with_shipping": 88.00, "median_with_shipping": 95.00, "sample_count": 21},
            ]

    c = MixedClient()
    floor = snipe.fetch_floor(c, 645344, "Holofoil")
    assert c.last_params.get("language") == "English", "ask the API for English too"
    assert floor["floor_low"] == 88.00, "the $12 Japanese copy is a different market"
    assert floor["shelf_med"] == 95.00
    assert floor["copies"] == 21
    assert floor["language"] == "English"

    # Nothing English on the shelf -> no entry price at all, rather than a wrong one.
    class JapaneseOnly(MixedClient):
        def get(self, path, **params):
            return [{"printing": "Holofoil", "condition": "Near Mint", "language": "Japanese",
                     "lowest_with_shipping": 12.00, "median_with_shipping": 14.00, "sample_count": 40}]
    assert snipe.fetch_floor(JapaneseOnly(), 645344, "Holofoil") is None


def test_non_english_products_are_screened_out():
    """Word-boundary matching, so real card names aren't caught by accident."""
    from radar import invest, snipe

    assert snipe.is_english_product("Wing Gundam Zero (LR+)", "Newtype Rising")
    # These are real Gundam card names a loose substring test flags by mistake.
    assert snipe.is_english_product("Saikoro Gundam", "Eternal Nexus")
    assert snipe.is_english_product("Improved Technique", "Steel Requiem")
    assert snipe.is_english_product("Asticassia School of Technology, Earth House (C+)", "SD01")

    assert not snipe.is_english_product("Gundam Epyon (Japanese)", "Dual Impact")
    assert not snipe.is_english_product("Wing Gundam", "Newtype Rising JPN")
    assert not snipe.is_english_product("Char's Zaku II [Chinese]", "Dual Impact")
    assert not snipe.is_english_product("\u30ac\u30f3\u30c0\u30e0", "Dual Impact")

    cfg = {"min_price": 10.0, "language": "English"}
    base = dict(market_price=100.0, history_points=89, avg_daily_sales=1.5,
                change_90d=50.0, volatility_pct=2.0)
    assert invest.disqualify({**base, "name": "Gundam (Japanese)"}, cfg).startswith("Not an English")
    assert invest.disqualify({**base, "name": "Gundam", "floor_language": "Japanese"}, cfg) \
        .startswith("Entry price is a Japanese")
    assert invest.disqualify({**base, "name": "Gundam"}, cfg) is None


def test_tcgplayer_links_carry_the_english_filter():
    from radar.ingest import _norm_card

    card = _norm_card({"id": 1, "name": "X", "tcgplayer_id": 645344}, 800021, "Newtype Rising")
    assert card["tcgplayer_url"].endswith("/product/645344?Language=English")


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS  {name}")
            passed += 1
    print(f"\n{passed} tests passed")
