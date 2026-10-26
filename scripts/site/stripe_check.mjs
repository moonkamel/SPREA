// Live check of the payment setup, run from a GitHub runner: prices published
// by /api/config, then a Checkout session for each plan opened under a
// temporary account (live or test mode, amount shown by Stripe), and the
// webhook refusing an unsigned call. Nothing is paid; the account and its
// agency are deleted at the end, and with STRIPE_SECRET_KEY the sessions are
// expired and the Stripe customer deleted too.
// Writes stripe-report/ (results.json, screenshots of the Checkout pages).
//   BASE_URL=https://sprea.app SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... node scripts/site/stripe_check.mjs
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const BASE = (process.env.BASE_URL || 'https://sprea.app').replace(/\/$/, '');
const SB = process.env.SUPABASE_URL;
const SERVICE = process.env.SUPABASE_SERVICE_ROLE_KEY;
const STRIPE = process.env.STRIPE_SECRET_KEY;
const OUT = 'stripe-report';
fs.mkdirSync(OUT, { recursive: true });

const results = { base: BASE, started: new Date().toISOString(), steps: [] };
const save = () => fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify(results, null, 1));

async function step(name, fn) {
    const entry = { name, ok: false };
    try {
        const notes = await fn();
        entry.ok = true;
        if (notes) entry.notes = notes;
    } catch (e) {
        entry.error = String(e && e.message || e).split('\n').slice(0, 4).join(' | ');
    }
    results.steps.push(entry);
    console.log(`${entry.ok ? 'OK ' : 'ERR'} ${name}${entry.notes ? ' — ' + JSON.stringify(entry.notes) : ''}${entry.error ? ' — ' + entry.error : ''}`);
    save();
    return entry.ok;
}

const config = await (await fetch(BASE + '/api/config')).json();
await step('prix publiés (/api/config)', async () => {
    if (!config.billing_enabled) throw new Error('billing_enabled = false');
    const missing = ['solo_monthly', 'solo_yearly', 'agence_monthly', 'agence_yearly'].filter(p => !config.plans?.[p]);
    if (missing.length) throw new Error('formules sans prix : ' + missing.join(', ') + ' — ' + JSON.stringify(config.plans));
    return config.plans;
});

await step('webhook refuse un appel non signé', async () => {
    const r = await fetch(BASE + '/api/stripe/webhook', { method: 'POST', body: '{}', headers: { 'Content-Type': 'application/json' } });
    if (r.status !== 400) throw new Error(`statut ${r.status} (400 attendu) : ${(await r.text()).slice(0, 200)}`);
    return 'statut 400';
});

const admin = { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, 'Content-Type': 'application/json' };
const email = `stripe-check-${Date.now()}@sprea.invalid`;
const password = 'Chk-' + Math.random().toString(36).slice(2) + '-9aZ';
let userId = null, token = null;

const created = await step('compte temporaire (non abonné)', async () => {
    if (!SB || !SERVICE || !config.auth_enabled) throw new Error('secrets Supabase absents ou comptes désactivés');
    const u = await fetch(`${SB}/auth/v1/admin/users`, { method: 'POST', headers: admin, body: JSON.stringify({ email, password, email_confirm: true }) });
    const uj = await u.json();
    if (!u.ok) throw new Error('création : ' + JSON.stringify(uj).slice(0, 200));
    userId = uj.id;
    const s = await fetch(`${SB}/auth/v1/token?grant_type=password`, {
        method: 'POST', headers: { apikey: config.supabase_anon_key, 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    });
    const sj = await s.json();
    if (!s.ok) throw new Error('connexion : ' + JSON.stringify(sj).slice(0, 200));
    token = sj.access_token;
});

let orgId = null, customerId = null;
const sessions = [];
if (created) {
    const browser = await chromium.launch();
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'fr-FR' })).newPage();
    const plans = [
        ['solo_monthly', {}], ['solo_yearly', {}],
        ['agence_monthly', { seats: 2, agency_name: 'Agence Contrôle Stripe' }],
        ['agence_yearly', { seats: 2, agency_name: 'Agence Contrôle Stripe' }],
    ];
    for (const [plan, extra] of plans) {
        await step(`Checkout ${plan}`, async () => {
            const r = await fetch(BASE + '/api/billing/subscribe', {
                method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ plan, accept_terms: true, ...extra }),
            });
            const j = await r.json();
            if (!r.ok) throw new Error(`statut ${r.status} : ${JSON.stringify(j).slice(0, 200)}`);
            const url = j.checkout_url || '';
            if (!url.startsWith('https://checkout.stripe.com/')) throw new Error('URL inattendue : ' + url.slice(0, 120));
            const sid = (url.match(/\/(cs_(?:live|test)_[A-Za-z0-9]+)/) || [])[1];
            if (sid) sessions.push(sid);
            const mode = /\/cs_live_/.test(url) ? 'live' : /\/cs_test_/.test(url) ? 'test' : 'inconnu';
            // Checkout keeps connections open: networkidle never comes
            await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
            await page.getByText(/€/).first().waitFor({ timeout: 30000 });
            await page.waitForTimeout(1500);
            await page.screenshot({ path: path.join(OUT, `${plan}.png`), fullPage: true });
            const text = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
            const amounts = [...new Set(text.match(/\d[\d\s ]*(?:,\d{2})?\s?€/g) || [])].slice(0, 6);
            return { mode, montants: amounts, extrait: text.slice(0, 300) };
        });
    }
    await browser.close();
    // Where a failed Checkout stops: Stripe customer created (the session failed) or not (the key cannot write)
    await step('client Stripe créé pour le compte', async () => {
        const r = await fetch(`${SB}/rest/v1/profiles?id=eq.${userId}&select=stripe_customer_id`, { headers: admin });
        const id = r.ok ? ((await r.json())[0] || {}).stripe_customer_id : null;
        if (!id) throw new Error('aucun client Stripe enregistré');
        customerId = id;
        return id.slice(0, 8) + '…';
    });
    const m =await fetch(`${SB}/rest/v1/memberships?user_id=eq.${userId}&select=org_id`, { headers: admin });
    orgId = m.ok ? ((await m.json())[0] || {}).org_id : null;
}

if (STRIPE && (sessions.length || customerId)) {
    await step('nettoyage Stripe (sessions expirées, client supprimé)', async () => {
        const stripe = (method, p) => fetch('https://api.stripe.com/v1' + p, { method, headers: { Authorization: `Bearer ${STRIPE}` } });
        for (const sid of sessions) await stripe('POST', `/checkout/sessions/${sid}/expire`);
        if (customerId) {
            const r = await stripe('DELETE', `/customers/${customerId}`);
            if (!r.ok) throw new Error('client : statut ' + r.status);
        }
        return `${sessions.length} sessions, client ${customerId ? 'supprimé' : 'absent'}`;
    });
}

await step('suppression du compte temporaire', async () => {
    if (orgId) await fetch(`${SB}/rest/v1/organizations?id=eq.${orgId}`, { method: 'DELETE', headers: admin });
    if (userId) {
        const r = await fetch(`${SB}/auth/v1/admin/users/${userId}`, { method: 'DELETE', headers: admin });
        if (!r.ok) throw new Error('statut ' + r.status);
    }
    return orgId ? 'compte et agence supprimés' : 'compte supprimé';
});

results.finished = new Date().toISOString();
save();
const failed = results.steps.filter(s => !s.ok).length;
console.log(`${results.steps.length - failed}/${results.steps.length} OK`);
process.exit(failed ? 1 : 0);
