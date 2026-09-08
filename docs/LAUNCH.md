# Launch plan: Market Haro on Ghost, sold to GUNDECK customers

From the repo you have to a paying subscriber opening the report with a magic link. Six phases, about a week of calendar time, roughly six hours of your hands. Every step names the screen it happens on. Nothing here requires code changes; everything the code needs is already in the repo.

**How the "tokenized" login works, in one paragraph, so you can explain it to customers:** Ghost does not use passwords. A member enters their email, Ghost sends a one-time sign-in link, and clicking it sets a signed session cookie for your site. The report is a members-only page on that site, so the cookie is the access control. For the watchlist and alerts, the page asks Ghost for a short-lived signed token for the logged-in member (`/members/api/session`) and hands it to the Worker, which verifies the signature against your site's published keys. Nobody creates an account, nobody stores a password, and the Worker never holds a Ghost admin key. Stripe holds the card; Ghost holds the membership; you hold the data.

---

## Phase 0 — Accounts and decisions (30 minutes)

| Need | Choice | Why |
|---|---|---|
| Ghost | **Ghost(Pro)** on a plan that allows custom integrations (the Admin API is how the pipeline publishes), or self-hosted Ghost 5.x | Ghost(Pro) sends the email, handles Stripe, and updates itself. Self-host only if you already run a server. |
| Domain | `haro.gundeck.ai` (recommended) or a standalone domain | Subdomain keeps the brand and makes the GUNDECK cross-sell natural. |
| Stripe | Your existing Stripe account, or a new one for this product | Ghost connects with one click; payouts land in Stripe as usual. |
| Email sending | Ghost(Pro) sends the daily issue. **Resend** sends per-member alerts from the Worker | Ghost can't send a different email to each member; the Worker can. |
| Cloudflare | Free account, one Worker, one KV namespace | Watchlist sync and alerts. |
| GitHub | Private repo, Actions enabled | The daily run. Free tier covers it. |
| tcgapi.dev | Pro plan, the key already in your `.env` | ~60 requests a day of 10,000. |

Decide once, before Phase 2: **monthly $35, yearly $300, 7-day trial, no free tier, no founding discount.** The one exception is a GUNDECK-customer offer (Phase 5), which is a coupon, not a tier.

---

## Phase 1 — The pipeline runs by itself (Day 1, ~1 hour)

1. **Push the repo** to a private GitHub repository.
   ```bash
   cd gundam-price-radar
   git remote add origin git@github.com:aaron-TGM/gundam-price-radar.git
   git push -u origin main
   git ls-files | grep -i "\.env$"     # must print nothing
   ```
2. **Repo secrets** — Settings → Secrets and variables → Actions → New repository secret:
   `TCGAPI_KEY` = your tcgapi.dev key, and `ANTHROPIC_API_KEY` = a key from
   console.anthropic.com, which writes each card's case, the email's opening and the
   weekly-note draft (about a dollar a day; without it the templates run).
3. **Run it once by hand** — Actions → *daily* → Run workflow. Watch it: restore → sync → build → export → test → commit. Green means the archive committed a new day and `out/` was kept as a run artifact. Download the artifact and open `index.html`; it should be today's report.
4. **Turn on failure email** — your GitHub profile → Settings → Notifications → Actions → *Send notifications for failed workflows*. This is the only monitoring you need: the issue goes out even on a late feed, so the failure you care about is the run itself.

*Check:* the `data/history/2026-09.ndjson` file in the repo grew by one day.

---

## Phase 2 — The Ghost site (Day 1–2, ~2 hours)

**2a. Create the site and the domain.**
Ghost(Pro) → new site → title *Market Haro*. Settings → General → set the site description to the one-liner: *The daily market terminal for people who invest in the Gundam Card Game.* Settings → Domain → add `haro.gundeck.ai`, then add the CNAME it gives you at your DNS host. Wait for the lock icon.

**2b. Connect Stripe.**
Settings → Membership → *Connect with Stripe* → authorise. Use live mode. (Ghost takes 0% on Ghost(Pro); Stripe's usual fee applies.)

**2c. The tier.**
Settings → Membership → Tiers → the default paid tier → rename to **Market Haro** →
Monthly **$35**, Yearly **$300**, *Free trial days* **7**, *Welcome page* `/market-haro/`.
Benefits (these print on the signup card — keep them to what the product does):
- The daily report: every English single ranked, gated and explained
- Market Haro 50, sealed screen, release playbook
- Your holdings and alerts, across your devices
- The daily email, and the weekly note

**2d. Make "no free tier" real** — two settings people miss:
Settings → Membership → *Subscription access* → **Paid-members only**.
Settings → Portal → *Tiers* → untick the **Free** tier so it never appears on the signup screen. Also under Portal: turn on *Show portal button*, set the signup text to *Start 7-day trial*.

**2e. The newsletter.**
Settings → Newsletters → the default newsletter → name **Market Haro Daily**, sender name *Market Haro*, sender email `haro@gundeck.ai` (Ghost(Pro) will verify the address). Turn on *Show badge* off, *Feedback* off. Design: header with title only; the digest carries its own layout.

**2f. The integration key the pipeline uses.**
Settings → Integrations → *Add custom integration* → name **market-haro** → copy the **Admin API key** (`id:secret`) and the site URL.
Back in GitHub → repo secrets: `GHOST_URL` = `https://haro.gundeck.ai`, `GHOST_ADMIN_KEY` = the key.

**2g. Point the email at the report.**
In `config.yaml` under `publish:` set `report_url: https://haro.gundeck.ai/market-haro/`. Commit and push.

**2h. First publish, safely.**
```bash
GHOST_URL=https://haro.gundeck.ai GHOST_ADMIN_KEY=... python -m radar publish --dry-run
GHOST_URL=https://haro.gundeck.ai GHOST_ADMIN_KEY=... python -m radar publish --no-email
```
Then open the site. `/market-haro/` should show the paywall to a stranger and the report to a paid member; `/track-record/` should be public. Trigger the workflow by hand once more and let it send the email for real — to you, because you are the only member.

*Check:* you received the Market Haro Daily email, clicked *Open today's report*, and the report opened without a password prompt.

---

## Phase 3 — The Worker: watchlists that follow the member, and alerts (Day 2, ~45 minutes)

```bash
cd worker
npm install
npx wrangler login
npx wrangler kv namespace create HARO        # paste the id it prints into wrangler.toml
```
Edit `wrangler.toml`: `GHOST_URL = "https://haro.gundeck.ai"`, `REPORT_URL = "https://haro.gundeck.ai/market-haro/"`, `MAIL_FROM = "Market Haro <haro@gundeck.ai>"`.

```bash
npx wrangler secret put ADMIN_SECRET          # any long random string; keep it
npx wrangler secret put RESEND_API_KEY        # from resend.com after verifying gundeck.ai
npx wrangler deploy                           # prints the Worker URL
```

Then: `config.yaml → publish.sync_url` = the Worker URL. GitHub repo secret `HARO_ADMIN_SECRET` = the same string as above. Commit, push.

**Resend:** resend.com → Domains → add `gundeck.ai` → add the DKIM/SPF records it gives you at your DNS host → verified. Create an API key with *sending* access only.

*Check:* open the report as a signed-in member. The line under the index reads **Watchlist synced to your account.** Star a card on your laptop; open the report on your phone; it is there. Then, from your machine:
```bash
curl -X POST -H "X-Admin-Secret: $HARO_ADMIN_SECRET" https://<worker>/admin/alerts/run
```
It answers with `members`, `sent`, `skipped`. If you hold something that broke trend today, you have an email.

---

## Phase 4 — Rehearsal: the subscriber journey, end to end (Day 3, ~1 hour)

Do this with a second email address you control, on your phone, without touching the admin.

1. Open `haro.gundeck.ai`. You should see the track record and a *Start 7-day trial* button. Nothing else is readable.
2. Start the trial. Stripe asks for a card. Choose monthly. After checkout Ghost lands you on `/market-haro/` — the report, signed in, no password.
3. Enter a budget, tap a row, star two cards, enter copies and cost on one. Reload: it persists. Open on another device: it is there.
4. Wait for the next morning's email (or trigger the workflow by hand). The email arrives from *Market Haro*, the button opens the report, you are still signed in.
5. Sign out (Portal → *Sign out*). Reopen the report: paywall. Click *Sign in*, enter the email, click the link in the email: report. That link is the "tokenized login" — no password anywhere.
6. Cancel the trial from Portal → *Manage subscription*. Access ends at the trial's end; Ghost handles the Stripe side.
7. In Ghost admin → Members, delete the test member.

If any step fails, fix it before Phase 5. The three most common: the report page not `paid` (re-run `radar publish`), the free tier still visible in Portal (2d), sender email unverified (2e).

---

## Phase 5 — Launch to GUNDECK customers (Day 4–7)

You have paying GUNDECK.AI customers (30-day Pro at $3, lifetime at $29). They are the first hundred subscribers if the offer is right and the ask is small. Three moves:

**5a. The offer.** Settings → Offers → *New offer*: name **GUNDECK member**, tier Market Haro, monthly, **first month $15** (57% off once), or yearly **$240** (20% off the first year). Ghost gives you a link like `haro.gundeck.ai/gundeck-member`. It stacks with the 7-day trial: card entered, nothing charged for a week, then the discounted first period. No free tier, one coupon, expires in 30 days — say so.

**5b. Comped seats for a dozen believers.** Ghost admin → Members → the member → *Complimentary*. Give the first ten to fifteen GUNDECK regulars who post decks or prices — the ones other players listen to — three free months in exchange for one thing: screenshots of the report in their communities. Their watchlists and alerts work like anyone else's.

**5c. The email to your list.** From GUNDECK.AI, not from Market Haro, to every GUNDECK customer, sent the morning a good issue lands. Keep it short:

> **Subject:** The market half of GUNDECK — Market Haro
>
> Every morning Market Haro measures the whole English Gundam market and tells you which cards are worth holding, which are listed ahead of themselves, what every set release did to prices, and what changed on the cards *you* follow. It scores its own past calls in public.
>
> It's $35 a month. As a GUNDECK member your first month is $15, and the first week is free — you'll see two issues before you're charged anything.
>
> [Start the trial] · [See the public track record first]
>
> — Aaron

Link the first button to the offer URL and the second to `/track-record/`. Send it once, then a reminder to non-openers five days later, then stop; the offer expiring does the rest.

**5d. Inside gundeck.ai.** A single persistent line in the app for logged-in customers — *Market Haro: today's market, ranked. First month $15 for members →* — is worth more than any email. Put the live Market Haro 50 number in it if the app can fetch `data/index.ndjson` from the repo (it is public text; the last line is today's level).

**5e. The public page.** `/track-record/` is the landing page a stranger should hit. Set it as the site's home page: Settings → Navigation → primary link *Track record* → `/track-record/`; and in Settings → General → *Publication home page* choose the track record page if your theme allows, otherwise pin it first in navigation. Add one line to it via the theme's code injection if you want a hero above it; the page itself stays generated.

---

## Phase 6 — Operating it (weekly, ~20 minutes)

| When | What | Where |
|---|---|---|
| Weekly | Write the note: `data/notes/YYYY-MM-DD.md`, a few hundred words, commit | repo |
| Weekly | Glance at Ghost → Dashboard: new trials, conversions, churn, opens | Ghost admin |
| Weekly | Glance at the last run's summary; if `sync` was red, check the feed age line in the email | GitHub Actions |
| Monthly (1st) | The workflow runs `radar validate` and commits it; read the verdict line in `data/validation_history.json`. Below +0.20 two months running is the signal to revisit the score | repo |
| Monthly | Stripe payout reconciliation; refund anyone who asks within 14 days without a fight | Stripe |
| Quarterly | Rotate `GHOST_ADMIN_KEY` and `ADMIN_SECRET`; confirm `.env` is still ignored | Ghost, Cloudflare, GitHub |
| When a set releases | The chart marks appear on their own. Write the banlist, if there is one, into the note — the price data cannot see it | repo |

Backups: the archive is in git; that is the backup. Ghost(Pro) backs up the site; Stripe holds billing. The only data of yours outside those is the Worker's KV (watchlists, emails, ~1 KB a member); export it quarterly with `npx wrangler kv key list` + `get`, or accept that its loss costs each member their starred list and nothing else.

---

## Money and terms, stated once

- **Price:** $35/month, $300/year, 7-day trial, no free tier. GUNDECK members: first month $15 or first year $240, for 30 days from launch.
- **Refunds:** 14 days, no questions, from Stripe. Say it on the signup page; it lowers the barrier more than it costs.
- **Terms:** two paragraphs on a public `/terms/` page: information only, not financial advice, cards can lose value, data from tcgapi.dev under commercial licence, you may cancel any time, we store your email and your watchlist and nothing else. The report footer already says the substantive part.
- **Privacy:** the Worker stores the member's email (to send alerts) and watchlist, keyed by a hash. Ghost stores the membership. Stripe stores the card. Nothing is sold or shared.
- **Running cost before the first subscriber:** Ghost(Pro) plan + tcgapi.dev Pro + a domain. Cloudflare, Resend and GitHub are free at this scale. Three subscribers cover it.

---

## The order, as a checklist

- [ ] 0 · Decide the domain; confirm Ghost plan allows custom integrations
- [ ] 1 · Repo pushed, `TCGAPI_KEY` set, one green run, failure notifications on
- [ ] 2 · Site, domain, Stripe, tier ($35/$300/7 days), paid-only access, free tier hidden, newsletter sender verified, integration key, `report_url`, publish dry-run then `--no-email`, then a real send to yourself
- [ ] 3 · Worker deployed, KV created, `ADMIN_SECRET` + `RESEND_API_KEY`, Resend domain verified, `sync_url` + `HARO_ADMIN_SECRET`, "synced to your account" seen, alert run answered
- [ ] 4 · Full rehearsal with a second email on a phone: trial → report → watchlist → email → sign out → magic link → cancel
- [ ] 5 · Offer created, comped seats given, GUNDECK email sent, in-app line live, track record as the front door
- [ ] 6 · Weekly note written; the calendar reminder for the rest exists
