# Launch plan: Market Haro at marketharo.gundeck.ai

From the repo you have to a GUNDECK customer opening the report with the account they already own. Four phases on this side, one appendix of changes on the gundeck.ai side, about three hours of your hands. Every step names the screen it happens on.

**How access works, in one paragraph, so you can explain it to customers:** Market Haro is an add-on to a GUNDECK.AI account. You sign in with the same account, on a subdomain of the same site; Clerk — the login gundeck.ai already uses — hands the browser a short-lived signed token, and the Market Haro server checks that signature and reads one field on your account: whether Stripe says you have an active Market Haro subscription. That field is written by Stripe's webhook on gundeck.ai when you subscribe, cancel or lapse. No second password, no second account, no email newsletter. The report is the product.

**The stranger's path, end to end.** Someone types `marketharo.io` (or clicks it in a video) → lands on `marketharo.gundeck.ai`, the splash → taps *Start monthly* → Clerk's sign-up opens right there (email + password or Google; this creates their GUNDECK account) → they land on `gundeck.ai/market-haro/subscribe?plan=monthly`, which opens Stripe Checkout with the 7-day trial (card entered, nothing charged) → Stripe returns them to `marketharo.gundeck.ai/?checkout=success` → the splash shows "Finishing your subscription…" and polls for a few seconds while Stripe's webhook writes the entitlement onto their account → the report opens. Next time: `marketharo.io` → already signed in → the report. Someone who already has a GUNDECK account taps *Already subscribed? Sign in* or the plan button; Clerk recognises them and skips sign-up.

---

## Phase 0 — Accounts and decisions (15 minutes)

| Need | Choice | Why |
|---|---|---|
| Identity | gundeck.ai's Clerk instance (`clerk.gundeck.ai`) | One account, one login; the add-on framing is only true if it is the same account. |
| Billing | gundeck.ai's Stripe account: one Product, two Prices | Same payout, same customer record, self-serve cancel through the portal you already have. |
| Domain | `marketharo.gundeck.ai`; `marketharo.io` as a 301 to it | A subdomain of the Clerk primary domain, so the signed-in state carries over; the .io is the name people say and type. |
| Cloudflare | Free account, one Worker, one KV namespace | Serves the page, gates it, keeps watchlists. |
| GitHub | Private repo, Actions enabled | The daily run. |
| tcgapi.dev | Pro plan, the key already in your `.env` | ~60 requests a day of 10,000. |

Decided: **$8 a month, $88 a year, 7-day trial, no free tier, no discounts, no coupon.** One price for everyone; the trial is the offer.

**How it sits beside GUNDECK.** The account is free and is the hub; GUNDECK Pass ($3, 30 days) and GUNDECK Lifetime ($29) are one-time purchases of a tool; Market Haro is a subscription to a daily feed, and the pricing page says why in one line — *GUNDECK is a tool, you buy it once; Market Haro is a daily market feed, it's a subscription because the data costs us every day.* Nothing requires anything else. The ladder runs one way: **a Market Haro subscription includes GUNDECK while it is active**, so Pass → Lifetime → Market Haro is a climb and "do I need both?" never comes up. Lifetime holders get a **30-day trial instead of 7** — time, not a discount; the price stays one price.

---

## Phase 1 — The pipeline runs by itself (Day 1, ~45 minutes)

1. Push the repo (private). `git ls-files | grep -i env` must print only `.env.example`.
2. Repo secrets: `TCGAPI_KEY`; `HARO_ADMIN_SECRET` after Phase 2 (a long random string you make up; the Worker gets the same value).
3. Actions tab → *daily* → *Run workflow*. Watch it go green: restore, sync, build, tests, commit. Download the run artifact and open `dashboard.html` — that is what subscribers will see.
4. Settings → Notifications → Actions → email on failure.

## Phase 2 — The site (Day 1, ~45 minutes)

DEPLOY.md §5 has the commands. In order: `wrangler login`; create the KV namespace and paste its id; `wrangler secret put ADMIN_SECRET`; fill `CLERK_PUBLISHABLE_KEY` and the gundeck.ai URLs in `wrangler.toml`; `wrangler deploy`; confirm `https://marketharo.gundeck.ai/health`. Then in Clerk: *Sessions → Customize session token* → add `"public_metadata": "{{user.public_metadata}}"`. Then add `HARO_ADMIN_SECRET` to GitHub and re-run the workflow; the last step pushes the pages. Open the site signed out: the splash.

## Phase 3 — gundeck.ai (Day 2, your side; the appendix below is the brief)

Stripe Product and Prices, the webhook that writes the entitlement onto the Clerk user, the nav item, the pricing card, the account line. When the webhook has run once for your own account, open marketharo.gundeck.ai signed in: the report, and the watchlist line says "synced to your account".

## Phase 4 — Rehearsal, then launch (Day 2–3, ~1 hour)

With a second email on a phone: subscribe (trial) → open the report → star three cards, enter a holding → sign out → sign in → the holding is there → cancel from the account page → the site shows the splash again. Then the launch itself: a top-level *Market Haro* item in gundeck.ai's nav, the pricing card, one email to your customer list from GUNDECK.AI (below), and `/track-record` as the link you give strangers.

> **Subject:** The market half of GUNDECK — Market Haro
>
> Every morning Market Haro measures the whole English Gundam market and ranks what is worth holding: every single scored, every box measured against the cards inside it, every chart marked with the set calendar, and a public record of every call scored a month later. Same account, one page, no newsletter.
>
> $8 a month or $88 a year, first week free. It's an add-on — billed separately from your GUNDECK plan, cancel any time.
>
> [Open Market Haro] · [See the public track record]
>
> — Aaron

Send it once, a reminder to non-openers five days later, then stop.

---

## Operating it (weekly, ~10 minutes)

| When | What | Where |
|---|---|---|
| Weekly | Glance at the last run's summary; if `sync` was red, the page's freshness line says how old the prices are | GitHub Actions |
| Weekly | Stripe → Subscriptions: trials, conversions, churn | Stripe |
| Monthly (1st) | The workflow runs `radar validate` and commits it; read the verdict line in `data/validation_history.json`. Below +0.20 two months running is the signal to revisit the score | repo |
| Quarterly | Rotate `ADMIN_SECRET` / `HARO_ADMIN_SECRET`; confirm `.env` is still ignored | Cloudflare, GitHub |

Backups: the archive is in git; that is the backup. Clerk holds accounts, Stripe holds billing. The only data of yours outside those is the Worker's KV (watchlists, ~1 KB a user, keyed by Clerk user id); export it quarterly with `npx wrangler kv key list` + `get`, or accept that its loss costs each user their starred list and nothing else.

## Money and terms, stated once

- **Price:** $8/month, $88/year, 7-day trial, no free tier, no discounts. An add-on to GUNDECK.AI, billed separately.
- **Refunds:** 14 days, no questions, from Stripe.
- **Terms:** two paragraphs on gundeck.ai's existing terms page: information only, not financial advice, cards can lose value, data from tcgapi.dev under commercial licence, cancel any time, we store your watchlist and nothing else. The report footer already says the substantive part.
- **Privacy:** the Worker stores the watchlist keyed by Clerk user id. Clerk stores the account. Stripe stores the card. Nothing is sold or shared.
- **Running cost before the first subscriber:** tcgapi.dev Pro. Cloudflare and GitHub are free at this scale.

## The order, as a checklist

- [ ] 1 · Repo pushed, `TCGAPI_KEY` set, one green run, artifact opened, failure notifications on
- [ ] 2 · Worker deployed on `marketharo.gundeck.ai`, KV id and publishable key in `wrangler.toml`, `ADMIN_SECRET` set both sides, Clerk session token carries `public_metadata`, `/health` ok, splash shows signed out
- [ ] 3 · gundeck.ai: Product + two Prices, the `/market-haro/subscribe` route with success/cancel URLs, webhook writing `publicMetadata.marketHaro`, nav item, pricing card, account line (appendix)
- [ ] 4 · Rehearsal on a second account: trial → report → watchlist survives sign out → cancel → splash. Then the email.

---

## Appendix — changes on gundeck.ai (the brief for Manus)

Market Haro is a separate subscription sold as an add-on. gundeck.ai keeps owning identity (Clerk) and billing (Stripe); the Market Haro server only reads one field on the Clerk user. Four pieces of work.

**A. Stripe.** One Product, "Market Haro", with two recurring Prices: `$8.00 / month` and `$88.00 / year`, both with a 7-day trial (`trial_period_days: 7`, card collected) and no setup fee. Checkout Sessions for these two Prices must set `subscription_data.metadata.clerkUserId` (and `client_reference_id`) to the signed-in user's Clerk id, and use the existing Stripe Customer for that user if there is one (`customer` on the session) so one customer record holds the lifetime purchase and the subscription. `cancel_at_period_end` is the cancel path, through the existing customer portal.

**A1. Lifetime perk.** In the subscribe route, if the user's account carries the GUNDECK Lifetime flag, create the Checkout Session with `trial_period_days: 30` instead of 7. Same Prices, same everything else.

**A2. The subscribe route** — the one URL the Market Haro splash sends people to: `GET https://gundeck.ai/market-haro/subscribe?plan=monthly|annual`. If the visitor is not signed in, send them through Clerk sign-in/sign-up with `redirect_url` back to this same URL (the splash normally completes sign-up first, so this is the safety net). If signed in, create the Checkout Session for the matching Price as in (A) with `success_url = https://marketharo.gundeck.ai/?checkout=success` and `cancel_url = https://marketharo.gundeck.ai/`, and redirect to it. If the user already has an active or trialing Market Haro subscription, skip Checkout and redirect to `https://marketharo.gundeck.ai/`. That is the whole route.

**B. The webhook.** On `customer.subscription.created`, `customer.subscription.updated` and `customer.subscription.deleted` for subscriptions whose Price belongs to the Market Haro Product, read `clerkUserId` from the subscription metadata (fall back to the customer's metadata) and set the Clerk user's public metadata:

```json
"publicMetadata": {
  "marketHaro": {
    "status": "active" | "trialing" | "past_due" | "canceled" | "unpaid",
    "plan": "monthly" | "annual",
    "currentPeriodEnd": 1767225600,
    "stripeSubscriptionId": "sub_…"
  }
}
```

`status` is Stripe's subscription status verbatim. Merge, do not replace, the rest of `publicMetadata` (`PATCH /v1/users/{id}/metadata` on the Clerk Backend API merges). The Market Haro server treats `active` and `trialing` as entitled and everything else as not; it re-reads the token on every request, so the change is live within a minute of the webhook. Nothing else on gundeck.ai needs to know the field exists.

**C. Clerk dashboard (one setting).** *Sessions → Customize session token*: add `"public_metadata": "{{user.public_metadata}}"`. Without it the token does not carry the field and every subscriber sees the splash. `marketharo.gundeck.ai` is a subdomain of the primary domain, so no satellite-domain setup is expected; if the splash shows "sign in" to a signed-in user, add it as a satellite under *Domains*.

**C2. GUNDECK includes with Market Haro.** Wherever gundeck.ai checks whether a user may use GUNDECK's paid features, treat `publicMetadata.marketHaro.status` in `active` or `trialing` as equivalent to an active Pass or Lifetime. One condition; nothing else changes.

**D. gundeck.ai app.**
- Nav: a top-level item **Market Haro** → `https://marketharo.gundeck.ai/`.
- Pricing page: three cards in a row — **GUNDECK Pass** $3 / 30 days · **GUNDECK Lifetime** $29 once · **Market Haro** $8/month or $88/year, 7-day free trial (30 days for Lifetime members), *includes GUNDECK while active*. Under the row, one line: "GUNDECK is a tool — you buy it once. Market Haro is a daily market feed — it's a subscription because the data costs us every day." Market Haro copy: *Today's Gundam market, ranked.* "A daily dashboard of every Gundam single worth holding and every box measured against the cards inside it, with a public record of every call. Cancel any time." Two buttons → the subscribe route (A2). Nothing requires anything else.
- Account page: a line **Market Haro · active until {date} · Manage** that opens the Stripe customer portal; *Not subscribed · Start a trial* otherwise.
- Sign-up and sign-in happen on the Market Haro splash itself, in Clerk's modal (same instance, same root domain); nothing to build for that. Do make sure the Clerk instance allows sign-ups (email + password or the social providers gundeck.ai already offers) — the splash opens the standard sign-up, so whatever is enabled there is what strangers get.
- Terms: the two paragraphs under "Money and terms" above, appended to the existing terms.

What Market Haro will never do: write to Clerk or Stripe, store an email address, or send mail. If a subscriber can't see the report, the first three checks are: the token carries `public_metadata` (C), the webhook wrote `marketHaro.status` (B), and the status is `active` or `trialing`.
