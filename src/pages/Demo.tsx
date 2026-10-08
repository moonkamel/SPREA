import { useEffect, type ReactNode } from 'react';
import { ArrowRight, Check, ShieldCheck } from 'lucide-react';
import { Button } from '../ui';
import { useAccount } from '../account';
import { navigate } from '../router';
import { SiteFooter, SiteHeader } from './site';
import { Screen } from './Screen';
import { useSeo } from '../seo';

// Product walkthrough for professionals: a morning with SPREA, from the new
// DPE of the day to the valuation handed to the owner.

function Step({ id, kicker, title, children, points, media, reverse = false }: {
    id?: string;
    kicker: string;
    title: string;
    children: ReactNode;
    points: string[];
    media: ReactNode;
    reverse?: boolean;
}) {
    return (
        <section id={id} className="scroll-mt-24 max-w-7xl mx-auto px-4 sm:px-6 py-14 sm:py-20 grid gap-10 lg:grid-cols-12 items-center">
            <div className={`lg:col-span-5 ${reverse ? 'lg:order-2' : ''}`}>
                <p className="text-sm text-brass tracking-wide">{kicker}</p>
                <h2 className="mt-3 text-3xl sm:text-4xl text-ink leading-tight">{title}</h2>
                <div className="mt-5 text-muted leading-relaxed space-y-3">{children}</div>
                <ul className="mt-6 space-y-2.5">
                    {points.map(p => (
                        <li key={p} className="flex items-start gap-2.5 text-sm text-ink-soft">
                            <Check size={16} className="shrink-0 mt-0.5 text-brass" /><span>{p}</span>
                        </li>
                    ))}
                </ul>
            </div>
            <div className={`lg:col-span-7 ${reverse ? 'lg:order-1' : ''}`}>{media}</div>
        </section>
    );
}

export default function DemoPage() {
    const { me, startSubscription } = useAccount();

    useSeo({
        title: "Démo SPREA : prospection DPE, alertes, avis de valeur avant / après travaux",
        description: "Prospection des passoires thermiques, alertes nouveaux DPE, courriers avec QR code, simulateur de rénovation et avis de valeur avant / après travaux : découvrez SPREA en images.",
        path: '/demo',
    });
    useEffect(() => {
        // Anchor from the home page (/demo#convaincre)
        const target = window.location.hash.slice(1);
        if (target) setTimeout(() => document.getElementById(target)?.scrollIntoView({ behavior: 'smooth' }), 150);
    }, []);

    const start = () => (me?.is_pro ? navigate('/') : navigate('/tarifs'));

    return (
        <div className="min-h-screen flex flex-col">
            <SiteHeader />
            <main className="flex-1">
                <section className="relative overflow-hidden border-b border-line/60">
                    <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(201,164,92,0.12),transparent_60%)] pointer-events-none" />
                    <div className="relative max-w-3xl mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-14 text-center">
                        <p className="text-sm text-brass tracking-wide mb-5">Démo</p>
                        <h1 className="text-4xl sm:text-5xl leading-[1.1] text-ink">Une matinée avec SPREA</h1>
                        <p className="mt-6 text-lg text-muted">
                            De la publication d'un DPE au rendez-vous chez le propriétaire : voici comment SPREA vous fait gagner des mandats, écran par écran.
                        </p>
                        <ol className="mt-10 grid grid-cols-2 sm:grid-cols-4 gap-3 text-left">
                            {[['8 h', 'Les nouveaux DPE', 'alertes'], ['8 h 15', 'La carte du secteur', 'prospecter'], ['8 h 30', 'Le courrier', 'contacter'], ['14 h', 'Le rendez-vous', 'convaincre']].map(([h, t, a]) => (
                                <li key={a}>
                                    <a href={`#${a}`} className="block rounded-xl border border-line bg-panel px-4 py-3 hover:border-brass/50 transition-colors">
                                        <span className="block font-serif text-xl text-brass">{h}</span>
                                        <span className="block text-sm text-ink-soft mt-1">{t}</span>
                                    </a>
                                </li>
                            ))}
                        </ol>
                    </div>
                </section>

                <Step id="alertes" kicker="8 h 00 · Alertes" title="Les DPE publiés la veille dans vos secteurs"
                    points={['Jusqu\'à 10 zones, de 200 m à 3 km de rayon', 'Filtres par étiquette (E, F, G) et type de bien', 'Récapitulatif par email chaque matin']}
                    media={<Screen src="/demo/alerts.webp" alt="Page Alertes : trois zones suivies et les nouveaux DPE du jour, avec leur étiquette" width={1600} height={1000} />}>
                    <p>Un DPE est obligatoire avant de vendre ou de louer. Quand un propriétaire en fait réaliser un, il prépare presque toujours un projet : vous le savez le lendemain, avant que le bien n'arrive sur les portails.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step id="prospecter" kicker="8 h 15 · Prospection" title="Toutes les passoires de votre secteur sur une carte" reverse
                    points={['Toutes les adresses classées E, F ou G, logement par logement', 'Filtres par type de bien et ancienneté du DPE', 'Export CSV pour votre CRM']}
                    media={<Screen src="/demo/map.webp" alt="Carte de prospection : 105 logements classés F ou G dans le centre de Lille" width={1560} height={628} />}>
                    <p>Les propriétaires de logements classés F et G doivent rénover ou vendre : la location leur est progressivement interdite et leur bien perd de la valeur. Ce sont vos futurs vendeurs.</p>
                    <p className="text-xs text-faint">Capture réelle (Lille, DPE publics de l'ADEME), adresses masquées.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step id="contacter" kicker="8 h 30 · Courrier" title="Un courrier qui donne envie de vous rappeler"
                    points={['Courrier prêt à imprimer, personnalisable', 'QR code unique par logement', 'Page propriétaire à vos couleurs, avec ses chiffres', 'Demandes de rappel avec consentement, dans « Contacts »']}
                    media={
                        <div className="grid gap-4 sm:grid-cols-2">
                            <Screen src="/demo/letter.webp" alt="Courrier pré-rédigé avec QR code pour un appartement classé G" width={1400} height={1120} />
                            <Screen src="/demo/owner.webp" alt="Page vue par le propriétaire après avoir scanné le QR code" width={1600} height={1000} />
                        </div>
                    }>
                    <p>En deux clics, un courrier sobre et conforme : le propriétaire scanne le QR code et découvre ce qu'une rénovation changerait pour son logement, au nom de votre agence. S'il le souhaite, il vous laisse ses coordonnées.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step kicker="Le lendemain · Contacts" title="Les propriétaires intéressés arrivent chez vous" reverse
                    points={['Nom, téléphone, email et message', 'Statut « à rappeler » ou « contacté »', 'Consentement horodaté (RGPD)']}
                    media={<Screen src="/demo/contacts.webp" alt="Page Contacts : trois demandes de rappel de propriétaires" width={1600} height={1000} />}>
                    <p>Chaque demande arrive avec l'adresse du logement et le DPE concerné : vous rappelez un propriétaire qui sait déjà ce que vaut son bien et ce que coûteraient les travaux.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step id="convaincre" kicker="14 h · Rendez-vous" title="Le simulateur : travaux, aides, reste à charge, en direct"
                    points={['Travaux recommandés selon le DPE du logement', 'Nouvelle étiquette, consommation et émissions', 'MaPrimeRénov\', CEE et éco-PTZ selon les barèmes en vigueur', 'Deux scénarios à comparer']}
                    media={<Screen src="/demo/works.webp" alt="Simulateur : choix des travaux et projet de passage de F à C" width={1600} height={1000} />}>
                    <p>Tapez l'adresse : SPREA retrouve le DPE officiel et propose les travaux qui font vraiment gagner des classes. Cochez, décochez : tout se recalcule devant le propriétaire.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step kicker="L'argument décisif" title="L'avis de valeur avant / après travaux" reverse
                    points={['Ventes DVF comparables à moins de 500 m, 1 km, 2 km', 'Écart de prix par classe DPE mesuré sur 1,27 million de ventes', 'Ajustement du conseiller (état, étage, extérieur…)', 'PDF à votre nom, à remettre au client']}
                    media={
                        <div className="grid gap-4 sm:grid-cols-5 items-start">
                            <div className="sm:col-span-3"><Screen src="/demo/valuation.webp" alt="Avis de valeur : 235 000 € aujourd'hui en F, 309 000 € après travaux en C" width={1400} height={1090} /></div>
                            <div className="sm:col-span-2"><Screen src="/demo/avis_1.webp" alt="Avis de valeur en PDF aux couleurs de l'agence" width={900} height={1273} chrome={false} /></div>
                        </div>
                    }>
                    <p>Combien vaut le bien aujourd'hui, combien il vaudrait après travaux, et ce que les travaux rapportent une fois les aides déduites. De quoi fixer un prix juste et le défendre face aux acheteurs.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step kicker="À laisser au client" title="Un rapport complet, rédigé pour lui"
                    points={['Synthèse, analyse rédigée, plan de travaux et de financement', 'Valeur verte et calendrier de la loi Climat', 'Inclus sans limite dans l\'abonnement']}
                    media={
                        <div className="grid grid-cols-2 gap-4">
                            <Screen src="/demo/rapport_1.webp" alt="Rapport PDF, page 1 : synthèse et analyse" width={900} height={1273} chrome={false} />
                            <Screen src="/demo/rapport_2.webp" alt="Rapport PDF, page 2" width={900} height={1273} chrome={false} />
                        </div>
                    }>
                    <p>Un document de 5 pages, clair et sourcé, qui reste chez le propriétaire et qui porte votre travail : chaque chiffre est expliqué et sourcé.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step kicker="Pour votre communication" title="L'observatoire de la valeur verte" reverse
                    points={['Mis à jour chaque mois', 'France entière et 90 départements', 'Des chiffres à citer en rendez-vous et sur vos réseaux']}
                    media={<Screen src="/demo/observatoire.webp" alt="Observatoire : écart de prix par classe DPE, maisons et appartements" width={1600} height={1000} />}>
                    <p>Une maison classée G se vend 18 % moins cher qu'une maison classée D, à emplacement et surface comparables. Montrez-le à vos vendeurs.</p>
                </Step>

                <section className="border-t border-line/60 bg-panel/40">
                    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-16 sm:py-20 text-center">
                        <h2 className="text-3xl sm:text-4xl text-ink">Le calcul est vite fait</h2>
                        <p className="mt-5 text-lg text-muted">
                            Sur une vente à 250 000 €, des honoraires de 5 % TTC représentent plus de 10 000 € HT. L'abonnement Solo annuel coûte 790 € HT :
                            un seul mandat signé grâce à SPREA le rembourse plus de dix fois.
                        </p>
                        <div className="mt-9 flex flex-col sm:flex-row gap-3 justify-center">
                            {me?.is_pro
                                ? <Button onClick={start} className="sm:w-60">Ouvrir le simulateur <ArrowRight size={18} /></Button>
                                : <Button onClick={() => startSubscription('solo_monthly')} className="sm:w-60">Démarrer à 79 € HT / mois</Button>}
                            <Button variant="secondary" onClick={() => navigate('/tarifs')} className="sm:w-60">Formules Agence et Réseau</Button>
                        </div>
                        <p className="mt-5 text-sm text-muted flex items-center justify-center gap-2">
                            <ShieldCheck size={16} className="text-sage" /> Satisfait ou remboursé pendant 14 jours · sans engagement
                        </p>
                        <p className="mt-8 text-xs text-faint">Captures réalisées avec des données d'exemple, sauf la carte (DPE publics, adresses masquées).</p>
                    </div>
                </section>
            </main>
            <SiteFooter />
        </div>
    );
}
