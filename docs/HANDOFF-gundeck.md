# Market Haro × gundeck.ai — a handoff note

Hi — this is from the Market Haro side. Aaron asked me to write up what we've built and what it needs from gundeck.ai, so you can decide how it fits your code. I don't know your codebase, so treat everything below as "here's the shape we're relying on" rather than "here's how to build it." Where you'd do something differently, you almost certainly know better; the couple of places where the shape matters on our end are called out, and even those are configurable.

## What Market Haro is

A daily market dashboard for the Gundam Card Game — every English single scored and ranked, every box measured against the cards inside it, a public track record. It's sold as a subscription, **$8/month or $88/year with a 7-day trial**, as its own product: someone who only wants the market can buy Market Haro without buying GUNDECK, and vice versa. What the two share is the account. It lives on its own at **`marketharo.io`** (a small Cloudflare Worker) and it isn't part of the gundeck.ai app at all — and, deliberately, nothing about gundeck.ai's DNS changes for it.

The reason it touches gundeck.ai is that we didn't want a second login or a second billing relationship. So Market Haro uses the same Clerk instance you already use (`clerk.gundeck.ai`) — the .io is registered with Clerk as a *satellite domain* of gundeck.ai, which is Clerk's mechanism for exactly this: one account, one session, a second domain. Sign-in and sign-up for the satellite happen on gundeck.ai's own pages and come straight back. And it uses Stripe billing that lives on your side. Our server's whole job at request time is: look at the Clerk session token the browser already has, verify it against Clerk's published keys, and read one field on the user to see whether they're subscribed. It never calls Clerk, Stripe or gundeck.ai while serving a page.

## The one field we read

We look at the user's Clerk **public metadata** for something like:

```json
"marketHaro": { "status": "trialing", "plan": "monthly", "currentPeriodEnd": 1767225600 }
```

and we treat `status` of `active` or `trialing` as "subscribed" and anything else as not. We chose Stripe's subscription status verbatim so nothing has to be translated. If a different key name or shape is more natural in your metadata conventions, that's fine — our side has a config setting for the path and the values, just let Aaron know what you landed on before we go live.

For the field to reach us, Clerk's session token has to carry public metadata. Aaron has already done that in the dashboard (**Sessions → Customize session token** now has `"public_metadata": "{{user.public_metadata}}"`), and he's added `marketharo.io` as a satellite domain under **Domains** with its CNAME verified — so nothing in the Clerk dashboard is waiting on you.

One thing we noticed while doing it, which you'll already know but is worth saying so nobody is surprised: the session-token preview for Aaron's own account shows `public_metadata: {}`. So GUNDECK's Pass/Lifetime status lives in your own database rather than in Clerk public metadata today, and the Market Haro field will be the first thing written there. That's fine on our end — we only need `marketHaro` itself in public metadata — and your GUNDECK-side checks can keep reading from wherever they read from now. It just means the webhook needs to write to Clerk specifically, not only to your database.

## What we're hoping gundeck.ai does

Roughly four things, and you'll know the right way to do each in your stack:

**Stripe products.** One Product, "Market Haro", with a monthly ($8) and an annual ($88) recurring Price. Trials at checkout, card collected up front (the Market Haro page tells people "card entered, nothing charged for seven days," so that's the experience we've promised).

**A way to start checkout for a signed-in user.** Our splash page links to a single URL with the plan in the query — we've assumed `gundeck.ai/market-haro/subscribe?plan=monthly|annual`, but any path works; it's one config value on our end. What we need from that route: it opens Stripe Checkout for the right Price for the signed-in user, tags the subscription with their Clerk user id so the webhook can find them, and sends them back to us afterwards — success to `https://marketharo.io/?checkout=success`, cancel to `https://marketharo.io/`. If the user is already subscribed, just bouncing them to `marketharo.io` is the right answer. Same 7-day trial for everyone, no exceptions (an earlier draft had a longer trial for Lifetime holders; that's dropped).

Sign-up itself goes through gundeck.ai's sign-up page: our splash calls Clerk's `redirectToSignUp` with a redirect back to the checkout URL, so a stranger lands on your sign-up, creates the account, and continues to checkout without touching our page again until Stripe returns them. The one thing that has to be true on your side is that the sign-in and sign-up pages honour a `redirect_url` pointing at `https://marketharo.io/...` (and at the subscribe route). If your route gets a signed-out user anyway, sending them through sign-in with a redirect back to the same URL is all we'd need.

We've tested this bit already (Sep 10): from marketharo.io, *Sign in* correctly lands on gundeck.ai's sign-in page and the sign-in succeeds — but afterwards the user ends up on gundeck.ai's home page rather than back on marketharo.io. So the `redirect_url` is currently being dropped. Two usual reasons, and you'll know which applies: the sign-in/sign-up components are given a fixed after-sign-in destination (`forceRedirectUrl` / `afterSignInUrl`, or the equivalent in the Clerk dashboard's Paths settings) that overrides the query param; or Clerk's own safety check is discarding a cross-origin `redirect_url` — Clerk ignores redirects to origins it doesn't recognise unless they're listed in `allowedRedirectOrigins` on `<ClerkProvider>`, so adding `https://marketharo.io` there may be all it takes. Not urgent for anything else to work — someone who lands on gundeck.ai and then opens marketharo.io is recognised there — but it's the difference between a smooth sign-up flow and a confusing one, so it's worth doing before launch.

**The webhook.** When a Market Haro subscription is created, changes, or ends (`customer.subscription.created/updated/deleted`), write the field above onto the Clerk user — merged into public metadata so nothing else you keep there is disturbed, and on delete set status to `canceled` rather than removing the key. That's it. Because we read it from the session token, a change shows up for the user within about a minute of the webhook without anything on our side polling.

**Nothing in GUNDECK's own entitlement.** An earlier draft had Market Haro include GUNDECK; that's gone. The two are independent — a Market Haro subscription says nothing about GUNDECK access, and the other way round. Whatever your entitlement check does today stays as it is.

## GUNDECK's own pricing is changing too

This is the part that's entirely yours, and it's a bigger change than anything above, so it goes in its own section. Aaron's decisions (Sep 10):

- **GUNDECK Pass ($3 for 30 days, one-time) becomes a subscription: $3/month.** A new recurring Price; the old one-time Pass stops being sold. People who already bought a Pass finish their 30 days as normal and see the new subscription when it ends. Nobody gets converted to a subscription automatically — that needs their consent through Checkout.
- **A GUNDECK annual price: $29/year.** Same product, second recurring Price (Stripe's fee on a $3 charge is ~13%; on $29 it's ~4%, which is the main reason it exists).
- **GUNDECK Lifetime goes from $29 to $59.** Existing Lifetime holders keep what they have. Aaron will announce the increase with a short window at the old price before it takes effect (he'll give you the date), so the old Price needs to stay purchasable until then.

So GUNDECK ends up with monthly / annual / Lifetime, and Market Haro with monthly / annual — two products, one account, each bought on its own.

**The cross-sell.** The one place the products meet is right after checkout, and it's one screen each way. On your side: when someone finishes buying GUNDECK, the post-checkout page offers Market Haro — one line, a *See Market Haro* button to `https://marketharo.io`, and a *Not now*. On our side: when someone finishes buying Market Haro, the first view of the report carries the mirror-image banner for GUNDECK, linking to your pricing page (we've assumed `https://gundeck.ai/pricing`; if it's somewhere else, tell Aaron and it's a config value). Neither side needs the other's cooperation for its banner. (We looked at Stripe Checkout's built-in cross-sell; it only pairs Prices with the same billing interval, so it can't do annual-to-monthly or the one-time Lifetime — the post-checkout screen is simpler.)

## UI, for completeness

These are Aaron's calls; I'm just recording them so they're in one place: a top-level **Market Haro** nav item pointing at `marketharo.io`; the pricing page as two products side by side — **GUNDECK** ($3/mo · $29/yr · $59 Lifetime) and **Market Haro** ($8/mo · $88/yr, 7-day trial) — with one line under them: *"GUNDECK is for playing. Market Haro is for the market. One account; take either or both."* An account-page line showing Market Haro status and a *Manage* link into the Stripe portal (yours already handles GUNDECK). A couple of paragraphs on the terms page (information only, not financial advice, cards can lose value, data from tcgapi.dev, cancel any time, 14-day refunds).

## What the timing looks like after checkout

Stripe sends the browser back to us before the webhook necessarily lands. Our page handles that: it shows "Finishing your subscription…" and polls its own `/me` endpoint for up to a minute until the metadata shows up. So you don't need to do anything special about ordering; it just means a few-second webhook delay is invisible to the user and a minutes-long one would show as that waiting screen.

## How we'd know it's working

The end-to-end we'll run (test mode is fine; we only read `status`): sign up cold from the splash on a phone, pay with a test card, land back on the report with the GUNDECK banner across the top; `marketharo.io/me` returning `{"signed_in":true,"entitled":true}`; that same account *not* getting GUNDECK's paid features from it (they're separate now); cancel from the account page and, once Stripe reports it ended, the site drops back to the splash; a GUNDECK checkout ending on your page with the Market Haro offer; and a user already signed in on gundeck.ai opening marketharo without being asked to sign in again.

That last one is Clerk's satellite sync doing its job — a user who is signed in on gundeck.ai and opens marketharo.io should be recognised after a quick hop through gundeck.ai. It's the part I couldn't test from our side, so I'd rather see it on a test account than a customer's.

## What we'll never do

Write to Clerk or Stripe, store an email, send mail, or call gundeck.ai. If a subscriber ever can't see the report, the three checks in order are: does the session token carry `public_metadata`, did the webhook write `marketHaro.status`, is it `active` or `trialing`. `/me` shows what our server sees for whoever is signed in.

Anything unclear or awkward, ask Aaron and it'll get to me — most of what's above is adjustable on our end, and I'd rather adapt to your conventions than have you contort to ours.
