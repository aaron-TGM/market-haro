# Changelog

Newest first. Dates are the day the work landed; issue dates are the price date the
report carries.

## 2026-10-08 — TCGplayer affiliate links

- Impact's tag for TCGplayer's affiliate program goes in the `<head>` of the report and
  the front door, verbatim as the account issued it, from `affiliate.impact_utt` in
  config (`radar/affiliate.py`; a value that is not Impact's script address is refused).
  It rewrites links to TCGplayer into tracked links; the report asks it to rescan after
  every redraw and every opened row, because its rows are drawn after load. Checked in a
  browser with a stand-in for Impact's script: 400 of 400 row links and the opened row's
  button tracked, the English filter kept; with the tag blocked the links stay plain
  TCGplayer links and nothing breaks.
- Disclosure, as TCGplayer's partner guidelines and the FTC ask: a sentence above the
  list ("…affiliate links… It never affects the ranking."), "affiliate link" beside every
  Open on TCGplayer button, and a footer line on both pages saying the tag is there.
- The first live issue on the hold rankings (2026-10-08) came out as expected: sales
  figures back on 313 of 401 ranked cards (none the day before), 63 live entries, 56
  cards ranked for under 30 days.
- Tests: 65 (one new: the tag byte for byte, its place in both heads, the disclosures,
  and a bad config value refused). The Worker is not touched.

## 2026-10-08 — Ranked by how long you hold; costs on every row; sales figures flow again

- **The score is retired.** Walked forward on every week the archive can score (June to
  September), the original score did worse than its own pool at every horizon: rank
  correlation −0.13 at 30 days, −0.19 at 60, −0.11 at 90; its top 20 beat the pool in 3
  of 12 weekly tests at 30 days and 0 of 7 at 60. Of the 60 September top-20 calls with a
  live entry, 2 made money after costs. The monthly validation of 1 October had already
  said INVERTED; the page never showed it. Its issues stay in the record, labelled.
- **How long will you hold?** The first question on the page, and it picks the ranking
  (`radar/horizon.py`). 3–6 months and 1 year+: the hold score — rarity, set age and sales
  a day as percentiles of the day's pool — whose top 20 rose a median +37.6% over 90 days
  against +6.9% for the field (9 of 9 monthly tests since October 2025) and +60.1% against
  +25.2% over 180 (6 of 6); it holds on what copies sold for, inside the $10–100 band, and
  since June. Under 30 days: ordered by the break-even, because nothing measured made short
  holds pay after costs (about one card in nine did); needs a sale a day, a live entry and
  real recent sales. Choice remembered in the browser. The pool is every English single at
  $10+ — the "up over 30 days" filter halved the hold ranking's result and is gone.
- **Under the question, that ranking's record**: the newest `radar validate` run, the next
  booster with what past releases did, and the retired score's verdict.
- **Costs** (`radar/costs.py`, `costs:` in config): entry, what it sells for, and the
  break-even after TCGplayer's 10.75% + 2.5% + $0.30 on every row; holdings show P&L after
  costs; cards whose cheapest copy costs more than 30% over what they sell for are screened
  out (cards over $500 sat a median 68% above their market price in September).
- **Budget tool**: presets ($250 to $5,000), a 50% cap per set beside the 25% per card,
  the plan's own break-even and days to exit; sized down the ranking you picked. Python
  and JavaScript twins checked against each other in a test that runs the page's code.
- **Track record**: every call also resolved as bought at the live entry and sold at the
  market less costs; the $500 and $2,500 plans each issue would have drawn, valued the
  same way; each issue labelled with its ranking; the walk-forward tables, newest run
  first (the track page had been showing August's +0.24 instead of October's −0.32).
- **Fixed: sales figures stopped entering the archive on 7 September.** The batch has no
  sales and history was only pulled for new cards, so liquidity decayed by itself and no
  card had a settled price by 7 October; by December every card would have failed "no
  sales in 90 days". `ingest.refresh_sales` refreshes a month of history for any pool card
  whose sales are over two days old (~500 requests a day of 10,000), and sales a day is
  measured only over days with figures. `vs sold` is no longer quoted as a 30-day edge:
  that edge was the market price catching up to sales, not a return.
- `radar validate` now runs the horizon walk-forward (`--legacy` for the old test); the
  first record, run 2026-10-08, is committed. Tests: 64 in the pipeline (8 new), the
  Worker's 3 unchanged. The Worker is not touched.

## 2026-09-11 — The front door, and rows that open in place

- The splash is the product. `/` for a stranger or an unsubscribed account is now
  the real dashboard cut to ten rows: the report's KPI tiles, the top card open with
  its full-width 90-day chart and release marks, nine more rows with art and
  sparklines, three blurred rows, then the plans. Built by the pipeline every morning
  (`radar/preview.py`, using the report's own stylesheet and `haro.kpi_tiles`); the
  Worker fills three markers and the plan hrefs, and knows nothing about cards. Everything
  the old splash did stays: `?checkout=success` waiting state, "Signed in as … no
  subscription yet", plan buttons through Clerk sign-up, Manage, Sign out. `/preview`
  and `/track-record` redirect to `/`. A plain door is served if the Worker is deployed
  before the pipeline's next run.
- Report: a clicked row opens in place. Its own image grows to 200×280, its own chart
  grows to full width and gains the range switch, the detail fades in beneath; no
  second image, no second chart. Transforms and opacity, ~280 ms, the row's height
  tweened so the rows below slide; instant under prefers-reduced-motion. Collapse
  reverses it. After the grow the same image quietly upgrades to the CDN's sharp copy.
- Tests: 55 in the pipeline (two new: the front door's contract, the open row's), the
  Worker's 3 updated to the new door.

## 2026-09-11 — Launched


- Live at marketharo.io. Production trial end to end: sign-up on gundeck.ai, Stripe
  checkout, webhook → Clerk `marketHaro.status`, report; account linkage confirmed.
- The public page is now the preview (`/preview`): today's real top ten with art, then
  the plans; `/track-record` redirects there. `radar/preview.py`.
- Worker: satellite domain via `data-clerk-domain`, `azp` check, one-time GUNDECK
  cross-sell banner after checkout (`?welcome=1`), deployed through the Cloudflare
  dashboard (not wrangler).
- Products decoupled: Market Haro no longer includes GUNDECK; GUNDECK moves to
  $3/mo · $29/yr · Lifetime $59 from Oct 30 (Manus's build). 7-day trial for everyone.
- `CLAUDE.md` added: the briefing for whoever picks this up next.

## 2026-09-10 — marketharo.io, a satellite

- The site moves to `marketharo.io` itself so gundeck.ai's DNS is never touched. The .io is a
  Clerk satellite domain of gundeck.ai: the Worker loads Clerk with `isSatellite`, sign-in and
  sign-up go to gundeck.ai's pages and return, tokens may carry either issuer. `wrangler.toml`
  gains `CLERK_SATELLITE_DOMAIN`, `SIGN_IN_URL`, `SIGN_UP_URL`; the route is the apex.

## 2026-09-09 — marketharo.gundeck.ai

- **Ghost is gone.** The site is one Cloudflare Worker at marketharo.gundeck.ai that serves
  the report to signed-in GUNDECK users whose account carries a Market Haro subscription
  (Clerk session token verified against clerk.gundeck.ai's keys; entitlement read from
  `public_metadata.marketHaro.status`, written by Stripe's webhook on gundeck.ai), the splash
  to everyone else, the public track record, and each user's watchlist by user id.
  `radar publish` PUTs the two pages to it. Alerts and Resend are gone with the email.
- Pricing stays $8 / $88; an add-on to a GUNDECK account. docs/LAUNCH.md is rewritten
  around this and ends with the appendix of changes on gundeck.ai.

## 2026-09-09 — a dashboard, not a newsletter

- **Removed**: the model-written commentary (`radar/commentary.py`, the relay, `docs/VOICE.md`,
  the OpenAI/Anthropic keys), the weekly note (`radar/note.py`, `data/notes/`,
  `radar note-draft`), the Market Haro 50 (`radar/index.py`, `data/index.ndjson`), and the
  daily email (the digest renderers, `out/digest.*`, `out/lead.txt`). `data/rankings/` stays:
  it is what the track record scores and what rank movement reads.
- Each card keeps its one-line template case and watch. The reader draws the conclusion.
- The pitch and build-review pages are gone; `scripts/build_consumer.py` shows the report
  and the track record. Ghost, the Worker and alerts are unchanged in this commit and are
  decided next (see DEPLOY.md when it lands).

## 2026-09-09 — before hosting

- **Pricing**: $8 a month, $88 a year.
- Tooltips on the *Pass the screen* and *Screened out* tiles (the pool, the five gates; the
  second tile links to the list at the bottom of the page).
- The workflow no longer deploys the report to Cloudflare Pages — Ghost is the only host
  of the paid page — and caches card art between runs.

## 2026-09-09 — the page opens on the ranking

- The **weekly note** panel and the **Market Haro 50** panel are gone from the page and the
  email. The index is still computed to `data/index.ndjson` (the playbook's whole-market
  column and the track record read it); `radar note-draft` still exists but nothing shows a
  note. The page now opens on the budget line and the ranking.

## 2026-09-09 — what a number is for

- **Shelf arithmetic** on every single and every box: days of shelf (listings ÷ sales a day)
  and dollars to clear it (listings × price) — how long the shelf lasts and how little money
  moves the price. In the detail, and in the writer's facts (`invest.shelf_math`).
- **Money through it**: copies sold × what they sold for over 30 days, per product
  (`dollars_30d`), and **what is under each box** — a panel per set: singles worth $50/$100/$500,
  what the top ten are worth and how that moved this month, money through singles and sealed
  (`radar/depth.py`). Every sealed case is written with its own set's row; the email lead is
  given the three sets money is moving through.
- **High since tracked** and its date, and how far off it the card sits, in the detail and the
  facts — not only the 90-day high.
- **Voice**: two rules. A number must carry a consequence; a watch names a mechanism.

## 2026-09-09 — the record, the shelf, the price

- **Pricing** reset to **$9.99 a month, $89 a year**. Single paid tier, 7-day trial, no free
  tier, and no member coupon — one price for everyone.
- **The record, per call**: every top-20 pick is resolved on its own 30 days after its issue
  against that issue's pool. One sentence at the top of the track record and a tile on the
  report: "Of N calls resolved at 30 days, X% beat their pool and Y% were up." `out/track.json`.
  The first window closes 2026-09-10.
- **The shelf**: listing counts are now a measured series (`db.listings_series`,
  `invest.supply`): listings today against 7 and 30 days ago, on singles and sealed. A verdict
  chip when the shelf drains 20%+ or grows 25%+; a line in the detail; in the writer's facts.
  Recorded daily since 2026-09-03, so the deltas appear from 2026-09-10.
- **Market Haro 50** folds closed by default: one line at the top, the chart on a click.
- **Commentary relay** (`--relay DIR`, `scripts/relay.html`) for machines without network.

## 2026-09-08 — the voice

- **Written, not templated**: each card's case and watch, the email's opening paragraph and a
  draft of the weekly note come from a model that is given only measured facts and
  `docs/VOICE.md`; every number in its output is checked against the facts and a refused
  sentence falls back to the template (`radar/commentary.py`, `radar note-draft`). Cached
  per issue in `data/commentary/`. GPT-5.6 Sol via `OPENAI_API_KEY` by default; Anthropic
  as the alternative provider. `--relay DIR` for machines without network: requests are queued
  to a file and `scripts/relay.html` answers them from a browser tab; the next run reads them.
- Issue 2026-09-07: the first batch fully stamped on its own day since the rebuild.

## 2026-09-06 — the $35 build

- **Market Haro 50**: equal-weight, chain-linked
  index of the fifty most-traded singles $5+, base 100, members fixed per month, a year
  of history with release marks. First panel on the page. `data/index.ndjson`.
- **Your holdings**: positions, cost in, value now, P&L, trend-broke count at the top of
  the page; account sync via the Worker when served on the site; browser-only otherwise.
- **Alerts**: a Cloudflare Worker (`worker/`) with Ghost member identity (signed session
  token, JWKS), per-member watchlists in KV, a daily alert pass through Resend. Rules in
  `radar/alerts.py`, mirrored in the Worker, held together by a shared test fixture.
- **Sealed screen**: boxes, decks, cases against their earliest price, days since release,
  drawdown, units a day, ask vs sold. Not scored. Own case, watch text and checklist.
- **Release playbook**: prior set / new set / market at +30/60/90 days for every release
  on record (eight), medians with n.
- **Track record**: public page; every issue's top 20 vs its pool at +30/60/90 days,
  losers kept; validation history with caveats.
- **Weekly note** slot: `data/notes/YYYY-MM-DD.md`, ten days of freshness, page + email.
- **Chart ranges** 30 days / 90 days / 1 year in the detail; `change_180d`, `change_1y`.
- **Data**: history for every single $2+ and every sealed product, 90 days daily and a
  year weekly (798 products; 98,134 points across 13 months). `features()` measures its
  90-day window by date so the long series cannot distort it.
- **Packaging**: $35/month, $300/year, 7-day trial, no free tier. DEPLOY §5b for the Worker.
- **Docs rebuilt**: README (the product), docs/METHOD.md (the measurements),
  docs/ARCHITECTURE.md (the code), docs/SOW-two-fifties.md (next), this file.

## 2026-09-06 — prices through 2026-09-05; release marks

- Full pull; issue dated the last complete day. 126 candidates from 207 screened.
- The hand-kept catalyst flag is gone. Every chart carries a dashed mark at each set
  release, labelled from the card numbers (GD05, EB01 + ST10, ST11–14), and a ring on any
  day that moved 15%+. Hover names the release and the day's move. Next-release tile.
- Sets archived (`data/sets.ndjson`) and restored; the snapshot loader takes S rows.

## 2026-09-06 — Market Haro v3, the human-first pass

- Card art embedded in the file (the CDN was fine; sandboxed previews were not).
- Filters in two layers: search / views / sort in one row, the rest behind one button.
- Detail panel rebuilt: art, verdict chips, hero numbers, callouts, four boxes.
- The "Since <date>" panel removed from the page (the digest's job).

## 2026-09-04 — Market Haro v2 and the subscriber product

- The subscriber screen (`radar/haro.py`): budget hero, rich rows with art and a large
  chart, watchlist with P&L and trend-broke, rank movement, catalyst flags.
- `radar digest` (the daily diff, emailed) and `radar publish` (Ghost).
- Pricing first set at $15/$125, single tier, no free.
- Full-game refresh; shelf median and language stored on floors.

## 2026-08-09 → 2026-08-12 — the hold screen

- Rebuilt around a hold thesis: score on value, liquidity, trend, stability, scarcity,
  anchored to the market's own quartiles; gates for the un-holdable.
- English printings only, end to end. The broken 24h field dropped; 3d/7d/30d from
  stored history. The settled (vs sold) price — the one signal that survived testing.
- Market heat (search attention, manual capture) and `radar validate` (walk-forward).
- Snapshot rows dated by the API's `last_updated_at`, never the fetch. NDJSON archive.
- Budget-driven sizing, expandable rows, live entry prices (`radar snipe`).

## 2026-08-09 — Gundam Price Radar

- First version: track Gundam Card Game prices on tcgapi.dev, surface cards that are
  rising, a filterable dashboard.
