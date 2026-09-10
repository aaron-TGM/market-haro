// The gate: a Clerk session token is verified against a JWK set and the
// entitlement Stripe wrote onto the user decides what the reader sees.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker, { verifyToken, entitled } from '../src/index.js';

const b64u = buf => Buffer.from(buf).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const { subtle } = globalThis.crypto;

async function keypair() {
  const kp = await subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']);
  const jwk = await subtle.exportKey('jwk', kp.publicKey);
  return { priv: kp.privateKey, jwks: [{ kty: 'RSA', n: jwk.n, e: jwk.e, kid: 'k1', alg: 'RS256', use: 'sig' }] };
}
async function sign(priv, claims, header = { alg: 'RS256', typ: 'JWT', kid: 'k1' }) {
  const h = b64u(JSON.stringify(header)), p = b64u(JSON.stringify(claims));
  const sig = await subtle.sign('RSASSA-PKCS1-v1_5', priv, new TextEncoder().encode(`${h}.${p}`));
  return `${h}.${p}.${b64u(sig)}`;
}
const env = { CLERK_ISSUER: 'https://clerk.gundeck.ai, https://clerk.marketharo.io', CLERK_PUBLISHABLE_KEY: 'pk_test', ADMIN_SECRET: 's3',
              ENTITLEMENT_VALUES: 'active,trialing', CLERK_SATELLITE_DOMAIN: 'marketharo.io', SIGN_IN_URL: 'https://gundeck.ai/sign-in' };
const now = () => Math.floor(Date.now() / 1000);

test('a good token verifies; expired, wrong issuer, wrong key and tampered ones do not', async () => {
  const { priv, jwks } = await keypair();
  const claims = { iss: 'https://clerk.gundeck.ai', sub: 'user_1', exp: now() + 60, nbf: now() - 5, public_metadata: { marketHaro: { status: 'active' } } };
  const tok = await sign(priv, claims);
  assert.equal((await verifyToken(tok, env, jwks)).sub, 'user_1');
  assert.equal(await verifyToken(await sign(priv, { ...claims, exp: now() - 120 }), env, jwks), null);
  assert.equal(await verifyToken(await sign(priv, { ...claims, iss: 'https://clerk.example.com' }), env, jwks), null);
  assert.equal((await verifyToken(await sign(priv, { ...claims, iss: 'https://clerk.marketharo.io' }), env, jwks)).sub, 'user_1');
  // azp: minted for one of our origins, or absent -- never for a stranger's
  assert.equal((await verifyToken(await sign(priv, { ...claims, azp: 'https://marketharo.io' }), env, jwks)).sub, 'user_1');
  assert.equal((await verifyToken(await sign(priv, { ...claims, azp: 'https://gundeck.ai' }), env, jwks)).sub, 'user_1');
  assert.equal(await verifyToken(await sign(priv, { ...claims, azp: 'https://evil.example' }), env, jwks), null);
  assert.equal(await verifyToken(await sign(priv, { ...claims, azp: 'https://gundeck.ai' }), { ...env, CLERK_AUTHORIZED_PARTIES: 'https://marketharo.io' }, jwks), null);
  const other = await keypair();
  assert.equal(await verifyToken(tok, env, other.jwks), null);
  const [h, p, s] = tok.split('.');
  const forged = b64u(JSON.stringify({ ...claims, sub: 'user_2' }));
  assert.equal(await verifyToken(`${h}.${forged}.${s}`, env, jwks), null);
  assert.equal(await verifyToken(await sign(priv, claims, { alg: 'HS256', kid: 'k1' }), env, jwks), null);
});

test('the entitlement is read from public metadata, either spelling, or from a Clerk Billing plan', () => {
  assert.equal(entitled({ public_metadata: { marketHaro: { status: 'active' } } }, env), true);
  assert.equal(entitled({ public_metadata: { market_haro: { status: 'trialing' } } }, env), true);
  assert.equal(entitled({ public_metadata: { marketHaro: { status: 'canceled' } } }, env), false);
  assert.equal(entitled({ public_metadata: { marketHaro: true } }, env), true);
  assert.equal(entitled({ public_metadata: {} }, env), false);
  assert.equal(entitled({ pla: 'u:market_haro o:team' }, { ...env, ENTITLEMENT_PLAN: 'market_haro' }), true);
  assert.equal(entitled({ pla: 'u:free' }, { ...env, ENTITLEMENT_PLAN: 'market_haro' }), false);
  assert.equal(entitled({ public_metadata: { haro: { tier: 'pro' } } }, { ...env, ENTITLEMENT_PATH: 'public_metadata.haro.tier', ENTITLEMENT_VALUES: 'pro' }), true);
});

test('the front door: splash for strangers, splash for the unsubscribed, the report for subscribers', async () => {
  const { priv, jwks } = await keypair();
  const store = new Map();
  const kv = { get: async (k, t) => { const v = store.get(k) ?? null; return t === 'json' && v ? JSON.parse(v) : v; }, put: async (k, v) => { store.set(k, v); } };
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (u) => String(u).endsWith('/.well-known/jwks.json') ? new Response(JSON.stringify({ keys: jwks })) : realFetch(u);
  const e = { ...env, HARO: kv };
  try {
    let r = await worker.fetch(new Request('https://marketharo.io/admin/report', { method: 'PUT', headers: { 'X-Admin-Secret': 's3' }, body: '<!doctype html><html><head><title>t</title></head><body>REPORT</body></html>' }), e);
    assert.equal(r.status, 200);
    r = await worker.fetch(new Request('https://marketharo.io/admin/report', { method: 'PUT', headers: { 'X-Admin-Secret': 'wrong' }, body: '<html>' }), e);
    assert.equal(r.status, 403);
    r = await worker.fetch(new Request('https://marketharo.io/admin/track', { method: 'PUT', headers: { 'X-Admin-Secret': 's3' }, body: '<!doctype html><html><body>TRACK</body></html>' }), e);
    assert.equal(r.status, 200);

    r = await worker.fetch(new Request('https://marketharo.io/'), e);
    assert.equal(r.status, 200); let body = await r.text();
    assert.match(body, /Start monthly/); assert.match(body, /Sign in/); assert.doesNotMatch(body, /REPORT/);
    assert.equal(r.headers.get('cache-control'), 'private, no-store');
    r = await worker.fetch(new Request('https://marketharo.io/track-record'), e);
    assert.match(await r.text(), /TRACK/);
    assert.match(body, /subscribe\?plan=monthly/); assert.match(body, /redirectToSignUp/); assert.match(body, /checkout.*success/);
    assert.match(body, /&quot;isSatellite&quot;:true/); assert.match(body, /&quot;signInUrl&quot;:&quot;https:\/\/gundeck.ai\/sign-in&quot;/);
    assert.match(body, /data-clerk-domain="marketharo.io"/);   // clerk-js reads the satellite domain from the tag
    r = await worker.fetch(new Request('https://marketharo.io/me'), e);
    assert.deepEqual(await r.json(), { signed_in: false, entitled: false });

    const noplan = await sign(priv, { iss: 'https://clerk.gundeck.ai', sub: 'user_2', exp: now() + 60, public_metadata: {} });
    r = await worker.fetch(new Request('https://marketharo.io/', { headers: { Cookie: `__session=${noplan}` } }), e);
    body = await r.text(); assert.match(body, /no Market Haro subscription/); assert.doesNotMatch(body, /REPORT/);
    r = await worker.fetch(new Request('https://marketharo.io/positions', { headers: { Cookie: `__session=${noplan}` } }), e);
    assert.equal(r.status, 403);
    r = await worker.fetch(new Request('https://marketharo.io/me', { headers: { Cookie: `__session=${noplan}` } }), e);
    assert.deepEqual(await r.json(), { signed_in: true, entitled: false });

    const sub = await sign(priv, { iss: 'https://clerk.marketharo.io', sub: 'user_1', exp: now() + 60, public_metadata: { marketHaro: { status: 'trialing', plan: 'monthly' } } });
    r = await worker.fetch(new Request('https://marketharo.io/', { headers: { Cookie: `__session=${sub}` } }), e);
    body = await r.text(); assert.match(body, /REPORT/); assert.match(body, /clerk.browser.js/); assert.match(body, /&quot;isSatellite&quot;:true/);
    assert.doesNotMatch(body, /haro-welcome/);   // the GUNDECK cross-sell shows once, right after checkout, not every day
    r = await worker.fetch(new Request('https://marketharo.io/?welcome=1', { headers: { Cookie: `__session=${sub}` } }), e);
    body = await r.text(); assert.match(body, /haro-welcome/); assert.match(body, /gundeck.ai\/pricing/); assert.match(body, /<body><div id="haro-welcome"/);
    r = await worker.fetch(new Request('https://marketharo.io/', { headers: { Authorization: `Bearer ${sub}` } }), e);
    assert.match(await r.text(), /REPORT/);
    r = await worker.fetch(new Request('https://marketharo.io/me', { headers: { Authorization: `Bearer ${sub}` } }), e);
    assert.deepEqual(await r.json(), { signed_in: true, entitled: true });

    r = await worker.fetch(new Request('https://marketharo.io/positions', { method: 'PUT', headers: { Cookie: `__session=${sub}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ positions: { '1|Normal': { qty: 2, cost: 10.5, since: '2026-09-01T00:00:00Z' }, bad: 'x', '2|Normal': { qty: -1, cost: 'no' } } }) }), e);
    assert.equal((await r.json()).count, 2);
    r = await worker.fetch(new Request('https://marketharo.io/positions', { headers: { Cookie: `__session=${sub}` } }), e);
    const got = await r.json();
    assert.deepEqual(got.positions['1|Normal'], { qty: 2, cost: 10.5, since: '2026-09-01' });
    assert.deepEqual(got.positions['2|Normal'], { qty: null, cost: null, since: null });
    assert.equal(store.has('u:user_1'), true);
    r = await worker.fetch(new Request('https://marketharo.io/positions'), e);
    assert.equal(r.status, 401);
  } finally { globalThis.fetch = realFetch; }
});
