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
    rows = [
        dict(card_id="1", printing="Normal", name='Amuro "Ray" <R+>', set_name="Freedom Ascension",
             number="FA-101", rarity="Rare", market_price=41.5, change_24h=3.0,
             change_7d=18.0, change_30d=42.0, total_listings=14, sales_volume=9,
             tcgplayer_id=707579, image_url="https://example.test/x.jpg"),
        dict(card_id="2", printing="Holofoil", name="Giant Killing", set_name="Destiny Ignition",
             number="ST09-009", rarity="Common", market_price=4.44, change_24h=0.0,
             change_7d=24.37, change_30d=162.72, total_listings=20, sales_volume=0,
             tcgplayer_id=684008, image_url=None),
    ]
    series = {("1", "Normal"): _flat_series(30.0), ("2", "Holofoil"): _flat_series(2.0)}
    ranked = signals.evaluate(rows, series, _cfg(), as_of=TODAY)
    html = dashboard.render(
        ranked,
        obs_date="2026-08-09",
        stats={"cards": 1683, "snapshot_dates": 3},
        top_n=10,
        fallers=[],
        watchlist=ranked[:1],
    )
    assert html.startswith("<!doctype html>")
    assert html.count("<html") == 1 and "</html>" in html
    # Self-contained: no external css/js.
    assert "<link" not in html and "src=\"http" not in html.replace('src="https://example.test', "")
    # XSS-ish name is escaped in the payload and the static table.
    assert 'Amuro "Ray" <R+>' not in html
    assert "&lt;R+&gt;" in html or "\\u003c" in html
    # Sparkline SVG rendered server-side for the watchlist table.
    assert "<polyline" in html
    # Signals surfaced.
    assert "sustained" in html
    return html




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


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS  {name}")
            passed += 1
    print(f"\n{passed} tests passed")
