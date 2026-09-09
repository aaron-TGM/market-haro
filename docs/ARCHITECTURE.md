# Architecture

Plain Python, one SQLite file as a cache, plain-text NDJSON as the store, one static HTML
page as the product, one small Worker for the two things a static page cannot do. No
framework, no server of our own.

## Data flow, one issue

```
tcgapi.dev ──sync──▶ SQLite (cache) ◀──restore── data/history/*.ndjson (the asset)
                        │                              ▲
                        │ invest                       │ export
                        ▼                              │
   measure ─▶ score/gate ─▶ live shelf ─▶ index · sealed · playbook · track ─▶ out/
                                                                            ├ dashboard.html   paid Ghost page  /market-haro/
                                                                            ├ digest.html      paid Ghost post, emailed
                                                                            ├ track-record.html public Ghost page /track-record/
                                                                            ├ issue.json       ─▶ Worker /admin/issue ─▶ alert emails
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
| `alerts.py` | alert rules + issue file | mirrored in `worker/src/index.js`; Python writes the cases the Worker test replays |
| `art.py` | card art | cached under `data/images/`, 240px WebP data URIs in the page |
| `haro.py` | the page | one file: CSS, JS, JSON payload; nothing decided on the page that a test cannot check |
| `digest.py` | the stored rankings | snapshot per issue in `data/rankings/`; the diff between two issues |
| `ghost.py` | Ghost Admin API | HS256 JWT; pages as Lexical HTML cards; paid vs public visibility |
| `validate.py` | walk-forward test | appends to `data/validation_history.json`; verdict thresholds |
| `heat.py`, `setreport.py`, `signals.py`, `dashboard.py` | the earlier tools | search attention (manual capture), per-set reports, the first dashboard whose helpers the page still reuses |
| `cli.py` | `python -m radar …` | `cmd_invest` is the issue; read it top to bottom to follow one day |

## What is an asset and what is a cache

- **Assets** (committed): `data/history/*.ndjson`, `data/cards.ndjson`, `data/sets.ndjson`,
  `data/index.ndjson`, `data/index_members.json`, `data/rankings/*.json`,
  `data/validation_history.json`, `data/market_heat.json`, `data/notes/*.md`.
  Every daily point the API will not sell back next year lives here.
- **Caches** (ignored): `radar.sqlite3`, `data/images/`, `out/`, `.env`.
  Rebuildable from the assets plus the API.

## The Worker

`worker/src/index.js`, one KV namespace. Identity is Ghost's signed member session token
(`/members/api/session`) verified against the site's JWKS — no login of our own.
`GET/PUT /positions` per member; `PUT /admin/issue` from the pipeline; a daily cron runs
`evaluate()` for every member and sends at most one email per issue through Resend. The
alert rules are a mirror of `radar/alerts.py`; if they disagree, Python is right.

## The page's contract, pinned by tests

- One file plus the Google Fonts stylesheet; no `<script src>`; card art embedded.
- Nothing the reader types leaves the browser except to two named endpoints, both only
  when a sync URL is configured and the reader is signed in on the site.
- Every CSS variable used is declared; no glyph characters that could render as tofu.
- The release calendar, the index and the sealed rows ship in the JSON payload; the
  catalyst flag does not exist.
- A late feed is the first panel after the header, and the issue still goes out.
