# Changelog

Newest first. Dates are the day the work landed; issue dates are the price date the
report carries.

## 2026-09-09 — the record, the shelf, the price

- **Pricing** reset to **$7.99 a month, $75 a year** (GUNDECK offer: first month $3.99, first
  year $60). Single paid tier, 7-day trial, no free tier, as before.
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
