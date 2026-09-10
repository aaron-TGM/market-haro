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
   measure ─▶ score/gate ─▶ live shelf ─▶ sealed · depth · playbook · track ─▶ out/
                                                                            ├ dashboard.html    ─▶ Worker /admin/report ─▶ marketharo.io/  (entitled sessions)
                                                                            ├ track-record.html ─▶ Worker /admin/track  ─▶ …/track-record        (public)
                                                                            └ dashboard.csv
```

## Modules

| Module | Job | Notes |
|---|---|---|
| `client.py` | tcgapi.dev v1 client | unwraps the varying payload keys, tracks the daily budget, backs off on 429/5xx |
| `ingest.py` | sync + backfill | rows dated by `last_updated_at`, never the fetch (pinned by test) |
| `db.py` | SQLite | `latest_prices` = newest row per product within 7 days, not one date; `sets()`; `all_series_with_volume()` |
| `archive.py` | NDJSON export/restore | deterministic bytes per month; `sets.ndjson` too |
| `invest.py` | measure + score + gates | `features()` measures a 90-day window by date; `change_1y` from the long series; `settled()` = ask vs sold |
| `plan.py` | budget sizing | twin of the page's `allocate()` |
| `snipe.py` | live NM English shelf | entry price = cheapest NM shipped; English enforced twice |
| `sealed.py` | the sealed screen | against earliest price held + release date; its own case/watch/checklist; not scored |
| `depth.py` | what is under each box | per set: singles ≥$50/$100/$500, top-10 value and its 30d move, money through singles and sealed; a panel, and sealed facts |
| `releases.py` | the set calendar | codes from card numbers (GD05, ST11–14); marks on every chart; next-release tile |
| `playbook.py` | what releases did | prior set / new set / market at +30/60/90, medians with n |
| `track.py` | the public track record | every issue's top 20 vs its pool; validation history |
| `art.py` | card art | cached under `data/images/`, 240px WebP data URIs in the page |
| `haro.py` | the page | one file: CSS, JS, JSON payload; nothing decided on the page that a test cannot check |
| `digest.py` | the stored rankings | snapshot per issue in `data/rankings/`; the diff between two issues |
| `validate.py` | walk-forward test | appends to `data/validation_history.json`; verdict thresholds |
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
serves the report to entitled sessions and the splash to everyone else; `GET
/track-record` is public; `GET/PUT /positions` per user id; `PUT /admin/report` and
`/admin/track` from the pipeline with the admin secret. The served report has Clerk's
script injected so the cookie stays fresh. `npm test` signs tokens with a generated key
and walks every door.

## The page's contract, pinned by tests

- One file plus the Google Fonts stylesheet; no `<script src>`; card art embedded.
- Nothing the reader types leaves the browser except to `/positions` on the page's own
  origin, only when the Worker serves the page and the reader is signed in.
- Every CSS variable used is declared; no glyph characters that could render as tofu.
- The release calendar and the sealed rows ship in the JSON payload; the catalyst flag
  does not exist.
- A late feed is the first panel after the header, and the issue still goes out.
