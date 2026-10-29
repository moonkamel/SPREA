// Screenshots of the Prospection dashboard for the demo page, on illustrative data
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
// Every recent DPE of the map and the whole buildings, same fictitious streets
const addresses = items.map((o, i) => ({ address: o.address, lat: o.lat, lon: o.lon, worst: o.label,
    dpe: [{ number: o.number, label: o.label, kind: o.kind, surface: o.surface, date: o.dpe_date, period: o.period, detail: null }] }));
const buildings = items.slice(0, 6).map((o, i) => ({ id: `b${i}`, address: o.address, lat: o.lat + 0.001, lon: o.lon - 0.001, nb_log: 4 + i * 2,
    levels: 3 + (i % 3), year_built: 1900 + i * 9, owner: { siren: '', name: `SCI EXEMPLE ${i + 1}`, legal_form: 'SCI', city: 'Tourcoing' }, owner_share: 1,
    dpe_label: i % 2 ? 'F' : 'E', dpe_date: o.dpe_date, dpe_count: 2 + i, dpe_fg: i % 3, last_sale_date: null, last_sale_price: null, last_sale_units: null,
    signal_score: [72, 55, 40, 30, 20, 12][i], signal_level: ['fort', 'moyen', 'moyen', 'faible', 'faible', 'faible'][i] }));
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
        if (u.includes('/api/prospection')) return json({ locked: false, addresses, dwellings: addresses.length, total: addresses.length, truncated: false });
        if (u.includes('/api/monopro')) return json({ buildings, truncated: false });
        if (u.includes('/api/estimate-leads')) return json({ leads });
        if (u.includes('/api/signals')) return json({ total: items.length, truncated: false, dvf_since: 2021, strong: 5,
            items: items.map((o, i) => { const score = Math.max(12, 88 - i * 5); return { address: o.address, lat: o.lat, lon: o.lon, insee: '59599',
                score, level: score >= 60 ? 'fort' : score >= 35 ? 'moyen' : 'faible', label: o.label, dpe_date: o.dpe_date, dwellings: 1, kind: o.kind,
                surface: o.surface, dpe_number: o.number, long_held: i % 2 === 0, last_sale: null, near_sales: i % 3, near_sale: null,
                reasons: [{ points: 35, label: 'DPE de moins de 3 mois : souvent le premier signe d\'une vente ou d\'une location', kind: 'dpe' },
                    { points: 15, label: 'Classé G : plus de nouveau bail possible depuis 2025', kind: 'rental' },
                    ...(i % 2 === 0 ? [{ points: 15, label: 'Aucune vente enregistrée depuis 2021 : propriétaire depuis au moins 5 ans', kind: 'held' }] : [])] }; }) });
        if (u.includes('/api/sales')) return json({ latest: day(150), truncated: false, sales: items.slice(0, 12).map((o, i) => ({
            date: day(150 + i * 20), price: o.price, surface: o.surface, price_m2: Math.round(o.price / o.surface), kind: o.kind,
            street: o.address.replace(/^\d+ /, '').replace(/ 59200.*$/, '').toUpperCase(), number: null, commune: 'Tourcoing',
            lat: o.lat + 0.0006, lon: o.lon - 0.0006, rooms: '4' })) });
        if (u.includes('/api/alerts')) return json({ email_enabled: true, zones: [
            { id: 'z1', name: 'Tourcoing centre', lat: C.lat, lon: C.lon, radius_m: 900, labels: 'F,G', kind: null, email: true, active: true, last_checked_on: day(0), mine: true },
            { id: 'z2', name: 'Blanc Seau', lat: C.lat + 0.008, lon: C.lon - 0.012, radius_m: 600, labels: 'E,F,G', kind: 'maison', email: false, active: true, last_checked_on: day(0), mine: true }],
            hits: items.slice(0, 6).map((o, i) => ({ id: `h${i}`, zone_id: i % 2 ? 'z2' : 'z1', dpe_number: o.number, address: o.address, label: o.label,
                kind: o.kind, surface: o.surface, dpe_date: o.dpe_date, received_on: day(i < 3 ? 0 : 1), detail: null, created_at: iso(i < 3 ? 0 : 1) })) });
        if (u.includes('/api/search-address')) return json({ count: 1, results: [{ address: items[0].address, ademe_dpe_number: items[0].number,
            date_etablissement: items[0].dpe_date, shab: items[0].surface, dpe_class_current: items[0].label, building_type: 'Maison',
            latitude: items[0].lat, longitude: items[0].lon, construction_period: items[0].period }] });
        if (u.includes('/api/agent-page')) return json({ agent_name: 'Tarik Lakel', agency_name: 'SPREA Immobilier' });
        return json({});
    });
    // The map tiles (IGN) must be there before each capture
    const tiles = async () => {
        await p.waitForFunction(() => document.querySelectorAll('.leaflet-tile-loaded').length >= 12, null, { timeout: 30000 }).catch(() => {});
        await p.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
        await p.waitForTimeout(1500);
    };
    await p.goto(`${base}/prospection`, { waitUntil: 'domcontentloaded' });
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
    for (const [name, label] of [['dpe', 'Récents'], ['immeubles', 'Immeubles'], ['alertes', 'Alertes'], ['signaux', 'Signaux']]) {
        await p.getByRole('button', { name: label, exact: true }).click();
        await p.waitForTimeout(2500);
        await tiles();
        await p.screenshot({ path: `${out}/command-${name}.png` });
    }
    await p.getByRole('button', { name: 'DPE', exact: true }).click();
    await p.getByLabel('Adresse ou numéro de DPE').fill('3 rue de Lille, Tourcoing');
    await p.keyboard.press('Enter');
    await p.waitForTimeout(2500);
    await p.screenshot({ path: `${out}/command-fiche.png` });
    await p.getByRole('button', { name: 'Signaux', exact: true }).click();
    await p.waitForTimeout(1500);
    for (let i = 0; i < 6; i++) await p.locator('aside').getByRole('button', { name: 'Tournée', exact: true }).first().click().catch(() => {});
    await p.locator('nav').getByRole('button', { name: /Tournée/ }).click();
    await p.waitForTimeout(800);
    await p.getByRole('button', { name: "Optimiser l'ordre" }).click().catch(() => {});
    await p.waitForTimeout(1500);
    await p.screenshot({ path: `${out}/command-tournee.png` });
    if (errors.length) { console.error(errors); process.exitCode = 1; }
    await b.close();
})();
