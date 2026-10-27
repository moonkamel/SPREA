// Prerenders the public pages after `vite build`: one HTML file per page with
// its own title, description, canonical URL, social preview, structured data
// (JSON-LD) and a readable version of its content inside #root, replaced by
// the React app once loaded. Crawlers and link previews that do not run
// JavaScript get the real page; also writes sitemap.xml and robots.txt.
//
// The observatory pages (one per department) come from
// src/data/observatoire.json, exported monthly with the green value.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DIST = join(ROOT, 'dist');
const SITE = (process.env.PUBLIC_SITE_URL || 'https://sprea.app').replace(/\/$/, '');
const OG_IMAGE = `${SITE}/og.jpg`;

const template = readFileSync(join(DIST, 'index.html'), 'utf8');
// Shell of the other routes (tools, owner pages): no indexing, no static content
writeFileSync(join(DIST, 'app.html'), template.replace(/<!--seo-->[\s\S]*<!--\/seo-->/,
    '<title>SPREA</title>\n    <meta name="robots" content="noindex" />'));
const obs = JSON.parse(readFileSync(join(ROOT, 'src', 'data', 'observatoire.json'), 'utf8'));
const faq = JSON.parse(readFileSync(join(ROOT, 'src', 'data', 'estimation_faq.json'), 'utf8'));

// --- Helpers ---

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const int = n => n.toLocaleString('fr-FR').replace(/\u202f/g, ' ');
const pct = v => (v == null ? '–' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`);
const abs = v => pct(v).replace(/^[+−]/, '');
// Same rule as departmentSlug in src/seo.ts
const slug = (name, code) => `${name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}-${code.toLowerCase()}`;
const LABELS = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
const period = p => (p && /^\d{4}T\d-\d{4}T\d$/.test(p) ? `${p.slice(0, 4)} à ${p.slice(7, 11)}` : p);

const ORG = {
    '@type': 'Organization', '@id': `${SITE}/#org`, name: 'SPREA', url: SITE, logo: `${SITE}/favicon.svg`,
};
const SOFTWARE = {
    '@context': 'https://schema.org', '@type': 'SoftwareApplication', name: 'SPREA', applicationCategory: 'BusinessApplication',
    operatingSystem: 'Web', url: SITE, publisher: ORG,
    description: "Logiciel pour agents immobiliers : prospection des passoires thermiques, alertes nouveaux DPE, courriers avec QR code, simulateur de rénovation et avis de valeur avant / après travaux.",
    offers: [
        { '@type': 'Offer', name: 'Solo', price: '79', priceCurrency: 'EUR', category: 'subscription', description: 'Par mois, TTC' },
        { '@type': 'Offer', name: 'Agence', price: '59', priceCurrency: 'EUR', category: 'subscription', description: 'Par agent et par mois, TTC' },
    ],
};
const DATASET = (name, description, path, sales) => ({
    '@context': 'https://schema.org', '@type': 'Dataset', name, description, url: `${SITE}${path}`,
    creator: ORG, license: 'https://www.etalab.gouv.fr/licence-ouverte-open-licence/',
    isBasedOn: ['https://www.data.gouv.fr/fr/datasets/demandes-de-valeurs-foncieres-geolocalisees/', 'https://data.ademe.fr/datasets/dpe03existant'],
    temporalCoverage: obs.period ? `${obs.period.slice(0, 4)}/${obs.period.slice(7, 11)}` : undefined,
    spatialCoverage: 'France', dateModified: obs.updated, variableMeasured: 'Écart de prix au m² selon la classe DPE',
    measurementTechnique: `Régression hédonique sur ${int(sales)} ventes DVF rapprochées de leur DPE`,
});
const BREADCRUMB = items => ({
    '@context': 'https://schema.org', '@type': 'BreadcrumbList',
    itemListElement: items.map(([name, path], i) => ({ '@type': 'ListItem', position: i + 1, name, item: `${SITE}${path}` })),
});

const page = ({ path, title, description, body = '', jsonld = [], noindex = false }) => {
    const url = `${SITE}${path}`;
    const head = [
        `<title>${esc(title)}</title>`,
        description && `<meta name="description" content="${esc(description)}" />`,
        `<link rel="canonical" href="${esc(url)}" />`,
        `<meta name="robots" content="${noindex ? 'noindex, nofollow' : 'index, follow'}" />`,
        '<meta property="og:site_name" content="SPREA" />',
        '<meta property="og:type" content="website" />',
        '<meta property="og:locale" content="fr_FR" />',
        `<meta property="og:title" content="${esc(title)}" />`,
        description && `<meta property="og:description" content="${esc(description)}" />`,
        `<meta property="og:url" content="${esc(url)}" />`,
        `<meta property="og:image" content="${OG_IMAGE}" />`,
        '<meta property="og:image:width" content="1200" />',
        '<meta property="og:image:height" content="630" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        ...jsonld.map(j => `<script type="application/ld+json">${JSON.stringify(j).replace(/</g, '\\u003c')}</script>`),
    ].filter(Boolean).join('\n    ');
    let html = template.replace(/<!--seo-->[\s\S]*<!--\/seo-->/, head);
    if (body) {
        html = html.replace('<div id="root"></div>',
            `<div id="root"><div style="max-width:60rem;margin:0 auto;padding:3rem 1.25rem;color:#E8E6E1;font-family:system-ui,sans-serif;line-height:1.6">${body}</div></div>`);
    }
    const file = path === '/' ? join(DIST, 'index.html') : join(DIST, path.slice(1), 'index.html');
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, html);
    return path;
};

const nav = `<nav><a href="/">SPREA</a> · <a href="/demo">Visite guidée</a> · <a href="/tarifs">Tarifs</a> · <a href="/estimation">Estimation immobilière gratuite</a> · <a href="/observatoire">Observatoire de la valeur verte</a></nav>`;
const ul = items => `<ul>${items.map(i => `<li>${i}</li>`).join('')}</ul>`;

// --- Pages ---

const pages = [];

pages.push(page({
    path: '/',
    title: "SPREA · Le mandat avant les autres : l'outil DPE des conseillers immobiliers indépendants",
    description: "Conseiller indépendant ou mandataire : recevez chaque matin les nouveaux DPE de votre secteur, envoyez un courrier en un clic et signez avec un avis de valeur avant / après travaux fondé sur les ventes DVF.",
    jsonld: [SOFTWARE],
    body: `${nav}
<p>Pour les conseillers immobiliers indépendants</p>
<h1>Le prochain mandat de votre secteur, repérez-le avant les autres.</h1>
<p>Pas de vitrine, pas de fichier d'agence, pas de standard qui sonne : votre prospection, c'est vous. SPREA vous signale chaque matin les logements qui viennent de recevoir un DPE, prépare votre courrier et vous arme de chiffres pour le rendez-vous.</p>
<h2>Une journée avec SPREA</h2>
${ul([
        '<strong>7 h 30 · Les DPE de la veille</strong> : dans vos communes, les logements qui viennent de recevoir un DPE. Un DPE précède souvent une vente ou une mise en location.',
        '<strong>8 h 15 · Votre secteur, passoire par passoire</strong> : toutes les adresses classées E, F ou G sur une carte, triées par potentiel.',
        '<strong>9 h 00 · Un courrier à votre nom</strong> : prêt à imprimer, avec un QR code vers la rénovation du logement.',
        "<strong>14 h 00 · L'avis de valeur qui fait signer</strong> : travaux, aides, reste à charge et valeur avant / après rénovation, appuyée sur les ventes DVF du quartier.",
        '<strong>17 h 30 · Le bien F qui ne partait pas</strong> : un dossier acheteur à vos couleurs en deux minutes.',
    ])}
<h2>Pensé pour les indépendants</h2>
${ul([
        '<strong>Pas de vitrine ?</strong> Chaque nouveau DPE est une porte à laquelle frapper.',
        "<strong>Seul face aux agences du coin</strong> : DPE de l'ADEME, ventes DVF de la DGFiP, barèmes d'aides en vigueur.",
        '<strong>Votre temps, c\'est votre chiffre</strong> : du DPE au courrier en un clic, du rendez-vous au dossier chiffré en deux minutes.',
        "<strong>Un outil à votre taille</strong> : 79 € TTC par mois en Solo. Un seul mandat signé rembourse des années d'abonnement.",
    ])}
<p>${int(obs.total_sales)} ventes rapprochées de leur DPE pour mesurer la valeur verte.</p>
<p><a href="/demo">Faire la visite guidée</a> · <a href="/tarifs">Voir les tarifs</a></p>`,
}));

// Public estimator: the long tail of "estimation (maison|immobilière) gratuite / en ligne / sans inscription"
pages.push(page({
    path: '/estimation',
    title: 'Estimation immobilière gratuite en ligne, immédiate et sans inscription | SPREA',
    description: "Estimez gratuitement votre maison ou votre appartement en 30 secondes : prix calculé sur les ventes réelles autour de chez vous (DVF), ajusté de l'étiquette énergie. Sans inscription.",
    jsonld: [
        {
            '@context': 'https://schema.org', '@type': 'WebApplication', name: 'Estimation immobilière gratuite SPREA',
            url: `${SITE}/estimation`, applicationCategory: 'FinanceApplication', operatingSystem: 'Web', publisher: ORG,
            offers: { '@type': 'Offer', price: '0', priceCurrency: 'EUR' },
            description: "Estimation en ligne d'une maison ou d'un appartement à partir des ventes DVF comparables et de l'étiquette énergie.",
        },
        { '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: faq.map(f => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })) },
        BREADCRUMB([['SPREA', '/'], ['Estimation immobilière', '/estimation']]),
    ],
    body: `${nav}
<h1>Estimation immobilière gratuite : combien vaut votre bien ?</h1>
<p>Estimez votre maison ou votre appartement en ligne, immédiatement et sans inscription. Le prix est calculé sur les ventes réelles enregistrées autour de votre adresse (DVF, DGFiP), pour des biens de même type et de surface comparable, puis ajusté de l'étiquette énergie, de l'état, de l'étage et des atouts du bien.</p>
<h2>Comment fonctionne l'estimation</h2>
${ul([
        "<strong>Les ventes réelles</strong> : les prix de vente enregistrés chez les notaires (DVF) autour de votre adresse, actualisés au dernier trimestre connu.",
        `<strong>L'étiquette énergie</strong> : l'écart de prix entre classes DPE, mesuré sur ${int(obs.total_sales)} ventes rapprochées de leur DPE.`,
        "<strong>Vos atouts</strong> : état, étage, balcon, terrasse, parking, chacun affiché avec son poids.",
    ])}
<h2>Questions fréquentes</h2>
${faq.map(f => `<h3>${esc(f.q)}</h3><p>${esc(f.a)}</p>`).join('\n')}
<p><a href="/estimation">Estimer mon bien gratuitement</a></p>`,
}));

pages.push(page({
    path: '/demo',
    title: "Visite guidée de SPREA : prospection DPE, signaux de vente des SCI, PV d'AG lus par l'IA",
    description: "Prospection des passoires thermiques, immeubles entiers détenus par des SCI et signaux de vente au BODACC, biens à fort potentiel et dossier acheteur, PV d'AG lus par l'IA, alertes nouveaux DPE, courriers avec QR code, simulateur de rénovation, avis de valeur : la journée d'un agent avec SPREA, écran par écran.",
    jsonld: [SOFTWARE, BREADCRUMB([['SPREA', '/'], ['Visite guidée', '/demo']])],
    body: `${nav}
<h1>Une journée avec SPREA</h1>
<p>De la publication d'un DPE au rendez-vous chez le propriétaire : comment SPREA fait gagner des mandats aux agents immobiliers.</p>
<h2>8 h 00 · Les DPE publiés la veille dans vos secteurs</h2>
<p>Un DPE est obligatoire avant de vendre ou de louer : quand un propriétaire en fait réaliser un, il prépare presque toujours un projet. Jusqu'à 10 zones, filtres par étiquette, récapitulatif par email chaque matin.</p>
<h2>8 h 15 · Toutes les passoires de votre secteur sur une carte</h2>
<p>Les adresses classées E, F ou G, logement par logement, avec export CSV pour votre CRM.</p>
<h2>8 h 20 · Les biens à fort potentiel et leur suivi</h2>
<p>Les DPE récents du secteur classés par potentiel de revalorisation, fraîcheur du DPE et valeur ; le suivi de chaque adresse partagé dans l'agence ; un dossier propriétaire pour le premier rendez-vous.</p>
<h2>8 h 30 · Un courrier qui donne envie de vous rappeler</h2>
<p>Un courrier prêt à imprimer et un QR code unique : le propriétaire découvre ce qu'une rénovation changerait pour son logement, au nom de votre agence, et vous laisse ses coordonnées.</p>
<h2>Les propriétaires intéressés arrivent chez vous</h2>
<p>Nom, téléphone, email et message, avec l'adresse et le DPE du logement, et le consentement horodaté.</p>
<h2>11 h · Les immeubles entiers détenus par une SCI</h2>
<p>Tous les immeubles de 3 logements ou plus détenus en entier par une SCI ou une société privée, hors copropriétés et bailleurs sociaux, avec leur DPE, leur dernière vente, le siège et les gérants de la société propriétaire.</p>
<h2>11 h 15 · Le dossier de cession</h2>
<p>Logements interdits à la location, gel des loyers, travaux à prévoir, valeur lot par lot et en bloc, audit obligatoire à la vente : un dossier PDF à vos couleurs pour convaincre le propriétaire de vendre.</p>
<h2>14 h · Le simulateur : travaux, aides, reste à charge</h2>
<p>Travaux recommandés selon le DPE, nouvelle étiquette, MaPrimeRénov', CEE et éco-PTZ selon les barèmes en vigueur, deux scénarios à comparer.</p>
<h2>14 h 10 · La fiche immeuble des copropriétés</h2>
<p>Registre national des copropriétés, DPE collectif, plan pluriannuel de travaux : les gros travaux à venir et la quote-part de l'appartement, avant et après aides.</p>
<h2>14 h 20 · Les artisans RGE les plus proches</h2>
<p>Pour chaque travail retenu, les entreprises qualifiées RGE les plus proches d'après l'annuaire de l'ADEME, reprises dans le rapport.</p>
<h2>15 h · Le dossier acheteur d'une passoire sous mandat</h2>
<p>Depuis le simulateur, le projet chiffré à remettre aux acquéreurs : programme de travaux, aides, valeur après rénovation étayée par les ventes DVF comparables, loyer et rendement, à partir du prix du mandat.</p>
<h2>L'avis de valeur avant / après travaux</h2>
<p>Ventes DVF comparables autour du bien, écart de prix par classe DPE mesuré sur ${int(obs.total_sales)} ventes, ajustement du conseiller, PDF à votre nom.</p>
<h2>Un rapport complet pour le client</h2>
<p>Synthèse, analyse rédigée, plan de travaux et de financement, valeur verte et calendrier de la loi Climat, fiche immeuble et artisans RGE.</p>
<h2>Toute l'agence sur le même outil</h2>
<p>Une place par agent, invitations par lien, contacts et alertes partagés dans l'agence, console réseau.</p>
<p><a href="/tarifs">Démarrer à 79 € TTC / mois</a></p>`,
}));

const FAQ = [
    ["Puis-je voir SPREA avant de m'abonner ?", "Oui : la visite guidée présente chaque outil en images (simulateur, carte de prospection, alertes, avis de valeur, immeubles de SCI et signaux de vente, biens à fort potentiel, dossier acheteur, PV d'AG lus par l'IA). Pour une présentation en direct, écrivez-nous."],
    ["Y a-t-il un engagement ?", "Oui, 12 mois pour toutes les formules. En paiement mensuel, l'abonnement est payé chaque mois pendant au moins 12 mois ; en annuel, les 12 mois sont payés d'avance. À l'issue de l'engagement, l'abonnement est résiliable à tout moment depuis « Mon compte »."],
    ['Les prix sont-ils TTC ?', "Oui, tous les prix affichés incluent la TVA à 20 %. La facture détaille le montant hors taxes et la TVA, avec votre raison sociale et votre numéro de TVA."],
    ['Comment équiper toute mon agence ?', "Avec la formule Agence, vous payez par agent (2 agents minimum) et invitez vos agents par email depuis la page Équipe. Vous ajoutez des agents à tout moment, au prorata ; le nombre d'agents peut être réduit à la fin de l'engagement."],
    ["D'où viennent les données ?", "Des bases publiques officielles : DPE de l'ADEME, ventes immobilières DVF de la DGFiP, Base Adresse Nationale."],
];
pages.push(page({
    path: '/tarifs',
    title: 'Tarifs SPREA : dès 79 € TTC par mois pour les agents immobiliers',
    description: "Solo 79 € TTC / mois, Agence 59 € TTC par agent, Réseau sur devis. Tous les outils inclus : prospection DPE, immeubles de rapport, alertes, avis de valeur, rapports.",
    jsonld: [SOFTWARE, {
        '@context': 'https://schema.org', '@type': 'FAQPage',
        mainEntity: FAQ.map(([q, a]) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })),
    }],
    body: `${nav}
<h1>Tarifs SPREA</h1>
${ul([
        '<strong>Solo</strong> : 79 € TTC par mois ou 790 € TTC par an, pour un agent ou un mandataire indépendant.',
        "<strong>Agence</strong> : 59 € TTC par agent et par mois, à partir de 2 agents, contacts et alertes partagés dans l'agence.",
        '<strong>Réseau</strong> : sur devis, à partir de 39 € TTC par agent et par mois, console du siège.',
    ])}
<p>Tous les outils inclus dans chaque formule. Engagement de 12 mois, paiement mensuel ou annuel.</p>
<h2>Questions fréquentes</h2>
${FAQ.map(([q, a]) => `<h3>${esc(q)}</h3><p>${esc(a)}</p>`).join('')}`,
}));

// Observatory
const nat = obs.national;
const deps = obs.departments;
const totalSales = d => (d.maisons?.sales || 0) + (d.appartements?.sales || 0);
const table = series => `<table><thead><tr><th>Classe DPE</th>${series.map(([n]) => `<th>${n}</th>`).join('')}</tr></thead><tbody>${
    LABELS.map(c => `<tr><td>${c}</td>${series.map(([, s]) => `<td>${s ? pct(s.premium[c]) : '–'}</td>`).join('')}</tr>`).join('')}</tbody></table>`;

pages.push(page({
    path: '/observatoire',
    title: 'Observatoire de la valeur verte : prix des logements selon le DPE · SPREA',
    description: "Combien vaut un logement selon son DPE ? Écarts de prix entre classes énergétiques mesurés sur plus d'un million de ventes réelles, en France et par département.",
    jsonld: [DATASET('Observatoire de la valeur verte', 'Écarts de prix des logements entre classes DPE, en France et par département, mesurés sur les ventes DVF rapprochées de leur DPE.', '/observatoire', obs.total_sales),
        BREADCRUMB([['SPREA', '/'], ['Observatoire de la valeur verte', '/observatoire']])],
    body: `${nav}
<h1>Combien le DPE pèse-t-il sur le prix d'un logement ?</h1>
<p>Écarts de prix entre classes énergétiques, mesurés sur ${int(obs.total_sales)} ventes réelles rapprochées une à une du DPE du logement vendu (${period(obs.period)}). En France, une maison classée G se vend ${abs(nat.maisons?.premium.G)} moins cher qu'une maison classée D comparable, un appartement classé G ${abs(nat.appartements?.premium.G)} moins cher.</p>
${table([['Maisons', nat.maisons], ['Appartements', nat.appartements]])}
<h2>Par département</h2>
${ul(deps.map(d => `<a href="/observatoire/${slug(d.name, d.code)}">Valeur verte ${esc(d.name)} (${d.code})</a> : maison G ${pct(d.maisons?.premium.G)}, appartement G ${pct(d.appartements?.premium.G)}`))}`,
}));

for (const [i, d] of deps.entries()) {
    const path = `/observatoire/${slug(d.name, d.code)}`;
    const where = d.name === 'Paris' ? 'à Paris' : `dans le département ${d.name} (${d.code})`;
    const parts = [];
    if (d.maisons) {
        const gap = d.maisons.premium.G - (nat.maisons?.premium.G ?? d.maisons.premium.G);
        parts.push(`Dans le département ${d.name === 'Paris' ? 'de Paris' : `${d.name} (${d.code})`}, une maison classée G se vend ${abs(d.maisons.premium.G)} moins cher qu'une maison classée D comparable`
            + (Math.abs(gap) >= 1 ? `, soit ${Math.abs(gap).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} points ${gap < 0 ? 'de plus' : 'de moins'} qu'en moyenne en France.` : ', comme en moyenne en France.'));
    }
    if (d.appartements) parts.push(`Pour un appartement, l'écart entre G et D atteint ${abs(d.appartements.premium.G)}.`);
    const summary = parts.join(' ');
    const poor = d.maisons ? Math.round((d.maisons.mix.F || 0) + (d.maisons.mix.G || 0)) : null;
    const prev = deps[i - 1], next = deps[i + 1];
    pages.push(page({
        path,
        title: `Valeur verte ${d.name} (${d.code}) : prix selon le DPE · SPREA`,
        description: `${summary} Calculé sur ${int(totalSales(d))} ventes réelles rapprochées de leur DPE.`,
        jsonld: [DATASET(`Valeur verte ${d.name} (${d.code})`, `Écarts de prix des logements entre classes DPE ${where}.`, path, totalSales(d)),
            BREADCRUMB([['SPREA', '/'], ['Observatoire de la valeur verte', '/observatoire'], [d.name, path]])],
        body: `${nav}
<p><a href="/observatoire">Observatoire de la valeur verte</a> › ${esc(d.name)}</p>
<h1>Valeur verte ${esc(where)}</h1>
<p>${esc(summary)}</p>
<p>Écart de prix par rapport à un logement classé D, à emplacement, surface, époque de construction et date de vente comparables, mesuré sur ${int(totalSales(d))} ventes (${period(obs.period)}).</p>
${table([['Maisons', d.maisons], ['Appartements', d.appartements]])}
${poor != null ? `<p>${poor} % des maisons vendues ${esc(where)} étaient classées F ou G.</p>` : ''}
<h2>Vous êtes agent immobilier ${esc(where)} ?</h2>
<p>Avec SPREA, repérez les passoires thermiques de votre secteur, recevez les nouveaux DPE chaque matin et remettez à vos vendeurs un avis de valeur avant / après travaux. <a href="/demo">Faire la visite guidée</a>.</p>
<p>${prev ? `<a href="/observatoire/${slug(prev.name, prev.code)}">← ${esc(prev.name)}</a>` : ''} ${next ? `<a href="/observatoire/${slug(next.name, next.code)}">${esc(next.name)} →</a>` : ''}</p>`,
    }));
}

// Legal pages: metadata only, the app renders the content
pages.push(page({ path: '/cgv', title: 'Conditions générales de vente · SPREA' }));
pages.push(page({ path: '/mentions-legales', title: 'Mentions légales · SPREA' }));
pages.push(page({ path: '/confidentialite', title: 'Politique de confidentialité · SPREA' }));

// --- Sitemap and robots ---

const priority = p => (p === '/' ? '1.0' : ['/demo', '/tarifs', '/observatoire'].includes(p) ? '0.9' : p.startsWith('/observatoire/') ? '0.7' : '0.3');
writeFileSync(join(DIST, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${pages.map(p => `  <url><loc>${SITE}${p}</loc><lastmod>${obs.updated}</lastmod><priority>${priority(p)}</priority></url>`).join('\n')}
</urlset>
`);
writeFileSync(join(DIST, 'robots.txt'), `User-agent: *
Allow: /
Disallow: /api/
Disallow: /l/
Disallow: /rejoindre
Disallow: /equipe
Disallow: /contacts
Disallow: /alertes
Disallow: /prospection

Sitemap: ${SITE}/sitemap.xml
`);
console.log(`Prerendered ${pages.length} pages, sitemap and robots.txt`);
