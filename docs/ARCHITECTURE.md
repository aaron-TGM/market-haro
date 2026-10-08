# Architecture

Plain Python, one SQLite file as a cache, plain-text NDJSON as the store, one static HTML
page as the product, one small Worker to serve it behind gundeck.ai's login and keep
watchlists. No framework, no server of our own, no email.

## Data flow, one issue

```
tcgapi.dev ──sync──▶ SQLite (cache) ◀──restore── data/history/*.ndjson (the asset)
                        │                              ▲
                        │ invest                       │ export
                        ▼                              │
   refresh sales ─▶ measure ─▶ gate/rank per horizon ─▶ live shelf ─▶ costs ─▶ sealed · depth · playbook · track ─▶ out/
                                    ▲
             data/validation_history.json (radar validate, monthly) ── the record each horizon shows
                                                                            ├ dashboard.html    ─▶ Worker /admin/report ─▶ marketharo.io/  (entitled sessions)
                                                                            ├ preview.html      ─▶ Worker /admin/preview ─▶ marketharo.io/  (everyone else: the front door)
                                                                            └ dashboard.csv
```

## Modules

| Module | Job | Notes |
|---|---|---|
| `client.py` | tcgapi.dev v1 client | unwraps the varying payload keys, tracks the daily budget, backs off on 429/5xx |
| `ingest.py` | sync + backfill + sales refresh | rows dated by `last_updated_at`, never the fetch (pinned by test); `refresh_sales` keeps the pool's sales figures current (the batch has none) |
| `db.py` | SQLite | `latest_prices` = newest row per product within 7 days, not one date; `sets()`; `all_series_with_volume()` (a missing sales figure stays None); `entry_series()`, `card_meta()`, `sales_last_seen()` |
| `archive.py` | NDJSON export/restore | deterministic bytes per month; `sets.ndjson` too |
| `invest.py` | measure (+ the retired score) | `features()` measures a 90-day window by date; `sales_rate()` = sales a day over days with figures, weekly totals spread over the week; `settled()` = what copies sold for, last 14 days by date; `evaluate()` is the retired score, kept for `validate` |
| `horizon.py` | the rankings | per hold horizon: gates (incl. a cheapest copy >30% over what it sells for), the hold score (rarity, set age, sales a day as percentiles), the under-30-days order (break-even hurdle); which cards get a live shelf; the page's words |
| `costs.py` | the round trip | proceeds, break-even, hurdle, net return; TCGplayer's cut by default (`costs:` in config) |
| `affiliate.py` | TCGplayer's affiliate program | Impact's tag for the `<head>`, verbatim, from `affiliate.impact_utt`; the disclosure wording |
| `plan.py` | budget sizing | twin of the page's `allocate()` (a test runs both); per-card and per-set caps |
| `snipe.py` | live NM English shelf | entry price = cheapest NM shipped; English enforced twice |
| `sealed.py` | the sealed screen | against earliest price held + release date; its own case/watch/checklist; not scored |
| `depth.py` | what is under each box | per set: singles ≥$50/$100/$500, top-10 value and its 30d move, money through singles and sealed; a panel, and sealed facts |
| `releases.py` | the set calendar | codes from card numbers (GD05, ST11–14); marks on every chart; next-release tile |
| `playbook.py` | what releases did | prior set / new set / market at +30/60/90, medians with n |
| `track.py` | the track record | every issue's top 20 vs its pool, and after costs; the $500/$2,500 plans each issue would have drawn; which ranking each issue used; the walk-forward tables |
| `preview.py` | the front door | the report's tiles and its top ten (first row open, big chart), ghosts, the plans; the Worker fills its markers and serves it at `/` to anyone not entitled |
| `art.py` | card art | cached under `data/images/`, 240px WebP data URIs in the page |
| `haro.py` | the page | one file: CSS, JS, JSON payload; nothing decided on the page that a test cannot check |
| `digest.py` | the stored rankings | snapshot per issue in `data/rankings/` (with `method`, the hold score, the short rank, costs); the diff between two issues; the newest shelf for an offline build |
| `validate.py` | walk-forward tests | `run_horizons`: every ranking at its windows, monthly splits, market and sold basis, plus the short test on buyable terms and the retired score; `run`: the original single split (`--legacy`). Appends to `data/validation_history.json`; the page reads the newest |
| `heat.py`, `setreport.py`, `signals.py`, `dashboard.py` | the earlier tools | search attention (manual capture), per-set reports, the first dashboard whose helpers the page still reuses |
| `cli.py` | `python -m radar …` | `cmd_invest` is the issue; read it top to bottom to follow one day |

## What is an asset and what is a cache

- **Assets** (committed): `data/history/*.ndjson`, `data/cards.ndjson`, `data/sets.ndjson`,
  `data/rankings/*.json`, `data/validation_history.json`, `data/market_heat.json`.
  Every daily point the API will not sell back next year lives here.
- **Caches** (ignored): `radar.sqlite3`, `data/images/`, `out/`, `.env`.
  Rebuildable from the assets plus the API.

## The Worker

`worker/src/index.js`, one KV namespace, at marketharo.io — a Clerk satellite domain of
gundeck.ai, so sign-in happens on gundeck.ai's pages and returns. Identity is Clerk's
(gundeck.ai's instance): the session token in the `__session` cookie or a bearer header,
RS256, verified against `clerk.gundeck.ai/.well-known/jwks.json`; the entitlement is the
`public_metadata.marketHaro.status` claim Stripe's webhook wrote onto the user. `GET /`
serves the report to entitled sessions and the front door to everyone else (`/preview`
and `/track-record` redirect to `/`); `GET/PUT /positions` per user id; `PUT /admin/report` and
`/admin/preview` from the pipeline with the admin secret. The served report has Clerk's
script injected so the cookie stays fresh. `npm test` signs tokens with a generated key
and walks every door.

## The page's contract, pinned by tests

- One file plus the Google Fonts stylesheet; no `<script src>`; card art embedded.
- Nothing the reader types leaves the browser except to `/positions` on the page's own
  origin, only when the Worker serves the page and the reader is signed in.
- The one third-party script is Impact's tag for TCGplayer's affiliate program
  (`affiliate.impact_utt` in config, `radar/affiliate.py`), in the `<head>` of the report
  and the front door. It records page views and rewrites links to TCGplayer into tracked
  links; the report asks it to rescan after every redraw. The page hands it nothing.
  When it is on, the report says so above the list, beside every TCGplayer button, and
  in the footer. Empty config: no tag, plain links, no disclosure.
- Every CSS variable used is declared; no glyph characters that could render as tofu.
- The release calendar and the sealed rows ship in the JSON payload; the catalyst flag
  does not exist.
- A late feed is the first panel after the header, and the issue still goes out.
