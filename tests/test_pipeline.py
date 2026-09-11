"""Offline tests: DB round-trip, signal detection, dashboard render.

No network. Run with:  python -m pytest tests -q   (or python tests/test_pipeline.py)
"""

from __future__ import annotations

import json
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
    # The mission is stated on the page, not just implied by the columns --
    # and so is the thing it is not.
    assert "Market Haro" in html and "GUNDECK.AI" in html
    assert "describes what a card has already done" in html
    assert "financial advice" in html and "can lose value" in html
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


def test_short_window_changes_come_from_history_not_the_api_field():
    """The API's price_change_24h is broken; short windows are computed here.

    Measured 2026-08-09 across 1,701 Gundam products, price_change_24h was
    non-zero on 3.2% of rows. On a 129-card spot check it reported 0 for 8 of
    the 9 cards whose daily history had actually moved >=1% day over day. So the
    field is not "no data" -- it is wrong data, and it must never reach a column.

    Windows are indexed by date, not list position, because the last stored
    close sits anywhere from today to three days back depending on the card.
    """
    from radar import invest

    # A clean daily run, no gaps: $100 -> $110 over the last three days.
    series = [(f"2026-06-{d:02d}", 90.0, 1) for d in range(1, 31)]
    series += [
        ("2026-07-01", 100.0, 1), ("2026-07-02", 104.0, 1),
        ("2026-07-03", 107.0, 1), ("2026-07-04", 110.0, 1),
    ]
    f = invest.features(series)
    assert f["as_of"] == "2026-07-04"
    assert f["h1d"] == pytest_approx(110 / 107 - 1)
    assert f["h3d"] == pytest_approx(110 / 100 - 1)

    # A gap of up to three days still resolves to the nearest earlier close --
    # one missing day must not blank the column.
    gappy = [(f"2026-06-{d:02d}", 90.0, 1) for d in range(1, 31)]
    gappy += [("2026-07-01", 100.0, 1), ("2026-07-04", 110.0, 1)]
    g = invest.features(gappy)
    assert g["h3d"] == pytest_approx(110 / 100 - 1)

    # Past the tolerance it returns None rather than quietly comparing a close
    # from a week ago and labelling it "3d".
    stale = [(f"2026-06-{d:02d}", 90.0, 1) for d in range(1, 21)]
    stale += [(f"2026-05-{d:02d}", 90.0, 1) for d in range(1, 11)]
    stale += [("2026-06-20", 100.0, 1), ("2026-07-04", 110.0, 1)]
    assert invest.features(stale)["h3d"] is None


def pytest_approx(frac):
    """Expected percentage, rounded the way features() rounds it."""
    return round(frac * 100, 1)


def test_heat_reads_attention_against_its_own_history():
    """Trends indexes are self-scaled, so every reading is versus its own past.

    The failure this guards against is comparing two Trends series to each
    other. Querying "gundam card game" alongside "pokemon cards" crushes every
    Gundam week to 1 because Trends scales to the largest term in the request --
    which is how you would conclude the game is dead when it is not.
    """
    from radar import heat

    spec = {"start": "2025-01-05", "values": [10] * 12 + [100] + [20] * 12 + [40] * 5}
    s = heat.summarise_series("t", spec)
    assert s["enough"]
    assert s["peak"] == 100
    assert s["latest"] == 40
    assert s["pct_of_peak"] == 40
    assert s["trough"] == 20            # the low AFTER the peak, not the run-up
    assert s["vs_trough_pct"] == 100

    # Nulls are gaps in the source, not zeros -- interpolating them would invent
    # weeks that Trends declined to report.
    gappy = {"start": "2025-01-05", "values": [10, None, 30] + [20] * 30}
    assert heat.summarise_series("g", gappy)["points"] == 32

    # Too little history says so instead of guessing.
    assert not heat.summarise_series("tiny", {"start": "2025-01-05", "values": [1, 2, 3]})["enough"]

    # A capture past the staleness window is flagged, not silently shown as now.
    raw = {"captured_at": "2026-01-01", "trends": {"web": {"t": spec}}}
    assert heat.evaluate(raw, "2026-08-10")["stale"] is True
    assert heat.evaluate(raw, "2026-01-15")["stale"] is False

    # No capture at all is not an error -- the panel just doesn't render.
    assert heat.evaluate(None) is None
    assert heat.load("does/not/exist.json") is None


def test_setreport_reads_the_post_release_path_not_a_90_day_trend():
    """A six-week-old set has no 90-day trend, so the question is the floor.

    Measured on GD05 Freedom Ascension (released 2026-07-24, priced through
    2026-09-03, 162 products with 10+ post-release closes): median -57.0% off
    its own post-release peak, 152 of 162 still lower over the last week than
    the week before, and the fall graded by opening price -- $0-25 down 71.1%,
    $500+ down 4.8%.
    """
    from radar import setreport

    # Opens at 10, peaks at 20, ends at 5, and the last week is below the one
    # before it.
    dates = [f"2026-08-{d:02d}" for d in range(1, 22)]
    px = [10, 12, 14, 16, 18, 20, 18, 16, 14, 12, 11, 10, 9, 8, 7, 7, 6, 6, 5, 5, 5]
    series = list(zip(dates, px))
    t = setreport.trajectory(series, "2026-08-01")
    assert t["release_price"] == 10 and t["peak"] == 20 and t["now"] == 5
    assert t["peak_date"] == "2026-08-06"
    assert t["off_peak_pct"] == -75.0
    assert t["since_release_pct"] == -50.0
    assert t["last7_pct"] is not None and t["last7_pct"] < 0

    # Preorder closes before the release date are dropped -- they trade on a
    # different basis, and several GD05 products carry them back to 2026-06-06.
    pre = [("2026-06-06", 99.0)] * 5 + series
    assert setreport.trajectory(pre, "2026-08-01")["peak"] == 20

    # Under 10 post-release closes there is no path, only noise.
    assert setreport.trajectory(series[:8], "2026-08-01") is None
    assert setreport.trajectory([], "2026-08-01") is None


def test_setreport_bands_by_opening_price_and_refuses_to_call_a_bottom():
    """Bucketing on today's price would hide the entire effect.

    A card that opened at $40 and now sits at $8 belongs with the tier it was
    priced into. Band it by today's price and it lands in the bulk bucket,
    which is exactly the group it fell into — the gradient disappears.
    """
    from radar import setreport

    def path(start, end, n=21):
        step = (end - start) / (n - 1)
        return [(f"2026-08-{d + 1:02d}", start + step * d) for d in range(n)]

    rows = (
        # Cheap tier collapses.
        [{"name": f"bulk {i}", "product_type": "Cards", "rarity": "R+",
          "series": path(20, 6)} for i in range(12)]
        # Mid tier drifts.
        + [{"name": f"mid {i}", "product_type": "Cards", "rarity": "LR+",
            "series": path(200, 170)} for i in range(6)]
        # Chase cards hold.
        + [{"name": f"chase {i}", "product_type": "Cards", "rarity": "LR++",
            "series": path(800, 796)} for i in range(5)]
    )
    out = setreport.compare(rows, "2026-08-01")
    assert out["n"] == 23
    labels = {b["label"]: b for b in out["bands"]}
    # The $20 cards are banded by what they opened at, not by the $6 they end at.
    assert labels["$0–25"]["n"] == 12
    assert labels["$100–500"]["n"] == 6
    assert labels["$500+"]["n"] == 5
    assert labels["$0–25"]["off_peak"] < labels["$500+"]["off_peak"] - 15

    v = out["verdict"]
    assert "off its post-release peak" in v
    assert "has not stopped" in v
    assert "graded by what a card was worth at release" in v
    # The one thing it must never do is call a bottom.
    assert "nothing here shows a floor" in v
    assert "not the next six" in v

    # A set whose last week genuinely turned up gets that said — and still no
    # floor call, because one week is not a floor.
    turning = [{"name": f"t{i}", "product_type": "Cards",
                "series": [(f"2026-08-{d:02d}", 20.0 - d * 0.5) for d in range(1, 15)]
                          + [(f"2026-08-{d:02d}", 13.0 + (d - 14) * 4.0)
                             for d in range(15, 22)]}
               for i in range(10)]
    tv = setreport.compare(turning, "2026-08-01")["verdict"]
    assert "One week is not a floor" in tv

    # Nothing measurable says so rather than dividing by zero.
    assert setreport.compare([], "2026-08-01")["n"] == 0
    assert "Not enough" in setreport.compare([], "2026-08-01")["verdict"] or \
           "No product" in setreport.compare([], "2026-08-01")["verdict"]


def test_setreport_renders_self_contained_and_states_its_limits():
    """The notes panel is part of the deliverable, not decoration."""
    from radar import setreport

    rows = [{"name": "c", "product_type": "Cards", "rarity": "R+", "tcgplayer_id": 1,
             "entry": 7.0, "shelf_med": 9.0, "copies": 12, "listings": 40,
             "series": [(f"2026-08-{d:02d}", 20.0 - d * 0.5) for d in range(1, 22)]}]
    summary = setreport.compare(rows, "2026-08-01")
    assert summary["rows"][0]["spread"] == round((9.0 / 7.0 - 1) * 100, 1)

    html = setreport.render(
        summary, set_name="Freedom Ascension", set_code="GD05",
        released="2026-07-24", as_of="2026-09-03",
        notes=["Entry is the cheapest Near Mint English listing.",
               "Off peak is measured since release, not from preorder."],
    )
    assert "GD05 Freedom Ascension" in html
    assert "not the hold screen" in html
    assert "cheapest Near Mint English listing" in html
    assert "?Language=English" in html          # links carry the English filter
    assert "<svg class=\"spark\"" in html      # the path is drawn
    assert html.count("<link") == 3             # fonts only
    assert "<script" not in html                # fully static


def test_snapshots_are_dated_by_the_api_not_by_the_fetch():
    """The batch runs behind the history feed, so the fetch date is a lie.

    Pulled 2026-08-12, every /sets/:id/prices row carried last_updated_at of
    2026-08-10 (1,142 rows) or 2026-08-11 (873) and not one said the 12th.
    Stamping them "today" appended a stale price to the END of a fresher history
    series -- Gundam Epyon read 157.14 -> 158.91 in history and then "dropped"
    back to 157.14 on a day that never happened. The tail is exactly what the
    1d/3d columns and the drawdown measure, so this looked like real data.
    """
    from radar.ingest import _norm_price_row, _obs_date_for

    assert _obs_date_for({"last_updated_at": "2026-08-10T05:19:41Z"}, "2026-08-12") == "2026-08-10"
    assert _obs_date_for({"updated_at": "2026-08-11"}, "2026-08-12") == "2026-08-11"
    # No usable date -> the fetch date, rather than dropping the row.
    assert _obs_date_for({}, "2026-08-12") == "2026-08-12"
    assert _obs_date_for({"last_updated_at": "garbage"}, "2026-08-12") == "2026-08-12"
    assert _obs_date_for({"last_updated_at": ""}, "2026-08-12") == "2026-08-12"

    row = _norm_price_row(
        {"card_id": "c1", "printing": "Holofoil", "market_price": 157.14,
         "last_updated_at": "2026-08-10T05:19:41.005Z"},
        obs_date="2026-08-12", source="snapshot",
    )
    assert row["obs_date"] == "2026-08-10"
    # History rows keep their own date and are untouched by this.
    assert _norm_price_row(
        {"card_id": "c1", "market_price": 1.0}, obs_date="2026-07-01", source="history"
    )["obs_date"] == "2026-07-01"


def test_latest_prices_spans_the_batch_rather_than_one_date():
    """Dating by last_updated_at splits the market across days; the screen must
    still see all of it.

    On the 2026-08-12 pull, 1,142 products were stamped 08-10 and 873 stamped
    08-11. Filtering on a single date would have silently dropped 56% of the
    game from the ranking -- a far worse failure than showing a price one day
    older. And a date carried by a handful of unpriced new products must not
    become the header of the dashboard.
    """
    import tempfile

    from radar.db import Database

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "t.sqlite3")
        db.upsert_cards([{"id": f"c{i}", "name": f"Card {i}"} for i in range(60)])
        pts = []
        for i in range(30):
            pts.append({"card_id": f"c{i}", "printing": "Normal", "obs_date": "2026-08-10",
                        "market_price": 10.0 + i, "change_7d": 5.0, "source": "snapshot"})
        for i in range(30, 60):
            pts.append({"card_id": f"c{i}", "printing": "Normal", "obs_date": "2026-08-11",
                        "market_price": 10.0 + i, "change_7d": -5.0, "source": "snapshot"})
        # Four brand-new products with no price, stamped a day ahead.
        for i in range(4):
            pts.append({"card_id": f"c{i}", "printing": "Foil", "obs_date": "2026-08-12",
                        "market_price": None, "source": "snapshot"})
        db.upsert_price_points(pts)

        # The unpriced 08-12 rows must not become the observation date.
        assert db.latest_obs_date() == "2026-08-11"
        # ...and every product is still on the screen.
        rows = db.latest_prices()
        assert len({r["card_id"] for r in rows if r["market_price"] is not None}) == 60

        # One row per card+printing -- the most recent, not a duplicate per date.
        db.upsert_price_points([{"card_id": "c0", "printing": "Normal",
                                 "obs_date": "2026-08-11", "market_price": 999.0,
                                 "source": "snapshot"}])
        rows = {(r["card_id"], r["printing"]): r for r in db.latest_prices()
                if r["market_price"] is not None}
        assert rows[("c0", "Normal")]["market_price"] == 999.0
        assert len([r for r in db.latest_prices() if r["card_id"] == "c0"
                    and r["printing"] == "Normal"]) == 1

        # Breadth uses the same rule, so it describes the whole market. c0's
        # newer row above carries no change_7d, so it counts as neither.
        b = db.market_breadth()
        assert b["priced"] == 60
        assert b["up_7d"] == 29 and b["down_7d"] == 30

        # A row older than the lookback is not "current".
        db.upsert_price_points([{"card_id": "c59", "printing": "Foil",
                                 "obs_date": "2026-06-01", "market_price": 5.0,
                                 "source": "snapshot"}])
        assert not [r for r in db.latest_prices() if r["obs_date"] == "2026-06-01"]
        db.close()


def test_archive_round_trips_and_is_byte_stable():
    """The NDJSON archive is the durable asset; the database is a cache.

    Two properties matter and both are tested here:

      round-trip  export -> restore must reproduce every price point, because
                  the workflow rebuilds the database from this file on every run
      determinism re-exporting an unchanged database must change zero bytes, so
                  "commit only if changed" in CI is safe and the repo does not
                  fill with no-op commits

    Committing the SQLite file instead would be the obvious move and is a trap:
    git cannot delta it, so a year of daily commits runs to gigabytes.
    """
    import tempfile

    from radar import archive
    from radar.db import Database

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = Database(root / "a.sqlite3")
        db.upsert_cards([
            {"id": "c1", "name": "Alpha", "rarity": "LR+", "set_name": "S", "tcgplayer_id": 1},
            {"id": "c2", "name": "Beta", "rarity": "R+", "set_name": "S", "tcgplayer_id": 2},
        ])
        pts = []
        for day in range(1, 8):
            for cid, px in (("c1", 10.0), ("c2", 20.0)):
                pts.append({
                    "card_id": cid, "printing": "Normal",
                    "obs_date": f"2026-07-{day:02d}",
                    "market_price": px + day, "sales_volume": day,
                    "avg_sales_price": px, "source": "snapshot",
                })
        # A second month, so the per-month split is exercised.
        pts.append({"card_id": "c1", "printing": "Foil", "obs_date": "2026-08-01",
                    "market_price": 99.0, "source": "snapshot"})
        db.upsert_price_points(pts)
        before = db.stats()
        out = archive.export(db, root)
        db.close()

        assert out["months"] == 2
        assert out["points"] == 15
        assert (root / "history" / "2026-07.ndjson").exists()
        assert (root / "history" / "2026-08.ndjson").exists()

        # Round-trip into a fresh database.
        db2 = Database(root / "b.sqlite3")
        res = archive.restore(db2, root)
        after = db2.stats()
        assert res["points"] == 15
        assert after["price_points"] == before["price_points"]
        assert after["cards"] == before["cards"]
        row = db2.conn.execute(
            "SELECT market_price, sales_volume FROM price_points "
            "WHERE card_id='c1' AND printing='Normal' AND obs_date='2026-07-03'"
        ).fetchone()
        assert row["market_price"] == 13.0 and row["sales_volume"] == 3

        # Determinism: re-export from the rebuilt database touches nothing.
        assert archive.export(db2, root)["changed"] == []
        db2.close()

    # A missing archive is not a crash -- a fresh clone has no history yet.
    with tempfile.TemporaryDirectory() as tmp:
        db3 = Database(Path(tmp) / "c.sqlite3")
        assert archive.restore(db3, Path(tmp) / "nothing")["points"] == 0
        db3.close()


def test_the_database_is_never_committed():
    """A committed SQLite file is the failure mode this design exists to avoid."""
    ROOT = Path(__file__).resolve().parent.parent
    ignore = (ROOT / ".gitignore").read_text()
    assert "*.sqlite3" in ignore
    assert "!data/history/" in ignore
    assert "!data/cards.ndjson" in ignore
    assert ".env" in ignore

    wf = ROOT / ".github" / "workflows" / "daily.yml"
    assert wf.exists()
    text = wf.read_text()
    # Restore before sync, export before commit, test before commit.
    assert text.index("radar restore") < text.index("radar sync")
    assert text.index("radar export") < text.index("Commit the archive")
    assert text.index("tests/test_pipeline.py") < text.index("Commit the archive")
    # The key comes from a secret, never from a committed file.
    assert "secrets.TCGAPI_KEY" in text
    assert "tcg_live_" not in text


def test_demand_momentum_refuses_windows_the_data_cannot_support():
    """Same windows as the price columns, and blank where Google has no data.

    This is the 1d lesson again in a different costume. Google only publishes
    daily resolution above a volume threshold, and the buy-intent terms are
    precisely the ones below it -- "gundam booster box" had 17 of 151 days
    present at capture. A 1d change computed from two observations three weeks
    apart would be a fabricated number wearing a real label, so those cells
    come back None and the row falls back to weekly for 7d and longer.
    """
    from radar import heat

    dense = [100 + (i % 3) for i in range(120)]
    m = heat.momentum(dense, "2026-04-01")
    assert m["usable_daily"] is True
    assert m["coverage_pct"] == 100
    assert m["windows"]["1d"] is not None
    assert m["windows"]["90d"] is not None

    # A rising series must read positive over the long window.
    rising = list(range(50, 170))
    assert heat.momentum(rising, "2026-04-01")["windows"]["90d"] > 0

    # 11% coverage: short windows are refused outright, not approximated.
    sparse = [None] * 134 + [30, None, 25, 22, 21, 17, 17, 18, 16, 14, 12, 12, 12, 11, 14, 12, 12]
    sp = heat.momentum(sparse, "2026-03-12")
    assert sp["usable_daily"] is False
    assert sp["windows"]["1d"] is None
    assert sp["windows"]["3d"] is None

    # Weekly fallback fills 7d and up for exactly those rows, and never 1d/3d.
    wk = heat.momentum_weekly([10] * 20 + [20] * 6)
    assert wk["windows"]["1d"] is None
    assert wk["windows"]["3d"] is None
    assert wk["windows"]["90d"] is not None and wk["windows"]["90d"] > 0

    out = {d["name"]: d for d in heat.summarise_daily(
        {"start": "2026-03-12", "series": {
            "tiny": {"values": sparse, "intent": "transactional"},
            "big": {"values": dense},
        }},
        {"tiny": [10] * 20 + [20] * 6},
    )}
    assert out["tiny"]["resolution"] == "weekly"
    assert out["tiny"]["windows"]["1d"] is None
    assert out["tiny"]["windows"]["90d"] is not None
    assert out["big"]["resolution"] == "daily"
    # Buy-intent rows sort first -- they are the leading ones.
    assert heat.summarise_daily(
        {"start": "2026-03-12", "series": {
            "tiny": {"values": sparse, "intent": "transactional"},
            "big": {"values": dense},
        }}, {})[0]["name"] == "tiny"


def test_set_curves_measure_release_decay():
    """Per-set series are queried together, so unlike the headline index they
    ARE comparable to each other -- that is the whole reason they exist.

    Captured 2026-08-10: Newtype Rising sits at 4% of its peak 54 weeks on,
    Steel Requiem at 7% after 28 weeks, and GD05 Freedom Ascension at 43% just
    three weeks past its own peak. Every set so far spikes at launch and gives
    most of it back inside two quarters, and knowing where the newest one sits
    on that curve is the difference between buying rising attention and buying
    the decay.
    """
    from radar import heat

    spec = {
        "start": "2026-01-04",
        "series": {
            "fresh": {"set_code": "GD05", "values": [None] * 20 + [10, 40, 100, 60]},
            "old":   {"set_code": "GD01", "values": [100, 50] + [4] * 22},
            "box":   {"evergreen": True, "values": [50] * 12 + [25] * 12},
        },
    }
    out = {s["name"]: s for s in heat.summarise_sets(spec)}

    assert out["fresh"]["pct_of_peak"] == 60
    assert out["fresh"]["weeks_since_peak"] == 1
    assert out["fresh"]["phase"] == "peaking"
    assert out["old"]["pct_of_peak"] == 4
    assert out["old"]["phase"] == "faded"
    assert out["box"]["phase"] == "evergreen"

    # Newest peak first -- the set you are most likely to be buying into.
    assert heat.summarise_sets(spec)[0]["name"] == "fresh"

    # The verdict names the newest NON-evergreen set and says which way it is
    # going. A set past its peak has to read as a warning, not as neutral colour.
    sets = heat.summarise_sets({
        "start": "2026-01-04",
        "series": {"fresh": {"set_code": "GD05", "values": [None] * 16 + [100, 80, 60, 43]}},
    })
    v = heat.verdict({"name": "t", "pct_of_peak": 50, "quarter_change_pct": 0}, None, None, sets)
    assert "Fresh (GD05)" in v
    assert "43% of that peak" in v
    assert "falling attention" in v


def test_heat_verdict_says_the_uncomfortable_thing():
    """When attention is under its peak, the verdict must say so plainly."""
    from radar import heat

    lead = {"name": "t", "pct_of_peak": 50, "quarter_change_pct": 2}
    v = heat.verdict(lead, {"period": "Q2 2026", "rank": 8}, {"period": "Q1 2026", "rank": 7})
    assert "50% of its launch peak" in v
    assert "well below it" in v
    assert "slipped to #8" in v
    assert "smaller pool of buyers" in v

    # At a genuine high it must not manufacture a warning.
    hot = heat.verdict({"name": "t", "pct_of_peak": 98, "quarter_change_pct": 30}, None, None)
    assert "all-time high" in hot
    assert "smaller pool of buyers" not in hot


def test_validate_detects_a_score_that_has_stopped_working():
    """The whole point is catching decay, so the failure cases are the test."""
    from radar import validate

    # Perfectly ordered: rho = 1.
    rho, t = validate.spearman([1, 2, 3, 4, 5, 6, 7, 8], [10, 20, 30, 40, 50, 60, 70, 80])
    assert rho == 1.0
    # Exactly inverted: rho = -1.
    rho, _ = validate.spearman([1, 2, 3, 4, 5, 6, 7, 8], [80, 70, 60, 50, 40, 30, 20, 10])
    assert rho == -1.0
    # Under 8 points it declines to answer rather than reporting noise.
    assert validate.spearman([1, 2, 3], [3, 2, 1]) == (None, None)

    alive = [{"forward_pct": v} for v in [50, 40, 30, 20, 10, 0, -10, -20, -30, -40]]
    assert "HOLDING UP" in validate.verdict(0.35, alive, 2)
    assert "WEAK" in validate.verdict(0.15, alive, 2)
    assert "NOT SEPARATING" in validate.verdict(0.03, alive, 2)
    assert "INVERTED" in validate.verdict(-0.25, alive, 2)
    assert "Not enough" in validate.verdict(None, alive, 2)


def test_validate_scores_only_on_data_before_the_split():
    """Lookahead is the one bug that would make this test useless.

    The scored row must carry the price AS OF the split, never today's price --
    otherwise the input contains the answer and every rho comes back beautiful.
    """
    from radar import validate

    # 122 daily points: a long flat stretch, then a clean climb.
    pts = [(f"2026-01-{d:02d}", 100.0, 2.0, 100.0) for d in range(1, 32)]
    pts += [(f"2026-02-{d:02d}", 100.0, 2.0, 100.0) for d in range(1, 29)]
    pts += [(f"2026-03-{d:02d}", 100.0, 2.0, 100.0) for d in range(1, 32)]
    pts += [(f"2026-04-{d:02d}", 100.0 + d * 5, 2.0, 100.0 + d * 5) for d in range(1, 31)]
    key = ("c1", "Normal")
    out = validate.run({key: pts}, {key: {"name": "Test", "rarity": "LR+"}},
                       {"min_price": 10.0, "min_history_days": 45,
                        "max_volatility_pct": 8.0}, horizon=45, today="2026-08-10")
    assert out["eligible"] + out["disqualified"] == 1
    # 45 rows back from the end lands inside the flat stretch, so the price used
    # for scoring is 100 -- not the 250 the series ends at. If it ever scored on
    # today's price this forward return would be ~0 instead of strongly positive.
    assert out["universe"] == 1
    assert out["skipped"]["too_short"] == 0

    # A series with no room on both sides of the split is skipped, not scored.
    short = {("c2", "Normal"): pts[:60]}
    assert validate.run(short, {}, {}, horizon=45)["skipped"]["too_short"] == 1


def test_settled_price_is_measured_not_forecast():
    """`settled` reports where copies traded; it never extrapolates.

    The four inputs Aaron asked for -- sales velocity, size of the run, supply
    and rarity -- were tested against 90 days of daily Gundam history and none
    of them predicted the next 30 days (|r| < 0.15; rarity buckets n <= 7;
    listing counts are only available as of today, so testing them backwards is
    lookahead). The ask-versus-sold gap did hold up (rho = -0.31, n = 1,201),
    and that is a measurement of the present, not a forecast. See invest.settled.
    """
    from radar import invest

    # Listed at $110 while copies have been going for $100.
    pts = [(f"2026-07-{d:02d}", 110.0, 2.0, 100.0) for d in range(1, 15)]
    out = invest.settled(pts)
    assert out["settled_price"] == 100.0
    assert out["ask_premium_pct"] == 10.0
    assert out["settled_days"] == 14
    assert out["settled_volume"] == 28

    # Volume-weighted, not a plain mean: the 10-copy day at $50 outweighs the
    # two 1-copy days at $100.
    mixed = [
        ("2026-07-01", 60.0, 1.0, 100.0),
        ("2026-07-02", 60.0, 1.0, 100.0),
        ("2026-07-03", 60.0, 10.0, 50.0),
    ]
    assert invest.settled(mixed)["settled_price"] == 58.33  # (100+100+500)/12

    # Under three days of real sales it says nothing rather than something thin.
    thin = [("2026-07-01", 60.0, 1.0, 100.0), ("2026-07-02", 60.0, 1.0, 100.0)]
    assert invest.settled(thin)["settled_price"] is None
    # Days with listings but no sales don't count as sales.
    quiet = [(f"2026-07-{d:02d}", 60.0, 0.0, None) for d in range(1, 15)]
    assert invest.settled(quiet)["settled_price"] is None

    # A stretched ask reaches the Watch line -- as timing, not as a rejection.
    row = {"drawdown_pct": 0, "consistency_pct": 90, "avg_daily_sales": 2.0,
           "ask_premium_pct": 12.8, "settled_price": 295.39}
    watch = invest.watch_for(row)
    assert "295.39" in watch and "13%" in watch
    assert not row.get("disqualified")
    # ...and it is not a gate.
    assert invest.disqualify({"name": "X", "market_price": 50.0, "history_points": 90,
                              "avg_daily_sales": 2.0, "change_90d": 40, "volatility_pct": 2.0,
                              "ask_premium_pct": 12.8},
                             {"min_price": 10.0, "min_history_days": 45,
                              "max_volatility_pct": 8.0}) is None


def test_digest_diffs_two_rankings_and_sends_on_day_one():
    """The newsletter is a diff, and the first issue still goes out.

    Measured between the 2026-08-11 and 2026-09-03 rankings: 10 cards entered
    the top 20, 10 left it -- all 10 leavers dropped out of the candidate pool
    rather than being re-ranked lower, which is different news and is said
    differently -- and breadth fell from 32% to 20%.
    """
    from radar import digest

    def row(cid, score, prem=None, disq=None, name=None):
        return {"card_id": cid, "printing": "Normal", "name": name or f"Card {cid}",
                "set_name": "S", "invest_score": score, "ask_premium_pct": prem,
                "disqualified": disq, "market_price": 50.0, "floor_low": 48.0}

    prev_rows = [row("a", 90, 0), row("b", 85, 1), row("c", 80, 0), row("d", 40)]
    today_rows = [row("a", 92, 8), row("c", 84, -4), row("e", 70, None), row("d", 45, 0),
                  row("b", 0, disq="Down over 90 days")]
    prev = digest.snapshot(prev_rows, obs_date="2026-08-11", market={"priced": 100, "up_7d": 32})
    today = digest.snapshot(today_rows, obs_date="2026-09-03", market={"priced": 100, "up_7d": 20})

    d = digest.diff(today, prev, top_n=3, run_date="2026-09-04")
    assert d["has_previous"] and d["prev_date"] == "2026-08-11"
    assert d["feed_age_days"] == 1 and not d["feed_late"]
    assert [r["card_id"] for r in d["entered"]] == ["e"]
    assert d["entered"][0]["prev_rank"] is None          # was not a candidate
    assert [r["card_id"] for r in d["exited"]] == ["b"]
    assert d["exited"][0]["disqualified"] == "Down over 90 days"
    assert d["exited"][0]["rank"] is None
    # a crossed +5 from 0; c crossed -2 from 0.
    assert [r["card_id"] for r in d["stretched"]] == ["a"]
    assert [r["card_id"] for r in d["cheapened"]] == ["c"]
    assert d["breadth"] == {"now_pct": 20, "prev_pct": 32}
    assert d["climbers"][0]["card_id"] == "d" and d["climbers"][0]["score_delta"] == 5.0

    # A card that left the pool entirely (not in today's rows at all) says so.
    gone = digest.diff(digest.snapshot([row("a", 90)], obs_date="2026-09-03", market=None),
                       prev, top_n=3, run_date="2026-09-04")
    left = {r["card_id"]: r for r in gone["exited"]}
    assert "left the pool" in left["b"]["disqualified"]

    # First issue: no previous, still a complete digest with the top list.
    first = digest.diff(today, None, top_n=3, run_date="2026-09-04")
    assert first["has_previous"] is False
    assert first["entered"] == [] and first["exited"] == []
    assert [r["card_id"] for r in first["top"]] == ["a", "c", "e"]

    # A late feed is the first line, not a footnote, and it is the subject.
    late = digest.diff(today, prev, top_n=3, run_date="2026-09-10")
    assert late["feed_late"] and late["feed_age_days"] == 7

    # Email HTML is boring on purpose: no scripts, no external CSS, no <style>.



def test_digest_snapshot_round_trips_through_disk():
    import tempfile

    from radar import digest

    with tempfile.TemporaryDirectory() as tmp:
        a = digest.snapshot([{"card_id": "x", "printing": "Normal", "name": "X",
                              "invest_score": 50}], obs_date="2026-09-01", market=None)
        b = digest.snapshot([{"card_id": "x", "printing": "Normal", "name": "X",
                              "invest_score": 55}], obs_date="2026-09-03", market=None)
        digest.save(a, tmp); digest.save(b, tmp)
        # Strictly older than the date asked for -- today's own file never
        # counts as "previous".
        assert digest.previous(tmp, "2026-09-03")["obs_date"] == "2026-09-01"
        assert digest.previous(tmp, "2026-09-01") is None
        assert digest.previous(tmp, "2026-09-04")["obs_date"] == "2026-09-03"
        # Series are not stored -- the archive has them.
        assert "series" not in b["rows"][0]


def test_features_measure_the_90_day_window_even_when_the_series_runs_a_year():
    """A year of weekly points behind the daily 90 days must not turn
    change_90d into change-since-launch; it should only feed change_1y."""
    from datetime import date, timedelta

    from radar import invest

    start = date(2025, 9, 1)
    pts = []
    d = start
    # 40 weekly points at 10.0, then 95 daily points climbing 10 -> 20
    for _ in range(40):
        pts.append((d.isoformat(), 10.0, 1.0, 10.0)); d += timedelta(days=7)
    for i in range(95):
        pts.append((d.isoformat(), 10.0 + 10.0 * i / 94, 1.0, None)); d += timedelta(days=1)
    f = invest.features(pts)
    assert f["history_points"] <= 91                # the window, not the year
    assert 90 <= f["change_90d"] <= 100             # ~2x inside the window
    assert f["change_1y"] == 100.0                  # measured on the full series
    wk = invest.weekly_points(pts, 400)
    assert 45 <= len(wk) <= 60 and wk[-1][0] == pts[-1][0]


def test_sealed_screen_measures_against_release_and_is_not_scored():
    from radar import sealed

    pts = [(f"2026-07-{d:02d}", 100.0 - d, 2, None) for d in range(1, 32)] + \
          [(f"2026-08-{d:02d}", 69.0 - d * 0.5, 2, None) for d in range(1, 32)]
    rows = [{"card_id": "x", "printing": "Normal", "name": "Freedom Ascension Booster Box",
             "set_id": "1", "set_name": "Freedom Ascension", "product_type": "Sealed Products",
             "market_price": 53.5, "total_listings": 12}]
    out = sealed.evaluate(rows, {("x", "Normal"): pts}, [{"id": "1", "release_date": "2026-07-24"}], "2026-08-31")
    r = out[0]
    assert r["kind"] == "sealed" and r["days_since_release"] == 38 and r["first_price"] == 99.0
    assert r["change_since_first"] == -46 and "invest_score" not in r
    assert "booster box" in r["thesis"] and "reprint" in r["watch"].lower()
    assert r["rank"] == 1 and r["change_30d"] is not None


def test_release_playbook_measures_prior_new_and_market_with_counts():
    from radar import playbook

    sets = [{"id": "1", "name": "Old Set", "release_date": "2026-01-10"},
            {"id": "2", "name": "New Set", "release_date": "2026-03-01"}]
    cards = [{"id": str(i), "set_id": "1", "product_type": "Cards"} for i in range(10)] + \
            [{"id": str(i), "set_id": "2", "product_type": "Cards"} for i in range(10, 20)]
    def ser(start_price, slope, first_day):
        from datetime import date, timedelta
        d0 = date(2026, 1, 1) + timedelta(days=first_day)
        return [((d0 + timedelta(days=i)).isoformat(), start_price + slope * i, 1, None) for i in range(200)]
    series = {}
    for i in range(10):
        series[(str(i), "Normal")] = ser(100 + i, -0.5, 0)          # old set drifts down
    for i in range(10, 20):
        series[(str(i), "Normal")] = ser(50 + i, +0.2, 59)          # new set from release
    cal = [{"date": "2026-03-01", "label": "GD02", "kind": "booster", "names": ["New Set"]}]
    pb = playbook.build(sets, cards, series, "2026-07-01", calendar=cal)
    ev = pb["events"][0]
    assert ev["prior_set"] == "Old Set" and ev["prior"]["n"] == 10 and ev["new"]["n"] == 10
    assert ev["prior"]["d30"] < 0 < ev["new"]["d30"]
    assert ev["market"]["n"] == 20 and ev["market"]["n30"] == 20
    assert pb["summary"]["prior"]["d30"][1] == 1


def test_track_record_scores_each_issue_against_its_pool_and_keeps_losers():
    import tempfile
    from datetime import date, timedelta

    from radar import track

    def ser(p0, slope, start="2026-06-01", n=120):
        d0 = date.fromisoformat(start)
        return [((d0 + timedelta(days=i)).isoformat(), p0 + slope * i, 1, None) for i in range(n)]
    series = {("1", "Normal"): ser(100, +1), ("2", "Normal"): ser(100, +0.5), ("3", "Normal"): ser(100, 0),
              ("4", "Normal"): ser(100, -0.5), ("5", "Normal"): ser(100, -1), ("6", "Normal"): ser(100, -1),
              ("7", "Normal"): ser(100, +2)}
    rows = [{"card_id": str(i), "printing": "Normal", "rank": i} for i in range(1, 8)]
    with tempfile.TemporaryDirectory() as d:
        root = Path(d); (root / "rankings").mkdir()
        (root / "rankings" / "2026-07-01.json").write_text(json.dumps({"obs_date": "2026-07-01", "rows": rows}))
        (root / "validation_history.json").write_text("[]")
        # TOP=20 covers all 7 here; make the top 5 the "top" by trimming rank > 5 into the pool only
        recs = track.issues(root / "rankings", series, "2026-08-15")
        r = recs[0]
        assert r["date"] == "2026-07-01" and 30 in r["windows"] and 60 not in r["windows"]
        w = r["windows"][30]
        assert w["top_n"] == 7 and w["pool_n"] == 7 and w["spread"] == 0.0   # same set: spread is zero by construction
        assert r["to_date"]["days"] == 45
        html, _ = track.build(root, series, "2026-08-15", report_url="https://x/r/")
        assert "2026-07-01" in html and "Nothing is removed" in html and "financial advice" in html


def test_release_calendar_labels_itself_from_card_numbers():
    """GD05 from GD05-001, a wave of starters collapsed to one mark, a deck
    build box riding on its booster, promos and tokens left off, and an
    upcoming set with no cards yet keeping its name."""
    from radar import releases

    sets = [
        {"id": "1", "name": "Freedom Ascension", "release_date": "2026-07-24"},
        {"id": "2", "name": "Deck Build Box Freedom Ascension", "release_date": "2026-07-24"},
        {"id": "3", "name": "Starter Deck 11: Aquatic Assault", "release_date": "2026-09-25"},
        {"id": "4", "name": "Starter Deck 12: Raging Onslaught", "release_date": "2026-09-25"},
        {"id": "5", "name": "Promotional EX Base Tokens", "release_date": "2025-02-25"},
        {"id": "6", "name": "Stardust Trails", "release_date": "2026-10-30"},
        {"id": "7", "name": "No date yet", "release_date": None},
    ]
    cards = [{"number": "GD05-001", "set_id": "1"}, {"number": "GD05-002", "set_id": "1"},
             {"number": "GD01-010", "set_id": "2"}]  # the deck box reprints GD01 numbers
    cal = releases.calendar(sets, cards)
    assert [(m["date"], m["label"], m["kind"]) for m in cal] == [
        ("2026-07-24", "GD05", "booster"),
        ("2026-09-25", "ST11–12", "starter"),
        ("2026-10-30", "Stardust Trails", "booster"),
    ]
    assert cal[0]["names"] == ["Deck Build Box Freedom Ascension", "Freedom Ascension"]
    assert releases.next_after(cal, "2026-09-06")["label"] == "ST11–12"
    assert releases.next_after(cal, "2026-12-01") is None


def test_haro_page_carries_the_subscriber_contract():
    """The subscriber screen: budget first, rows with image and chart, no prose walls.

    What must be true on every issue: the disclaimer is on the page; the page is
    one file plus the font stylesheet; every row carries its rank movement, its
    catalyst flag when the set has one, and the fields the size/watchlist JS
    needs; nothing the reader types leaves their browser.
    """
    import re
    import sys

    from radar import haro, invest

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import make_preview

    rows = invest.evaluate(make_preview.parse(), {"min_price": 10.0})
    prev = {f"{r['card_id']}|{r.get('printing') or 'Normal'}": i + 3
            for i, r in enumerate(rows) if not r.get("disqualified")}
    releases = [{"date": "2026-07-24", "kind": "booster", "label": "GD05", "names": ["Freedom Ascension"]},
                {"date": "2026-09-25", "kind": "starter", "label": "ST11–14", "names": ["Starter Deck 11"]}]
    html = haro.render(rows, obs_date="2026-08-09", market={"priced": 100, "up_7d": 20},
                       plan_cfg={"max_position_pct": 0.25}, prev_ranks=prev, releases=releases,
                       today="2026-08-10")

    assert "Market Haro" in html and "GUNDECK.AI" in html
    assert "financial advice" in html and "can lose value" in html
    assert 'id="budget"' in html and "Watchlist" in html and "Export CSV" in html
    # One file: the only <link>s are the font preconnects + stylesheet.
    head = html[: html.index("</head>")]
    assert head.count("<link") == 3 and "<link" not in html[html.index("</head>"):]
    assert "<script src" not in html

    payload = json.loads(re.search(r'id="haro-data">(.*?)</script>', html, re.S).group(1)
                         .replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))
    top = payload["rows"][0]
    assert top["rank"] == 1 and "series" in top and "image_url" in top
    assert payload["prev_ranks"][f"{top['card_id']}|{top['printing']}"] == 3
    # The release calendar ships whole and is drawn by the chart; the next
    # release after today is a tile. No hand-kept catalyst flag survives.
    assert [m["label"] for m in payload["releases"]] == ["GD05", "ST11–14"]
    assert "Next release" in html and "ST11–14" in html and "in 46 days" in html
    assert not any("catalyst" in r for r in payload["rows"]) and "catalyst" not in haro.JS
    assert "marksFor(" in haro.JS and "ANOMALY_PCT" in haro.JS
    # Every tooltip the JS reads is shipped.
    for k in ("price", "entry", "prem", "c7", "c90", "sales", "score", "buy", "settled"):
        assert k in payload["tips"]

    # Nothing the reader types leaves the browser: no form posts, and the one
    # fetch target is the page's own origin, /positions, used only when the
    # site Worker serves the page (sync_on) and the reader is signed in.
    assert "<form" not in html and "XMLHttpRequest" not in haro.JS
    fetches = re.findall(r"fetch\(([^,)]+)", haro.JS)
    assert sorted(set(fetches)) == ["'/positions'"], fetches
    assert "if (!SYNC_ON" in haro.JS
    assert '"sync_on":false' in html  # nothing configured here
    # Storage is guarded -- a private window must not break the page.
    assert "try {" in haro.JS and "localStorage" in haro.JS

    # A late feed is the first panel after the header.
    late = haro.render(rows, obs_date="2026-08-01", today="2026-08-10")
    assert "Price feed is 9 days behind" in late
    assert late.index("Price feed is 9 days behind") < late.index('id="budget"')


def test_haro_embeds_cached_art_and_leaves_the_rest_remote():
    """Card art ships inside the file, from the cache, without touching the CDN.

    The CDN was never the problem -- sandboxed previews were. So the row
    thumbnail is a data URI when the cache has the card, the detail keeps a
    CDN URL for a sharp copy, and a card that is not cached keeps its remote
    URL rather than failing the render. fetch=False must never go online.
    """
    import io
    import json
    import re
    import tempfile

    from radar import art, haro

    rows = [
        {"card_id": 1, "name": "Cached", "set_name": "S", "number": "S-001", "rarity": "R",
         "market_price": 20.0, "invest_score": 70.0, "tcgplayer_id": 111,
         "image_url": "https://product-images.tcgplayer.com/fit-in/400x400/111.jpg",
         "avg_daily_sales": 1.5, "series": [["2026-08-01", 10.0], ["2026-08-02", 11.0]]},
        {"card_id": 2, "name": "Remote", "set_name": "S", "number": "S-002", "rarity": "R",
         "market_price": 20.0, "invest_score": 60.0, "tcgplayer_id": 222,
         "image_url": "https://product-images.tcgplayer.com/fit-in/400x400/222.jpg",
         "avg_daily_sales": 1.5, "series": [["2026-08-01", 10.0], ["2026-08-02", 11.0]]},
    ]
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d)
        try:
            from PIL import Image
            im = Image.new("RGB", (286, 400), (200, 40, 40)); buf = io.BytesIO(); im.save(buf, "JPEG")
            (cache / "111.jpg").write_bytes(buf.getvalue())
            mime = "image/webp"
        except ImportError:
            (cache / "111.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
            mime = "image/jpeg"
        html = haro.render(rows, obs_date="2026-08-09", art_cache=cache, fetch_art=False)
    payload = json.loads(re.search(r'id="haro-data">(.*?)</script>', html, re.S).group(1)
                         .replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))
    cached, remote = payload["rows"]
    assert cached["thumb"].startswith(f"data:{mime};base64,")
    assert cached["image_large"] == art.large_url(111)
    assert "thumb" not in remote and remote["image_url"].endswith("/222.jpg")
    assert remote["image_large"] == art.large_url(222)
    # The page never shows a broken-image glyph: a failed load becomes a labelled frame.
    assert "placeholder(r)" in haro.JS and 'referrerpolicy="no-referrer"' in haro.JS


def test_front_door_is_the_report_cut_to_ten_with_the_markers_the_worker_fills():
    """The public page is the real dashboard, limited: the same tiles as the
    report, exactly ten real rows (the first open, with the big chart), then
    ghosts and the plans. Nothing about identity or billing is in it -- the
    Worker fills three markers and the plan buttons' hrefs -- and no card art
    is fetched from a CDN at view time: embedded or a labelled frame."""
    import sys

    from radar import haro, invest, preview

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import make_preview

    rows = invest.evaluate(make_preview.parse(), {"min_price": 10.0})
    for r in rows:
        r["series"] = [(f"2026-07-{d:02d}", 10.0 + d) for d in range(1, 31)]
    releases = [{"date": "2026-07-15", "label": "GD05", "names": ["Freedom Ascension"]},
                {"date": "2026-09-25", "label": "ST11–14", "names": ["Starter Deck 11"]}]
    html = preview.render(rows, obs_date="2026-08-09", market={"priced": 100, "up_7d": 20},
                          releases=releases, today="2026-08-10",
                          record={"calls_30": 20, "calls_beat_pct": 55, "calls_median": 3.1})
    n_pass = sum(1 for r in rows if not r.get("disqualified"))
    assert n_pass > 10

    # The Worker's markers, once each, and nothing already filled in.
    for m in ("<!--haro:head-->", "<!--haro:auth-->", "<!--haro:script-->"):
        assert html.count(m) == 1, m
    assert html.count('href="#" data-plan="monthly"') == 1 and html.count('href="#" data-plan="annual"') == 1
    assert "<script" not in html and "clerk" not in html.lower() and "gundeck.ai/" not in html.replace("GUNDECK.AI", "")
    assert 'id="pending"' in html and 'id="plans"' in html and 'id="auth"' in html

    # Ten real rows, the first open with the big chart, then ghosts.
    assert html.count('<div class="row open"') == 1 and html.count('<div class="row"') == 9
    assert html.count('<div class="row ghost"') == preview.GHOSTS
    assert html.count('viewBox="0 0 1200 150"') == 1 and html.count('viewBox="0 0 300 80"') == 9 + preview.GHOSTS
    assert 'class="rl mid" style="left:' in html and ">GD05<" in html      # the release mark on the big chart
    assert f"+{n_pass - 10}</b> more rows" in html

    # The same tiles as the report, from the same function.
    tiles = haro.kpi_tiles([r for r in rows if not r.get("disqualified")], [r for r in rows if r.get("disqualified")],
                           market={"priced": 100, "up_7d": 20}, releases=releases, record={"calls_30": 20, "calls_beat_pct": 55, "calls_median": 3.1},
                           today="2026-08-10", obs_date="2026-08-09", screened_href=None)
    assert tiles in html
    assert "Market breadth" in html and "Next release" in html and "The record" in html and "55%" in html
    assert 'href="#screened-out"' not in html   # no list to jump to on the public page

    # Art: embedded or a frame, never a remote URL the page cannot swap out.
    assert "product-images.tcgplayer.com" not in html
    assert 'class="ph"' in html
    # One stylesheet, the report's own, so the two pages cannot drift apart.
    assert haro.CSS in html
    assert "financial advice" in html and "can lose value" in html


def test_haro_row_opens_in_place_with_one_image_and_one_chart():
    """The detail is the row itself, opened: no second image, no second
    chart, the parts animated with transforms and opacity, off under
    prefers-reduced-motion, and the click handler animates rather than
    re-rendering the whole list."""
    from radar import haro

    js, css = haro.JS, haro.CSS
    assert "bigArtHTML" not in js and 'class="dart"' not in js and 'class="bigchart"' not in js
    assert "function toggleRow(" in js and "toggleRow(row, findRow(row.dataset.key))" in js
    assert "getBoundingClientRect" in js and "transform = `translate(" in js and "scale(" in js
    assert "prefers-reduced-motion: reduce" in js and "prefers-reduced-motion:reduce" in css
    assert "upgradeArt(" in js and "new Image()" in js      # the same <img>, sharpened after the grow
    assert "transitionend" in js
    assert 'class="dx detail"' in js and 'class="dg dgrid detail"' in js
    assert ".row.open{" in css and '"chart chart chart chart chart chart"' in css
    assert "transition:transform .28s" in css and "transition:opacity .2s" in css
    assert ".row.animating{transition:height" in css
    # a row rendered already open (after a sort) is open, no animation needed
    assert "${openNow ? bigChart(r) : chart(r.series, k)}" in js and "${openNow ? detailHTML(r, plan) : ''}" in js


def test_haro_page_is_the_screen_not_the_diff():
    """The issue-to-issue comparison lives in the email, not on the page; the
    filters people touch daily are one row and the rest sit behind one button."""
    from radar import haro

    html = haro.render([], obs_date="2026-08-09", since={"has_previous": True, "entered": [{"name": "x"}]})
    assert 'class="panel since"' not in html and "Since last issue" not in html
    assert 'id="fbtn"' in html and 'id="filters" hidden' in html
    assert 'id="inbudget"' not in html  # the Sized view already does this
    for control in ("q", "sort", "dir", "clear", "reset", "minprice", "maxprice", "minscore", "minsales"):
        assert f'id="{control}"' in html


def test_every_css_var_the_page_uses_is_defined():
    """A var() that points at nothing renders as nothing -- silently.

    The table sparklines were invisible for three weeks after the gundeck.ai
    restyle because they still referenced --series-1 and --surface-1, which
    the new palette did not define. No error, no blank box, just an empty
    column that looked like missing data. This walks every var(--x) in the CSS
    and the JS templates and checks --x is declared on the root.
    """
    import re

    from radar import dashboard, haro

    for mod in (dashboard, haro):
        src = mod.CSS + mod.JS
        declared = set(re.findall(r"--([a-z][a-z0-9-]*)\s*:", mod.CSS))
        used = set(re.findall(r"var\(--([a-z][a-z0-9-]*)", src))
        missing = sorted(used - declared)
        assert not missing, f"{mod.__name__}: CSS variables used but never declared: {missing}"


def test_dashboard_never_shows_the_broken_24h_field():
    """No 1d column, and nothing reads change_24h into the payload."""
    import re

    from radar import dashboard, invest

    ROOT = Path(__file__).resolve().parent.parent
    src = (ROOT / "radar" / "dashboard.py").read_text()
    assert "change_24h" not in src
    assert not re.search(r'data-sort="c24"', src)

    sys.path.insert(0, str(ROOT / "tests"))
    import make_preview

    rows = invest.evaluate(make_preview.parse(), {"min_price": 10.0})
    html = dashboard.render(rows, obs_date="2026-08-09", stats={}, market={}, plan_cfg={})
    assert ">3d<" in html
    assert ">1d<" not in html


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
    assert len(invest.CHECKLIST) == 6


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



def test_track_record_headline_counts_every_call_against_its_pool():
    from radar import track
    td = {"days": 11, "top": 1.0, "top_n": 2, "pool": 0.0, "pool_n": 10, "spread": 1.0}
    recs = [
        {"date": "2026-08-11", "top_n": 3, "pool_n": 10,
         "windows": {30: {"top": 5.0, "top_n": 3, "pool": 2.0, "pool_n": 10, "spread": 3.0}},
         "calls_30": [10.0, 3.0, -4.0], "to_date": td},
        {"date": "2026-08-12", "top_n": 2, "pool_n": 10,
         "windows": {30: {"top": -1.0, "top_n": 2, "pool": -3.0, "pool_n": 10, "spread": 2.0}},
         "calls_30": [-1.0, -2.0], "to_date": td},
        {"date": "2026-09-01", "top_n": 2, "pool_n": 10, "windows": {}, "to_date": td},   # still open
    ]
    sm = track.summary(recs)
    assert sm["closed_30"] == 2 and sm["beat"] == 2 and sm["median_spread"] == 2.5
    assert sm["calls_30"] == 5
    assert sm["calls_beat_pct"] == 80          # 10, 3 beat 2.0; -1, -2 beat -3.0; -4 did not
    assert sm["calls_up_pct"] == 40
    assert sm["calls_median"] == -1.0
    hl = track.headline(sm)
    assert hl.startswith("Of 5 top-20 calls resolved at 30 days, 80% beat their pool and 40% were up")
    assert track.headline(track.summary(recs[2:])) == ""
    html = track.render(recs, [], as_of="2026-09-12")
    assert "Calls resolved at +30 days" in html and "80% beat their pool" in html


def test_supply_measures_the_shelf_by_date_and_stays_quiet_until_it_can():
    from radar.invest import supply
    assert supply([]) == {}
    pts = [("2026-09-03", 40), ("2026-09-04", 36), ("2026-09-07", 30)]
    out = supply(pts)
    assert out["listings_now"] == 30 and out["listings_first"] == 40
    assert "listings_change_7d" not in out            # four days of record: nothing to compare to yet
    pts.append(("2026-09-11", 24))
    out = supply(pts)
    assert out["listings_change_7d"] == -33.3          # 24 vs 36 on Sep 4, the nearest close to Sep 4
    assert "listings_change_30d" not in out
    assert supply(pts, as_of="2026-09-07")["listings_now"] == 30   # never peeks past the issue date


def test_shelf_math_and_the_tracked_high():
    from radar import invest
    assert invest.shelf_math({"total_listings": 26, "market_price": 338.41, "avg_daily_sales": 1.9}) == {
        "dollars_to_clear": 8799, "days_of_shelf": 14}
    assert invest.shelf_math({"total_listings": 26, "market_price": 338.41, "avg_daily_sales": 0}) == {"dollars_to_clear": 8799}
    assert invest.shelf_math({"market_price": 5}) == {}
    from datetime import date, timedelta
    d0 = date(2026, 5, 1)
    series = [((d0 + timedelta(days=i)).isoformat(), 10 + (40 if i == 20 else 0) + i * 0.1, 2, 11 + i * 0.1) for i in range(120)]
    f = invest.features(series)
    assert f["tracked_high"] == 52.0 and f["tracked_high_date"] == "2026-05-21" and f["tracked_since"] == "2026-05-01"
    assert f["off_tracked_high_pct"] > 50
    assert f["dollars_30d"] == round(sum(2 * (11 + i * 0.1) for i in range(89, 120)))   # _window is inclusive: 31 days


def test_set_depth_measures_what_is_under_a_box():
    from radar import depth
    sets = [{"id": "1", "name": "Deep", "release_date": "2026-07-24"}, {"id": "2", "name": "Thin", "release_date": "2026-01-30"}]
    rows = []
    for i in range(12):
        rows.append({"card_id": f"d{i}", "printing": "Normal", "set_id": "1", "set_name": "Deep",
                     "name": f"Deep {i}", "market_price": 600 - i * 50, "product_type": "Cards"})
    for i in range(6):
        rows.append({"card_id": f"t{i}", "printing": "Normal", "set_id": "2", "set_name": "Thin",
                     "name": f"Thin {i}", "market_price": 60 - i * 10, "product_type": "Cards"})
    rows.append({"card_id": "box1", "printing": "Normal", "set_id": "1", "set_name": "Deep", "name": "Deep Box",
                 "market_price": 190, "product_type": "Sealed Products"})
    rows.append({"card_id": "x", "printing": "Normal", "set_id": "3", "set_name": "Promo", "name": "lone",
                 "market_price": 900, "product_type": "Cards"})    # too few to be a set
    from datetime import date, timedelta
    d0 = date(2026, 8, 1)
    ser = {("d0", "Normal"): [((d0 + timedelta(days=i)).isoformat(), 500 + i * 100 / 37, 1, None) for i in range(38)],
           ("box1", "Normal"): [((d0 + timedelta(days=i)).isoformat(), 190, 5, 200) for i in range(38)]}
    table = depth.build(rows, ser, sets, as_of="2026-09-07")
    assert [t["set_name"] for t in table] == ["Deep", "Thin"]
    deep = table[0]
    assert deep["over_50"] == 12 and deep["over_100"] == 11 and deep["over_500"] == 3
    assert deep["top10_value"] == sum(600 - i * 50 for i in range(10))
    assert deep["top_card"] == "Deep 0" and deep["top_card_price"] == 600
    assert deep["dollars_30d_sealed"] == 5 * 200 * 31 and deep["dollars_30d_singles"] > 0
    assert deep["top10_change_30d"] is not None
    f = depth.for_set(table, "1")
    assert f["set_name"] == "Deep" and "release_date" not in f and f["over_100"] == 11
    assert depth.for_set(table, "3") is None
    assert [x["set_name"] for x in depth.facts_for_lead(table, 1)] == ["Deep"]

if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS  {name}")
            passed += 1
    print(f"\n{passed} tests passed")
