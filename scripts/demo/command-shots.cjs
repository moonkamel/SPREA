// Screenshots of SPREA Command for the demo page, on illustrative data
// (fictitious addresses and figures, real map). Usage:
//   node scripts/demo/command-shots.cjs http://localhost:4173 public/demo
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://localhost:4173';
const out = process.argv[3] || 'public/demo';
const day = n => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
const C = { lat: 50.7225, lon: 3.1590 };
const streets = ['rue de Lille', 'rue du Calvaire', 'rue Nationale', 'rue Gambetta', 'rue de Roubaix', 'rue Pasteur', 'rue Faidherbe',
    'rue de Tournai', 'rue de Mouvaux', 'rue des Piats', 'rue Saint-Jacques', 'boulevard Gambetta', 'rue du Château', 'rue de la Cloche',
    'rue Winoc-Chocqueel', 'rue de Guisnes', 'rue du Dragon', 'rue Desurmont'];
let seed = 7;
const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const items = streets.map((s, i) => {
    const maison = i % 3 !== 2;
    const surface = maison ? 78 + Math.round(rnd() * 50) : 42 + Math.round(rnd() * 30);
    const label = i % 4 === 1 ? 'F' : i % 7 === 6 ? 'E' : 'G';
    const price = Math.round((maison ? 1650 : 1550) * surface * (0.9 + rnd() * 0.25) / 1000) * 1000;
    const works = Math.round((maison ? 380 : 330) * surface / 1000) * 1000;
    const aids = Math.round(works * (0.25 + rnd() * 0.15) / 100) * 100;
    const created = Math.round((price * (0.06 + rnd() * 0.12)) / 100) * 100 - i * 400;
    const ang = rnd() * Math.PI * 2, dist = 0.002 + rnd() * 0.011;
    return {
        number: `2659E${String(1000000 + i * 7919).slice(0, 7)}${String.fromCharCode(65 + i)}`,
        address: `${3 + Math.round(rnd() * 90)} ${s} 59200 Tourcoing`, lat: C.lat + Math.sin(ang) * dist * 0.7, lon: C.lon + Math.cos(ang) * dist,
        city: 'Tourcoing', kind: maison ? 'Maison' : 'Appartement', surface, period: ['avant 1948', '1948-1974', '1975-1981'][i % 3],
        dpe_date: day([20, 1, 9, 35, 50, 14, 70, 120, 4, 200, 31, 90, 15, 260, 44, 8, 150, 60][i]), label, new_label: label === 'E' ? 'C' : i % 2 ? 'D' : 'C',
        works_names: maison ? ['Isolation des combles', 'Pompe à chaleur', 'Fenêtres'] : ['Isolation des murs', 'Fenêtres', 'Ventilation'],
        price, notary: 0, works, works_low: Math.round(works * 0.86 / 1000) * 1000, works_high: Math.round(works * 1.17 / 1000) * 1000, aids, total: 0,
        resale: price + created + works - aids, margin: 0, margin_pct: null, value_created: created,
        rent_month: Math.round(surface * 10.2 / 10) * 10, gross_yield: 6.4 + (i % 5) * 0.4,
        rental_now: label === 'G' ? 'Location interdite depuis 2025' : label === 'F' ? 'Louable jusqu\'en 2028' : 'Louable jusqu\'en 2034',
        rental_after: 'Louable sans limite', risks: [`Prix estimé sur ${30 + i * 3} ventes à moins de 500 m`],
    };
});
const scan = { profile: 'bailleur', sort: 'potentiel', analysed: 143, valued: 96, positive: 37, items };
const iso = n => new Date(Date.now() - n * 86400000).toISOString();
const pipeline = [
    { number: items[1].number, status: 'courrier', address: items[1].address, updated_at: iso(3), mine: true },
    { number: items[5].number, status: 'courrier', address: items[5].address, updated_at: iso(16), mine: true },
    { number: 'X1', status: 'courrier', address: '5 rue Pasteur 59200 Tourcoing', updated_at: iso(6), mine: true },
    { number: items[2].number, status: 'relance', address: items[2].address, updated_at: iso(15), mine: true },
    { number: 'X2', status: 'relance', address: '14 rue Faidherbe 59200 Tourcoing', updated_at: iso(4), mine: false },
    { number: 'X3', status: 'rendez_vous', address: '3 place de la Victoire 59200 Tourcoing', updated_at: iso(2), mine: true },
    { number: 'X4', status: 'rendez_vous', address: '61 rue de Mouvaux 59200 Tourcoing', updated_at: iso(5), mine: true },
    { number: 'X5', status: 'mandat', address: '33 rue de Tournai 59200 Tourcoing', updated_at: iso(1), mine: true },
];
const leads = [{ id: 'l1', name: 'Marie Martin', address: '27 rue de la Bourgogne 59200 Tourcoing', city: 'Tourcoing', lat: C.lat + 0.006, lon: C.lon - 0.008,
    project: 'vendre_3m', status: 'new', phone: '06 12 34 56 78', created_at: iso(0) }];

(async () => {
    const b = await chromium.launch();
    const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
    const errors = [];
    p.on('pageerror', e => errors.push(e.message));
    await p.addInitScript(([c]) => {
        localStorage.setItem(`sb-${location.hostname.split('.')[0]}-auth-token`, JSON.stringify({ access_token: 'x.eyJzdWIiOiJ1In0.x', token_type: 'bearer', expires_in: 3600,
            expires_at: Math.floor(Date.now() / 1000) + 3600, refresh_token: 'r', user: { id: 'u', email: 'demo@sprea.app', aud: 'authenticated' } }));
        sessionStorage.setItem('sprea-command-center', JSON.stringify({ lat: c.lat, lon: c.lon, label: 'Tourcoing' }));
        localStorage.setItem('sprea-command-goal', '5');
    }, [C]);
    await p.route('**/api/**', r => {
        const u = r.request().url();
        const json = body => r.fulfill({ json: body });
        if (u.includes('/api/config')) return json({ auth_enabled: true, supabase_url: base, supabase_anon_key: 'k' });
        if (u.includes('/api/me')) return json({ id: 'u', email: 'demo@sprea.app', is_pro: true, subscription_status: 'active', plan: 'pro' });
        if (u.includes('/api/opportunities')) return json(scan);
        if (u.includes('/api/prospect-status/all')) return json({ items: pipeline });
        if (u.includes('/api/prospection')) return json({ locked: false, addresses: [], dwellings: 14, total: 14, truncated: false });
        if (u.includes('/api/monopro')) return json({ buildings: [{ signal_level: 'fort' }, { signal_level: 'moyen' }, { signal_level: 'moyen' }], truncated: false });
        if (u.includes('/api/estimate-leads')) return json({ leads });
        if (u.includes('/api/agent-page')) return json({ agent_name: 'Tarik Lakel', agency_name: 'SPREA Immobilier' });
        return json({});
    });
    // The map tiles (IGN) must be there before each capture
    const tiles = async () => {
        await p.waitForFunction(() => document.querySelectorAll('.leaflet-tile-loaded').length >= 12, null, { timeout: 30000 }).catch(() => {});
        await p.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
        await p.waitForTimeout(1500);
    };
    await p.goto(`${base}/command`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(4000);
    await tiles();
    await p.screenshot({ path: `${out}/command-radar.png` });
    await p.keyboard.press('Enter').catch(() => {});
    await p.getByText('Ouvrir la cible #1').click();
    await p.waitForTimeout(2500);
    await tiles();
    await p.screenshot({ path: `${out}/command-cible.png` });
    await p.getByRole('button', { name: /Suivi/ }).first().click();
    await p.waitForTimeout(1200);
    await p.screenshot({ path: `${out}/command-suivi.png` });
    if (errors.length) { console.error(errors); process.exitCode = 1; }
    await b.close();
})();
