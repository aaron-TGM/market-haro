// Market Haro at marketharo.io: one Worker that serves one page.
//
// What it does, and all it does:
//   GET  /                 the report, if the caller is a signed-in GUNDECK
//                          user with a Market Haro subscription; otherwise the
//                          splash (sign in / subscribe)
//   GET  /me               {signed_in, entitled} for the page's own scripts
//   GET  /track-record     the public track record
//   GET  /positions        the caller's watchlist + holdings   (signed in)
//   PUT  /positions        replace them                        (signed in)
//   PUT  /admin/report     today's report HTML, from the pipeline   (X-Admin-Secret)
//   PUT  /admin/track      the track record HTML, from the pipeline (X-Admin-Secret)
//   GET  /health
//
// Identity is Clerk's. The same Clerk instance that signs people in to
// gundeck.ai hands the browser a short-lived RS256 session token; Clerk's
// script on this domain keeps it in the `__session` cookie. This domain is a
// Clerk *satellite* of gundeck.ai (CLERK_SATELLITE_DOMAIN): sign-in and
// sign-up happen on gundeck.ai's pages and come back here; the session is
// the same. This Worker verifies the token against Clerk's published keys
// and reads the entitlement Stripe wrote onto the user (via the gundeck.ai
// webhook). No password, no session store, no call to Clerk or Stripe at
// request time.
//
// Vars (wrangler.toml): CLERK_ISSUER (one or more, comma-separated),
//   CLERK_PUBLISHABLE_KEY, CLERK_SATELLITE_DOMAIN, SIGN_IN_URL, SIGN_UP_URL,
//   CHECKOUT_URL, MANAGE_URL, ENTITLEMENT_PATH, ENTITLEMENT_VALUES, ENTITLEMENT_PLAN
// Secret (`npx wrangler secret put ADMIN_SECRET`): shared with the pipeline.

const MAX_BODY = 64 * 1024;
const MAX_PAGE = 12 * 1024 * 1024;
const LEEWAY_S = 30;

// ---------------------------------------------------------------- identity
const issuers = env => String(env.CLERK_ISSUER || '').split(',').map(s => s.trim().replace(/\/$/, '')).filter(Boolean);
const jwksCache = { at: 0, keys: null, issuer: null };
async function jwks(env) {
  const issuer = issuers(env)[0];
  if (jwksCache.keys && jwksCache.issuer === issuer && Date.now() - jwksCache.at < 3600e3) return jwksCache.keys;
  const r = await fetch(`${issuer}/.well-known/jwks.json`, { cf: { cacheTtl: 3600 } });
  if (!r.ok) throw new Error('jwks unavailable');
  const { keys } = await r.json();
  jwksCache.keys = keys; jwksCache.at = Date.now(); jwksCache.issuer = issuer;
  return keys;
}
const b64u = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '=')), c => c.charCodeAt(0));
const decode = s => JSON.parse(new TextDecoder().decode(b64u(s)));

function tokenFrom(req) {
  const auth = req.headers.get('Authorization') || '';
  if (auth.startsWith('Bearer ')) return auth.slice(7).trim();
  const cookie = req.headers.get('Cookie') || '';
  const m = /(?:^|;\s*)__session=([^;]+)/.exec(cookie);
  return m ? decodeURIComponent(m[1]) : null;
}

/** Verify a Clerk session token. Returns its claims, or null. `keys` may be
 *  passed by tests; otherwise Clerk's JWKS is fetched and cached. */
export async function verifyToken(tok, env, keys = null) {
  if (!tok) return null;
  const parts = tok.split('.');
  if (parts.length !== 3) return null;
  let header, payload;
  try { header = decode(parts[0]); payload = decode(parts[1]); } catch { return null; }
  if (header.alg !== 'RS256') return null;
  const now = Date.now() / 1000;
  if (typeof payload.exp !== 'number' || payload.exp + LEEWAY_S < now) return null;
  if (typeof payload.nbf === 'number' && payload.nbf - LEEWAY_S > now) return null;
  if (!issuers(env).includes(String(payload.iss || '').replace(/\/$/, ''))) return null;
  if (!payload.sub) return null;
  const list = keys || await jwks(env);
  const jwk = list.find(k => k.kid === header.kid) || (list.length === 1 ? list[0] : null);
  if (!jwk) return null;
  const key = await crypto.subtle.importKey('jwk', { kty: jwk.kty, n: jwk.n, e: jwk.e }, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
  const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64u(parts[2]), new TextEncoder().encode(`${parts[0]}.${parts[1]}`));
  return ok ? payload : null;
}

/** Does this session carry a Market Haro subscription?
 *
 *  Stripe's webhook on gundeck.ai writes the entitlement onto the Clerk
 *  user's public metadata, and Clerk's session-token template copies
 *  public_metadata into the token. ENTITLEMENT_PATH is the dotted path to
 *  the status field (default public_metadata.marketHaro.status, with
 *  market_haro accepted too); ENTITLEMENT_VALUES the statuses that count.
 *  If Clerk Billing is used instead, ENTITLEMENT_PLAN names the plan slug
 *  to look for in Clerk's `pla` / `fea` claims. */
export function entitled(claims, env) {
  if (!claims) return false;
  const values = String(env.ENTITLEMENT_VALUES || 'active,trialing').split(',').map(s => s.trim().toLowerCase());
  const paths = env.ENTITLEMENT_PATH ? [env.ENTITLEMENT_PATH]
    : ['public_metadata.marketHaro.status', 'public_metadata.market_haro.status', 'public_metadata.marketHaro', 'public_metadata.market_haro'];
  for (const p of paths) {
    const v = p.split('.').reduce((o, k) => (o && typeof o === 'object') ? o[k] : undefined, claims);
    if (v === true) return true;
    if (typeof v === 'string' && values.includes(v.toLowerCase())) return true;
  }
  const plan = env.ENTITLEMENT_PLAN;
  if (plan) {
    for (const claim of ['pla', 'fea']) {
      const s = claims[claim];
      const items = Array.isArray(s) ? s : String(s || '').split(/[\s,]+/);
      if (items.some(x => x === plan || x.endsWith(':' + plan))) return true;
    }
  }
  return false;
}

async function whoami(req, env) {
  try { return await verifyToken(tokenFrom(req), env); } catch { return null; }
}

// ---------------------------------------------------------------- pages
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');

/** Clerk's browser script, which keeps the session cookie fresh on this
 *  domain and lets the splash know who is signed in. */
function clerkOptions(env) {
  // A satellite domain must say so, and name the primary's sign-in page.
  const o = {};
  if (env.CLERK_SATELLITE_DOMAIN) {
    o.isSatellite = true;
    o.domain = env.CLERK_SATELLITE_DOMAIN;
    o.signInUrl = env.SIGN_IN_URL || 'https://gundeck.ai/sign-in';
    o.signUpUrl = env.SIGN_UP_URL || 'https://gundeck.ai/sign-up';
  }
  return o;
}
function clerkScript(env) {
  const host = issuers(env)[0].replace(/^https?:\/\//, '');
  const opts = esc(JSON.stringify(clerkOptions(env)));   // inside an attribute: quotes as &quot;
  return `<script async crossorigin="anonymous" data-clerk-publishable-key="${esc(env.CLERK_PUBLISHABLE_KEY || '')}" src="https://${esc(host)}/npm/@clerk/clerk-js@5/dist/clerk.browser.js" onload="window.Clerk.load(${opts}).then(function(){window.__clerkLoaded=true;document.dispatchEvent(new Event('clerk:loaded'))})"></script>`;
}

function splash(env, state) {
  // state: 'anon' (no valid session) | 'noplan' (signed in, not subscribed)
  // The one route on gundeck.ai that starts a subscription for the signed-in
  // user: CHECKOUT_URL + ?plan=monthly|annual opens Stripe Checkout and, on
  // success, returns to this page with ?checkout=success. Sign-up happens
  // here, in Clerk's own modal, before that hand-off.
  const track = '/track-record';
  const checkout = env.CHECKOUT_URL || 'https://gundeck.ai/market-haro/subscribe';
  const monthly = `${checkout}?plan=monthly`, annual = `${checkout}?plan=annual`;
  const manage = env.MANAGE_URL || 'https://gundeck.ai/account';
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Haro — from GUNDECK.AI</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap">
<style>
:root{--bg:#07090c;--surface:#0d1117;--line:#2a2418;--text:#f2ead8;--muted:#9a917f;--accent:#e0a030;--up:#5fd08a}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 "JetBrains Mono",ui-monospace,Menlo,monospace}
.wrap{max-width:760px;margin:0 auto;padding:40px 20px 80px}
.brand{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}
h1{margin:6px 0 4px;font-size:34px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.tag{color:var(--muted);font-size:13px;margin:0 0 26px}
p{margin:0 0 14px;max-width:64ch}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:26px 0 12px}
.plan{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:2px;padding:18px 18px 16px}
.plan::before{content:"";position:absolute;top:-1px;left:-1px;width:12px;height:12px;border:2px solid var(--accent);border-right:0;border-bottom:0}
.plan .l{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
.plan .v{font-size:30px;font-weight:700;color:var(--accent);line-height:1.1;margin:6px 0 2px}.plan .v small{font-size:13px;color:var(--muted);font-weight:400}
.plan .f{font-size:12px;color:var(--muted);margin-bottom:14px}
a.btn{display:inline-block;background:var(--accent);color:var(--bg);text-decoration:none;font-weight:700;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:11px 16px;border-radius:2px}
a.btn.quiet{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}
.who{font-size:12px;color:var(--muted);margin-top:14px}.who b{color:var(--text)}
ul{padding-left:18px;color:var(--muted)}li{margin:4px 0}
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:11px;line-height:1.6}
</style></head><body><div class="wrap">
<div class="brand">from GUNDECK.AI</div><h1>Market Haro</h1>
<p class="tag">Today's Gundam Card Game market, ranked. Rebuilt every morning from the whole English market on TCGplayer.</p>
<p>Every single worth holding, scored 0–100 on value, liquidity, trend, stability and scarcity and gated on the things that make a card un-holdable. Every box and deck measured against what is inside it. A 90-day chart on every row with every set release marked. Your watchlist and holdings, with P&amp;L, following your GUNDECK account across devices. And a public record of every call, scored 30 days later, losers kept.</p>
<ul><li>~130 singles pass the screen each day, from ~200 that qualify</li><li>Sealed: boxes, decks, cases against release and against the set beneath them</li><li>What every release did to prices, on our own record</li><li>No newsletter, no hot takes. Numbers, and you draw the conclusion.</li></ul>
<div id="pending" class="plan" hidden><div class="l">One moment</div><div class="v" style="font-size:18px">Finishing your subscription…</div><div class="f" id="pending-f">Stripe is telling your GUNDECK account about it. This usually takes a few seconds.</div></div>
<div class="plans" id="plans">
  <div class="plan"><div class="l">Monthly</div><div class="v">$8<small> / month</small></div><div class="f">7-day free trial · cancel any time</div><a class="btn" href="${esc(monthly)}" data-plan="monthly">Start monthly</a></div>
  <div class="plan"><div class="l">Annual</div><div class="v">$88<small> / year</small></div><div class="f">7-day free trial · eleven months for twelve</div><a class="btn" href="${esc(annual)}" data-plan="annual">Start annual</a></div>
</div>
<p class="tag">Card entered at sign-up, nothing charged for seven days. An add-on to GUNDECK.AI — one account for both, billed separately. Prices from tcgapi.dev under commercial licence.</p>
<div class="row" id="auth">${state === 'noplan'
  ? `<span class="who" id="who">Signed in. This account has no Market Haro subscription yet — pick a plan above.</span> <a class="btn quiet" href="${esc(manage)}">Manage account</a> <a class="btn quiet" href="#" id="signout">Sign out</a>`
  : `<a class="btn quiet" href="#" id="signin">Already subscribed? Sign in</a>`}</div>
<div class="row"><a class="btn quiet" href="${track}">See the public track record</a></div>
<p class="tag" style="margin-top:14px">Signing in or up takes you to gundeck.ai for a moment and brings you straight back.</p>
<footer>Market Haro is published by GUNDECK.AI. Every number describes what a card has already done. Nothing here is a forecast, a recommendation or financial advice; trading cards can lose value.</footer>
</div>
${clerkScript(env)}
<script>
(function(){
  var state = ${JSON.stringify(state)};
  var params = new URLSearchParams(location.search);
  var afterCheckout = params.get('checkout') === 'success';
  function $(id){ return document.getElementById(id); }

  // Back from Stripe: the webhook that writes the entitlement onto the
  // account can land a few seconds after the browser does. Ask Clerk for a
  // fresh token, ask this server whether it now sees the subscription, and
  // open the report the moment it does. Give up after a minute, kindly.
  function waitForEntitlement(C){
    $('pending').hidden = false; $('plans').hidden = true;
    var tries = 0;
    (function poll(){
      tries++;
      var p = (C && C.session) ? C.session.getToken({ skipCache: true }).catch(function(){ return null; }) : Promise.resolve(null);
      p.then(function(tok){
        var h = tok ? { Authorization: 'Bearer ' + tok } : {};
        return fetch('/me', { credentials: 'same-origin', headers: h }).then(function(r){ return r.json(); });
      }).then(function(me){
        if (me && me.entitled) { location.replace('/'); return; }
        if (tries < 20) setTimeout(poll, 3000);
        else $('pending-f').textContent = 'This is taking longer than usual. Your payment is safe; reload this page in a minute, or check your GUNDECK account page.';
      }).catch(function(){ if (tries < 20) setTimeout(poll, 3000); });
    })();
  }

  function onClerk(){
    var C = window.Clerk;
    if (afterCheckout) { waitForEntitlement(C); return; }
    if (state === 'anon' && C.user) {
      // Signed in on gundeck.ai: Clerk has just set this domain's session
      // cookie, so one reload lets the server read it. Guarded: once.
      var k = 'haro.reloaded', t = 0; try { t = +sessionStorage.getItem(k) || 0; } catch(e){}
      if (Date.now() - t > 30000) { try { sessionStorage.setItem(k, String(Date.now())); } catch(e){} location.reload(); return; }
    }
    if (state === 'noplan' && C.user) {
      var who = $('who'); var em = C.user.primaryEmailAddress && C.user.primaryEmailAddress.emailAddress;
      if (who && em) who.innerHTML = 'Signed in as <b>' + em.replace(/[<>&]/g, '') + '</b>. This account has no Market Haro subscription yet — pick a plan above.';
    }
    // The plan buttons: a stranger creates the GUNDECK account first --
    // on gundeck.ai's sign-up page (this domain is a satellite, so Clerk
    // sends them there and back) -- and lands on checkout when it is done;
    // someone already signed in goes straight to checkout.
    var satellite = ${JSON.stringify(!!env.CLERK_SATELLITE_DOMAIN)};
    document.querySelectorAll('a[data-plan]').forEach(function(a){
      a.onclick = function(e){
        e.preventDefault();
        if (C.user) { location.href = a.href; return; }
        if (satellite) C.redirectToSignUp({ redirectUrl: a.href, signInForceRedirectUrl: a.href, signUpForceRedirectUrl: a.href });
        else C.openSignUp({ forceRedirectUrl: a.href, signInForceRedirectUrl: a.href });
      };
    });
    var so = $('signout'); if (so) so.onclick = function(e){ e.preventDefault(); C.signOut().then(function(){ location.reload(); }); };
    var si = $('signin'); if (si) si.onclick = function(e){ e.preventDefault(); if (C.user) { location.reload(); return; }
      if (satellite) C.redirectToSignIn({ redirectUrl: location.origin + '/', signInForceRedirectUrl: location.origin + '/' });
      else C.openSignIn({ forceRedirectUrl: location.origin + '/' }); };
  }
  // Clerk's script is async and may finish before or after this one runs.
  if (window.__clerkLoaded) onClerk(); else document.addEventListener('clerk:loaded', onClerk);
  if (afterCheckout) { setTimeout(function(){ if (!window.__clerkLoaded) waitForEntitlement(null); }, 8000); }
})();
</script>
</body></html>`;
}

/** The report page as the pipeline built it, with Clerk's script added so
 *  the session cookie stays fresh while the reader keeps the tab open. */
function withClerk(html, env) {
  const tag = clerkScript(env);
  return html.includes('</head>') ? html.replace('</head>', tag + '</head>') : tag + html;
}

// ---------------------------------------------------------------- http
const noStore = { 'Cache-Control': 'private, no-store', 'X-Robots-Tag': 'noindex' };
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...noStore } });
const html = (body, status = 200, extra = {}) => new Response(body, { status, headers: { 'Content-Type': 'text/html; charset=utf-8', ...noStore, ...extra } });
const num = v => (typeof v === 'number' && isFinite(v) && v > 0) ? v : null;

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';

    if (path === '/health') return json({ ok: true });

    if (path.startsWith('/admin/')) {
      if (!env.ADMIN_SECRET || req.headers.get('X-Admin-Secret') !== env.ADMIN_SECRET) return json({ error: 'forbidden' }, 403);
      if (req.method !== 'PUT') return json({ error: 'method' }, 405);
      const key = { '/admin/report': 'report', '/admin/track': 'track' }[path];
      if (!key) return json({ error: 'not found' }, 404);
      const body = await req.text();
      if (body.length > MAX_PAGE) return json({ error: 'too large' }, 413);
      if (!/<html|<!doctype/i.test(body.slice(0, 200))) return json({ error: 'not a page' }, 400);
      await env.HARO.put(key, body);
      await env.HARO.put(key + ':meta', JSON.stringify({ bytes: body.length, at: new Date().toISOString() }));
      return json({ ok: true, key, bytes: body.length });
    }

    if (path === '/me') {
      const who = await whoami(req, env);
      return json({ signed_in: !!who, entitled: !!who && entitled(who, env) });
    }

    if (path === '/track-record') {
      const page = await env.HARO.get('track');
      return page ? html(page, 200, { 'Cache-Control': 'public, max-age=600', 'X-Robots-Tag': 'all' })
                  : html('<!doctype html><title>Market Haro</title><p style="font-family:monospace;padding:2rem">The track record has not been published yet.</p>', 404);
    }

    if (path === '/positions') {
      const who = await whoami(req, env);
      if (!who) return json({ error: 'sign in first' }, 401);
      if (!entitled(who, env)) return json({ error: 'no subscription' }, 403);
      const k = 'u:' + who.sub;
      if (req.method === 'GET') {
        const cur = await env.HARO.get(k, 'json');
        return json(cur || { positions: {}, updated_at: null });
      }
      if (req.method === 'PUT') {
        const body = await req.text();
        if (body.length > MAX_BODY) return json({ error: 'too large' }, 413);
        let incoming; try { incoming = JSON.parse(body); } catch { return json({ error: 'bad json' }, 400); }
        const positions = {};
        for (const [key, v] of Object.entries(incoming.positions || {})) {
          if (typeof key !== 'string' || key.length > 80 || !v || typeof v !== 'object') continue;
          positions[key] = { qty: num(v.qty), cost: num(v.cost), since: typeof v.since === 'string' ? v.since.slice(0, 10) : null };
        }
        const rec = { positions, updated_at: new Date().toISOString() };
        await env.HARO.put(k, JSON.stringify(rec));
        return json({ ok: true, updated_at: rec.updated_at, count: Object.keys(positions).length });
      }
      return json({ error: 'method' }, 405);
    }

    if (path === '/') {
      if (req.method !== 'GET' && req.method !== 'HEAD') return json({ error: 'method' }, 405);
      const who = await whoami(req, env);
      if (!who) return html(splash(env, 'anon'));
      if (!entitled(who, env)) return html(splash(env, 'noplan'));
      const page = await env.HARO.get('report');
      if (!page) return html('<!doctype html><title>Market Haro</title><p style="font-family:monospace;padding:2rem">Today\'s report is not published yet. Check back shortly.</p>', 503, { 'Retry-After': '600' });
      return html(withClerk(page, env));
    }

    return json({ error: 'not found' }, 404);
  },
};
