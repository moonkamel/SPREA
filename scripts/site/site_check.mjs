// Live check of the site, run from a GitHub runner (the dev sandbox cannot
// reach it): every public page and link, then the Pro journeys with real data
// under a temporary subscriber account, deleted at the end. Read-only for the
// site's data apart from that account. Writes site-report/ (results.json,
// screenshots, the PDFs downloaded).
//   BASE_URL=https://sprea.app SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... node scripts/site/site_check.mjs
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const BASE = (process.env.BASE_URL || 'https://sprea.app').replace(/\/$/, '');
const SB = process.env.SUPABASE_URL;
const SERVICE = process.env.SUPABASE_SERVICE_ROLE_KEY;
const OUT = 'site-report';
fs.mkdirSync(path.join(OUT, 'shots'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'pdf'), { recursive: true });

const results = { base: BASE, started: new Date().toISOString(), steps: [], pages: [], links: [], console: [], failed: [] };
const save = () => fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify(results, null, 1));

async function step(name, fn) {
    const t0 = Date.now();
    const entry = { name, ok: false, ms: 0 };
    try {
        const notes = await fn();
        entry.ok = true;
        if (notes) entry.notes = notes;
    } catch (e) {
        entry.error = String(e && e.message || e).split('\n').slice(0, 4).join(' | ');
    }
    entry.ms = Date.now() - t0;
    results.steps.push(entry);
    console.log(`${entry.ok ? 'OK ' : 'ERR'} ${name} (${entry.ms} ms)${entry.error ? ' — ' + entry.error : ''}`);
    save();
    return entry.ok;
}

function watch(page, label) {
    page.on('console', m => { if (m.type() === 'error') results.console.push({ where: label(), text: m.text().slice(0, 300) }); });
    page.on('pageerror', e => results.console.push({ where: label(), text: 'pageerror: ' + e.message.slice(0, 300) }));
    page.on('response', r => {
        const u = r.url();
        if (r.status() >= 400 && u.startsWith(BASE)) results.failed.push({ where: label(), url: u.replace(BASE, ''), status: r.status() });
    });
}

// Closes the guided tour when it shows up
async function skipTour(page) {
    const b = page.getByRole('button', { name: 'Passer' });
    if (await b.isVisible().catch(() => false)) await b.click().catch(() => {});
}

async function overflow(page) {
    return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
let where = 'start';

// ---------- 1. Public site ----------
const pub = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'fr-FR' });
const p = await pub.newPage();
watch(p, () => where);

const PUBLIC = ['/', '/demo', '/tarifs', '/observatoire', '/cgv', '/mentions-legales', '/confidentialite', '/prospection', '/alertes', '/contacts'];
let sitemap = [];
await step('sitemap.xml et robots.txt', async () => {
    const sm = await p.request.get(BASE + '/sitemap.xml');
    if (!sm.ok()) throw new Error('sitemap ' + sm.status());
    sitemap = [...(await sm.text()).matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1].replace(/^https?:\/\/[^/]+/, ''));
    const rb = await p.request.get(BASE + '/robots.txt');
    if (!rb.ok()) throw new Error('robots ' + rb.status());
    return `${sitemap.length} URL dans le sitemap`;
});

const linkSet = new Set();
for (const route of [...new Set([...PUBLIC, ...sitemap])]) {
    where = route;
    await step(`page ${route}`, async () => {
        const res = await p.goto(BASE + route, { waitUntil: 'networkidle', timeout: 45000 });
        const status = res ? res.status() : 0;
        await p.waitForTimeout(400);
        const info = await p.evaluate(() => ({
            title: document.title,
            description: document.querySelector('meta[name="description"]')?.content || '',
            h1: document.querySelector('h1')?.textContent?.trim() || '',
            // The site's own images (map tiles come from IGN)
            images: [...document.images].filter(i => i.complete && i.naturalWidth === 0 && i.src.startsWith(location.origin)).map(i => i.src),
            links: [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')),
        }));
        info.links.filter(h => h && h.startsWith('/') && !h.startsWith('//')).forEach(h => linkSet.add(h.split('#')[0]));
        results.pages.push({ route, status, title: info.title, description: info.description.length, h1: info.h1, brokenImages: info.images });
        if (status >= 400) throw new Error('HTTP ' + status);
        if (!info.title) throw new Error('pas de titre');
        if (info.images.length) throw new Error('images cassées : ' + info.images.join(', '));
        return `${info.title.slice(0, 70)} · h1 « ${info.h1.slice(0, 50)} »`;
    });
}
await step('page inexistante → 404 propre', async () => {
    where = '/page-qui-nexiste-pas';
    await p.goto(BASE + '/page-qui-nexiste-pas', { waitUntil: 'networkidle' });
    const txt = await p.textContent('body');
    if (!/introuvable|n'existe pas|404/i.test(txt)) throw new Error('pas de message 404');
});
await step('liens internes', async () => {
    const bad = [];
    for (const href of linkSet) {
        if (!href || href === '/') continue;
        const r = await p.request.get(BASE + href);
        results.links.push({ href, status: r.status() });
        if (r.status() >= 400) bad.push(`${href} (${r.status()})`);
    }
    if (bad.length) throw new Error(bad.join(', '));
    return `${linkSet.size} liens vérifiés`;
});
await step('visite guidée publique : ancres de la frise', async () => {
    where = '/demo';
    await p.goto(BASE + '/demo', { waitUntil: 'networkidle' });
    const anchors = await p.evaluate(() => [...document.querySelectorAll('ol a[href^="#"]')].map(a => a.getAttribute('href')));
    const missing = [];
    for (const a of anchors) if (!(await p.locator(a).count())) missing.push(a);
    if (missing.length) throw new Error('ancres sans étape : ' + missing.join(', '));
    const imgs = await p.evaluate(() => [...document.images].map(i => i.getAttribute('src')).filter(s => s && s.startsWith('/demo/')));
    for (const s of imgs) { const r = await p.request.get(BASE + s); if (!r.ok()) missing.push(s); }
    if (missing.length) throw new Error('captures manquantes : ' + missing.join(', '));
    return `${anchors.length} ancres, ${imgs.length} captures`;
});
await step('API publique (config, observatoire, géoloc)', async () => {
    for (const u of ['/api/config', '/api/geo']) {
        const r = await p.request.get(BASE + u);
        if (!r.ok()) throw new Error(`${u} ${r.status()}`);
    }
    const r = await p.request.get(BASE + '/api/opportunities?bbox=3.05,50.62,3.07,50.64');
    if (r.status() !== 401) throw new Error('/api/opportunities sans session : ' + r.status() + ' (401 attendu)');
});

// Mobile: no horizontal scroll, menu opens
const mob = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: 'fr-FR' });
const m = await mob.newPage();
watch(m, () => 'mobile ' + where);
for (const route of ['/', '/demo', '/tarifs', '/observatoire', '/prospection']) {
    where = route;
    await step(`mobile ${route} sans défilement horizontal`, async () => {
        await m.goto(BASE + route, { waitUntil: 'networkidle' });
        await m.waitForTimeout(500);
        const o = await overflow(m);
        await m.screenshot({ path: path.join(OUT, 'shots', `mobile${route.replace(/\//g, '_') || '_home'}.png`) });
        if (o > 2) throw new Error(`dépasse de ${o}px`);
    });
}

// ---------- 2. Pro journeys, real data ----------
const config = await (await p.request.get(BASE + '/api/config')).json();
const email = `site-check-${Date.now()}@sprea.invalid`;
const password = 'Chk-' + Math.random().toString(36).slice(2) + '-9aZ';
let userId = null;
const admin = { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, 'Content-Type': 'application/json' };

const created = await step('compte Pro temporaire', async () => {
    if (!SB || !SERVICE || !config.auth_enabled) throw new Error('secrets Supabase absents ou comptes désactivés');
    const u = await fetch(`${SB}/auth/v1/admin/users`, { method: 'POST', headers: admin, body: JSON.stringify({ email, password, email_confirm: true }) });
    const uj = await u.json();
    if (!u.ok) throw new Error('création : ' + JSON.stringify(uj).slice(0, 200));
    userId = uj.id;
    const pr = await fetch(`${SB}/rest/v1/profiles?on_conflict=id`, {
        method: 'POST', headers: { ...admin, Prefer: 'resolution=merge-duplicates' },
        body: JSON.stringify({ id: userId, email, subscription_status: 'active' }),
    });
    if (!pr.ok) throw new Error('profil : ' + (await pr.text()).slice(0, 200));
});

if (created) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 }, locale: 'fr-FR', acceptDownloads: true });
    const page = await ctx.newPage();
    watch(page, () => 'pro ' + where);
    const download = async (trigger, name) => {
        const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 150000 }), trigger()]);
        const file = path.join(OUT, 'pdf', name);
        await dl.saveAs(file);
        const head = fs.readFileSync(file).subarray(0, 5).toString();
        if (head !== '%PDF-') throw new Error(`${name} n'est pas un PDF`);
        return `${name} ${(fs.statSync(file).size / 1024).toFixed(0)} Ko`;
    };

    await step('connexion par le formulaire', async () => {
        where = 'connexion';
        await page.goto(BASE + '/tarifs', { waitUntil: 'networkidle' });
        await page.getByRole('button', { name: /Se connecter/ }).first().click();
        await page.locator('input[placeholder="vous@exemple.fr"]').fill(email);
        await page.locator('input[type="password"]').first().fill(password);
        await page.locator('form button[type="submit"]').first().click();
        await page.getByText('PRO', { exact: true }).first().waitFor({ timeout: 20000 });
    });

    await step('fiche agence (Contacts)', async () => {
        where = '/contacts';
        await page.goto(BASE + '/contacts', { waitUntil: 'networkidle' });
        await page.locator('input[aria-label="Nom de l\'agence"]').fill('Agence Contrôle Site');
        await page.locator('input[aria-label="Votre nom"]').fill('Test Automatique');
        await page.locator('input[aria-label="Nom de l\'agence"]').press('Enter');
        await page.waitForTimeout(1500);
    });

    await step('navigation de l\'en-tête (tous les liens)', async () => {
        where = 'nav';
        await page.goto(BASE + '/', { waitUntil: 'networkidle' });
        await skipTour(page);
        const visited = [];
        for (const label of ['Prospection', "PV d'AG", 'Alertes', 'Contacts', 'Observatoire', 'Simulateur']) {
            const t0 = Date.now();
            await page.locator('header nav a', { hasText: label }).first().click();
            await page.waitForLoadState('networkidle');
            await skipTour(page);
            const h1 = (await page.locator('h1').first().textContent().catch(() => '')) || '';
            visited.push(`${label} → ${new URL(page.url()).pathname} (${Date.now() - t0} ms, « ${h1.trim().slice(0, 30)} »)`);
        }
        await page.goBack(); await page.waitForLoadState('networkidle');
        await page.goForward(); await page.waitForLoadState('networkidle');
        return visited.join(' ; ');
    });

    let dashboardOk = false;
    await step('simulateur : recherche par adresse', async () => {
        where = 'simulateur adresse';
        await page.goto(BASE + '/', { waitUntil: 'networkidle' });
        await skipTour(page);
        await page.locator('input[aria-label="Adresse du logement"]').fill('47 rue de Bourgogne 59800 Lille');
        await page.locator('input[aria-label="Adresse du logement"]').press('Enter');
        await page.waitForFunction(() => /Votre projet|Choisissez un logement|logements? trouvé|Aucun DPE/i.test(document.body.innerText), null, { timeout: 60000 });
        await page.screenshot({ path: path.join(OUT, 'shots', 'search_address.png') });
        return (await page.locator('h1, h2').first().textContent()).trim().slice(0, 80);
    });
    await step('simulateur : DPE 2659E0132455X → fiche', async () => {
        where = 'simulateur DPE';
        await page.goto(BASE + '/?dpe=2659E0132455X', { waitUntil: 'networkidle' });
        await page.getByText('Votre projet').first().waitFor({ timeout: 90000 });
        await page.waitForTimeout(4000);
        await skipTour(page);
        dashboardOk = true;
        await page.screenshot({ path: path.join(OUT, 'shots', 'dashboard.png'), fullPage: true });
        const aside = await page.locator('[data-tour="sell-summary"]').innerText();
        fs.writeFileSync(path.join(OUT, 'dashboard_summary.txt'), aside);
        return aside.replace(/\s+/g, ' ').slice(0, 300);
    });
    if (dashboardOk) {
        await step('rapport PDF', async () => download(() => page.getByRole('button', { name: 'Télécharger le rapport PDF' }).click(), 'rapport.pdf'));
        await step('avis de valeur PDF', async () => {
            await page.getByRole('button', { name: /Avis de valeur avant/ }).click();
            await page.waitForTimeout(6000);
            await page.screenshot({ path: path.join(OUT, 'shots', 'avis_dialog.png') });
            const r = await download(() => page.getByRole('dialog').getByRole('button', { name: /Télécharger|PDF/ }).last().click(), 'avis.pdf');
            await page.getByRole('dialog').getByRole('button', { name: 'Fermer' }).click();
            return r;
        });
        await step('dossier acheteur PDF (prix du mandat)', async () => {
            await page.getByRole('button', { name: 'Dossier acheteur' }).click();
            await page.locator('input[aria-label="Prix du mandat"]').fill('850000');
            const r = await download(() => page.getByRole('button', { name: /Télécharger le dossier acheteur/ }).click(), 'dossier_acheteur.pdf');
            await page.getByRole('dialog').getByRole('button', { name: 'Fermer' }).click();
            return r;
        });
        await step('cocher / décocher un travail recalcule', async () => {
            const before = await page.locator('[data-tour="sell-summary"]').innerText();
            await page.locator('[data-tour="sell-works"] button, [data-tour="sell-works"] [role="checkbox"]').filter({ hasText: /Fenêtres|Isolation des murs/ }).first().click();
            await page.waitForTimeout(3500);
            const after = await page.locator('[data-tour="sell-summary"]').innerText();
            if (before === after) throw new Error('résumé inchangé après modification des travaux');
        });
    }

    let scanned = false;
    await step('carte : logements à rénover (Lille Vauban)', async () => {
        where = '/prospection';
        await page.goto(BASE + '/prospection', { waitUntil: 'networkidle' });
        await skipTour(page);
        await page.locator('input[aria-label="Commune ou adresse"]').fill('Place Philippe Lebon, Lille');
        await page.locator('input[aria-label="Commune ou adresse"]').press('Enter');
        await page.waitForTimeout(6000);
        const n = await page.locator('.sprea-map path.leaflet-interactive').count();
        await page.screenshot({ path: path.join(OUT, 'shots', 'map_dpe.png') });
        if (!n) throw new Error('aucun logement sur la carte');
        return `${n} marqueurs`;
    });
    await step('carte : immeubles entiers', async () => {
        await page.getByRole('tab', { name: 'Immeubles entiers' }).click();
        await page.waitForTimeout(8000);
        await page.screenshot({ path: path.join(OUT, 'shots', 'map_immeubles.png') });
        return `${await page.locator('.sprea-map path.leaflet-interactive').count()} marqueurs`;
    });
    await step('carte : biens à fort potentiel (analyse réelle)', async () => {
        await page.getByRole('tab', { name: 'Biens à fort potentiel' }).click();
        await page.waitForTimeout(1500);
        const tourShown = await page.getByText('Votre secteur').isVisible().catch(() => false);
        await skipTour(page);
        await page.getByRole('button', { name: 'Analyser cette zone' }).click();
        await page.getByText(/biens? à fort potentiel/).first().waitFor({ timeout: 150000 });
        scanned = true;
        await page.waitForTimeout(1500);
        await page.screenshot({ path: path.join(OUT, 'shots', 'map_potentiel.png') });
        const head = await page.locator('[data-tour="invest-list"]').innerText();
        const rows = await page.locator('select[aria-label^="Suivi de"]').count();
        fs.writeFileSync(path.join(OUT, 'potentiel_list.txt'), await page.locator('[data-tour="invest-list"]').locator('xpath=..').innerText());
        return `${head.replace(/\s+/g, ' ')} · ${rows} lignes · visite auto ${tourShown ? 'affichée' : 'non affichée'}`;
    });
    if (scanned) {
        await step('tri et filtres', async () => {
            const notes = [];
            for (const sort of ['recent', 'valeur']) {
                await page.locator('select[aria-label="Classement"]').selectOption(sort);
                await page.getByRole('button', { name: /Analyser cette zone|Relancer l'analyse/ }).click();
                await page.waitForTimeout(6000);
                notes.push(`${sort}: ${(await page.locator('[data-tour="invest-list"]').innerText()).split('\n')[0]}`);
            }
            await page.locator('select[aria-label="Classement"]').selectOption('potentiel');
            await page.locator('select[aria-label="Ancienneté du DPE"]').selectOption('6');
            await page.getByRole('button', { name: /Analyser cette zone|Relancer l'analyse/ }).click();
            await page.waitForTimeout(6000);
            notes.push(`< 6 mois: ${(await page.locator('[data-tour="invest-list"]').innerText()).split('\n')[0]}`);
            await page.locator('select[aria-label="Ancienneté du DPE"]').selectOption('');
            await page.getByRole('button', { name: /Analyser cette zone|Relancer l'analyse/ }).click();
            await page.waitForTimeout(6000);
            return notes.join(' ; ');
        });
        await step('suivi d\'une adresse : enregistré et retrouvé après rechargement', async () => {
            const sel = page.locator('select[aria-label^="Suivi de"]').first();
            const label = await sel.getAttribute('aria-label');
            await sel.selectOption('courrier');
            await page.waitForTimeout(1500);
            await page.reload({ waitUntil: 'networkidle' });
            await skipTour(page);
            await page.getByRole('tab', { name: 'Biens à fort potentiel' }).click().catch(() => {});
            await page.getByRole('button', { name: /Analyser cette zone|Relancer l'analyse/ }).click();
            await page.getByText(/biens? à fort potentiel/).first().waitFor({ timeout: 120000 });
            await page.waitForTimeout(2500);
            const again = page.locator(`select[aria-label="${label}"]`);
            const value = await again.inputValue();
            if (value !== 'courrier') throw new Error(`suivi perdu après rechargement (valeur « ${value} »)`);
            await again.selectOption('');
            await page.waitForTimeout(1500);
            return label;
        });
        await step('dossier propriétaire PDF', async () => {
            await page.getByText('Dossier propriétaire').first().click();
            const r = await download(() => page.getByRole('button', { name: /Télécharger le dossier propriétaire/ }).click(), 'dossier_proprietaire.pdf');
            await page.getByRole('dialog').getByRole('button', { name: 'Fermer' }).click();
            return r;
        });
    }

    await step('visite guidée in-app : relance depuis le menu (Vendre)', async () => {
        where = 'visite vendre';
        await page.goto(BASE + '/', { waitUntil: 'networkidle' });
        await skipTour(page);
        await page.getByRole('button', { name: 'Visite guidée' }).click();
        await page.getByRole('button', { name: /Vendre une passoire/ }).click();
        await page.getByText('Votre bien').first().waitFor({ timeout: 8000 });
        await page.screenshot({ path: path.join(OUT, 'shots', 'tour_vendre.png') });
        await page.getByRole('button', { name: 'Passer' }).click();
    });
    await step('visite guidée in-app : relance depuis le menu (Prospecter)', async () => {
        await page.getByRole('button', { name: 'Visite guidée' }).click();
        await page.getByRole('button', { name: /Prospecter/ }).click();
        await page.getByText('Votre secteur').first().waitFor({ timeout: 10000 });
        await page.getByRole('button', { name: 'Suivant' }).click();
        await page.getByText("L'analyse").first().waitFor({ timeout: 8000 });
        await page.screenshot({ path: path.join(OUT, 'shots', 'tour_prospecter.png') });
        await page.getByRole('button', { name: 'Passer' }).click();
    });
    for (const route of ['/alertes', '/documents-copro', '/observatoire', '/contacts']) {
        await step(`page Pro ${route}`, async () => {
            where = route;
            const t0 = Date.now();
            await page.goto(BASE + route, { waitUntil: 'networkidle' });
            await skipTour(page);
            await page.screenshot({ path: path.join(OUT, 'shots', `pro${route.replace(/\//g, '_')}.png`) });
            return `${Date.now() - t0} ms · ${(await page.locator('h1').first().textContent()).trim()}`;
        });
    }
    await step('fenêtre Mon compte', async () => {
        await page.getByRole('button', { name: /Mon compte/ }).click();
        await page.getByRole('dialog').first().waitFor({ timeout: 8000 });
        await page.screenshot({ path: path.join(OUT, 'shots', 'account.png') });
        await page.keyboard.press('Escape');
    });
    // Mobile, logged in
    await page.setViewportSize({ width: 390, height: 844 });
    for (const route of ['/', '/prospection?mode=potentiel', '/alertes', '/contacts']) {
        await step(`mobile Pro ${route} sans défilement horizontal`, async () => {
            where = 'mobile ' + route;
            await page.goto(BASE + route, { waitUntil: 'networkidle' });
            await page.waitForTimeout(1200);
            await page.screenshot({ path: path.join(OUT, 'shots', `mobile_pro${route.replace(/[/?=]/g, '_')}.png`) });
            await skipTour(page);
            const o = await overflow(page);
            if (o > 2) throw new Error(`dépasse de ${o}px`);
        });
    }
}

// ---------- 3. Cleanup ----------
if (userId) {
    await step('suppression du compte temporaire', async () => {
        const r = await fetch(`${SB}/auth/v1/admin/users/${userId}`, { method: 'DELETE', headers: admin });
        if (!r.ok) throw new Error('suppression ' + r.status);
    });
}
await browser.close();
results.finished = new Date().toISOString();
results.summary = { steps: results.steps.length, failed: results.steps.filter(s => !s.ok).map(s => s.name), console: results.console.length, httpErrors: results.failed.length };
save();
console.log(JSON.stringify(results.summary, null, 1));
