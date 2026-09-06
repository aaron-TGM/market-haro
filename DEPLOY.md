# Deploying this as a standalone project

Target: it runs itself every morning, the price history accumulates somewhere it
can't be lost, and you can open the dashboard from your phone without the world
being able to.

The shape that gets you there is **GitHub Actions for the schedule, git for the
data, Ghost for subscribers, payments, the email and the members-only report**.
Nothing here needs a server of your own; Ghost Pro or a $6 VPS is the only
running cost beyond the API plan.

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

Secrets are write-only once saved and are not exposed to forked-PR runs. Do not
put the key in `config.yaml` — that file is committed.

### 4. Turn the workflow on

`.github/workflows/daily.yml` is already in the repo. It runs at **13:10 UTC**,
after TCGplayer's overnight batch has settled, and you can trigger it by hand
from the Actions tab any time.

Each run: restore → sync → build dashboard → export → run the test suite →
commit → publish. The tests run *before* the commit on purpose, so a broken run
can't push a corrupted history.

On the 1st of each month it also runs `radar validate` and commits the result, so
score decay shows up in `data/validation_history.json` without you remembering to
check.

Trigger it once manually and watch it go green before trusting the schedule.

> **GitHub disables scheduled workflows after 60 days of repo inactivity.** The
> daily commit counts as activity, so this only bites if the workflow is already
> failing — which is exactly when you'd want it not to. Turn on Actions failure
> notifications: **Settings → Notifications → Actions → email on failure**.

### 5. Ghost — subscribers, payments, email, and the private report

This is the layer between the report and a paying reader, and Ghost does all of it:
Stripe memberships, member-only content, the email send, and magic-link sign-in.

1. Create the site (Ghost Pro, or self-hosted on a $6 VPS). Under **Settings →
   Membership** connect Stripe and set up **one paid tier**:

   | | |
   |---|---|
   | Monthly | **$35** |
   | Yearly | **$300** |
   | Free trial | **7 days** (Settings → Membership → the tier → "Free trial days") |
   | Free tier | off |
   | Founding / launch discount | none |

   Two settings make "no free" real, and both are easy to miss:
   **Settings → Membership → Subscription access → Paid-members only** (nobody can
   sign up without paying), and in **Settings → Portal** untick the free tier so it
   never appears on the signup screen. `radar publish` already sends only to
   `status:-free` and publishes with visibility `paid`, so the code side is
   consistent with this whether or not the settings are — but without them a
   free signup could still exist and simply see nothing, which is confusing rather
   than harmful.
2. **Settings → Integrations → Add custom integration** → name it `market-haro`.
   Copy the **Admin API key** (it looks like `<id>:<hex secret>`) and the site URL.
3. Add two repo secrets:

| Name | Value |
|---|---|
| `GHOST_URL` | `https://your-site.ghost.io` (no trailing path) |
| `GHOST_ADMIN_KEY` | the Admin API key from step 2 |

4. In `config.yaml` under `publish:` set `report_url` to where the report page will
   live — `https://<your-site>/market-haro/` — so the button in the email points at
   it. Everything else under `publish:` can stay as it is.
5. Run it once by hand before trusting the schedule:

```bash
GHOST_URL=... GHOST_ADMIN_KEY=... python -m radar publish --dry-run   # shows what would go out
GHOST_URL=... GHOST_ADMIN_KEY=... python -m radar publish --no-email  # publishes, no send
```

Open the site as a paid member and check the report page renders. Then let the
workflow send for real.

What gets published each day: the digest as a **paid post emailed to every paying
member** (`status:-free`), and the full dashboard as a **paid page at `/market-haro/`**
— the same slug every day, so the link in any past email opens the latest report.
Free members and the public see neither.

If a day's feed is late the issue still goes out; the feed age is the first line
and the subject. If Ghost itself is unreachable the workflow fails loudly and the
dashboard is still kept as a run artifact — turn on failure notifications so you
find out the same morning.

What gets published each day, in full: the digest as a **paid post emailed to
every paying member**, the full dashboard as a **paid page at `/market-haro/`**,
and the **track record as a public page at `/track-record/`** — the one page
without a paywall, because a prospect deserves to see the ranking scored before
they pay. Set `track_slug` under `publish:` to change its address.

### 5b. The sync + alerts Worker (optional, and what makes it a $35 product)

Without this, every subscriber's watchlist lives in their browser and dies on
their phone. With it, the watchlist and holdings follow the member across
devices, the page opens with their P&L, and they get one email on the days
something on their list changed — trend broke, a card listed below what it
sells for, a top-20 move, a release in seven days. It is one Cloudflare
Worker and one KV namespace; free tier covers thousands of members.

1. `cd worker && npm install`, then create the KV namespace:
   `npx wrangler kv namespace create HARO` — paste the id it prints into
   `wrangler.toml`. Set `GHOST_URL` and `REPORT_URL` there too.
2. Secrets: `npx wrangler secret put ADMIN_SECRET` (any long random string) and,
   for email, `npx wrangler secret put RESEND_API_KEY` (a [Resend](https://resend.com)
   key with the sending domain verified; set `MAIL_FROM` in `wrangler.toml`).
   Without the Resend key the Worker still syncs watchlists; it just cannot send.
3. `npx wrangler deploy`. Note the Worker URL it prints.
4. In `config.yaml` under `publish:` set `sync_url` to that URL. Add the repo
   secret `HARO_ADMIN_SECRET` with the same value as step 2, so `radar publish`
   can push the day's issue to the Worker.
5. Check it: open the report as a signed-in member; the line under the index
   should say "Watchlist synced to your account." Star a card on your laptop,
   open the report on your phone, it is there.

How identity works, so you can explain it to a subscriber: Ghost issues a
signed token to the logged-in member at `/members/api/session`; the page sends
that token to the Worker; the Worker verifies the signature against the
site's published keys. There is no password, no account to create, and the
Worker never sees a Ghost admin key. The alert rules live in `radar/alerts.py`
and are mirrored in the Worker; `python tests/test_pipeline.py` writes the
cases and `cd worker && npm test` replays them, so the two cannot drift.

**The weekly note.** Drop a file at `data/notes/YYYY-MM-DD.md` (a few hundred
words, small Markdown) and it appears at the top of the page and the email for
ten days. No file, no slot. This is the one thing in the product a person
writes, and it is the thing subscribers forward.

### 6. The private URL without Ghost (optional)

GitHub Pages on a private repo requires a paid plan, so the free path is
Cloudflare — and Cloudflare Access is genuinely better for this anyway, since it
puts an email login in front of the page rather than relying on an unguessable
address.

1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Direct Upload**.
   Name it `gundam-radar`. Don't upload anything; the workflow does that.
2. **My Profile → API Tokens → Create Token → Custom token**, one permission:
   *Account → Cloudflare Pages → Edit*.
3. Grab your account ID from the dashboard URL:
   `dash.cloudflare.com/<account-id>/...`
4. Back in GitHub, add two more secrets:

| Name | Value |
|---|---|
| `CLOUDFLARE_API_TOKEN` | the token from step 2 |
| `CLOUDFLARE_ACCOUNT_ID` | the ID from step 3 |

5. **Lock it down** — this is the step that makes the URL private, and it is easy
   to skip: Cloudflare dashboard → **Zero Trust → Access → Applications → Add an
   application → Self-hosted**. Point it at `gundam-radar.pages.dev`, add a policy
   of *Allow → Emails → aaron@tuffghostmedia.com*, choose the one-time-PIN login
   method. Free tier covers up to 50 users.

Without step 5 the page is world-readable at a guessable address. With it, you
get an email code on first visit and a session cookie after.

If you skip Cloudflare entirely, the workflow still builds the dashboard and
uploads it as a run artifact — the publish step is conditional on the token being
present, so nothing fails. You just have to download it from the Actions tab.

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
| Cloudflare Pages | free, unlimited requests |
| Cloudflare Access | free up to 50 users |
| Cloudflare Worker + KV | free tier: 100k requests/day, 1 GB KV |
| Resend | free tier: 3,000 emails/month; one email per member per day at most |
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
