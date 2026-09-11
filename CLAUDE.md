# Market Haro — briefing for anyone (or any Claude) picking this up

Read this first. It is the state of the project as of its launch (September 2026), and
the rules that keep it safe. The owner is Aaron (aaron@tuffghostmedia.com, GitHub
`aaron-TGM`). The MVP is live at **https://marketharo.io** with paying trials on it.

## What it is

A daily market dashboard for the Gundam Card Game: every English single scored and
ranked, every box measured against the cards inside it. One Python pipeline builds one
self-contained HTML report every morning; one Cloudflare Worker serves it to subscribers.
Sold as its own subscription — **$8/month or $88/year, 7-day trial** — signed in with a
GUNDECK.AI account. `README.md` is the product and method; `docs/ARCHITECTURE.md` is the
code map; `docs/METHOD.md` is the score.

## How it runs (nothing here needs a person)

- **GitHub Actions, `daily`, 13:10 UTC** (`.github/workflows/daily.yml`): restore the
  database from the archive → sync prices from tcgapi.dev → build the report and the
  public preview → tests → commit the archive → push both pages to the site. It has
  run green on its own since Sep 9. Secrets it uses: `TCGAPI_KEY`, `HARO_ADMIN_SECRET`.
- **The site**: one Cloudflare Worker, `market-haro`, custom domain `marketharo.io`,
  KV namespace `HARO`. Code is `worker/src/index.js`. **It was deployed through the
  Cloudflare dashboard, not wrangler**: to change it, edit the file in the repo, run
  `cd worker && npm test`, then Cloudflare → Workers & Pages → market-haro → Edit code →
  replace all → Deploy. Its variables are in the dashboard (Settings → Variables);
  `worker/wrangler.toml` mirrors them for reference. **Never run `wrangler deploy`** — it
  would replace the dashboard's configuration.
- **Identity**: Clerk, gundeck.ai's instance (`clerk.gundeck.ai`); marketharo.io is a
  Clerk *satellite domain*. The Worker verifies the session token (RS256, JWKS, issuer,
  `azp`) and reads one field: `public_metadata.marketHaro.status`; `active` or
  `trialing` opens the report. Clerk's session token carries `public_metadata` by a
  dashboard setting Aaron made.
- **Billing**: Stripe, on gundeck.ai, built by **Manus** (the AI developer of the
  gundeck.ai codebase, `aaron-TGM/gundeckai`). Its webhook writes `marketHaro` onto the
  Clerk user. Market Haro never calls Stripe or Clerk at request time.

## Rules

1. **Do not touch gundeck.ai** — not its DNS, code, Clerk settings that affect it, or
   Stripe. Anything gundeck.ai must do is written for Manus in `docs/HANDOFF-gundeck.md`
   (the contract) and sent by Aaron. Replies to their documents live in `docs/REPLY-*.md`.
2. **Secrets never enter the repo, config, or chat.** The tcgapi key lives only in a
   gitignored `.env` locally and in the GitHub secret `TCGAPI_KEY`; the Worker's
   `ADMIN_SECRET` only in Cloudflare and as `HARO_ADMIN_SECRET` in GitHub. Sweep anything
   you deliver for `tcg_live_`, `sk-`, `ghp_`. If a key is ever pasted in chat, treat it
   as burned and say so.
3. **The Worker's contract is frozen**: reads only `marketHaro.status`; permits only
   `active`/`trialing`; Stripe returns to `https://marketharo.io/?checkout=success`;
   `/me` returns `{signed_in, entitled}`. Changing any of these means changing Manus's
   side too.
4. Commit messages end with the attribution trailer the session provides
   (`Co-Authored-By` and `Claude-Session`). Keep the archive commits (`history: …`) from
   the bot untouched — `git fetch && git merge` before pushing, they land every morning.
5. Aaron prefers no command line where a dashboard will do, plain language over jargon,
   and documents written coworker-to-coworker rather than as orders. Ask before anything
   that costs money or touches customers.

## Where things are

| | |
|---|---|
| Pipeline | `radar/` — `cli.py` (commands), `invest.py` (score), `haro.py` (report), `preview.py` (public page), `track.py` (record), `depth.py`, `sealed.py`, `db.py`, `art.py` |
| Data | `data/history/*.ndjson` (the archive, in git), `data/rankings/YYYY-MM-DD.json` (every issue), `data/cards.ndjson`, `data/sets.ndjson` (set calendar — Stardust Trails GD06 is 2026-10-30) |
| Worker | `worker/src/index.js`, `worker/test/gate.test.js` (`npm test`), `worker/wrangler.toml` (mirror) |
| Tests | `python tests/test_pipeline.py` (53) and the Worker's 3 |
| Docs | `docs/PLAN.md` (the launch plan, all blocks done), `docs/LAUNCH.md`, `docs/HANDOFF-gundeck.md`, `docs/REPLY-implementation-plan.md`, `DEPLOY.md`, `docs/ARCHITECTURE.md`, `docs/METHOD.md` |
| Pages | `/` report (gated) or splash · `/preview` public, today's top ten · `/track-record` → `/preview` · `/me` · `/positions` · `/health` |

Local run: `pip install -r requirements.txt`, a `.env` with `TCGAPI_KEY=…`, then
`python -m radar restore && python -m radar invest --out out/index.html`. Without the key
you can still build from the archive with `--no-fetch`-style paths; see `DEPLOY.md`.

## Decisions that are settled (don't relitigate without Aaron)

- Two products, one account, no bundle: GUNDECK ($3/mo · $29/yr · Lifetime $29 → **$59
  on October 30, 2026**, the GD06 release day) and Market Haro ($8/mo · $88/yr). Each
  offers the other once, right after checkout (ours: the `?welcome=1` banner).
- No commentary, no newsletter, no alerts, no Market Haro 50 index, no Lifetime for
  Market Haro. Numbers; the reader draws the conclusion.
- The public page is the preview (top ten, real numbers), not the track record. The
  record is still computed every issue and its one-line summary appears on the preview
  once calls are 30 days old.

## Standing list after launch

- Daily: is the Action green? (email on failure is set up in GitHub).
- Weekly: Stripe trials → paid → churn; skim the report as a subscriber.
- **Oct 16**: the Lifetime-increase announcement. **Oct 30**: GD06 releases; tick the
  workflow's *backfill* box on the next manual run so the new cards get their history.
- Monthly (1st): the validation line the workflow appends to `data/validation_history.json`.
- Quarterly: rotate `ADMIN_SECRET`/`HARO_ADMIN_SECRET` together; export KV watchlists.
- If a subscriber can't see the report: does their token carry `public_metadata`, did
  the webhook write `marketHaro.status`, is it `active`/`trialing`. `/me` shows what the
  Worker sees.
