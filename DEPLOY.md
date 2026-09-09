# Deploying this as a standalone project

Target: it runs itself every morning, the price history accumulates somewhere it
can't be lost, and you can open the dashboard from your phone without the world
being able to.

The shape that gets you there is **GitHub Actions for the schedule, git for the
data, one Cloudflare Worker for the page, and gundeck.ai's Clerk and Stripe for
who is signed in and who has paid**. Nothing here needs a server of your own,
and nothing beyond the API plan costs money.

---

## The one design decision worth understanding first

**The SQLite database is not the asset. `data/history/*.ndjson` is.**

tcgapi.dev gives you weekly history back to March 2025 and daily history for
about a quarter. Every day you sync, you record a daily point the API will not
sell back to you next year. That accumulation is the only thing in this project
that cannot be recreated if it's lost.

So it's stored as plain text — one JSON object per line, one file per month,
deterministically sorted — and the database is treated as a cache:

```
radar export     database  ->  data/history/YYYY-MM.ndjson
radar restore    data/history/*.ndjson  ->  database
```

The daily workflow restores, syncs, exports, and commits. Roughly 1,700 rows a
day get appended to the end of one file and nothing else changes, so git stores
each day in kilobytes.

Committing `radar.sqlite3` instead would be the obvious move and it's a trap:
SQLite rewrites pages throughout the file on every write, git can't delta it, and
a year of daily commits of a growing binary runs at gigabytes against GitHub's
5 GB soft limit. `.gitignore` blocks it deliberately.

Sizing, for planning: ~140 bytes per price point, ~1,700 points a day, so **~85 MB
of text a year**, which packs down to a fraction of that. Fine indefinitely.

---

## Setup, about 20 minutes

### 1. Push to a private repo

```bash
cd gundam-price-radar
git remote add origin git@github.com:aaron-TGM/gundam-price-radar.git
git push -u origin main
```

Verify `.env` is not in there — it's gitignored, but check once:

```bash
git ls-files | grep -i env      # should print only .env.example
```

### 2. Seed the archive from your local database

The workflow starts by restoring from the archive, so the archive has to exist.
Run this once from the machine that already has your synced database:

```bash
python -m radar export
git add data/history data/cards.ndjson
git commit -m "history: seed archive"
git push
```

Sanity check that it round-trips before you rely on it:

```bash
RADAR_DB=/tmp/check.sqlite3 python -m radar restore
RADAR_DB=/tmp/check.sqlite3 python -m radar stats
```

The point count should match `python -m radar stats` against your real database.

### 3. Add the API key as a repo secret

**Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `TCGAPI_KEY` | your tcgapi.dev key |
| `HARO_ADMIN_SECRET` | the Worker's admin secret (step 5); without it the page is built but not pushed |

Secrets are write-only once saved and are not exposed to forked-PR runs. Do not
put the key in `config.yaml` — that file is committed.

### 4. Turn the workflow on

`.github/workflows/daily.yml` is already in the repo. It runs at **13:10 UTC**,
after TCGplayer's overnight batch has settled, and you can trigger it by hand
from the Actions tab any time.

Each run: restore → sync → build the issue (report, track record) → keep it as
a run artifact → export → run the test suite → commit → push the two pages to
the Worker. The tests run *before* the commit on purpose, so a broken run
can't push a corrupted history.

On the 1st of each month it also runs `radar validate` and commits the result, so
score decay shows up in `data/validation_history.json` without you remembering to
check.

Trigger it once manually and watch it go green before trusting the schedule.

> **GitHub disables scheduled workflows after 60 days of repo inactivity.** The
> daily commit counts as activity, so this only bites if the workflow is already
> failing — which is exactly when you'd want it not to. Turn on Actions failure
> notifications: **Settings → Notifications → Actions → email on failure**.

### 5. The site: one Worker at marketharo.gundeck.ai

`worker/` is the whole server. It holds the report the pipeline pushes each
morning, shows it to signed-in GUNDECK users whose account carries a Market Haro
subscription, shows the splash (sign in / subscribe) to everyone else, serves the
public track record at `/track-record`, and keeps each user's watchlist so it
follows them across devices. It never talks to Clerk or Stripe at request time:
it verifies Clerk's session token against Clerk's published keys and reads the
entitlement Stripe's webhook wrote onto the user.

**5a. Cloudflare.** `cd worker && npm install`, then `npx wrangler login`. Create
the KV namespace — `npx wrangler kv namespace create HARO` — and paste the id
it prints into `wrangler.toml`. Set the one secret: `npx wrangler secret put
ADMIN_SECRET` (make it long and random; the same value goes into the GitHub
secret `HARO_ADMIN_SECRET`). Fill in `CLERK_PUBLISHABLE_KEY` (the `pk_live_…`
from the Clerk dashboard; it is public), `CHECKOUT_URL` (the gundeck.ai
subscribe route, appendix item A2 in docs/LAUNCH.md) and `MANAGE_URL` in
`[vars]`. `npx wrangler deploy`. The `routes` line attaches the custom domain:
if the DNS record does not exist, wrangler creates it; if you manage DNS by
hand, add `marketharo CNAME market-haro.<your-subdomain>.workers.dev`, proxied.

**5b. Clerk** (in the Clerk dashboard for the gundeck.ai instance; see
docs/LAUNCH.md for the gundeck.ai side).
- *Sessions → Customize session token*: add `"public_metadata": "{{user.public_metadata}}"`
  so the entitlement rides in the token. This is the one setting the gate
  cannot work without.
- The Worker's domain is a subdomain of the instance's primary domain, so the
  signed-in state carries over on its own. If the splash still shows "sign in"
  while you are signed in on gundeck.ai, add `marketharo.gundeck.ai` under
  *Domains* as a satellite and redeploy.

**5c. The entitlement.** The Worker's defaults expect Stripe's webhook to write
`publicMetadata.marketHaro = {status: "active"|"trialing"|…, plan, currentPeriodEnd}`
on the Clerk user (either spelling of the key works). If your webhook writes a
different shape, set `ENTITLEMENT_PATH` (dotted path to the status) and
`ENTITLEMENT_VALUES` in `wrangler.toml`; if you move to Clerk Billing, set
`ENTITLEMENT_PLAN` to the plan slug instead and leave the path empty.

**5d. The vanity domain.** `marketharo.io` is a redirect, not a host: the app stays
on `marketharo.gundeck.ai` because that shares a root domain with gundeck.ai and
so shares its signed-in state; a different root domain would need Clerk's
satellite-domain setup. *Rules → Redirect Rules* → root and www → `https://marketharo.gundeck.ai${path}`,
301. The domain is registered at Namecheap; leave it there and point its
nameservers at Cloudflare (Add a site → Free → copy the two nameservers →
Namecheap → Manage → Nameservers → Custom DNS), because Namecheap's own redirect
is HTTP-only and cannot preserve paths. In Cloudflare add a proxied placeholder
`A @ 192.0.2.1` and `CNAME www → marketharo.io` so the proxy terminates the
request, set SSL/TLS to Full, then the rule: filter
`(http.host eq "marketharo.io") or (http.host eq "www.marketharo.io")`, dynamic
target `concat("https://marketharo.gundeck.ai", http.request.uri.path)`, 301,
preserve query string. Say `marketharo.io` everywhere people read; the redirect does the rest. If
the product ever needs to stand alone, that is the day to make the .io a satellite
domain and move the Worker's route.

**5e. Check it.** `curl https://marketharo.gundeck.ai/health` → `{"ok":true}`;
`/me` → `{"signed_in":false,"entitled":false}`.
Locally, `HARO_ADMIN_SECRET=… python -m radar publish` pushes the report and
the track record; open the site signed out (splash), signed in without a
subscription (splash, "no Market Haro subscription yet"), and signed in with one
(the report, and the watchlist status line says "synced to your account").
`cd worker && npm test` runs the gate against signed test tokens.

### 6. Where the report lives

Only in the Worker's KV, served only to entitled sessions with
`Cache-Control: private, no-store`. The GitHub Actions run keeps a copy of each
day's `out/` as a run artifact for seven days, which is your fallback if a push
ever fails. Nothing else hosts it.

---

## Verifying it actually works

```bash
# 1. The archive round-trips
python -m radar export
RADAR_DB=/tmp/v.sqlite3 python -m radar restore
RADAR_DB=/tmp/v.sqlite3 python -m radar stats

# 2. Re-exporting an unchanged database changes no bytes
python -m radar export      # must print "nothing changed"

# 3. Everything passes
python tests/test_pipeline.py
```

That second one matters more than it looks: the export is deterministic — sorted
rows, sorted JSON keys, `None` fields omitted — so an unchanged month produces a
byte-identical file. That's what makes "commit only if changed" in CI safe, and
what stops the repo filling with no-op commits.

---

## Running costs

| | |
|---|---|
| GitHub Actions, private repo | 2,000 min/month free; this uses ~3 min/day ≈ **90 min** |
| GitHub storage | ~85 MB/year of text |
| Cloudflare Worker + KV | free tier: 100k requests/day, 1 GB KV; the report is ~4.5 MB, one key |
| Clerk, Stripe | gundeck.ai's existing accounts; Stripe's usual fee per charge |
| tcgapi.dev Pro | your existing plan; a daily run costs ~60 requests of 10,000 |

So: **free**, with a wide margin on every limit.

---

## The two things that will break, eventually

**The market heat panel goes stale.** `data/market_heat.json` is a manual capture
— Google Trends, Semrush and the TCGplayer seller blog aren't one API with one
key, and pretending the CLI can fetch them would have meant writing a fetcher
that silently returns nothing. The panel greys itself out past 30 days and tells
you its age. Refresh it monthly; `radar heat --template` prints the exact queries.

**The score stops working.** Every threshold in `invest.py` was calibrated on one
90-day window in a market that rose the whole way through. `radar validate` runs
monthly and appends to `data/validation_history.json`. Watch the drift, not any
single run:

| | |
|---|---|
| ρ > 0.20, top quintile beats the pool | working |
| ρ near 0, quintiles overlapping | it has stopped separating |
| ρ < 0 | inverted — stop acting on the ranking |

The seeded baseline is ρ = 0.238 (n = 117).

---

## If you'd rather not use GitHub Actions

The project is a plain Python package with no framework, so anything that can run
a cron job works. On a VPS or a Pi:

```bash
git clone git@github.com:aaron-TGM/gundam-price-radar.git
cd gundam-price-radar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env      # add your key
.venv/bin/python -m radar restore
```

```cron
10 9 * * *  cd /srv/gundam-price-radar && .venv/bin/python -m radar run >> log 2>&1
```

Serve `out/` behind whatever auth you like — Caddy with `basicauth` is two lines.
You still want `radar export` in the loop and the archive pushed somewhere; a
disk that isn't backed up is not a place to keep the one dataset you can't
rebuild.
