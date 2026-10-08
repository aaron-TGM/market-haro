# Market Haro — from GUNDECK.AI

A daily market dashboard for people who invest in the Gundam Card Game. Every morning it
measures the whole English market on tcgapi.dev, ranks the singles worth holding for the
length of hold the reader picks, prices what each card costs to buy and to sell again,
screens sealed product, shows what is under every box, marks every chart with the set
calendar, and scores its own past calls in public — after costs. No newsletter, no written
commentary beyond a one-line case per card: the numbers are the product and the reader
draws the conclusion.

One paid tier: **$8 a month or $88 a year, 7-day trial, no free tier** — a standalone subscription, signed in with a GUNDECK.AI account (free). GUNDECK itself is a separate product on the same account; each is offered once, briefly, after checkout of the other. The report is
served by one Cloudflare Worker to signed-in GUNDECK users with the subscription; identity
is Clerk's and billing is Stripe's, both gundeck.ai's own (the .io is a Clerk satellite
domain, so nothing on gundeck.ai's DNS changes). DEPLOY.md has the setup.

```
Prices through 2026-10-07 · 381 cards pass the screen · held 3–6 months

  #1  Wing Gundam Zero (LR+)         sells for $313.79  break-even +15%  2.2 sales/day  14 mo  hold 83
  #2  Gundam (GD01-001) (LR+)        sells for  $64.23  break-even +16%  2.1 sales/day  14 mo  hold 83
  The hold ranking, walked forward: top 20 +37.6% at 90 days vs +6.9% for the field (9 of 9 months)
  Next booster: Stardust Trails (GD06) · 2026-10-30 · in 22 days
```

## What a subscriber gets

**How long will you hold?** The first question on the page, and it picks the ranking
(docs/METHOD.md has the evidence):

- *3–6 months* and *1 year+* rank by the **hold score**: rarity, set age and sales a day,
  as percentiles of today's pool — the three things that ordered the next 90 to 270 days
  in a walk-forward of the whole archive. Its top 20 rose a median +37.6% over 90 days
  against +6.9% for the field (9 of 9 monthly tests) and +60.1% against +25.2% over 180
  (6 of 6).
- *Under 30 days* ranks by the **break-even hurdle**, because nothing measured made short
  holds pay after costs: bought at the cheapest listing and sold a month later, about one
  card in nine made money. Only cards that sell daily, priced live, with real recent sales.

Under the question sits that ranking's own record, re-run monthly, and the next release
with what past releases did to prices.

**Your holdings.** Star a card, enter copies and cost, and the page opens with positions,
cost in, value at the market, and P&L *after selling costs* — what selling would actually
put back in your pocket — and how many broke trend. With the sync Worker deployed the list
follows the member across devices; without it, it lives in the browser.

**The hold screen.** Every English single priced $10+, measured on 90 days of daily price
and sales history, gated on the things that make a card un-holdable (too new, no sales,
too erratic, or a cheapest copy more than 30% over what it sells for), and shown as rich
rows: card art, a 90-day chart with release marks and 15%-day rings, entry / sells for /
break-even / 90d / sales a day / set age, the score for the chosen horizon, size at your
budget. Tap a row for the verdict chips (entry against sales, the break-even, the climb,
the exit, the shelf), four hero numbers, the case and what would break it, a wide chart
with 30 days / 90 days / 1 year, the score's parts or the round trip, the shelf, your
money, and a checklist.

**What a round trip costs.** Every row: the cheapest Near Mint English copy shipped (what
you pay), what copies actually sold for over 14 days, and the move the card needs before
selling it gives back what it cost — 10.75% + 2.5% + $0.30 of TCGplayer's cut by default
(`costs:` in config.yaml).

**The budget tool.** Enter a number or pick $250 / $500 / $1,000 / $2,500 / $5,000 and
every row gets a size — copies, cost, what limited it — walked down the chosen ranking with
a cap per card and per set; the plan shows its own break-even and how many days the exit
takes at today's pace. Arithmetic on your number, not advice.

**Sealed.** Booster boxes, decks and cases measured the way a sealed investor thinks:
against the earliest price held, days since release, drawdown from the 90-day high, units a
day, ask vs sold. Deliberately not scored.

**What releases did to prices.** For every release on record — eight so far — the
previous set's top 20, the new set's top 20 and the whole market at +30/60/90 days, medians
with n on every cell. The new set's chase cards fell a median 20–30% in their first two
months after every release measured.

**The front door.** What marketharo.io shows anyone not subscribed: the real dashboard cut to ten rows of the 3–6 month ranking — the same tiles as the report plus the hold ranking's tested record, the top card open with its full-width chart, nine more rows with art and sparklines, three blurred rows for the rest, and the two plans. The product itself is the pitch; the only prose is one line under the title. The track record — every issue's top 20 scored against its own
candidate pool at +30/60/90 days, spread shown, losers kept; every call also resolved as a
buyer lives it (bought at the live entry, sold at the market less costs); the $500 and
$2,500 budget plans each issue would have drawn, valued the same way; and the monthly
walk-forward of every ranking — with one sentence at the top: "Of N top-20 calls resolved
at 30 days, X% beat their pool … M of K made money after costs." Every issue is committed
to git the day it goes out and says which ranking produced it, so the sentence cannot be
improved after the fact.

**The shelf.** Listing counts, measured daily: how many copies are listed now against 7 and
30 days ago, how many days the shelf lasts at today's pace, and what it would cost to buy it
out. A shelf that drains while copies keep selling is demand eating supply — the thing a
price chart cannot show — and it is a verdict chip, a line in every detail, and a fact the
writer is given, along with the money that moved through the card in 30 days and the high
since we have tracked it.

**What is under each box.** For every set, the singles beneath it: how many are worth $50,
$100 and $500, what the top ten are worth and how that moved this month, and the money that
moved through the set's singles and its sealed product in 30 days. A box sells six a day or
none because of the cards inside it; this is the table that says which.

## How it works, in one paragraph

`radar sync` pulls the catalogue and today's batch prices, dated by the API's own
`last_updated_at` rather than the fetch. `radar invest` takes every English single at $10+,
pulls history for any without it and refreshes the sales figures of any whose sales are more
than two days old (the batch carries none), measures each series (90-day window by date; a
year of weekly points behind it for the long chart), gates and ranks for each hold horizon
(`radar/horizon.py`), prices the round trip (`radar/costs.py`), fetches a live Near Mint
English shelf for the top of the hold ranking and the short view's candidates, builds the
sealed screen, the set-depth table, the playbook, the track record and the preview, and
writes one self-contained HTML file with the card art embedded, plus a CSV. `radar export`
writes the price history to plain-text NDJSON so git, not SQLite, is the durable store.
`radar validate` walks every ranking forward across the archive monthly; the page shows the
newest run.

Everything the page computes in JavaScript — sizing, P&L — has a Python twin with tests.

## Quick start

```bash
git clone <this repo> && cd gundam-price-radar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # your tcgapi.dev key; never committed
python -m radar doctor          # verifies the key and every endpoint used
python -m radar restore         # rebuild the database from data/history
python -m radar run             # sync, measure, score, render
open out/dashboard.html         # the report; out/preview.html is the front door
python tests/test_pipeline.py   # 64 tests
```

A full daily run is ~300–700 API requests of the Pro plan's 10,000: about one per card whose
sales figures need refreshing, plus ~70 live shelves. The first run on an empty
archive backfills history and costs more; the archive in this repo already holds 98,000
points across 13 months, so a fresh clone does not need to.

## Commands

| | |
|---|---|
| `radar doctor` | verify the API key, game slug and every endpoint used |
| `radar sync [--no-history]` | catalogue + today's prices; dated by the API |
| `radar backfill --range quarter\|year` | history for cards that lack it |
| `radar invest [--date] [--today] [--no-fetch] [--no-art-fetch]` | the whole issue: report, front door, track record, CSV |
| `radar run` | sync then invest (what the workflow calls) |
| `radar publish [--dry-run]` | push the report and the front door to the site Worker |
| `radar export` / `radar restore` | the NDJSON archive, both directions |
| `radar validate [--legacy]` | walk-forward of every horizon's ranking (the retired score's single-split test with `--legacy`) |
| `radar snipe` | live entry prices and copy counts for the movers |
| `radar heat [--template]` | search attention outside the price data (manual capture) |
| `scripts/load_snapshot.py FILE.tsv` | replay a browser-pulled snapshot through the real normalisers |

## The repo

```
radar/            the package — see docs/ARCHITECTURE.md for what each module is for
worker/           the site: serves and gates the page, keeps watchlists (npm test signs test tokens)
data/history/     the archive: one NDJSON file per month, the one thing not rebuildable
data/rankings/    every issue's ranking, as published; the track record is built from these
tests/            python tests/test_pipeline.py
docs/METHOD.md    how the score, gates, settled price and validation were measured
docs/ARCHITECTURE.md   modules, data flow, what is a cache and what is an asset
docs/PLAN.md      the plan to go live, block by block, for Aaron
docs/HANDOFF-gundeck.md   the integration handoff for the gundeck.ai side (Clerk, Stripe, UI)
docs/LAUNCH.md    the launch plan, and the appendix of changes on gundeck.ai
DEPLOY.md         GitHub Actions, the Worker, Clerk, costs
CHANGELOG.md      what changed, by issue
```

## What this cannot tell you

Every number describes what a card has already done. Nothing here is a forecast, and
nothing knows *why* a price is moving: bans, reprints, rotation and tournament results end
runs and are invisible in price data. The release calendar is on the charts because it is
on record; a banlist is not. The first score was calibrated on a market that rose the whole
way through one 90-day window, and when `radar validate` walked it forward it had stopped
working — which is why it was replaced, and why the replacement is re-tested every month
with the result on the page. The hold ranking's evidence is thirteen months of one game,
mostly a rising market; the first full one-year window closes in October 2026. Trading
cards can lose value.
