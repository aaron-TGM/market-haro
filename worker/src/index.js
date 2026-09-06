// Market Haro sync + alerts. See wrangler.toml for what this is and why.
//
// Routes (all under the Worker's URL; CORS is restricted to GHOST_URL):
//   GET  /positions          the caller's watchlist + holdings   (member JWT)
//   PUT  /positions          replace them                        (member JWT)
//   PUT  /admin/issue        today's compact issue, from the pipeline (ADMIN_SECRET)
//   POST /admin/alerts/run   run the alert pass now               (ADMIN_SECRET)
//   GET  /health
// Cron: the alert pass, once a day after the pipeline has pushed the issue.
//
// The alert RULES are mirrored from radar/alerts.py. If they disagree, the
// Python file is right and this one is wrong. Keep evaluate() the same shape.

const TOP = 20;
const RELEASE_LEAD_DAYS = 7;
const MAX_BODY = 64 * 1024;

// ---------------------------------------------------------------- identity
// Ghost signs a JWT for the logged-in member at GET /members/api/session and
// publishes the verifying key at /members/.well-known/jwks.json. RS512.
const jwksCache = { at: 0, keys: null };
async function jwks(env) {
  if (jwksCache.keys && Date.now() - jwksCache.at < 6 * 3600e3) return jwksCache.keys;
  const r = await fetch(`${env.GHOST_URL.replace(/\/$/, '')}/members/.well-known/jwks.json`);
  if (!r.ok) throw new Error('jwks unavailable');
  const { keys } = await r.json();
  jwksCache.keys = keys; jwksCache.at = Date.now();
  return keys;
}
const b64u = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '=')), c => c.charCodeAt(0));
async function verifyMember(req, env) {
  const auth = req.headers.get('Authorization') || '';
  const tok = auth.startsWith('Bearer ') ? auth.slice(7).trim() : null;
  if (!tok) return null;
  const [h, p, s] = tok.split('.');
  if (!h || !p || !s) return null;
  const header = JSON.parse(new TextDecoder().decode(b64u(h)));
  const payload = JSON.parse(new TextDecoder().decode(b64u(p)));
  if (header.alg !== 'RS512') return null;
  if (payload.exp && payload.exp * 1000 < Date.now()) return null;
  const keys = await jwks(env);
  const jwk = keys.find(k => k.kid === header.kid) || keys[0];
  if (!jwk) return null;
  const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-512' }, false, ['verify']);
  const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64u(s), new TextEncoder().encode(`${h}.${p}`));
  if (!ok || !payload.sub) return null;
  return { email: String(payload.sub).toLowerCase() };
}
async function memberKey(email) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(email));
  return 'm:' + [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
}

// ---------------------------------------------------------------- http
function cors(env, extra = {}) {
  return { 'Access-Control-Allow-Origin': env.GHOST_URL.replace(/\/$/, ''), 'Access-Control-Allow-Methods': 'GET,PUT,POST,OPTIONS',
           'Access-Control-Allow-Headers': 'Authorization,Content-Type', 'Vary': 'Origin', 'Cache-Control': 'no-store', ...extra };
}
const json = (env, body, status = 200) => new Response(JSON.stringify(body), { status, headers: cors(env, { 'Content-Type': 'application/json' }) });

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors(env) });
    if (url.pathname === '/health') return json(env, { ok: true });

    if (url.pathname.startsWith('/admin/')) {
      if (req.headers.get('X-Admin-Secret') !== env.ADMIN_SECRET || !env.ADMIN_SECRET) return json(env, { error: 'forbidden' }, 403);
      if (url.pathname === '/admin/issue' && req.method === 'PUT') {
        const body = await req.text();
        if (body.length > 4 * 1024 * 1024) return json(env, { error: 'too large' }, 413);
        const iss = JSON.parse(body);
        await env.HARO.put('issue', body);
        return json(env, { ok: true, date: iss.date, cards: Object.keys(iss.cards || {}).length });
      }
      if (url.pathname === '/admin/alerts/run' && req.method === 'POST') {
        return json(env, await runAlerts(env));
      }
      return json(env, { error: 'not found' }, 404);
    }

    if (url.pathname === '/positions') {
      const who = await verifyMember(req, env).catch(() => null);
      if (!who) return json(env, { error: 'sign in on the site first' }, 401);
      const k = await memberKey(who.email);
      if (req.method === 'GET') {
        const cur = await env.HARO.get(k, 'json');
        return json(env, cur || { positions: {}, updated_at: null });
      }
      if (req.method === 'PUT') {
        const body = await req.text();
        if (body.length > MAX_BODY) return json(env, { error: 'too large' }, 413);
        let incoming; try { incoming = JSON.parse(body); } catch { return json(env, { error: 'bad json' }, 400); }
        const positions = {};
        for (const [key, v] of Object.entries(incoming.positions || {})) {
          if (typeof key !== 'string' || key.length > 80) continue;
          positions[key] = { qty: num(v.qty), cost: num(v.cost), since: typeof v.since === 'string' ? v.since.slice(0, 10) : null };
        }
        const rec = { email: who.email, positions, updated_at: new Date().toISOString(), last_alert_date: (await env.HARO.get(k, 'json'))?.last_alert_date || null };
        await env.HARO.put(k, JSON.stringify(rec));
        return json(env, { ok: true, updated_at: rec.updated_at, count: Object.keys(positions).length });
      }
    }
    return json(env, { error: 'not found' }, 404);
  },

  async scheduled(_event, env, ctx) { ctx.waitUntil(runAlerts(env)); },
};
const num = v => (typeof v === 'number' && isFinite(v) && v > 0) ? v : null;

// ---------------------------------------------------------------- alerts
// Mirror of radar/alerts.py::evaluate. Same rules, same order, same words.
export function evaluate(iss, positions, today) {
  const out = [];
  const cards = iss.cards || {}, top = iss.top || TOP;
  for (const [k, pos] of Object.entries(positions)) {
    const c = cards[k]; if (!c) continue;
    const held = !!pos.qty, name = c.name || k;
    if (c.trend_broke && !c.prev_trend_broke)
      out.push({ kind: 'trend_broke', key: k, name, text: `${name} broke trend today` + (held ? ' — you hold it.' : '.') });
    if (c.prem != null && c.prem < -2 && (c.prev_prem == null || c.prev_prem >= -2) && !c.sealed)
      out.push({ kind: 'ask_below_sold', key: k, name, text: `${name} is now listed ${Math.abs(c.prem).toFixed(0)}% below what it has been selling for.` });
    const r = c.rank, pr = c.prev_rank;
    if (pr != null && pr <= top && (r == null || r > top))
      out.push({ kind: 'left_top_20', key: k, name, text: `${name} left the top ${top}` + (r ? ` (now #${r}).` : ' (screened out).') });
    if (r != null && r <= top && (pr == null || pr > top) && !held)
      out.push({ kind: 'entered_top_20', key: k, name, text: `${name} entered the top ${top} at #${r}.` });
  }
  const nxt = iss.next_release; today = today || iss.date;
  if (nxt && today) {
    const lead = Math.round((Date.parse(nxt.date) - Date.parse(today)) / 86400e3);
    if (lead === RELEASE_LEAD_DAYS) {
      const names = (nxt.names && nxt.names.length ? nxt.names : [nxt.label || '']).join(', ');
      out.push({ kind: 'release_soon', key: null, name: nxt.label, text: `${names} releases in ${RELEASE_LEAD_DAYS} days (${nxt.date}). On record, the previous set's top cards fell into a release; see the playbook.` });
    }
  }
  const order = { trend_broke: 0, left_top_20: 1, ask_below_sold: 2, entered_top_20: 3, release_soon: 4 };
  out.sort((a, b) => (order[a.kind] ?? 9) - (order[b.kind] ?? 9) || String(a.name).localeCompare(String(b.name)));
  return out;
}
export function pnl(iss, positions) {
  let basis = 0, value = 0, n = 0;
  for (const [k, pos] of Object.entries(positions)) {
    const px = iss.cards?.[k]?.price;
    if (!pos.qty || !pos.cost || !px) continue;
    n++; basis += pos.qty * pos.cost; value += pos.qty * px;
  }
  if (!n) return null;
  return { positions: n, basis, value, pnl: value - basis, pct: basis ? (value / basis - 1) * 100 : null };
}

async function runAlerts(env) {
  const iss = await env.HARO.get('issue', 'json');
  if (!iss) return { ok: false, reason: 'no issue pushed yet' };
  let members = 0, sent = 0, skipped = 0, cursor;
  do {
    const page = await env.HARO.list({ prefix: 'm:', cursor });
    cursor = page.list_complete ? null : page.cursor;
    for (const { name } of page.keys) {
      const rec = await env.HARO.get(name, 'json'); if (!rec || !rec.email) continue;
      members++;
      if (rec.last_alert_date === iss.date) { skipped++; continue; }
      const alerts = evaluate(iss, rec.positions || {}, iss.date);
      const p = pnl(iss, rec.positions || {});
      if (alerts.length && env.RESEND_API_KEY) {
        await sendMail(env, rec.email, iss, alerts, p);
        sent++;
      }
      rec.last_alert_date = iss.date;
      await env.HARO.put(name, JSON.stringify(rec));
    }
  } while (cursor);
  return { ok: true, date: iss.date, members, sent, skipped };
}

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export function mailHTML(iss, alerts, p) {
  const money = v => '$' + Math.abs(v).toFixed(2);
  const pnlLine = p ? `<p style="margin:0 0 14px;font-size:15px"><b>Your ${p.positions} ${p.positions === 1 ? 'position' : 'positions'}:</b> ${money(p.value)} now against ${money(p.basis)} in — <b style="color:${p.pnl >= 0 ? '#2e9e4f' : '#c43a2f'}">${p.pnl >= 0 ? '+' : '−'}${money(p.pnl)} (${p.pct >= 0 ? '+' : ''}${p.pct.toFixed(1)}%)</b></p>` : '';
  const items = alerts.map(a => `<li style="margin:6px 0">${esc(a.text)}</li>`).join('');
  return `<div style="font-family:ui-monospace,Menlo,monospace;font-size:14px;line-height:1.55;color:#111;max-width:600px">
    <p style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#888;margin:0 0 6px">Market Haro · from GUNDECK.AI · ${esc(iss.date)}</p>
    ${pnlLine}
    <p style="margin:0 0 6px"><b>${alerts.length} ${alerts.length === 1 ? 'thing' : 'things'} changed on cards you follow:</b></p>
    <ul style="padding-left:18px;margin:0 0 16px">${items}</ul>
    ${iss.report_url ? `<p><a href="${esc(iss.report_url)}" style="display:inline-block;background:#e0a030;color:#111;padding:9px 14px;text-decoration:none;font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:12px">Open today's report</a></p>` : ''}
    <p style="font-size:11px;color:#888;margin-top:18px">These are changes in what the numbers say about cards on your watchlist. Nothing here is a forecast or financial advice; trading cards can lose value.</p>
  </div>`;
}
async function sendMail(env, to, iss, alerts, p) {
  const lead = alerts[0];
  const subject = `Market Haro ${iss.date} — ${alerts.length === 1 ? lead.text.replace(/\.$/, '') : `${alerts.length} changes on cards you follow`}`;
  const r = await fetch('https://api.resend.com/emails', {
    method: 'POST', headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: env.MAIL_FROM, to: [to], subject, html: mailHTML(iss, alerts, p) }),
  });
  if (!r.ok) throw new Error(`resend ${r.status}`);
}
