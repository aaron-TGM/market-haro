# Scope of work: the two Fifties

**Market Haro 50** — the fifty most traded, most investable singles. A price index.
**GUNDECK 50** — the fifty most *played* cards. A meta index, with every version of each card priced side by side.

Two different questions, two different names, each explained in one sentence at the top of the page so nobody has to ask what they are looking at.

---

## 0. The decision that gates everything: where "most played" comes from

Price data comes from tcgapi.dev. Play data does not exist there, so the GUNDECK 50 needs a second source. Three options, in order of preference:

| Source | What it gives | What it costs |
|---|---|---|
| **gundeck.ai's own deck data** | Cards per deck across every deck built or saved on the site, refreshed whenever you like. Proprietary — nobody else can publish this number. | An export or endpoint from gundeck.ai: `card_number, copies, deck_id, saved_at, format`. Half a day on your side if the data is queryable. |
| **Tournament results** (Limitless-style event pages, Bandai official top-cut decklists) | Play share in *winning* decks — the number competitive players care about. | A scraper per source, brittle when their HTML changes, and a card-name matcher. Two to three days, ongoing maintenance. |
| **Hand-curated list** | A start on day one. | You maintain it. Not a product feature, a placeholder. |

Recommendation: gundeck.ai data as the primary, tournament data later as a second column ("played" vs "winning"). If gundeck.ai has the data, the GUNDECK 50 becomes something only GUNDECK can publish — the same moat the release playbook has.

**Needed from you before build starts:** which source, what "format" means (Standard only? all decks?), and the window (last 4 weeks is the usual for a meta share).

---

## 1. Market Haro 50 — rename, explain, show the constituents

*What exists:* the index built last week, currently labelled "GUNDECK 50". Equal-weight, chain-linked, fifty most-traded singles $5+, members fixed per month.

1. Rename everywhere: page, email, `data/index.ndjson`, track record, README. Code name `haro50`.
2. **A deliberate "what you are looking at" strip at the very top of the page**, above everything, two lines:
   *Market Haro 50 — the fifty most traded, most investable Gundam singles, as one number. Base 100 in March 2026.*
   *GUNDECK 50 — the fifty most played cards in the current meta, every version priced. → its own page.*
3. **Show the fifty.** Today the number is on the page but the list is not. A collapsed "the fifty" panel under the index: rank, card, set, 90-day copies sold, price, 7d — and a note of when the basket was last rebalanced and who came in and went out.
4. Alert rule: a watched card entered or left the Market Haro 50 at a monthly rebalance.

Effort: ~1 day. No new data.

---

## 2. GUNDECK 50 — the most played cards, every version priced

*A new page, `/gundeck-50/`.* Refreshed weekly (the meta moves in weeks, not days), published by the same pipeline.

**2a. The play data** (`radar/meta.py`)
- Ingest from the chosen source into `data/meta/YYYY-MM-DD.json`: per card number, share of decks containing it and average copies, over the window.
- Rank by deck share; take fifty. Keep the previous week's ranking so movement shows (+3 / −5 / new), the way the hold screen does.
- Join to tcgapi on the **card number** (GD01-024). Verified: every version of a card carries the same number in the API — base *Wing Gundam Zero* (Legend Rare), *Wing Gundam Zero (LR+)*, *Wing Gundam Zero (Championship) (Winner)* are three products under GD01-024, and 487 numbers in the game have more than one version. No name matching needed.

**2b. Versions** (`radar/versions.py`)
- Group products by number. Classify each: **base** (the plain printing), **parallel** (R+, C+, U+, LR+, LR++ — the alt-art chase versions), **promo/event** (Championship, Regional, Newtype Challenge, Premium Card Collection).
- For each GUNDECK 50 card: base price, then every parallel with price, entry, 7d/30d, sales/day, and the **alt premium** — how many times the base the alt costs, and how that ratio has moved over 30 days. That ratio is the number an alt-art investor actually trades on and nobody publishes it.
- Promos shown but folded ("+2 promo versions"), because they are illiquid and would clutter the row.

**2c. The page**
- Same visual language as Market Haro: card art (base), name, number, **deck share** as the hero number with a 4-week trend, then a version strip — base | LR+ | LR++ — each with price, 7d, a 90-day chart, and the alt/base ratio.
- Tap a row: full version table, the hold-screen verdicts for each version (timing, trend, exit), the release marks, "your money" if you hold it, and a **play vs price** read in one line: *"Played in 61% of decks, up 9 points in four weeks; base price flat, LR+ up 22% — the alt is moving, the base is not."*
- A **GUNDECK 50 price index** alongside the play ranking: equal-weight of the fifty base printings, so the meta's cost can be charted against the Market Haro 50. Two lines, one chart: "what the market is doing" vs "what a competitive deck costs".
- Filters: colour/faction if the source carries it, version type, price band.

**2d. Alerts and the email**
- A card entering or leaving the GUNDECK 50; a watched card's deck share moving 10+ points in a week; an alt premium crossing a round number (the LR+ is now 5× the base).
- The weekly digest gets a "meta" line: the three biggest risers in play, and whether their prices have noticed yet.

**2e. Public or paid**
- Recommendation: the ranking (names and deck share) **public** — it is the marketing page, the thing a Reddit thread links to. The prices, versions, alt premiums and the index **paid**. Ghost can do that with two pages or one page with a paid section.

Effort: 4–5 days after the data source is settled. Weekly cost: one refresh in the existing daily workflow, gated to Mondays.

---

## 3. Order of work

1. You decide the play-data source and hand over a sample (one week of it is enough to build against).
2. Market Haro 50 rename + top strip + the-fifty panel (day 1).
3. Meta ingest + versions module + tests (days 2–3).
4. The GUNDECK 50 page, index and detail (days 4–5).
5. Alerts, digest line, Ghost publishing, docs (day 6).

Everything in §1 can start now. Nothing in §2 should start until §0 is answered, because the page's whole design changes depending on whether "played" means *saved on gundeck.ai* or *won an event*.

---

## 4. Out of scope, on purpose

- Deck archetype pages, matchup data, or anything that turns this into a meta site. The GUNDECK 50 is a *card* ranking with prices; the deck-building site is gundeck.ai.
- Japanese product. Different market, different numbers.
- Predicting which cards will become played. The page shows what is played and what that is doing to price; it does not forecast the meta.
