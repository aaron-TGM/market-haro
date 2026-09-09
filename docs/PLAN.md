# Market Haro — the plan to go live

For Aaron. Six blocks, in order; each says what you do, where, how long, and how you know it worked. Blocks 1–3 are yours alone and can happen today. Block 4 is Manus's (the handoff is `docs/HANDOFF-gundeck.md`) and runs in parallel. Blocks 5–6 need both done. Realistic elapsed time: launch on the day after Manus finishes.

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

## 2. The site Worker — 45 minutes, today

Where: your terminal, Cloudflare dashboard, Clerk dashboard. Step list also in `DEPLOY.md §5`.

1. `cd worker && npm install && npx wrangler login`.
2. `npx wrangler kv namespace create HARO` → paste the printed `id` into `wrangler.toml` under `[[kv_namespaces]]`.
3. `npx wrangler secret put ADMIN_SECRET` → paste a long random string (make one: `openssl rand -hex 32`). Keep it; step 6 uses it.
4. Edit `wrangler.toml` `[vars]`: `CLERK_PUBLISHABLE_KEY` = the `pk_live_…` from Clerk → API keys. Leave `CHECKOUT_URL` and `MANAGE_URL` as they are unless Manus tells you different paths.
5. `npx wrangler deploy`. It attaches `marketharo.gundeck.ai` as a custom domain (creates the DNS record in the gundeck.ai zone; if the zone isn't in your Cloudflare account, add a CNAME `marketharo` → the `workers.dev` URL it prints, proxied).
6. GitHub → the repo's secrets → **`HARO_ADMIN_SECRET`** = the same string from step 3. Re-run the *daily* workflow; its last step now pushes the pages.
7. Clerk dashboard → **Sessions → Customize session token** → add `"public_metadata": "{{user.public_metadata}}"` → save. Check Clerk → User & authentication that sign-ups are on.

**Done when:** `https://marketharo.gundeck.ai/health` → `{"ok":true}`; `/me` → `{"signed_in":false,"entitled":false}`; the bare URL shows the splash; `/track-record` shows the track record; and signed in to gundeck.ai in the same browser, the bare URL shows the splash with "Signed in as you@… no Market Haro subscription yet" (this proves Clerk carries over; if it still says "sign in", add the subdomain as a satellite domain in Clerk → Domains and redeploy).

## 3. marketharo.io — 15 minutes plus DNS propagation, today

Where: Cloudflare, Namecheap. Also in `DEPLOY.md §5d`.

1. Cloudflare → Add a site → `marketharo.io` → Free → copy the two nameservers.
2. Namecheap → Domain List → Manage → Nameservers → *Custom DNS* → paste both → save.
3. Cloudflare → DNS: `A @ 192.0.2.1` proxied; `CNAME www marketharo.io` proxied. SSL/TLS → Full.
4. Rules → Redirect Rules → create: expression `(http.host eq "marketharo.io") or (http.host eq "www.marketharo.io")`, dynamic redirect to `concat("https://marketharo.gundeck.ai", http.request.uri.path)`, 301, preserve query string.

**Done when:** `https://marketharo.io/track-record` lands on the track record (may take up to a day for nameservers; usually an hour).

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
