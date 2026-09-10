# Market Haro — the plan to go live

For Aaron. Six blocks, in order; each says what you do, where, how long, and how you know it worked. Blocks 1–3 are done (Sep 10). Block 4 is Manus's (the handoff is `docs/HANDOFF-gundeck.md`) and runs in parallel. Blocks 5–6 need both done. Realistic elapsed time: launch on the day after Manus finishes.

---

## 1. Repo and the daily run — done Sep 9

Where: your machine, GitHub.

1. Unzip the latest `market-haro-repo.zip`, `cd gundam-price-radar`, confirm `git log --oneline -1` shows the newest commit.
2. Create the private repo `aaron-TGM/market-haro` on GitHub (empty, no README). Then:
   `git remote add origin https://github.com/aaron-TGM/market-haro.git && git push -u origin main`
3. Check nothing secret went up: `git ls-files | grep -i env` prints only `.env.example`.
4. Repo → Settings → Secrets and variables → Actions → **New repository secret**: `TCGAPI_KEY` = your tcgapi.dev key.
5. Repo → Actions → *daily* → **Run workflow**. Wait ~4 minutes.
6. Settings → Notifications: Actions failures → email.

**Done when:** the run is green, a new commit "history: 2026-09-xx" appeared, and the run's artifact (`issue-…`) downloads and its `dashboard.html` opens in your browser.

## 2. marketharo.io onto Cloudflare — done Sep 10

Where: Cloudflare, Namecheap. gundeck.ai is not touched at any point.

1. Cloudflare → **Add a site** → `marketharo.io` → Free → it scans (nothing to keep) → copy the two nameservers.
2. Namecheap → Domain List → marketharo.io → Manage → **Nameservers → Custom DNS** → paste both → save.
3. Wait for Cloudflare's "site is active" email (minutes to a few hours). Then Cloudflare → SSL/TLS → **Full**.
4. DNS: add `CNAME` `www` → `marketharo.io`, proxied (orange). Rules → Redirect Rules → Create: expression `http.host eq "www.marketharo.io"`, dynamic target `concat("https://marketharo.io", http.request.uri.path)`, 301, preserve query string → Deploy.

**Done when:** the zone shows Active in Cloudflare. (The apex itself gets its record from the Worker in block 3.)

## 3. The site Worker — done Sep 10, through the Cloudflare dashboard

Where: Cloudflare dashboard, Clerk dashboard, GitHub. No command line was needed; the Worker is one file, pasted into Cloudflare's editor.

What exists now, for the record:

- Cloudflare → Workers & Pages → **market-haro**: the code from `worker/src/index.js`; Settings → Variables: the eight `CLERK_*`/URL/entitlement values from `wrangler.toml` plus the secret `ADMIN_SECRET`; Bindings: KV namespace `HARO` → `HARO`; Domains: custom domain `marketharo.io`.
- Clerk → Domains → Satellites: `marketharo.io`, DNS verified (`clerk.marketharo.io` CNAME, DNS-only, in the Cloudflare zone). Sessions → session token carries `public_metadata`.
- Tested: `/health` ok; the splash on the bare URL; *Sign in* hops to gundeck.ai, and a signed-in GUNDECK account is recognised on marketharo.io ("Signed in as … no Market Haro subscription yet"). The return-to-marketharo.io after sign-in is the one gap, and it's on Manus's list (handoff, "A way to start checkout").

**To change the Worker later:** edit `worker/src/index.js` in the repo, run `npm test` in `worker/`, then Cloudflare → market-haro → Edit code → replace all → Deploy. The dashboard is the source of truth for the deployed settings; `wrangler.toml` mirrors them for reference. Don't run `wrangler deploy` — it would replace the dashboard's configuration with the file's.

Still to do from this block: GitHub → repo → Settings → Secrets and variables → Actions → **`HARO_ADMIN_SECRET`** = the same value as the Worker's `ADMIN_SECRET`; Actions → *daily* → Run workflow. When it's green, `https://marketharo.io/track-record` is live.

## 4. Manus builds the gundeck.ai side — their time; send the handoff today

Sent Sep 10; Manus's readiness review came back the same day and agrees with the architecture. Their finding that changes the timeline: gundeck.ai's current code has no subscriptions at all (only the two one-time purchases), so Block 4 is a full billing build — recurring checkout, lifecycle webhooks, a per-product subscription table, the Customer Portal, the redirect fix — not a patch. Budget accordingly; nothing else in this plan changes. `docs/HANDOFF-gundeck.md` is self-contained and, as of Sep 10, it also carries GUNDECK's own pricing change (Pass → $3/month, new $29/year, Lifetime $29 → $59) and the two post-checkout cross-sell screens — so it's a bigger job for Manus than the Market Haro plumbing alone. What comes back to you: confirmation of the subscribe route path (`/market-haro/subscribe`), the account page path, and the pricing page path (our post-checkout banner links to it, assumed `/pricing`); if any differ, change `CHECKOUT_URL` / `MANAGE_URL` / `GUNDECK_URL` in the Worker's Settings → Variables (two minutes).

Your own piece of Block 4: the Lifetime price goes to $59 on **October 30, 2026** (Stardust Trails / GD06 release day) — Manus has the date. The announcement to your list ("last two weeks at $29") goes out around **October 16**, once the new subscription Prices are live; if Manus isn't done by then, the announcement waits and the cutover moves with it — don't announce a date the site can't honour.

Ask them to run the handoff's "How we'd know it's working" list in Stripe test mode before saying done. Their Sep 10 readiness review adds a longer test-mode gate (duplicate-checkout protection, event replay, metadata integrity, portal); that's the one to hold them to.

## 5. Rehearsal — 45 minutes, the day Manus says done

Where: a phone and a laptop, a second email address, Stripe test mode first, then live mode once.

1. Signed out, phone: `marketharo.io` → splash → *Start monthly* → sign up as the second email → Checkout → test card → back → "Finishing…" → the report, with the one-time GUNDECK banner across the top (*Not now* dismisses it). Star three cards; enter copies and cost on one.
2. Laptop, same account: sign in → the starred cards and the holding are there ("Watchlist synced to your account").
3. gundeck.ai: the account page shows *Market Haro · active until …*.
4. Cancel from the account page → the report still opens (period not over) → in Stripe test dashboard delete the subscription → reload → the splash says "no Market Haro subscription".
5. Switch Stripe to live. Subscribe yourself with a real card on the annual plan (you'll want the real receipt and portal flow once). Leave it running; you're the first subscriber.
6. Buy GUNDECK (test mode) as a third account → the post-checkout page offers Market Haro. And the reverse: the Market Haro subscriber from step 1 does *not* have GUNDECK's paid features.

**Done when:** all six, and `data/rankings/` in the repo has one more day than yesterday (the pipeline kept running through all this).

## 6. Launch — one morning

1. Nav item and pricing cards live on gundeck.ai (Manus).
2. The email to your GUNDECK list, from GUNDECK.AI, the text in `docs/LAUNCH.md` Phase 4 — it now carries both stories: Market Haro is live, and GUNDECK's pricing is changing (Lifetime to $59 on the date you set). Send once; a reminder to non-openers five days later; stop.
3. One post wherever your audience is, linking `marketharo.io` and `marketharo.io/track-record`.
4. That evening: Stripe → Subscriptions, count trials. Actions tab: still green.

## After launch — the standing list

- **Daily, 30 seconds:** did the Action run green? (Email on failure covers this.)
- **Weekly, 10 minutes:** Stripe trials → paid → churn; skim the report once as a subscriber.
- **Sep 10 onward:** the track record's first 30-day window closes; the "of N calls resolved…" sentence appears on `/track-record` by itself.
- **Oct 16:** the Lifetime-increase announcement. **Oct 30:** GD06 releases; Lifetime is $59 from today; tick the *backfill* box on the next manual run so the new cards get their history.
- **Monthly (1st), 5 minutes:** read the verdict line the workflow appended to `data/validation_history.json`.
- **Quarterly:** rotate `ADMIN_SECRET` (Worker) and `HARO_ADMIN_SECRET` (GitHub) together; `npx wrangler kv key list` → export watchlists.
- **When anything breaks:** the last green run's artifact is the fallback page; `/me` tells you what the Worker sees for a user; the three checks at the end of the handoff ("What we'll never do") cover almost every "I can't see it".

## What you will spend

tcgapi.dev Pro (already paying). Cloudflare free. GitHub free. Clerk and Stripe as today plus Stripe's fee per charge. Break-even is about thirty Market Haro subscribers.
