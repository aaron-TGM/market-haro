# Gundam Price Radar

Tracks every product in the Gundam Card Game on TCGplayer (via [tcgapi.dev](https://tcgapi.dev))
and surfaces the ones that are actually rising — not just the ones that moved today.

One `python -m radar run` pulls the whole catalogue, stores it in SQLite, scores it,
and writes a self-contained HTML dashboard you can open from disk.

```
20 flagged of 1,685 products

  100.0  Argama                 Dual Impact       $7.75   +54.4% 24h  +438% 7d   sustained,spike,breakout
   83.0  Argama (R+)            Dual Impact      $74.15    +0.0% 24h   +72% 7d   sustained,breakout
   76.4  Zaku II                Edition Beta      $8.93    +0.0% 24h  +122% 7d   sustained,breakout
```

## Quick start

```bash
git clone <this repo> && cd gundam-price-radar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env       # then paste your tcgapi.dev key into it
python -m radar doctor     # verifies the key and every endpoint used
python -m radar run        # sync + score + dashboard
open out/dashboard.html
```

First run takes a couple of minutes (it backfills price history). After that a run is
~60 API requests and a few seconds. Your Pro plan allows 10,000/day.

## The three detectors

Percentage change alone is a bad signal — a card that goes from $0.11 to $0.33 is "up
200%" and means nothing. The radar runs three independent tests and only ranks what
survives the filters (`min_market_price`, `min_listings`).

| Signal | Fires when | Catches |
|---|---|---|
| **sustained** | up ≥8% over 7d **and** ≥15% over 30d | Real trends. Slow but honest. |
| **spike** | ≥12% in 24h, and 7d isn't already negative | Breaking meta/news. Early, noisier. |
| **breakout** | price clears its highest level from 90→7 days ago by ≥3% | A card leaving the band it traded in for months — usually what a genuine demand shift looks like before the % windows notice. |

The breakout window deliberately **excludes the last 7 days**. Comparing today to
yesterday makes every day of a climb a "new high", which is noise; comparing today to
the range the card held *before* the run is the question that matters.

Everything is tunable in `config.yaml` — thresholds, weights, price floor, watchlist.

### Score

A 0–100 blend of the three detector strengths (weights in config), plus a small bonus
for higher-priced cards and for cards with recorded sales volume. It ranks *attention*,
not conviction. Cards with no detector firing are halved so they sink below real calls.

## Commands

| Command | What it does |
|---|---|
| `python -m radar doctor` | Verify API key, game slug, and every endpoint. Run this first. |
| `python -m radar sync` | Pull catalogue + today's prices into SQLite |
| `python -m radar backfill --range all` | One-time deep history pull (weekly, back to Apr 2025) |
| `python -m radar report` | Score the latest snapshot, write dashboard + JSON + CSV |
| `python -m radar run` | `sync` then `report` — this is the cron command |
| `python -m radar stats` | What's in the local database |
| `python -m radar games` | List every game slug the API knows |

## Daily automation

```bash
crontab -e
# 8am daily
0 8 * * * /path/to/gundam-price-radar/scripts/run_daily.sh >> /tmp/radar.log 2>&1
```

## The data you accumulate is the point

`data/radar.sqlite3` is the real asset. The API gives history back to April 2025, but
only at these granularities:

| range | points | spacing |
|---|---|---|
| `month` | ~30 | daily |
| `quarter` | ~81 | daily |
| `year` | ~126 | weekly |
| `all` | ~143 | weekly (from 2025-04) |

Every daily sync you run adds a point the API can't hand you later. **Back up the
sqlite file.** Snapshots always take precedence over backfilled history for the same
date, so re-running a backfill can never overwrite what you observed.

## Layout

```
radar/
  config.py      config.yaml + .env loading
  client.py      tcgapi.dev client: retries, 429 backoff, daily-budget guard
  db.py          SQLite schema and upserts
  ingest.py      sets -> cards -> prices -> history backfill
  signals.py     the three detectors + scoring
  dashboard.py   single-file HTML output
  cli.py         command line
tests/
  test_pipeline.py   offline tests (no network)
  make_preview.py    regenerates a dashboard from a real captured snapshot
```

Run the tests with `python tests/test_pipeline.py` (or `pytest tests -q`). They cover the
API field mapping, the price-floor and listings filters, breakout maths, snapshot-beats-
history precedence, and HTML escaping — no network needed.

## Notes and gotchas

- **`market_price: 0` means "no market data"**, usually pre-release — not "free". It's
  normalised to NULL everywhere so it can't drag averages or breakout baselines down.
- **The API returns `price_change_24h/7d/30d`**; internally they're stored as
  `change_24h/7d/30d`. Verified against live data, and pinned by a test.
- **Printings are `Normal`, `Foil`, and `Holofoil`** in this game, and they move
  independently — each is scored as its own row.
- **Sealed products are tracked too** (`include_sealed: true`). Booster box movement
  often leads singles.
- **Not every TCGplayer product exists in tcgapi.dev yet.** Newer alt-art parallels can
  lag — e.g. product `707579` (Amuro Ray R+, Freedom Ascension) was missing as of
  2026-08-09, while the base `705621` printing was present. The watchlist logs a warning
  and carries on rather than failing the run.
- **Never commit `.env`.** It's gitignored, along with `data/` and `out/`.

## Reading the dashboard

Search, filter by set, and toggle the three signal chips. Click any column header to
sort. Card names link to TCGplayer. The trend sparkline mixes backfilled API history
with your own snapshots, so it gets denser the longer you run it. A watchlist table and
a biggest-fallers table sit below the main list — fallers are context, and where dips
show up.
