# Market Haro — the plan to go live

For Aaron. Six blocks, in order; each says what you do, where, how long, and how you know it worked. Blocks 1–3 are yours alone and can happen today (block 3 waits on block 2's DNS going active). Block 4 is Manus's (the handoff is `docs/HANDOFF-gundeck.md`) and runs in parallel. Blocks 5–6 need both done. Realistic elapsed time: launch on the day after Manus finishes.

---

## 1. Repo and the daily run — 30 minutes, today

Where: your machine, GitHub.

1. Unzip the latest `market-haro-repo.zip`, `cd gundam-price-radar`, confirm `git log --oneline -1` shows the newest commit.
2. Create the private repo `aaron-TGM/gundam-price-radar` on GitHub (empty, no README). Then:
   `git remote add origin git@github.com:aaron-TGM/gundam-price-radar.git && git push -u origin main`
3. Check nothing secret went up: `git ls-files | grep -i env` prints only `.env.example`.
4. Repo → Settings → Secrets and variables → Actions → **New repository secret**: `TCGAPI_KEY` = your tcgapi.dev key.
5. Repo → Actions → *daily* → **Run workflow**. Wait ~4 minutes.
6. Settings → Notifications: Actions failures → email.

**Done when:** the run is green, a new commit "history: 2026-09-xx" appeared, and the run's artifact (`issue-…`) downloads and its `dashboard.html` opens in your browser.

## 2. marketharo.io onto Cloudflare — 15 minutes plus DNS propagation, today

Where: Cloudflare, Namecheap. gundeck.ai is not touched at any point.

1. Cloudflare → **Add a site** → `marketharo.io` → Free → it scans (nothing to keep) → copy the two nameservers.
2. Namecheap → Domain List → marketharo.io → Manage → **Nameservers → Custom DNS** → paste both → save.
3. Wait for Cloudflare's "site is active" email (minutes to a few hours). Then Cloudflare → SSL/TLS → **Full**.
4. DNS: add `CNAME` `www` → `marketharo.io`, proxied (orange). Rules → Redirect Rules → Create: expression `http.host eq "www.marketharo.io"`, dynamic target `concat("https://marketharo.io", http.request.uri.path)`, 301, preserve query string → Deploy.

**Done when:** the zone shows Active in Cloudflare. (The apex itself gets its record from the Worker in block 3.)

## 3. The site Worker — 30 minutes, once block 2 is active

Where: cmd on the PC, Clerk dashboard, GitHub.

1. `node --version`. If not recognized: `winget install OpenJS.NodeJS.LTS`, then a new cmd window.
2. ```
   cd %USERPROFILE%\Downloads\gundam-price-radar\worker
   npm install
   npx wrangler login
   npx wrangler kv namespace create HARO
   ```
   Paste the printed `id` into `wrangler.toml` (Notepad) in place of `replace-with-your-kv-namespace-id`. In the same file set `CLERK_PUBLISHABLE_KEY` to the `pk_live_…` from Clerk → API keys. Save.
3. `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"` — copy the string; it's your admin secret, used twice.
4. `npx wrangler secret put ADMIN_SECRET` → paste it.
5. `npx wrangler deploy` → attaches `marketharo.io` as the Worker's custom domain (the zone is in Cloudflare now). `https://marketharo.io/health` → `{"ok":true}`; the bare URL → the splash.
6. Clerk dashboard → **Domains → Add satellite domain** → `marketharo.io`. Clerk shows a CNAME to add (something like `clerk.marketharo.io → frontend-api.clerk.services`): Cloudflare → DNS → add it exactly, **DNS only (grey cloud)**. Back in Clerk, wait for it to verify (minutes).
7. Clerk dashboard → **Sessions → Customize session token** → add `"public_metadata": "{{user.public_metadata}}"` → save. Check User & authentication that sign-ups are enabled.
8. GitHub → repo → Settings → Secrets → **`HARO_ADMIN_SECRET`** = the string from step 3. Actions → *daily* → Run workflow; its last step now pushes the pages. `https://marketharo.io/track-record` shows the track record.
9. Commit the config so the repo matches what's deployed (the KV id and publishable key aren't secrets):
   ```
   cd ..
   git add worker/wrangler.toml
   git commit -m "worker: KV id and publishable key"
   git push
   ```

**Done when:** `/health` ok; splash on the bare URL; `/track-record` live; *Already subscribed? Sign in* hops to gundeck.ai's sign-in and returns you to marketharo.io, and the splash then says "Signed in as you@… no Market Haro subscription yet". If the return lands you on gundeck.ai instead of back on marketharo.io, gundeck.ai's sign-in page isn't honouring `redirect_url` for our origin — that's in the handoff for Manus.

## 4. Manus builds the gundeck.ai side — their time; send the handoff today

Send `docs/HANDOFF-gundeck.md`. It is self-contained. What comes back to you: confirmation of the subscribe route path (`/market-haro/subscribe`) and the account page path; if either differs, change `CHECKOUT_URL` / `MANAGE_URL` in `wrangler.toml` and `npx wrangler deploy` (two minutes).

Ask them to run section 9 of the handoff in Stripe test mode before saying done.

## 5. Rehearsal — 45 minutes, the day Manus says done

Where: a phone and a laptop, a second email address, Stripe test mode first, then live mode once.

1. Signed out, phone: `marketharo.io` → splash → *Start monthly* → sign up as the second email → Checkout → test card → back → "Finishing…" → the report. Star three cards; enter copies and cost on one.
2. Laptop, same account: sign in → the starred cards and the holding are there ("Watchlist synced to your account").
3. gundeck.ai: the account page shows *Market Haro · active until …*; paid GUNDECK features work on this account.
4. Cancel from the account page → the report still opens (period not over) → in Stripe test dashboard delete the subscription → reload → the splash says "no Market Haro subscription".
5. Switch Stripe to live. Subscribe yourself with a real card on the annual plan (you'll want the real receipt and portal flow once). Leave it running; you're the first subscriber.
6. Sign in as a Lifetime holder → Checkout shows a 30-day trial.

**Done when:** all six, and `data/rankings/` in the repo has one more day than yesterday (the pipeline kept running through all this).

## 6. Launch — one morning

1. Nav item and pricing cards live on gundeck.ai (Manus).
2. The email to your GUNDECK list, from GUNDECK.AI, the text in `docs/LAUNCH.md` Phase 4. Send once; a reminder to non-openers five days later; stop.
3. One post wherever your audience is, linking `marketharo.io` and `marketharo.io/track-record`.
4. That evening: Stripe → Subscriptions, count trials. Actions tab: still green.

## After launch — the standing list

- **Daily, 30 seconds:** did the Action run green? (Email on failure covers this.)
- **Weekly, 10 minutes:** Stripe trials → paid → churn; skim the report once as a subscriber.
- **Sep 10 onward:** the track record's first 30-day window closes; the "of N calls resolved…" sentence appears on `/track-record` by itself.
- **Monthly (1st), 5 minutes:** read the verdict line the workflow appended to `data/validation_history.json`.
- **Quarterly:** rotate `ADMIN_SECRET` (Worker) and `HARO_ADMIN_SECRET` (GitHub) together; `npx wrangler kv key list` → export watchlists.
- **When anything breaks:** the last green run's artifact is the fallback page; `/me` tells you what the Worker sees for a user; the three checks in the handoff's section 10 cover almost every "I can't see it".

## What you will spend

tcgapi.dev Pro (already paying). Cloudflare free. GitHub free. Clerk and Stripe as today plus Stripe's fee per charge. Break-even is about thirty subscribers.
