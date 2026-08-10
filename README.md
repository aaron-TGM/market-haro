# Gundam Hold Screen

Finds Gundam Card Game singles that **already have value, have been climbing for months
rather than days, and sell often enough to get out of**. Built for buying and sitting on
— not for flipping.

One `python -m radar run` pulls the catalogue, measures 90 days of daily price and sales
history per candidate, scores them, and writes a self-contained HTML dashboard.

```
30 candidates, 7 screened out

  89.3  Gundam Epyon (LR+)            LR+   $156.25   90d  +60%   wk  92%   1.6 sales/day
  88.4  Freedom Gundam (LR+)          LR+   $ 66.64   90d  +85%   wk  92%   2.0 sales/day
  87.5  Wing Gundam Zero (LR+)        LR+   $333.16   90d +128%   wk  83%   1.8 sales/day
     --  Overflowing Affection (U+)   $4,798 — no recorded sales in 90 days, no way out
     --  Sayla Mass (STWP 01)         +531% over 90d — too erratic to sit on
```

## Quick start

```bash
git clone <this repo> && cd gundam-price-radar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env       # paste your tcgapi.dev key
python -m radar doctor     # verify the key and every endpoint
python -m radar run        # sync, measure, score, build the dashboard
open out/dashboard.html
```

The first run pulls 90 days of history for every candidate (~250 requests) and live entry
prices for the top 40. After that it's a few dozen requests a day. Your Pro plan allows
10,000.

## The screen

Five components, each 0–100, then weighted:

| Component | Weight | What it measures |
|---|---|---|
| **Liquidity** | 0.25 | Average daily sales and the share of days with any sale. The component that decides whether you can get out. |
| **Trend** | 0.25 | Share of weeks closing above the previous week, plus the 90-day change. Weekly closes, so one bad day isn't a reversal. |
| **Value** | 0.20 | Log-scaled price. $10 scores 0, $200 scores 100. A 50% move on a $3 card isn't an investment outcome. |
| **Stability** | 0.20 | Daily volatility and distance below the 90-day high. A card that triples then halves is not a hold. |
| **Scarcity** | 0.10 | Rarity tier and copies listed. The +/++ parallels are printed at a fraction of the base rate. |

### Thresholds come from the distribution, not from taste

Measured across 212 Gundam singles at $10+ that were up over 30 days (2026-08-09, 90 days
of daily history each):

| | min | Q1 | median | Q3 | max |
|---|---|---|---|---|---|
| weeks closing up | 8% | 50% | 67% | 92% | 100% |
| daily volatility | 0% | 1.1% | 1.9% | 3.1% | 84.9% |
| average daily sales | 0 | 0.6 | 1.3 | 1.8 | 16 |
| days with a sale | 0% | 29% | 47% | 57% | 89% |
| drawdown from 90-day high | 0% | 0% | 0% | 4.9% | 57.8% |

The component curves are anchored to those quartiles, so a high score means "top quarter
of this actual market", not "above a number that sounded good".

### What gets thrown out, and why

60 of those 212 failed a gate. Every one is listed on the dashboard with its reason:

| Gate | Failed | Example |
|---|---|---|
| No recorded sales in 90 days | 11 | **Overflowing Affection (U+) Foil, $4,798** — the most expensive card in the pool has not sold once |
| Down over 90 days | 39 | Aegis Gundam (LR+): +26% over 30d, **−26% over 90d** |
| Too erratic (>8% daily) | 8 | Sayla Mass (STWP 01): **+531% over 90d at 9.2% daily volatility** |
| Under 45 days of history | 2 | New promo tokens — a release, not a trend |

That third row is the point of the whole rebuild: a momentum screen puts Sayla Mass at
number one. A hold screen throws it out.

## Commands

| Command | What it does |
|---|---|
| `python -m radar doctor` | Verify API key, game slug, and every endpoint. Run this first. |
| `python -m radar sync` | Pull the catalogue and today's prices into SQLite |
| `python -m radar invest` | Measure, score, and build the dashboard |
| `python -m radar invest --no-fetch` | Re-score from the database with zero API calls |
| `python -m radar run` | `sync` then `invest` — this is the cron command |
| `python -m radar snipe` | Entry-price tool: live listing floors and copy counts |
| `python -m radar backfill --range all` | Deep history pull (weekly, back to Apr 2025) |
| `python -m radar stats` | What's in the local database |

## Reading the dashboard

Every row is a candidate that cleared all five gates. **Click any row** and it opens four
panels: the case in plain English, the score broken into its five components, the live
entry price today, and a before-you-buy checklist. The **Screened out** panel at the
bottom lists everything that failed and why — nothing is silently dropped.

Enter a **budget** at the top and each row gets a position: copies, cost, what limited it,
and — because this is a hold — *how many days it takes to sell that many at the card's own
sales rate*.

Filters: search, set, rarity, price band, minimum score, and **minimum sales/day** (set it
to 1.0 to keep only what you can exit reasonably quickly).

## Styling

The dashboard matches **gundeck.ai**. The palette is lifted straight from the live site's
`:root` tokens (oklch, unchanged), along with the type treatment — TRT Terminal Mono with a
JetBrains Mono fallback, uppercase letter-spaced labels, 2px radii — and the corner-bracket
panel frame. Dark only, because gundeck.ai is.

```
--bg        oklch(6.5% .008 220)     --accent   oklch(78% .18 65)   amber
--surface   oklch(9%   .01  220)     --up       oklch(68% .18 145)  green
--text      oklch(94%  .04  85)      --down     oklch(60% .22 25)   red
--border    oklch(20%  .04  65)      --cyan     oklch(72% .16 200)
```

One accessibility note on the brand palette: the site's green and red sit at **CVD ΔE 6.8
(deuteranopia)** against the card surface — close enough that a red-green colourblind
viewer may not separate them by hue. Every delta on this page therefore carries an explicit
`+`/`−` sign, so direction is never communicated by colour alone. (Amber vs. green is worse
at ΔE 2.7, which is why amber is used only for chrome and accents here, never as a data
series alongside green.)

## What this can't tell you

Every number describes what a card has **already done**. Nothing here is a forecast, and
nothing knows *why* a price is moving. Bans, reprints, rotation and tournament results are
what actually end a run, and none of them are visible in price data. A steady 90-day climb
is not a promise of a 91st day.

## Appendix: the entry-price tool (`radar snipe`)

Once a card has earned a place on the screen, this answers "what does one cost right now".

**Which field is the floor** — `/cards/:id/prices/conditions` returns both `low_price` and
`lowest_with_shipping`, and only one matches reality:

| Card | `low_price` | `lowest_with_shipping` | TCGplayer page |
|---|---|---|---|
| Gundam Barbatos Adapt (673480) | $2.81 | **$8.00** | "As low as $8.00" |
| Gundam (LR+) (641452) | $49.99 | **$49.99** | "As low as $49.99", next copy $161.94 |

`lowest_with_shipping` matched the site exactly on both. **`low_price` is not the buyable
price and is never used for a signal** — an earlier version of this tool did use it and
produced fake 70% discounts on cards you could not buy at that price.

`radar snipe` also flags when the cheapest copy sits ≥40% below the *median* copy on the
same shelf (both from the same live call). On a hold candidate that's a good entry; on its
own it is not a reason to buy anything.

## Daily automation

```bash
crontab -e
0 8 * * * /path/to/gundam-price-radar/scripts/run_daily.sh >> /tmp/radar.log 2>&1
```

## The data you accumulate is the point

`data/radar.sqlite3` is the real asset. The API gives history at these granularities:

| range | points | spacing |
|---|---|---|
| `month` | ~30 | daily |
| `quarter` | ~81 | daily |
| `year` | ~126 | weekly |
| `all` | ~143 | weekly (from 2025-04) |

The screen runs on `quarter` (daily, with sales volume). Every daily sync adds a point the
API can't hand you later. **Back up the sqlite file.** Snapshots always take precedence
over backfilled history for the same date.

## Layout

```
radar/
  config.py      config.yaml + .env loading
  client.py      tcgapi.dev client: retries, 429 backoff, daily-budget guard
  db.py          SQLite schema and upserts
  ingest.py      sets -> cards -> prices -> history backfill
  invest.py      the hold screen: features, gates, five-component score
  snipe.py       live listing floors -- entry pricing
  signals.py     short-term movement detectors (kept for the snipe tool)
  plan.py        budget -> position sizing (JS twin lives in dashboard.py)
  dashboard.py   single-file HTML output
  cli.py         command line
tests/
  test_pipeline.py   19 offline tests, no network
  make_preview.py    rebuilds the dashboard from a real captured snapshot
```

`python tests/test_pipeline.py` runs everything offline. Coverage includes the API field
mapping, the floor-field regression, every disqualifier, the score ordering, position
sizing, and HTML escaping.

## Notes and gotchas

- **`market_price` lags by up to two days** — it comes from a daily batch. The screen uses
  it for the Value component and as a reference; the entry price is live.
- **`market_price: 0` means "no market data"**, usually pre-release — not "free".
- **The API returns `price_change_24h/7d/30d`**; internally they're `change_24h/7d/30d`.
  Pinned by a test.
- **Printings are `Normal`, `Foil`, and `Holofoil`**, and they move independently — each is
  scored as its own row. The alt-art parallels are where the value sits.
- **Sealed products are excluded from the hold screen** (`include_sealed` still governs the
  sync). Sealed is a different thesis with different mechanics.
- **Copy counts are Near Mint only** and can disagree with what the TCGplayer page shows if
  the page is filtered differently.
- **Never commit `.env`.** It's gitignored, along with `data/` and `out/`.
