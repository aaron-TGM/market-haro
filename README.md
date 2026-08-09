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

### Which field is the floor

`/cards/:id/prices/conditions` returns both `low_price` and `lowest_with_shipping`.
They are not two views of the same number, and only one of them matches reality:

| Card | `low_price` | `lowest_with_shipping` | TCGplayer page says |
|---|---|---|---|
| Gundam Barbatos Adapt (673480) | $2.81 | **$8.00** | "As low as $8.00", 26 listings |
| Gundam (LR+) (641452) | $49.99 | **$49.99** | "As low as $49.99", next copy $161.94 |

`lowest_with_shipping` matched the site exactly on both. **`low_price` is not the
buyable price and is never used for a signal** — an earlier version of this tool did use
it and produced fake 70% "discounts" on cards you could not buy at that price.

### What the signal is

`market_price` comes from a daily batch and runs up to two days behind. Anything measured
against it is partly measuring the two feeds being out of step. The comparison that holds
up is **cheapest listing vs. median listing**, because both come from the same live call
at the same instant:

| Setup | Looks like | Means |
|---|---|---|
| **undercut** | cheapest copy ≥40% below the **median** copy | One listing is out of line with its neighbours, right now. Gundam (LR+): $49.99 with the next copy at $161.94. |
| **squeeze** | the whole shelf sits above the recorded batch price, on thin supply | The cheap copies are gone and the batch price hasn't caught up. |

Median undercut across the game is about 20% and a quarter of cards clear 25%, so the
40% default sits well out in the tail.

```bash
python -m radar snipe        # ~60 requests, one per mover
```

**Neither setup is a forecast.** An undercut says a listing is mispriced relative to its
neighbours; a squeeze says the recorded price is behind the shelf. Neither says the card
will be worth more tomorrow, and neither knows *why* anything is moving. `copies` is the
most honest number on the row — it is live, and it decides how much supply you would have
to clear.

Real rows from the 2026-08-09 capture:

```
  85  Resource (R-002) (C+)      $6.29 cheapest   $31.47 median    8 copies   undercut  -80%
  82  McGillis Fareed (C+)       $6.72 cheapest   $19.99 median    3 copies   undercut  -66%
  81  Shenlong Gundam (R+)      $49.99 cheapest  $134.36 median   10 copies   undercut  -63%
  86  Wing Gundam               $22.98 shelf     $3.56 recorded    1 copy     squeeze   6.5x
```

Snipe score is `0.55 × gap + 0.25 × scarcity + 0.20 × momentum`, all tunable under
`snipe:` in `config.yaml`. Shelves are stored as a time series, so a card going
40 → 12 → 4 copies across runs is supply drying up in front of you.

## Budget and position sizing

Enter a budget at the top of the dashboard and every row gets a suggested position.
The rules, in full:

```
unit cost    = lowest Near Mint listing WITH shipping (the number you actually pay)
position cap = budget x max_position_pct   (25% default; halved for a squeeze)
quantity     = min(copies listed, cap / unit, remaining budget / unit)
order        = the snipe board first, then whatever else is in view
```

Funded rows get a green edge and a `buy N · $X` pill. **Click any row** and it expands
into four panels: what the row says in plain English, the position at your budget (copies,
cost, % of budget, what limited it, whether it clears the shelf, budget left after), why it
ranked where it did (which detectors fired and how strongly), and a before-you-buy
checklist with the failure mode specific to that setup.

Greedy allocation in rank order is deliberate: it's transparent, it never silently
reallocates away from the row you're reading, and every line can be checked by hand.
`max_position_pct`, `squeeze_haircut` and `fee_pct` live under `plan:` in `config.yaml` —
set `fee_pct` to see break-even resale prices.

This is arithmetic on your inputs and the live floor. It has no view on whether a card is
worth owning and no idea why the price is moving.

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
  plan.py        budget -> position sizing (JS twin lives in dashboard.py)
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
- **`total_listings` (batch) and `copies` (live) can disagree**, and the live count can
  also disagree with what the TCGplayer page shows if the page is filtered differently.
  Trust the live count, but check the page before acting.
- **`low_price` from the conditions endpoint is not the buyable price** — see the table
  above. Only `lowest_with_shipping` matched the site.
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
