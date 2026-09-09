# Market Haro — from GUNDECK.AI

A daily market dashboard for people who invest in the Gundam Card Game. Every morning it
measures the whole English market on tcgapi.dev, ranks the singles worth holding, screens
sealed product, shows what is under every box, marks every chart with the set calendar, and
scores its own past calls in public. No newsletter, no written commentary beyond a one-line
case per card: the numbers are the product and the reader draws the conclusion.

One paid tier: **$8 a month or $88 a year, 7-day trial, no free tier** — an add-on to a
GUNDECK.AI account. One page at marketharo.gundeck.ai, rebuilt daily by GitHub Actions and
served by one Cloudflare Worker to signed-in GUNDECK users with the subscription; identity
is Clerk's and billing is Stripe's, both gundeck.ai's own. DEPLOY.md has the setup.

```
Prices through 2026-09-05 · 127 cards pass the screen · 207 screened

  #1  Wing Gundam Zero (LR+)   $338.41   entry $326   vs sold −3%   90d +84%   score 86
  #2  Resource (R-002) (C++)   $101.04   entry $106   vs sold +6%   90d +119%  score 85
  Sealed: Starter Deck 03: Zeon's Rush +62% over 30 days, 421 days after release
  Next release: ST11–14 · 2026-09-25 · in 19 days
```

## What a subscriber gets

**Your holdings.** Star a card, enter copies and cost, and the page opens with positions,
cost in, value now, P&L and how many broke trend. With the sync Worker deployed the list
follows the member across devices; without it, it lives in the browser.

**The hold screen.** Every English single priced $10+ and up over 30 days, measured on 90
days of daily price and sales history, scored 0–100 on value, liquidity, trend, stability
and scarcity against the market's own quartiles, gated on the things that make a card
un-holdable, and shown as rich rows: card art, a 90-day chart with release marks and
15%-day rings, price / entry / vs sold / 7d / 90d / sales a day, score, size at your
budget. Tap a row for three verdict chips (is it listed ahead of itself, is the climb
intact, can you get out), four hero numbers, the case and what would break it, a wide
chart with 30 days / 90 days / 1 year, the shelf, your money, and a checklist.

**The budget tool.** Enter a number and every row gets a size — copies, cost, what limited
it — walked down the ranking with a per-card cap. Arithmetic on your number, not advice.

**Sealed.** Booster boxes, decks and cases measured the way a sealed investor thinks:
against the earliest price held, days since release, drawdown from the 90-day high, units a
day, ask vs sold. Deliberately not scored.

**What releases did to prices.** For every release on record — eight so far — the
previous set's top 20, the new set's top 20 and the whole market at +30/60/90 days, medians
with n on every cell. The new set's chase cards fell a median 20–30% in their first two
months after every release measured.

**The track record.** The one public page: every issue's top 20 scored against its own
candidate pool at +30/60/90 days, spread shown, losers kept, plus the monthly walk-forward
validation of the score itself — and one sentence at the top, per call: "Of N top-20 calls
resolved at 30 days, X% beat their pool." Every issue is committed to git the day it goes
out, so the sentence cannot be improved after the fact.

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
`last_updated_at` rather than the fetch. `radar invest` loads daily history for the
candidate pool, measures each series (90-day window by date; a year of weekly points behind
it for the long chart), scores and gates, fetches a live Near Mint English shelf for the
strongest, builds the sealed screen, the set-depth table, the playbook and the track record,
and writes one self-contained HTML file with the card art embedded, plus a CSV. `radar
export` writes the price history to plain-text NDJSON so git, not SQLite, is the durable
store. `radar validate` re-runs the walk-forward test monthly.

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
open out/dashboard.html         # the report; out/track-record.html
python tests/test_pipeline.py   # 53 tests
```

A full daily run is ~60 API requests of the Pro plan's 10,000. The first run on an empty
archive backfills history and costs more; the archive in this repo already holds 98,000
points across 13 months, so a fresh clone does not need to.

## Commands

| | |
|---|---|
| `radar doctor` | verify the API key, game slug and every endpoint used |
| `radar sync [--no-history]` | catalogue + today's prices; dated by the API |
| `radar backfill --range quarter\|year` | history for cards that lack it |
| `radar invest [--date] [--today] [--no-fetch] [--no-art-fetch]` | the whole issue: report, track record, CSV |
| `radar run` | sync then invest (what the workflow calls) |
| `radar publish [--dry-run]` | push the report and the track record to the site Worker |
| `radar export` / `radar restore` | the NDJSON archive, both directions |
| `radar validate [--horizon]` | walk-forward: does the score still separate winners? |
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
docs/LAUNCH.md    the launch plan, and the appendix of changes on gundeck.ai
DEPLOY.md         GitHub Actions, the Worker, Clerk, costs
CHANGELOG.md      what changed, by issue
```

## What this cannot tell you

Every number describes what a card has already done. Nothing here is a forecast, and
nothing knows *why* a price is moving: bans, reprints, rotation and tournament results end
runs and are invisible in price data. The release calendar is on the charts because it is
on record; a banlist is not. The score was calibrated on a
market that rose the whole way through one 90-day window; `radar validate` exists because
that will not stay true. Trading cards can lose value.
