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

## Snipe mode — the part that matters for buying

`market_price` from `/sets/:id/prices` is a **daily batch** figure. Measured against
live data on 2026-08-09 it was stamped **2026-08-07** — up to two days behind. Good for
spotting what's moving; useless for deciding what to buy.

`/cards/:id/prices/conditions` is fetched on demand (the response carries
`meta.cached` and an `as_of` stamp), so a cold call gives you the **Near Mint listing
floor right now** plus `sample_count` — how many copies are actually on the shelf.

```bash
python -m radar snipe        # ~60 requests, one per mover
```

Comparing the live floor against the stale batch price gives two setups:

| Setup | Looks like | Means |
|---|---|---|
| **discount** | floor **below** the recorded market | Copies listed under what the card last traded at. Straight arbitrage — unless the market price is stale-high from a spike that already reversed. |
| **squeeze** | floor **above** the recorded market, on few copies | The cheap copies are already gone and the batch price hasn't caught up. This is what a card looks like *just before* the printed price moves. |

Both can be wrong for the same reason — the market price is old. **`copies` is the honest
number on the row**: it's live, and it's what decides how much supply you'd have to clear.
Counts at or under `thin_supply` (default 12) are highlighted.

Real rows from the 2026-08-09 capture:

```
  91  GQuuuuuuX (Omega Psycommu) (C+)   $7.89 market   $20.00 floor    4 copies   squeeze
  86  Wing Gundam                       $3.56 market   $19.99 floor    1 copy     squeeze
  83  Gundam Barbatos Adapt             $9.46 market    $2.81 floor   27 copies   discount
  82  Silver Bullet                     $4.58 market    $1.20 floor   29 copies   discount
```

Snipe score is `0.55 x gap + 0.25 x scarcity + 0.20 x momentum`, all tunable under
`snipe:` in `config.yaml`. Floors are stored as a time series, so a card going
40 → 12 → 4 copies across runs is supply drying up in front of you.

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
| `python -m radar snipe` | **Live listing floors + copy counts for the movers** |
| `python -m radar backfill --range all` | One-time deep history pull (weekly, back to Apr 2025) |
| `python -m radar enrich` | Pull real sales figures for flagged cards only (1 request each) |
| `python -m radar report` | Score the latest snapshot, write dashboard + JSON + CSV |
| `python -m radar run` | `sync` then `report` — this is the cron command |
| `python -m radar run --enrich --snipe` | Full pass: sync, score, sales volume, live floors |
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
  snipe.py       live listing floors, discount vs. squeeze, snipe score
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
- **The daily batch price lags by up to 2 days**; the conditions endpoint does not. Never
  size a buy off `market_price` alone — check the floor and the copy count.
- **`total_listings` (batch) and `copies` (live) can disagree.** Wing Gundam showed 0
  listings in the batch and 1 live NM copy at $19.99 on 2026-08-09. The snipe board
  trusts the live number; the movers table uses the batch one.
- **Never commit `.env`.** It's gitignored, along with `data/` and `out/`.

## Reading the dashboard

The **Snipe board** sits at the top: live floor, shipped price, copies, gap, setup and a
direct link to the TCGplayer page. A squeeze shows its gap as a multiple (`5.6×`) rather
than a percentage, because "-462% below market" is arithmetically true and unreadable.

**"How to read this"** at the top of the page is a collapsible glossary covering both price
sources, all three detectors, both snipe setups, both scores, and what the tool can't tell
you. Every column header, badge and control also has a hover tooltip — the `?` markers are
just the ones worth pointing at.

**Time window** — a 24h / 7d / 30d selector drives the movement filter, the default ranking
and which column is highlighted, so it's always visible what the order is based on. Pair it
with *min move %* (absolute, so it catches falls too) and *Risers* / *Fallers*.

**Filters** — search, set, rarity, printing, and Cards vs. Sealed, plus value filtering
two ways: preset bands (Under $5 / $5–20 / $20–100 / $100+, multi-select) or exact
min/max boxes for an arbitrary range. Supply filters: max copies, floor-under- vs.
floor-over-market, and live-floor-only. Plus a minimum Radar Score. Signal chips narrow to
sustained / spike / breakout. Everything composes, and Reset clears it all.

The squeeze screen is: **Floor over market** + **max copies 10**.

**Charts** — "Where the movement is" ranks the sets in view; "Breakdown" toggles between
price band, rarity, and printing. Both redraw with the filters, so filtering to `R+`
immediately shows which sets those cards are in.

**The table** — click any header to sort. Starts at 50 rows with *Show 50 more* and
*Show all*; `report.top_n` in `config.yaml` sets how many rows get embedded (default
400, flagged cards first). **Export CSV** writes exactly what the current filters show.
Card names link to TCGplayer.

A watchlist table and a biggest-fallers table sit below the main list — fallers are
context, and where dips show up.

## Liquidity: listings vs. sales

`total_listings` (from `/sets/:id/cards`) tells you how many copies are *for sale* —
it's free with the sync and good enough to filter out noise. `sales_volume` and
`avg_sales_price` are actual transactions, but they only come from `/cards/:id/prices`,
one request per card. `radar enrich` spends those requests on flagged cards only
(~50–200 requests), then re-scores — recorded sales add up to 6 points to the Radar
Score. A big % move on a card with listings but zero sales is a listing artifact, not
a market; this is how you tell them apart before acting.
