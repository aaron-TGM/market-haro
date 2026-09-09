# Market Haro × gundeck.ai — integration handoff

**For:** whoever builds gundeck.ai (the Manus project). **From:** Aaron / the Market Haro project.
**What this is:** everything gundeck.ai has to do so that Market Haro — a separate product on `marketharo.gundeck.ai` — can use gundeck.ai's Clerk accounts and Stripe billing. Nothing in this document changes how existing GUNDECK purchases work.

---

## 1. The shape of it, in five sentences

Market Haro is a daily market dashboard for the Gundam Card Game, sold as an **$8/month or $88/year subscription** with a **7-day trial**. It lives on **`marketharo.gundeck.ai`**, a Cloudflare Worker that is *not* part of the gundeck.ai codebase and never calls gundeck.ai, Clerk or Stripe at request time. It decides who may see the page by **verifying the Clerk session token** the browser already holds (same Clerk instance as gundeck.ai) and reading **one field on the user**: `publicMetadata.marketHaro`. gundeck.ai owns that field: **Stripe's webhook writes it** when a subscription is created, changes or ends. gundeck.ai also owns **checkout** (one route that opens Stripe Checkout for the signed-in user) and the **pricing/nav/account UI**.

So the integration is: one Stripe Product, one route, one webhook handler, one Clerk dashboard setting, one entitlement rule, and some UI. Sections 3–8. Section 9 is how to test it. Section 10 is what Market Haro promises never to do.

## 2. Facts you will need

| | |
|---|---|
| Clerk Frontend API (issuer) | `https://clerk.gundeck.ai` |
| Clerk JWKS | `https://clerk.gundeck.ai/.well-known/jwks.json` |
| Market Haro host | `https://marketharo.gundeck.ai` (also reached via a 301 from `marketharo.io`) |
| Return URLs Market Haro expects | success: `https://marketharo.gundeck.ai/?checkout=success` · cancel: `https://marketharo.gundeck.ai/` |
| The route Market Haro links to | `https://gundeck.ai/market-haro/subscribe?plan=monthly` and `…?plan=annual` |
| The account page Market Haro links to | `https://gundeck.ai/account` (tell Aaron if it is a different path) |
| Prices | $8.00 USD / month · $88.00 USD / year · 7-day trial (30 days for GUNDECK Lifetime holders) |

## 3. Stripe — one Product, two Prices

Create Product **"Market Haro"** with two recurring Prices:

- `price_market_haro_monthly` — $8.00 USD, billed monthly
- `price_market_haro_annual` — $88.00 USD, billed yearly

Trial and metadata are set per Checkout Session (below), not on the Price. Enable the **customer portal** for subscription cancellation if it is not already (Billing → Customer portal → allow cancel; "cancel at period end").

## 4. The subscribe route — `GET /market-haro/subscribe?plan=monthly|annual`

This is the only URL Market Haro sends people to for buying. Behaviour, in order:

1. If `plan` is not `monthly` or `annual` → 400 (or default to monthly).
2. If the visitor is **not signed in** → send them through Clerk sign-in/sign-up with `redirect_url` set to this exact URL (including `?plan=`). (Market Haro's own page normally completes sign-up before linking here, so this is a safety net, but it must work.)
3. If the user **already has** `publicMetadata.marketHaro.status` of `active` or `trialing` → redirect to `https://marketharo.gundeck.ai/` (nothing to buy).
4. Otherwise create a Stripe **Checkout Session**:
   - `mode: "subscription"`, `line_items: [{price: <the Price for plan>, quantity: 1}]`
   - `customer`: the user's existing Stripe Customer if gundeck.ai has one for them; otherwise `customer_email` = their primary email so Stripe creates one. Store the new customer id on the user afterwards if you keep that mapping.
   - `client_reference_id: <clerk user id>`
   - `subscription_data: { trial_period_days: 7, metadata: { clerkUserId: <clerk user id>, product: "market_haro", plan: "monthly"|"annual" } }`
   - **Lifetime perk:** if the user holds GUNDECK Lifetime, `trial_period_days: 30` instead of 7. Same Prices, nothing else differs.
   - `payment_method_collection: "always"` (card taken at trial start; this is the intended experience and the Market Haro page says so)
   - `success_url: "https://marketharo.gundeck.ai/?checkout=success"`, `cancel_url: "https://marketharo.gundeck.ai/"`
   - `allow_promotion_codes: false`
5. 303-redirect to the session's `url`.

## 5. The webhook — write the entitlement onto the Clerk user

Add to the existing Stripe webhook endpoint (or a new one) the events `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`. For each event whose subscription item's Price belongs to the Market Haro Product:

1. Find the Clerk user id: `subscription.metadata.clerkUserId`; fall back to the Stripe Customer's metadata, then to the customer's email → Clerk user lookup. If no user can be found, log loudly and return 200 (do not retry forever).
2. Update the Clerk user's **public metadata**, merging (Clerk's `PATCH /v1/users/{id}/metadata` merges top-level keys; do not overwrite other keys gundeck.ai already stores there):

```json
{
  "public_metadata": {
    "marketHaro": {
      "status": "<stripe subscription status verbatim: trialing | active | past_due | canceled | unpaid | incomplete | incomplete_expired | paused>",
      "plan": "monthly" | "annual",
      "currentPeriodEnd": <unix seconds>,
      "cancelAtPeriodEnd": true | false,
      "stripeSubscriptionId": "sub_…",
      "updatedAt": <unix seconds>
    }
  }
}
```

3. On `customer.subscription.deleted` set `status: "canceled"` (keep the object; do not delete the key).

Market Haro treats `active` and `trialing` as entitled and everything else as not. Because the Worker reads the session token, the change is live for the user within about a minute of the webhook (Clerk refreshes the token every 60 s). Idempotency: writing the same object twice is harmless.

## 6. Clerk dashboard — one setting, one check

- **Sessions → Customize session token** → add:
  ```json
  { "public_metadata": "{{user.public_metadata}}" }
  ```
  Without this the token does not carry `marketHaro` and every subscriber sees the "subscribe" page. This is the single most likely thing to be missed.
- **Sign-ups must be enabled** on the instance (email + password and/or the social providers gundeck.ai already offers). Market Haro's splash opens Clerk's standard `openSignUp()` modal on its own domain; whatever the instance allows is what new users get.
- `marketharo.gundeck.ai` is a subdomain of the instance's primary domain, so the signed-in state should carry over without configuration. If testing shows a signed-in gundeck.ai user as signed-out on marketharo, add `marketharo.gundeck.ai` under **Domains** as a satellite domain and tell Aaron; nothing else changes.

## 7. GUNDECK's own entitlement — one added condition

Wherever gundeck.ai decides whether a user may use paid GUNDECK features, add: **a user whose `publicMetadata.marketHaro.status` is `active` or `trialing` is treated as having an active GUNDECK Pass/Lifetime.** A Market Haro subscription includes GUNDECK while it is active. One condition; no other change to Pass or Lifetime.

## 8. UI on gundeck.ai

- **Nav:** a top-level item **Market Haro** → `https://marketharo.gundeck.ai/`.
- **Pricing page:** three cards in a row — *GUNDECK Pass* $3 / 30 days · *GUNDECK Lifetime* $29 once · *Market Haro* $8/month or $88/year, 7-day free trial (30 days for Lifetime members), "includes GUNDECK while active". One line under the row: *"GUNDECK is a tool — you buy it once. Market Haro is a daily market feed — it's a subscription because the data costs us every day."* Market Haro card copy: **Today's Gundam market, ranked.** "A daily dashboard of every Gundam single worth holding and every box measured against the cards inside it, with a public record of every call. Cancel any time." Two buttons → the subscribe route with `?plan=monthly` / `?plan=annual`. Nothing requires anything else.
- **Account page:** a line **Market Haro · active until {currentPeriodEnd, formatted} · Manage**, where *Manage* opens the Stripe customer portal session for that customer; if `cancelAtPeriodEnd`, say *ends on {date}*; if not subscribed, *Market Haro · not subscribed · Start a free trial* → the subscribe route.
- **Terms:** append two short paragraphs to the existing terms: Market Haro is information only, not financial advice; trading cards can lose value; price data from tcgapi.dev under commercial licence; the subscription is separate from GUNDECK purchases and can be cancelled any time; 14-day refunds on request; Market Haro stores the user's watchlist and nothing else.

## 9. How to test it (what "done" looks like)

1. **Fresh account, no GUNDECK purchase.** Open `https://marketharo.gundeck.ai/` signed out → the splash. *Start monthly* → Clerk sign-up modal → complete → lands on the subscribe route → Stripe Checkout (trial shown, card collected) → pay with a Stripe test card → returns to `marketharo.gundeck.ai/?checkout=success` → "Finishing your subscription…" → within ~10 s the report opens.
2. **`/me` says so.** `https://marketharo.gundeck.ai/me` while signed in as that user returns `{"signed_in":true,"entitled":true}`. Signed out: both false.
3. **GUNDECK follows.** That same user can use GUNDECK's paid features on gundeck.ai (section 7).
4. **Cancel.** Account page → Manage → cancel at period end → webhook → `cancelAtPeriodEnd: true`, status still `active` → the report still opens; after the period ends (or by deleting the subscription in the Stripe test dashboard) status `canceled` → `/me` is `entitled:false` and the site shows the splash with "no Market Haro subscription".
5. **Existing Lifetime user.** Sign in as a Lifetime holder → *Start annual* → Checkout shows a 30-day trial.
6. **Signed in on gundeck.ai, first visit to marketharo.** No sign-in prompt; the report (or the splash that says "signed in as … no subscription yet").
7. **Stripe → Clerk timing.** In the Stripe dashboard, resend a `customer.subscription.updated` event; the Clerk user's public metadata updates and nothing else on it is lost.

Stripe test mode is fine for all of this; Market Haro does not care which mode the subscription came from — it only reads `status`.

## 10. What Market Haro will never do

Write to Clerk or Stripe. Store an email address. Send mail. Call gundeck.ai. If a subscriber cannot see the report, the three things to check, in order: the session token carries `public_metadata` (6), the webhook wrote `marketHaro.status` (5), and that status is `active` or `trialing`. `https://marketharo.gundeck.ai/me` shows what the Worker sees.

## 11. Domain, for completeness (Aaron's side, no gundeck.ai work)

`marketharo.io` is registered at Namecheap and will 301 to `marketharo.gundeck.ai` via Cloudflare (nameservers moved to Cloudflare; a redirect rule preserving the path). Only `marketharo.gundeck.ai` needs to exist in Clerk's world. If the app ever moves to the .io as its host, that becomes a Clerk satellite domain; not now.

Questions → Aaron. The Market Haro side (the Worker, its `/me` endpoint, the entitlement path) is configurable if the metadata shape above is inconvenient; say so before building around a different one.
