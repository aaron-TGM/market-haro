# Launch plan: Market Haro at marketharo.io

From the repo you have to a GUNDECK customer opening the report with the account they already own. Four phases on this side, one appendix of changes on the gundeck.ai side, about three hours of your hands. Every step names the screen it happens on.

**How access works, in one paragraph, so you can explain it to customers:** Market Haro is its own subscription. You sign in with a GUNDECK.AI account (free to create) — marketharo.io is registered with Clerk as a satellite of gundeck.ai, so signing in hops to gundeck.ai for a second and comes straight back; Clerk hands the browser a short-lived signed token, and the Market Haro server checks that signature and reads one field on your account: whether Stripe says you have an active Market Haro subscription. That field is written by Stripe's webhook on gundeck.ai when you subscribe, cancel or lapse. GUNDECK itself is a separate subscription on the same account; neither requires the other. No second password, no second account, no email newsletter. The report is the product.

**The stranger's path, end to end.** Someone types `marketharo.io` (or clicks it in a video) → the splash → taps *Start monthly* → Clerk sends them to gundeck.ai's sign-up page (email + password or Google; this creates their GUNDECK account) and straight on to `gundeck.ai/market-haro/subscribe?plan=monthly`, which opens Stripe Checkout with the 7-day trial (card entered, nothing charged) → Stripe returns them to `marketharo.io/?checkout=success` → the splash shows "Finishing your subscription…" and polls for a few seconds while Stripe's webhook writes the entitlement onto their account → the report opens. Next time: `marketharo.io` → already signed in → the report. Someone who already has a GUNDECK account taps *Already subscribed? Sign in* or the plan button; Clerk recognises them on gundeck.ai and bounces them back signed in.

---

## Phase 0 — Accounts and decisions (15 minutes)

| Need | Choice | Why |
|---|---|---|
| Identity | gundeck.ai's Clerk instance (`clerk.gundeck.ai`) | One account, one login, two products; the cross-sell only works if it is the same account. |
| Billing | gundeck.ai's Stripe account: one Product, two Prices | Same payout, same customer record, self-serve cancel through the portal you already have. |
| Domain | `marketharo.io`, a Clerk satellite domain of gundeck.ai | gundeck.ai's DNS is not touched; the .io is the name people say and type. Sign-in hops to gundeck.ai and back. |
| Cloudflare | Free account, one Worker, one KV namespace | Serves the page, gates it, keeps watchlists. |
| GitHub | Private repo, Actions enabled | The daily run. |
| tcgapi.dev | Pro plan, the key already in your `.env` | ~60 requests a day of 10,000. |

Decided: **$8 a month, $88 a year, 7-day trial, no free tier, no discounts, no coupon.** One price for everyone; the trial is the offer.

**How it sits beside GUNDECK.** Two products, one free account, each bought on its own. **GUNDECK** — the game tools — moves from a one-time Pass to a subscription: **$3/month, $29/year, or $59 Lifetime** (up from $29; existing Lifetime holders keep theirs, and the increase is announced with a two-week window at the old price). **Market Haro** — the market — stays **$8/month or $88/year, 7-day trial**, no Lifetime. Nothing includes anything else; the pricing page says *GUNDECK is for playing, Market Haro is for the market — one account, take either or both.* The two meet in exactly one place: right after checkout, each offers the other once (a banner on the first view of the Market Haro report; a card on gundeck.ai's post-checkout page). One trial length for everyone, 7 days.

---

## Phase 1 — The pipeline runs by itself (Day 1, ~45 minutes)

1. Push the repo (private). `git ls-files | grep -i env` must print only `.env.example`.
2. Repo secrets: `TCGAPI_KEY`; `HARO_ADMIN_SECRET` after Phase 2 (a long random string you make up; the Worker gets the same value).
3. Actions tab → *daily* → *Run workflow*. Watch it go green: restore, sync, build, tests, commit. Download the run artifact and open `dashboard.html` — that is what subscribers will see.
4. Settings → Notifications → Actions → email on failure.

## Phase 2 — The site (Day 1, ~45 minutes)

DEPLOY.md §5 has the commands. In order: move marketharo.io's nameservers to Cloudflare; `wrangler login`; create the KV namespace and paste its id; `wrangler secret put ADMIN_SECRET`; fill `CLERK_PUBLISHABLE_KEY` in `wrangler.toml`; `wrangler deploy`; confirm `https://marketharo.io/health`. Then in Clerk: *Domains → Add satellite domain* → `marketharo.io` and add the CNAME it asks for (DNS only) in Cloudflare; *Sessions → Customize session token* → add `"public_metadata": "{{user.public_metadata}}"`. Then add `HARO_ADMIN_SECRET` to GitHub and re-run the workflow; the last step pushes the pages. Open the site signed out: the splash.

## Phase 3 — gundeck.ai (Day 2, your side; the appendix below is the brief)

Stripe Product and Prices, the webhook that writes the entitlement onto the Clerk user, the nav item, the pricing card, the account line. When the webhook has run once for your own account, open marketharo.io signed in: the report, and the watchlist line says "synced to your account".

## Phase 4 — Rehearsal, then launch (Day 2–3, ~1 hour)

With a second email on a phone: subscribe (trial) → open the report → star three cards, enter a holding → sign out → sign in → the holding is there → cancel from the account page → the site shows the splash again. Then the launch itself: a top-level *Market Haro* item in gundeck.ai's nav, the pricing card, one email to your customer list from GUNDECK.AI (below), and `/track-record` as the link you give strangers.

> **Subject:** The market half of GUNDECK — Market Haro
>
> Every morning Market Haro measures the whole English Gundam market and ranks what is worth holding: every single scored, every box measured against the cards inside it, every chart marked with the set calendar, and a public record of every call scored a month later. Same account, one page, no newsletter.
>
> $8 a month or $88 a year, first week free. Same account as GUNDECK, separate subscription — take either or both, cancel any time.
>
> [Open Market Haro] · [See the public track record]
>
> One more thing, about GUNDECK itself. The 30-day Pass is becoming a plain $3/month subscription (or $29 a year), and on [date] Lifetime goes from $29 to $59. If you've been meaning to grab Lifetime, the next two weeks are the time. Anyone who already has it keeps it, obviously.
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

- **Price:** $8/month, $88/year, 7-day trial, no free tier, no discounts. A standalone subscription on a GUNDECK.AI account, billed separately from GUNDECK ($3/mo · $29/yr · $59 Lifetime).
- **Refunds:** 14 days, no questions, from Stripe.
- **Terms:** two paragraphs on gundeck.ai's existing terms page: information only, not financial advice, cards can lose value, data from tcgapi.dev under commercial licence, cancel any time, we store your watchlist and nothing else. The report footer already says the substantive part.
- **Privacy:** the Worker stores the watchlist keyed by Clerk user id. Clerk stores the account. Stripe stores the card. Nothing is sold or shared.
- **Running cost before the first subscriber:** tcgapi.dev Pro. Cloudflare and GitHub are free at this scale.

## The order, as a checklist

- [ ] 1 · Repo pushed, `TCGAPI_KEY` set, one green run, artifact opened, failure notifications on
- [ ] 2 · marketharo.io on Cloudflare; Worker deployed on it; KV id and publishable key in `wrangler.toml`; `ADMIN_SECRET` set both sides; satellite domain added in Clerk with its CNAME verified; session token carries `public_metadata`; `/health` ok; splash shows signed out
- [ ] 3 · gundeck.ai: Product + two Prices, the `/market-haro/subscribe` route with success/cancel URLs, webhook writing `publicMetadata.marketHaro`, nav item, pricing card, account line (appendix)
- [ ] 4 · Rehearsal on a second account: trial → report → watchlist survives sign out → cancel → splash. Then the email.

---

## Appendix — changes on gundeck.ai (the brief for Manus)

Market Haro is a separate subscription, independent of GUNDECK. gundeck.ai keeps owning identity (Clerk) and billing (Stripe); the Market Haro server only reads one field on the Clerk user. The pieces of work, in the order they unblock each other — and, alongside them, GUNDECK's own price change (A3), which is the larger job. `docs/HANDOFF-gundeck.md` is the version of this written for Manus; this appendix is the terse form.

**A. Stripe.** One Product, "Market Haro", with two recurring Prices: `$8.00 / month` and `$88.00 / year`, both with a 7-day trial (`trial_period_days: 7`, card collected) and no setup fee. Checkout Sessions for these two Prices must set `subscription_data.metadata.clerkUserId` (and `client_reference_id`) to the signed-in user's Clerk id, and use the existing Stripe Customer for that user if there is one (`customer` on the session) so one customer record holds the lifetime purchase and the subscription. `cancel_at_period_end` is the cancel path, through the existing customer portal.

**A1. Trial.** 7 days for everyone. (An earlier draft gave Lifetime holders 30; dropped when the products were decoupled.)

**A2. The subscribe route** — the one URL the Market Haro splash sends people to: `GET https://gundeck.ai/market-haro/subscribe?plan=monthly|annual`. If the visitor is not signed in, send them through Clerk sign-in/sign-up with `redirect_url` back to this same URL (the splash normally completes sign-up first, so this is the safety net). If signed in, create the Checkout Session for the matching Price as in (A) with `success_url = https://marketharo.io/?checkout=success` and `cancel_url = https://marketharo.io/`, and redirect to it. If the user already has an active or trialing Market Haro subscription, skip Checkout and redirect to `https://marketharo.io/`. That is the whole route.

**A3. GUNDECK's own prices.** New recurring Prices on the GUNDECK Product: `$3.00 / month` and `$29.00 / year`; the one-time Pass stops being sold (existing Passes run out naturally; nobody is converted without going through Checkout). Lifetime becomes `$59.00`; the `$29.00` Lifetime Price stays purchasable until the announced date, then is archived. Post-checkout page for GUNDECK: one card offering Market Haro (*See Market Haro* → `https://marketharo.io`, *Not now*).

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

**C. Clerk dashboard (two settings).** *Sessions → Customize session token*: add `"public_metadata": "{{user.public_metadata}}"`. Without it the token does not carry the field and every subscriber sees the splash. And *Domains → Add satellite domain* → `marketharo.io` (Aaron adds the CNAME it asks for in the marketharo.io zone). Sign-in and sign-up for the satellite happen on gundeck.ai's own pages, so those pages must honour a `redirect_url` back to `https://marketharo.io/...`.

**C2. Entitlement.** Unchanged. Market Haro status has no effect on GUNDECK access and vice versa.

**D. gundeck.ai app.**
- Nav: a top-level item **Market Haro** → `https://marketharo.io/`.
- Pricing page: two products side by side — **GUNDECK** $3/month · $29/year · $59 Lifetime, and **Market Haro** $8/month or $88/year, 7-day free trial — with one line under them: *GUNDECK is for playing. Market Haro is for the market. One account; take either or both.*
- Account page: a line **Market Haro · active until {date} · Manage** that opens the Stripe customer portal; *Not subscribed · Start a trial* otherwise.
- Sign-up and sign-in: the Market Haro splash sends people to gundeck.ai's sign-up / sign-in pages with a `redirect_url` back to marketharo.io (Clerk's satellite flow). Those pages must honour the redirect for that origin; nothing else to build. Make sure sign-ups are enabled on the instance (email + password or the social providers gundeck.ai already offers).
- Terms: the two paragraphs under "Money and terms" above, appended to the existing terms.

What Market Haro will never do: write to Clerk or Stripe, store an email address, or send mail. If a subscriber can't see the report, the first three checks are: the token carries `public_metadata` (C), the webhook wrote `marketHaro.status` (B), and the status is `active` or `trialing`.
