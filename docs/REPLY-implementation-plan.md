# Notes on the GUNDECK Stripe subscription plan and the Clerk redirect patch

From the Market Haro side, Sep 10. Both look good, and nothing in them needs a change on our end — the Worker contract you're building against (`publicMetadata.marketHaro.status`, return to `/?checkout=success`, `/me`, the `azp` check) is exactly what's deployed at marketharo.io today. The notes below are all on the shared-Customer design and the patch, ordered by how much they'd matter if missed.

## The shared Stripe Customer

**Stripe's "limit customers to one subscription" setting should stay off.** The plan suggests enabling it as defence in depth. As far as we can tell it works per *Customer*, not per product: once a Customer has any active subscription, Checkout sends them to the portal instead of creating another. With one Customer for both products, a GUNDECK subscriber adding Market Haro would be redirected away from checkout — the cross-sell blocked by the safeguard. Your application-level per-product check (query `billing_subscriptions` for an active/trialing row of that product before creating a session) is the right guard. If you want the Stripe setting anyway, test it first in test mode with one account holding both products.

**`current_period_end` is on the subscription item now.** From Stripe API version 2025-03-31 onward it moved off the Subscription object to `subscription.items.data[0].current_period_end`. If the account pins a recent version, reading it from the Subscription yields `undefined`, and `marketHaro.currentPeriodEnd` never reaches Clerk. Read from the item (the subscriptions here all have one).

**Keep the Customer's email in step with Clerk.** The Customer gets the Clerk email at creation; a later email change in Clerk leaves Stripe sending receipts and portal links to the old address. Cheapest fix: in `ensureStripeCustomer`, on the reuse path, compare `customer.email` with the current Clerk email and update if different — that corrects it on every checkout and portal visit. A Clerk `user.updated` webhook is the thorough version; not needed for launch.

**Clean up the loser of the creation race.** The database-uniqueness handling is right (reuse the winner's Customer). The Customer the losing request created still exists in Stripe with nothing attached; `stripe.customers.del` it in that branch so support never finds two Customers for one person.

**Backfill `metadata.clerkUserId` on reused Customers.** If any `users.stripeCustomerId` values already exist from the old code, those Customers may not carry the metadata the webhook falls back to. One conditional `customers.update` on reuse closes that. It also makes a useful support path work: comping someone Market Haro by creating a subscription on their Customer in the Stripe dashboard (100% coupon) flows through the webhook via the Customer-metadata fallback, with no code involved — worth one test.

**Lifetime holders have no Customer.** Everyone who bought so far did so as a guest checkout (`customer_email`, no Customer), so the account page needs a state for "Lifetime — nothing to manage": no Manage button, or one that lazily creates the Customer. The plan notes the gap; the UI consequence is worth spelling out so it isn't a runtime error.

**Portal plan changes off — agreed, and for a stronger reason.** The portal's update feature lists products a customer may switch between; with two products on one Customer it would allow Market Haro ↔ GUNDECK swaps. Keep it off until each product can be confined to its own prices and that's tested.

Two smaller things, neither wrong as written: account deletion can simply delete the Stripe Customer (which cancels its subscriptions) rather than enumerating them; and `billing_checkout_locks` is more machinery than the problem needs — an idempotency key of `${clerkUserId}:${productKey}:${minute}` on the session-create call gives the same double-click protection with no table.

## The redirect patch

Clean, and the validator is solid (protocol-relative, `javascript:`, look-alike hosts and auth-route loops all fall back to `/`). One gap: the modals receive `forceRedirectUrl`, but a user who opens the sign-*in* modal and clicks its "sign up" link (or the reverse) falls back to Clerk's default and lands on home. Adding `signUpForceRedirectUrl={redirectTarget}` on `SignInButton` and `signInForceRedirectUrl={redirectTarget}` on `SignUpButton` covers it.

## Cutover

October 30, 00:00 Pacific (`2026-10-30T07:00:00Z`; still PDT that day) with sessions created before the boundary allowed to complete — agreed, and recorded on our side the same way.
