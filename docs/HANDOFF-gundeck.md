# Market Haro × gundeck.ai — a handoff note

Hi — this is from the Market Haro side. Aaron asked me to write up what we've built and what it needs from gundeck.ai, so you can decide how it fits your code. I don't know your codebase, so treat everything below as "here's the shape we're relying on" rather than "here's how to build it." Where you'd do something differently, you almost certainly know better; the couple of places where the shape matters on our end are called out, and even those are configurable.

## What Market Haro is

A daily market dashboard for the Gundam Card Game — every English single scored and ranked, every box measured against the cards inside it, a public track record. It's sold as a subscription, **$8/month or $88/year with a 7-day trial**, positioned as an add-on to a GUNDECK account. It lives on its own at **`marketharo.gundeck.ai`** (a small Cloudflare Worker; `marketharo.io` will 301 there) and it isn't part of the gundeck.ai app at all.

The reason it touches gundeck.ai is that we didn't want a second login or a second billing relationship. So Market Haro uses the same Clerk instance you already use (`clerk.gundeck.ai`), and it uses Stripe billing that lives on your side. Our server's whole job at request time is: look at the Clerk session token the browser already has, verify it against Clerk's published keys, and read one field on the user to see whether they're subscribed. It never calls Clerk, Stripe or gundeck.ai while serving a page.

## The one field we read

We look at the user's Clerk **public metadata** for something like:

```json
"marketHaro": { "status": "trialing", "plan": "monthly", "currentPeriodEnd": 1767225600 }
```

and we treat `status` of `active` or `trialing` as "subscribed" and anything else as not. We chose Stripe's subscription status verbatim so nothing has to be translated. If a different key name or shape is more natural in your metadata conventions, that's fine — our side has a config setting for the path and the values, just let Aaron know what you landed on before we go live.

For the field to reach us, Clerk's session token has to carry public metadata. That's a dashboard setting — **Sessions → Customize session token**, adding `"public_metadata": "{{user.public_metadata}}"` — and it's honestly the single most likely thing to be missed, so I'm mentioning it twice.

## What we're hoping gundeck.ai does

Roughly four things, and you'll know the right way to do each in your stack:

**Stripe products.** One Product, "Market Haro", with a monthly ($8) and an annual ($88) recurring Price. Trials at checkout, card collected up front (the Market Haro page tells people "card entered, nothing charged for seven days," so that's the experience we've promised).

**A way to start checkout for a signed-in user.** Our splash page links to a single URL with the plan in the query — we've assumed `gundeck.ai/market-haro/subscribe?plan=monthly|annual`, but any path works; it's one config value on our end. What we need from that route: it opens Stripe Checkout for the right Price for the signed-in user, tags the subscription with their Clerk user id so the webhook can find them, and sends them back to us afterwards — success to `https://marketharo.gundeck.ai/?checkout=success`, cancel to `https://marketharo.gundeck.ai/`. If the user is already subscribed, just bouncing them to `marketharo.gundeck.ai` is the right answer. One nicety Aaron wants: **GUNDECK Lifetime holders get a 30-day trial instead of 7** — same Prices, just the trial length.

Sign-up itself happens on our page (we open Clerk's standard sign-up modal on our domain before handing off to checkout), so your route can assume a signed-in user; if it gets a signed-out one anyway, sending them through Clerk sign-in with a redirect back to the same URL is all we'd need.

**The webhook.** When a Market Haro subscription is created, changes, or ends (`customer.subscription.created/updated/deleted`), write the field above onto the Clerk user — merged into public metadata so nothing else you keep there is disturbed, and on delete set status to `canceled` rather than removing the key. That's it. Because we read it from the session token, a change shows up for the user within about a minute of the webhook without anything on our side polling.

**One condition in GUNDECK's own entitlement.** Aaron's decided a Market Haro subscription includes GUNDECK while it's active, so wherever you check for a Pass or Lifetime, an `active`/`trialing` Market Haro status should count too. One extra `or`, nothing else changes about Pass or Lifetime.

## UI, for completeness

These are Aaron's calls; I'm just recording them so they're in one place: a top-level **Market Haro** nav item pointing at `marketharo.gundeck.ai`; the pricing page as three cards — Pass $3/30 days, Lifetime $29 once, Market Haro $8/mo or $88/yr with the trial, "includes GUNDECK while active" — and one line under the row: *"GUNDECK is a tool — you buy it once. Market Haro is a daily market feed — it's a subscription because the data costs us every day."* An account-page line showing Market Haro status and a *Manage* link into the Stripe portal. A couple of paragraphs on the terms page (information only, not financial advice, cards can lose value, data from tcgapi.dev, cancel any time, 14-day refunds).

## What the timing looks like after checkout

Stripe sends the browser back to us before the webhook necessarily lands. Our page handles that: it shows "Finishing your subscription…" and polls its own `/me` endpoint for up to a minute until the metadata shows up. So you don't need to do anything special about ordering; it just means a few-second webhook delay is invisible to the user and a minutes-long one would show as that waiting screen.

## How we'd know it's working

The end-to-end we'll run (test mode is fine; we only read `status`): sign up cold from the splash on a phone, pay with a test card, land back on the report; `marketharo.gundeck.ai/me` returning `{"signed_in":true,"entitled":true}`; the same account able to use GUNDECK paid features; cancel from the account page and, once Stripe reports it ended, the site drops back to the splash; a Lifetime account seeing a 30-day trial; and a user already signed in on gundeck.ai opening marketharo without being asked to sign in again.

That last one is the one thing I couldn't verify from our side: marketharo is a subdomain of your Clerk primary domain, so the signed-in state *should* carry over on its own, but if it doesn't, the fix is adding `marketharo.gundeck.ai` as a satellite domain in Clerk → Domains, and I'd rather know about that on a test account than a customer's.

## What we'll never do

Write to Clerk or Stripe, store an email, send mail, or call gundeck.ai. If a subscriber ever can't see the report, the three checks in order are: does the session token carry `public_metadata`, did the webhook write `marketHaro.status`, is it `active` or `trialing`. `/me` shows what our server sees for whoever is signed in.

Anything unclear or awkward, ask Aaron and it'll get to me — most of what's above is adjustable on our end, and I'd rather adapt to your conventions than have you contort to ours.
