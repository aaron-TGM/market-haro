# Method

How Market Haro measures, ranks, gates and validates. This is the long version; the
README says what the product is, DEPLOY.md says how to run it, ARCHITECTURE.md says where
the code lives. Everything here was measured on tcgapi.dev data for the Gundam Card Game,
and every threshold traces back to a distribution or a walk-forward test, not a preference.

The first section is October 2026's change and the evidence for it. Everything after it
describes the screen as it was built in August and September; the parts that were retired
say so.

## October 2026: ranked by how long you will hold

### Why the score was retired

The original score (value 20, liquidity 25, trend 25, stability 20, scarcity 10, over a
pool of cards up over 30 days) was walked forward across every week the archive lets the
live code score — 22 June to 7 September 2026 — with each card scored on only what was
known that day:

| Window | Weekly tests | Rank correlation with what came next | Its top 20 beat its own pool |
|---|---|---|---|
| 30 days | 12 | −0.13 (3 positive) | 3 of 12 |
| 60 days | 7 | −0.19 (1 positive) | 0 of 7 |
| 90 days | 3 | −0.11 (1 positive) | 0 of 3 |

The monthly `radar validate` of 1 October had already said INVERTED (ρ −0.32). Measured
on what copies actually sold for instead of the market price, the score was −0.20 at 30
days with 0 of 8 tests positive. Its trend component — a steady 90-day climb — was the
worst of the five: those climbs reversed. Liquidity looked anti-predictive on the market
price and neutral on sales, which is mostly a measurement effect: the market price of a
thin card moves less often.

What a reader actually lived, from the stored issues of September (the track record now
shows this on every issue): of 60 top-20 calls that carried a live entry price, bought at
that entry and sold 30 days later at the market less selling costs, **2 made money**;
the median was −22%. The $500 plan the page would have drawn on 3 September was −7% at
the market and −20% after costs a month later.

### What does predict, and at which horizon

The same walk-forward, asked a different question: across every card the archive could
score each month from October 2025, what ordered the next 3, 6 and 9 months? Monthly
splits, an English single at $10+ with 45 days of history and some sales, scored on what
was known at the split (`radar validate`, run 2026-10-08):

**3–6 months and 1 year+: the hold score.** Three facts about a card, none of them a
price trend — rarity tier (the print rate of the treatment), set age (days since its set
released; promo pools are aged from when we first priced the card), and sales a day — as
percentiles of the day's pool, averaged.

| Window | Monthly tests | ρ (positive) | Top 20, median | Field, median | Top 20 ahead | Top 20 after costs | ρ on sold prices |
|---|---|---|---|---|---|---|---|
| 90 days | 9 | +0.23 (7) | +37.6% | +6.9% | 9 of 9 | +18.4% (5 of 9 positive) | +0.22 (8) |
| 180 days | 6 | +0.29 (5) | +60.1% | +25.2% | 6 of 6 | +37.8% (6 of 6) | +0.26 (6) |
| 270 days | 3 | +0.34 (3) | +110.2% | +52.6% | 3 of 3 | +81.2% (3 of 3) | +0.24 (3) |
| 365 days | 0 | — | — | — | — | — | — |

"After costs" is bought at the market price and sold at the market less 13.25% + $0.30;
live entries can only make it worse. Two readings matter more than the headline: at 90
days even the top 20 cleared costs in only 5 of 9 months, and at 180 days it cleared them
in all 6. A three-month hold is barely long enough; six months has been. The first full
one-year window closes in October 2026.

Robustness checks, all run during the research (scripts kept out of the repo; the in-repo
test is `validate.run_horizons`):

- Within the $10–100 band alone: ρ +0.25 at 90 days (9 of 10), +0.36 at 180 (7 of 7) —
  the ordering is not "expensive cards went up".
- Rarity alone was the strongest single input in every band under $250 (above it the
  tests are too few to rank inputs); within the top rarities, set age was (ρ +0.34 at 90
  days, 10 of 10; +0.42 at 180, 7 of 7).
- Since June 2026, the stretch where the old score failed: 90-day ρ +0.14, 6 of 6 tests
  positive, top 20 +31% against +3%.
- Requiring a card to be up over 30 days — the old pool filter — cut the 90-day result
  of the top 20 from +24% to +10%; requiring it not to be down over 90 days, to +12%. So
  the pool is every English single at $10+ the gates pass.

The 3–6 month and 1 year+ views rank the same way, because nothing in the archive tells
them apart yet. They differ in the record they show and the window it is measured over.

**Under 30 days: nothing paid.** Bought at the cheapest listing (the batch's
`lowest_with_shipping`, any condition — optimistic for Near Mint) and sold 30 days later
at the market less costs, the two start dates the recorded entries allow:

| Start | Cards | Made money | 20 lowest hurdles made money | 20 strongest 7-day risers made money |
|---|---|---|---|---|
| 2026-08-10 | 219 | 16% (median −16.2%) | 10 of 20 (median +0.4%) | 1 of 20 (median −28.2%) |
| 2026-09-03 | 418 | 6% (median −20.2%) | 7 of 20 (median −12.3%) | 2 of 20 (median −33.8%) |

Momentum looked strong on the market price (+16 points over the field at 30 days in 15 of
15 weekly tests) and was a loss on buyable terms: the market price lags the listings, so a
riser's cheapest copy has already repriced above it. The one thing that helped was paying
less than the card sells for. So the under-30-days view is ordered by the break-even
hurdle, needs a sale a day (the exit has to happen inside the window), a live Near Mint
price, and real recent sales to measure against — against a lagging market price the
hurdle invents bargains.

### Costs

`radar/costs.py`. A round trip on TCGplayer costs a 10.75% commission plus 2.5% + $0.30
payment processing (eBay's card fee is within a point). So a card bought at what it sells
for needs +15.6% before selling gives the money back. Every row carries:

- **Entry** — the cheapest Near Mint English copy, shipped (live, for the top of each
  ranking).
- **Sells for** — the 14-day volume-weighted average of real sales; the market price,
  marked, when there are too few.
- **Break-even** — (entry + $0.30) / 0.8675, and the move from "sells for" it needs.

A card whose cheapest copy costs more than 30% over what it sells for is screened out: the
quoted price is not one anyone can buy at. In September the cheapest Near Mint copy of a
card over $500 sat a median 68% above its market price (n = 267 issue-rows); under $500,
within a few percent.

### Corrections to what this document said before

- **vs sold is not an edge.** The fifths table further down (+10.3% for asks 7% under
  recent sales, −4.0% for asks 9% over) measured the next 30 days of *market price*. The
  market price is built from recent sales and lags them, so a market price under the sales
  average rises toward it by construction. Against what copies sold for 30 days later the
  gap ran the wrong way (ρ −0.17, 0 of 8 tests). It stays on the page as a description and
  is no longer quoted as a return.
- **The steady climb is not a hold signal.** See the retired score above. Weeks-up is still
  shown, without colour, and "trend broke" still flags a position you hold.

### The sales figures stopped on 7 September

The daily price batch carries no sales; sales volume and the price copies sold for come
only from `/cards/:id/history`, which the pipeline called only for cards with under 45
days of history. Once the archive was deep enough, no sales figure entered it again: on 7
October not one ranked card had a settled price, and every batch row was being read as a
day with zero sales, so liquidity decayed by itself (Silver Bullet 7.8 → 3.9 a day in a
month). By early December every card would have failed "no sales in 90 days". Fixed two
ways: `ingest.refresh_sales` pulls the last month of history for every card on the page
whose sales are more than two days old (one request a card, about 500 a day of the plan's
10,000), and `invest.sales_rate` measures sales a day only over days that have figures —
unknown is not zero. Weekly history points carry a week's sales and are spread over the
week, so old and new history measure the same thing.

The "missing" issue dates of September (4, 6, 8, 11, 14, 17, 22, 23, 29) are not a
pipeline failure: issues are dated by the API's own `last_updated_at`, and the batch
refreshed every two or three days in September. It has refreshed daily since 1 October.

### What this cannot tell you

One game, thirteen months of history, and a market that rose over most of it (the field's
median was +25% at 180 days and +53% at 270 across the tests). Monthly tests with 90–270-day windows overlap, so they are not independent;
read the counts as "how often", not as a significance test. The walk-forward cannot apply
the volatility and entry-price gates before mid-2026 (no daily prices or live shelves in
the archive then), and the archive itself was drawn from cards worth $3+ when history was
backfilled, so a card that collapsed below that is missing. The 270-day row is three tests.
None of this is a forecast; `radar validate` re-runs it monthly and the page shows the
newest run.

## The screen (retired 2026-10-08)

The rest of this section describes the original score. It is kept because its record is
still on the track record page, and `radar validate --legacy` still measures it.

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

Change columns run **3d / 7d / 30d / 90d**, all sortable, and every one of them is computed
from the stored daily series rather than read off the API. Only the 90-day figure feeds the
score — the shorter windows are context.

There used to be a 1d column fed by the API's `price_change_24h`. It was removed because the
field is wrong, not empty: measured 2026-08-09 across all 1,701 Gundam products it was
non-zero on **3.2%** of rows, and on a 129-card spot check it reported `0` for **8 of the 9**
cards whose daily history had actually moved 1% or more day over day. The underlying history
moves on 37% of days. The fix was to stop trusting the field, not to drop the timeframe.

3 days rather than 1 because of how sparse daily moves are on this game (125 cards, 90 days
of daily history each):

| Window | Days with a move | Move ≥1% | Move ≥3% | Typical move |
|--------|-----------------|----------|----------|--------------|
| 1 day  | 37%             | 17%      | 6%       | 2.1% |
| 2 days | 53%             | 29%      | 13%      | 2.8% |
| 3 days | 63%             | 39%      | 20%      | 3.5% |
| 7 days | 80%             | 62%      | 39%      | 6.3% |

A 1d column is blank or 0.0% on nearly two-thirds of rows. 3d is the shortest window that
says something most of the time.

### vs sold

> **Corrected October 2026.** The table below measured the next 30 days of *market price*,
> which lags sales and closes this gap by construction. Against what copies actually sold
> for, the gap had no edge (ρ −0.17, 0 of 8 tests); see "Corrections" at the top. The column
> is gone from the rows; the gap is still described in the detail.

The **vs sold** column is the gap between the listed price and the volume-weighted average
of what copies *actually sold for* over the last 14 days. Listings are what sellers hope
for; `avg_sales_price` is what buyers agreed to. Green means buyers have been paying above
the current ask; red means sellers are ahead of the market. Blank means under three days
with a recorded sale — two transactions averaged together is not a price.

Measured across 1,201 observations of 290 Gundam cards, sorted into fifths by that gap:

| Listed vs. sold | Median next 30 days |
|-----------------|--------------------|
| ~7% below       | **+10.3%** |
| ~1% below       | +3.2% |
| level           | +1.1% |
| ~3% above       | −0.5% |
| ~9% above       | **−4.0%** |

Spearman ρ = −0.31 (t = −8.2), stable across both halves of the window (−0.32 / −0.28), and
still −0.23 after removing 30-day momentum. Stronger at 14 days (−0.38) than at 30 — the
correction lands fast.

It is deliberately **not in the score**. It is a timing read, not a quality read: a card can
be worth owning and still be listed ahead of itself, which says wait, not no. It shows in
the row, in the detail panel, and in the Watch line, and carries zero weight in the ranking.

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

## English printings only

Enforced in three places, because a Japanese copy trades in a different market and must
never become the entry price for an English card:

- the conditions endpoint is asked for `language=English`, and **every returned row is
  re-checked** — if nothing English is on the shelf the card gets no entry price rather
  than a wrong one;
- product names and set names are screened with word-boundary matching (a loose substring
  test flags "**Sai*kor*o** Gundam" as Korean and "Im*p*roved Technique" as Japanese —
  both are real cards);
- every TCGplayer link carries `?Language=English`, so the page you open is filtered the
  same way the screen is.

Measured on 2026-08-10: all 92 condition rows across a 60-card sample came back English,
and all 27 Gundam sets are English-language. So today this is a guard rather than a filter
— but it will hold if the API starts carrying Japanese product.

## Does the score actually predict anything?

A walk-forward test on the same data: score each card using **only its first 45 days** of
history, then measure the next 45 days. 117 cards cleared the gates as of the cut.

| | mean | median | win rate |
|---|---|---|---|
| Top 20% by score | +37.8% | **+44.1%** | **87%** |
| All eligible | +28.5% | +16.8% | — |
| Bottom 20% by score | +25.6% | **+5.7%** | 57% |

Spearman ρ between score and forward return = **0.238** (t = 2.62, p < 0.05).

**Read that honestly.** ρ = 0.24 is a *weak* positive correlation — the ranking tilts the
odds, it does not pick winners. Three of the top 23 still lost money (worst −11.4%), and
the best performer in the bottom quintile returned +197%. Three further caveats:

1. **The whole market rose.** Every eligible card averaged +28.5% over the window. The
   edge is relative; in a falling market this tells you nothing about absolute outcomes.
2. **Survivorship bias.** The universe was drawn from cards worth $10+ *today*, so cards
   that collapsed below $10 are missing. This inflates every number in the table.
3. **One window, one game, n=117.** Not a walk-forward across many periods.

Treat it as encouraging, not validated.

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
## New sets: `radar.setreport`

The hold screen needs 45+ days of history and a 90-day trend, so pointing it at a
six-week-old set disqualifies almost all of it as "too new" — correctly, and
uselessly. A new set has one question worth asking: **is it still repricing
downward, or has it found a floor?**

`radar/setreport.py` answers that from the post-release price path. On **GD05
Freedom Ascension** (released 2026-07-24, priced through 2026-09-03, 162 products
with 10+ post-release closes):

| | |
|---|---|
| Median off its post-release peak | **−57.0%** |
| Median since release | **−50.8%** |
| Last 7 days vs the 7 before | **−21.7%** |
| Still falling | **152 of 162** |

Graded almost perfectly by what a card was worth **at release**:

| Price at release | n | Off peak | Last 7d | Falling |
|---|---|---|---|---|
| $0–25 | 119 | **−71.1%** | **−42.9%** | 115 of 119 |
| $25–100 | 17 | −38.4% | −9.3% | 16 of 17 |
| $100–500 | 17 | −17.0% | −3.5% | 15 of 17 |
| $500+ | 9 | **−4.8%** | −0.9% | 6 of 9 |

That is a release flooding into supply. The commons and mid-rares have given up
two thirds of their value and were *still* dropping 43% in the final week, while
the LR++ chase cards barely moved. The useful part is the last column: **the fall
has not stopped**, so "it's down 70%, it must be cheap" is the wrong read — there
is no floor in the data yet.

Two details that matter:

- **Banded by opening price, not by today's price.** A card that opened at $40 and
  now sits at $8 belongs with the tier it was priced into. Band it by today's price
  and it lands in the bulk bucket — which is the group it fell *into* — and the
  gradient disappears.
- **Pre-release closes are dropped.** Several GD05 products carry preorder listings
  back to 2026-06-06; those trade on a different basis and would flatter the peak.

The attention data called this three weeks early: GD05 peaked in Google Trends on
**2026-07-19**, the week *before* release, and was at 43% of that peak by 2026-08-10.
`heat.py` said "singles from it are being bought into falling attention, not rising."
The prices followed.

## Market heat: is anyone outside this dashboard paying attention?

Price is a lagging, circular signal — a card is "rising" because people already
bought it. `radar heat` holds the part of the picture tcgapi.dev cannot see, and it
is placed above the table on purpose: it is the panel most likely to disagree with
the ranking, and a disagreement you have to go looking for is one you will not find.

**What it said on 2026-08-10, which is not what the price screen says:**

| | |
|---|---|
| Search interest, `gundam tcg` | **50 / 100** — half its launch peak (2025-07-27), +138% off the Nov-2025 low, +14% over the quarter |
| YouTube interest | **47 / 100** — 47% of peak, **−15%** over the quarter |
| TCGplayer sales rank | #8 in Q4 2025 → **#7** in Q1 2026 → **#8** in Q2 2026 |
| Newest set, GD05 Freedom Ascension | peaked **2026-07-19** (the week *before* release) and is at **43%** of that peak three weeks later |

Prices are climbing while attention sits at half its launch high and marketplace rank
has slipped back. That is not a contradiction to explain away — it is a smaller pool
of buyers bidding against each other, and it unwinds faster than it built.

### Demand momentum — the same windows as the price columns

The one genuinely *leading* number here. Price tells you a card already moved;
buying-intent search is people forming an intention before they transact. Measured on
1/3/7/14/30/60/90d so it sits alongside the price columns without mental arithmetic:

| Term | | 1d | 3d | 7d | 14d | 30d | 60d | 90d |
|---|---|---|---|---|---|---|---|---|
| `gundam booster box` | buy intent | — | — | −38% | −40% | **+83%** | **+116%** | **+121%** |
| `gundam card game` | awareness | +0% | +3% | −36% | −27% | +27% | +44% | +51% |

Buying intent is up 121% over 90 days and down 38% over 7 — that is the GD05 release
spike rolling out of the short windows, not demand leaving. Both readings are true and
they mean different things, which is why every window is shown rather than one summary.

**The blanks are the honest part.** Google only publishes daily resolution for terms
above a volume threshold, and the buy-intent terms are exactly the ones below it —
`gundam booster box` had **17 of 151 days** present at capture. Those rows fall back to
the weekly series for 7d and up, and 1d/3d stay empty because at weekly resolution they
do not exist. This is the same lesson as the price `1d` column in a different costume:
the timeframe exists, the data underneath it often does not.

### Set attention — the release-decay curve

These four terms are queried *together*, so unlike the headline index they **are**
comparable to each other:

| Set | | Now vs its own peak | Weeks past peak |
|---|---|---|---|
| Freedom Ascension | GD05 | **43%** | 3 |
| Steel Requiem | GD03 | 7% | 28 |
| Newtype Rising | GD01 | 4% | 54 |
| `gundam booster box` | evergreen | 29% | — |

Every set so far spikes the week of launch and gives most of it back inside two
quarters. Where the newest set sits on that curve is the difference between buying into
rising attention and buying the decay.

### Events the price data cannot see

Set releases and banlist updates are what actually start and end runs, and no amount of
price history anticipates them. Releases are on record, so every chart carries them
(`radar/releases.py`, from the API's own calendar) and the playbook measures what they did
(`radar/playbook.py`). Banlists are not on any API. When one lands, write it up in the
weekly note; the earlier hand-kept "catalyst" flag was retired because a flag with no
chart behind it told a reader nothing. For the record, the 2026-07-24 banlist did this in
two weeks: Amuro Ray (C+) −14%, Mikazuki Augus (Event Promo) −24%, Guntank (Championship
Pack 01) +19% — not uniform, not predictable from price.

### Where the data comes from, and why it is a file

Google Trends, Semrush and the TCGplayer seller blog are not one API with one key, and
none of them are on tcgapi.dev. Rather than pretend the CLI can fetch them,
`data/market_heat.json` is a **dated capture with the source recorded next to every
number**, and the panel greys itself out once it is more than 30 days old. Run
`radar heat --template` for the exact queries to re-run.

One trap worth repeating, because it will silently ruin the data: **query the Gundam
terms alone.** Google Trends scales to the largest term in a request, so putting
`pokemon cards` in the same query crushes every Gundam week to `1` — which is how you
would conclude the game is dead when it is at half its launch peak.

## Does the score still work? `radar validate`

The invest score was calibrated once, on one 90-day window, in a market that rose the
whole way through. If Gundam turns, those numbers quietly stop describing reality — and
a screen that was right last year and is wrong now looks exactly like a screen that is
right.

`radar validate` re-runs the walk-forward test on demand and appends a dated record to
`data/validation_history.json`, so drift is visible without digging:

```
radar validate                 # 45-day horizon, the calibration default
radar validate --horizon 30    # shorter window, more observations
```

It scores every card using **only** data up to the split point — the same
`invest.features` and `invest.evaluate` the live screen uses, no special path — then
measures what each card actually did afterwards. Reported three ways because one number
hides too much: Spearman ρ, the top-versus-bottom quintile spread, and the same test on
the `vs sold` premium. Every run also reports what the *screened-out* pile did; if the
rejects beat the candidates, the gates are the problem.

Reading it:

| | |
|---|---|
| ρ > 0.20, top quintile beats the pool | working |
| ρ near 0, quintiles overlapping | the score has stopped separating |
| ρ < 0 | inverted — stop acting on the ranking |

The seeded baseline is the original calibration run: **ρ = 0.238** (t = 2.62, n = 117),
top quintile +37.8% mean against +28.5% for all eligible. One run is one window; two
runs three months apart is a trend. Run it monthly.

## Running it on its own

See **[DEPLOY.md](DEPLOY.md)** for the full setup. The short version:

```
radar export     database  ->  data/history/YYYY-MM.ndjson    (the durable asset)
radar restore    data/history/*.ndjson  ->  database          (the cache)
```

`.github/workflows/daily.yml` runs at 13:10 UTC: restore, sync, build, export,
**test**, commit, publish. The tests run before the commit on purpose — a broken
run must not push a corrupted history. On the 1st of each month it also runs
`radar validate` and commits the result.

**The SQLite database is never committed.** SQLite rewrites pages throughout the
file on every write, so git stores a full copy of a binary it cannot delta, and a
year of daily commits would run to gigabytes against GitHub's 5 GB soft limit. The
durable artifact is NDJSON — sorted, one file per month, `None` fields omitted —
so a day's run appends ~1,700 lines and changes nothing else. Roughly **85 MB of
text a year**, and re-exporting an unchanged database is byte-identical, which is
what makes "commit only if changed" safe.

The report is pushed to the site Worker and served only to entitled sessions.
Without the admin secret the workflow still builds it and keeps it as a run artifact.

## Notes and gotchas

- **`market_price` lags by up to two days** — it comes from a daily batch. The screen uses
  it for the Value component and as a reference; the entry price is live.
- **Snapshot rows are dated by the API's `last_updated_at`, never by the fetch.** The batch
  runs behind the history feed: pulled 2026-08-12, 1,142 rows said 08-10 and 873 said 08-11,
  and not one said the 12th. Stamping them "today" appended a stale price to the *end* of a
  fresher series and manufactured a reversal — Gundam Epyon read 157.14 → 158.91 in history
  and then "dropped" to 157.14 on a day that never happened. The tail is exactly what the
  1d/3d columns and the drawdown measure, so it looked like real data. Pinned by a test.
- **`latest_prices` returns the newest row per card, not one date.** Because the batch does
  not reprice everything on the same day, filtering on a single date would silently drop
  half the game from the screen.
- **`market_price: 0` means "no market data"**, usually pre-release — not "free".
- **The API returns `price_change_24h/7d/30d`**; internally they're `change_24h/7d/30d`.
  Pinned by a test. `price_change_24h` is **not trusted** — see the 3d note above. 7d and 30d
  are used only as a coarse pre-filter before history is loaded; the displayed figures are
  computed from the daily series.
- **`avg_sales_price` is a different number from `market_price`** and the difference is the
  point. The first is realised transactions, the second is derived from listings. Days with
  `sales_volume: 0` carry no `avg_sales_price` and are skipped.
- **There is no settling-price forecast, and that was a decision.** The inputs suggested —
  sales velocity, size of the run, supply, rarity — were each tested against 90 days of daily
  history and none of them predicted the next 30 days (run size r = −0.13, velocity r = −0.15,
  run speed r = −0.06 across 47 run-ups of 25%+; the largest rarity bucket was n = 7; listing
  counts exist only as of today, so testing them against the past is lookahead bias). There
  was also nothing to settle back to: after a 25%+ run the median card was **up another 24%**
  thirty days later and 77% sat above the peak, because the whole market rose over this
  window. A model fitted here would have predicted perpetual gains. `vs sold` is what
  survived — a price copies are changing hands at, not a price they are heading to.
- **Printings are `Normal`, `Foil`, and `Holofoil`**, and they move independently — each is
  scored as its own row. The alt-art parallels are where the value sits.
- **Sealed products are excluded from the hold screen** and get their own screen instead
  (`radar/sealed.py`): no score, measured against release and the earliest price held.
- **Copy counts are Near Mint only** and can disagree with what the TCGplayer page shows if
  the page is filtered differently.
- **Google Trends indexes are self-scaled.** A series is comparable to its own history
  and to terms queried *in the same request*, never to a term queried separately.
  Semrush volumes are absolute and comparable; that is what the peer rows are for.
- **Semrush volume is a trailing 12-month average**, so it badly understates anything
  newly released. GD05 read 10-20/mo there while Google Trends had it at an all-time
  high in the same week. Use Semrush for evergreen terms and Trends for new sets.
- **`data/market_heat.json` is a manual capture, not a fetch.** It carries `captured_at`
  and a source string per block, and the dashboard greys the panel out past 30 days.
- **`radar validate` needs history on both sides of the split** — 45 points before and
  45 after by default. On a fresh database it will say so rather than report a number
  built on three cards.
- **Never commit `.env`.** It's gitignored, along with `out/`. `data/` keeps the text
  archive (`history/`, `cards.ndjson`, `sets.ndjson`, `index.ndjson`, `rankings/`,
  `notes/`, the two captured JSON files) and ignores the SQLite database and the image cache.
