import { useEffect, type ReactNode } from 'react';
import { ArrowRight, Check, ShieldCheck } from 'lucide-react';
import { Button } from '../ui';
import { useAccount } from '../account';
import { navigate } from '../router';
import { SiteFooter, SiteHeader } from './site';
import { Screen } from './Screen';
import { useSeo } from '../seo';

// Product walkthrough for professionals ("Visite guidée"): a day with SPREA, from the new
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
        title: "Visite guidée de SPREA : prospection DPE, signaux de vente des SCI, PV d'AG lus par l'IA",
        description: "Prospection des passoires thermiques, immeubles entiers détenus par des SCI et signaux de vente au BODACC, PV d'AG lus par l'IA, alertes nouveaux DPE, courriers avec QR code, simulateur de rénovation, avis de valeur : la journée d'un agent avec SPREA, écran par écran.",
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
                        <p className="text-sm text-brass tracking-wide mb-5">Visite guidée</p>
                        <h1 className="text-4xl sm:text-5xl leading-[1.1] text-ink">Une journée avec SPREA</h1>
                        <p className="mt-6 text-lg text-muted">
                            De la publication d'un DPE au rendez-vous chez le propriétaire : voici comment SPREA vous fait gagner des mandats, écran par écran.
                        </p>
                        <ol className="mt-10 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-left">
                            {[['8 h', 'Les nouveaux DPE', 'alertes'], ['8 h 15', 'La carte du secteur', 'prospecter'], ['8 h 30', 'Le courrier', 'contacter'], ['11 h', 'Les immeubles', 'immeubles-rapport'], ['12 h', "Les PV d'AG", 'pv-ag'], ['14 h', 'Le rendez-vous', 'convaincre']].map(([h, t, a]) => (
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
                <Step id="immeubles-rapport" kicker="11 h · Immeubles de rapport" title="Les immeubles entiers détenus par une SCI, avec leur propriétaire"
                    points={['Immeubles de 3 logements ou plus détenus en entier par une SCI ou une société privée', 'Hors copropriétés, bailleurs sociaux et organismes publics', 'Filtre « DPE F ou G » : les propriétaires qui ont une raison de vendre', 'Siège, gérants et autres immeubles de la société']}
                    media={
                        <div className="grid gap-4 sm:grid-cols-5 items-start">
                            <div className="sm:col-span-3"><Screen src="/demo/immeubles_carte.webp" alt="Carte des immeubles entiers détenus par des sociétés, colorés selon leur DPE, dans le centre de Lille" width={1600} height={1013} /></div>
                            <div className="sm:col-span-2"><Screen src="/demo/immeubles_liste.webp" alt="Liste des immeubles : adresse, nombre de logements, SCI propriétaire, DPE" width={760} height={824} /></div>
                        </div>
                    }>
                    <p>Le meilleur mandat, c'est un immeuble entier : vendu en bloc à un investisseur, ou découpé et revendu lot par lot. SPREA repère dans votre secteur tous les immeubles détenus par une seule société, avec leur DPE et leur dernière vente.</p>
                    <p>Pour chaque immeuble, vous savez à qui écrire : la SCI propriétaire, son siège, ses gérants et ses autres immeubles du secteur.</p>
                    <p className="text-xs text-faint">Captures réalisées avec des données d'exemple : noms de sociétés et de dirigeants fictifs.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step kicker="11 h 15 · Dossier de cession" title="Un dossier qui donne une raison de vendre maintenant" reverse
                    points={['Logements interdits à la location, avec le calendrier', 'Gel des loyers des logements F et G', 'Travaux à prévoir, à la charge du seul propriétaire', 'Valeur lot par lot, en bloc, et décote liée au DPE', 'Audit énergétique obligatoire pour vendre', 'Courrier à la gérance prêt à imprimer']}
                    media={
                        <div className="grid gap-4 sm:grid-cols-5 items-start">
                            <div className="sm:col-span-2"><Screen src="/demo/immeubles_fiche.webp" alt="Fiche d'un immeuble : SCI propriétaire, siège, gérants, autres immeubles, dossier de cession" width={1100} height={1352} /></div>
                            <div className="sm:col-span-3 grid grid-cols-2 gap-3">
                                <Screen src="/demo/immeubles_dossier_1.webp" alt="Dossier de cession, page 1 : pourquoi vendre maintenant et DPE des logements" width={900} height={1273} chrome={false} />
                                <Screen src="/demo/immeubles_dossier_2.webp" alt="Dossier de cession, page 2 : travaux, valeur de l'immeuble, obligations" width={900} height={1273} chrome={false} />
                            </div>
                        </div>
                    }>
                    <p>Un immeuble de logements classés G ne peut plus être reloué, ses loyers sont gelés, et il faut un audit énergétique pour le vendre. SPREA rassemble ces faits, chiffre les travaux et la valeur de l'immeuble, et en fait un dossier à vos couleurs.</p>
                    <p>Vous arrivez chez le gérant de la SCI avec des chiffres, pas avec une simple demande de mandat.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step kicker="11 h 30 · Signaux de vente" title="Les SCI qui vont vendre, repérées au BODACC"
                    points={['Dissolution, liquidation, procédure collective, radiation, changement de dirigeant', 'Annonces légales vérifiées chaque semaine pour chaque société propriétaire', 'Contour rouge sur la carte et filtre « signal de vente fort »', 'Lecture par l\'IA : ce que ça implique, qui contacter, à quel horizon']}
                    media={<Screen src="/demo/sig_sheet.webp" alt="Fiche d'un immeuble dont la SCI est en liquidation judiciaire : annonces du BODACC et lecture par l'IA" width={1100} height={1879} />}>
                    <p>Une SCI en liquidation judiciaire vend ses immeubles, une SCI dissoute aussi, et un changement de gérant annonce souvent une succession ou un arbitrage. Ces annonces sont publiques mais personne ne les lit : SPREA les croise chaque semaine avec les immeubles de votre secteur.</p>
                    <p>L'IA vous dit ce que la situation implique et à qui s'adresser : le liquidateur plutôt que le gérant, le notaire chargé d'une succession… Vous arrivez au bon moment, avec le bon interlocuteur.</p>
                    <p className="text-xs text-faint">Capture réalisée avec des données d'exemple : société, dirigeants et annonces fictifs.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step id="pv-ag" kicker="12 h · Documents de copropriété" title="Les PV d'AG lus par l'IA en deux minutes" reverse
                    points={['PV d\'AG, carnet d\'entretien, pré-état daté : PDF ou photos', 'Travaux votés et appels de fonds, travaux à venir, procédures, impayés', 'Points de vigilance classés, avec la page de chaque information', 'Questions à poser au syndic et documents manquants', 'Synthèse PDF à vos couleurs pour l\'acheteur ou le notaire']}
                    media={
                        <div className="grid gap-4 sm:grid-cols-5 items-start">
                            <div className="sm:col-span-3"><Screen src="/demo/docs_result.webp" alt="Synthèse des PV d'AG d'une copropriété : risque, points de vigilance, travaux votés et à venir, finances" width={1400} height={2426} /></div>
                            <div className="sm:col-span-2"><Screen src="/demo/docs_pdf.webp" alt="Synthèse de copropriété en PDF à remettre à l'acheteur" width={900} height={1272} chrome={false} /></div>
                        </div>
                    }>
                    <p>Avant chaque compromis, il faut lire les trois derniers PV d'assemblée générale : des dizaines de pages pour trouver le ravalement voté, l'ascenseur refusé ou la procédure contre un copropriétaire. Déposez-les : l'IA en sort l'essentiel, page par page.</p>
                    <p>Vous anticipez les questions de l'acheteur et du notaire, et vous évitez la mauvaise surprise qui fait tomber une vente.</p>
                    <p className="text-xs text-faint">Capture réalisée avec un PV d'AG fictif. Les documents sont supprimés après l'analyse.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step id="convaincre" kicker="14 h · Rendez-vous" title="Le simulateur : travaux, aides, reste à charge, en direct"
                    points={['Travaux recommandés selon le DPE du logement', 'Nouvelle étiquette, consommation et émissions', 'MaPrimeRénov\', CEE et éco-PTZ selon les barèmes en vigueur', 'Deux scénarios à comparer']}
                    media={<Screen src="/demo/works.webp" alt="Simulateur : choix des travaux et projet de passage de F à C" width={1600} height={1000} />}>
                    <p>Tapez l'adresse : SPREA retrouve le DPE officiel et propose les travaux qui font vraiment gagner des classes. Cochez, décochez : tout se recalcule devant le propriétaire.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step id="immeuble" kicker="14 h 10 · Copropriété" title="La fiche immeuble : ce que la copropriété va coûter" reverse
                    points={['Registre national des copropriétés : lots, syndic, période de construction', 'DPE collectif et étiquettes des autres appartements', 'Obligations : plan pluriannuel de travaux, DPE collectif', 'Travaux collectifs probables et quote-part de l\'appartement, avant et après aides']}
                    media={<Screen src="/demo/immeuble.webp" alt="Fiche immeuble : copropriété de 20 lots, DPE collectif E, travaux de façade et de chaufferie, quote-part de l'appartement" width={1400} height={1493} />}>
                    <p>Pour un appartement, la vraie question de l'acheteur, ce sont les charges à venir. SPREA croise le registre des copropriétés, le DPE de l'immeuble et la loi pour chiffrer les gros travaux et la part de ce lot.</p>
                    <p>Un argument de négociation que vous apportez avant lui, plutôt que de le subir après la visite.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step kicker="14 h 20 · Artisans" title="Les artisans RGE les plus proches, travail par travail"
                    points={['Annuaire officiel de l\'ADEME, mis à jour chaque jour', 'Entreprises qualifiées pour chaque travail retenu, les plus proches d\'abord', 'Rénovation globale et audit énergétique pour les projets d\'ampleur', 'Repris dans le rapport remis au client']}
                    media={<Screen src="/demo/rge.webp" alt="Liste des artisans RGE les plus proches pour chaque travail, avec téléphone et site" width={1400} height={1343} />}>
                    <p>Les aides ne sont versées que pour des travaux réalisés par une entreprise RGE. Le propriétaire repart avec des noms et des numéros de téléphone : son projet devient concret.</p>
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
                    points={['Synthèse, analyse rédigée, plan de travaux et de financement', 'Valeur verte et calendrier de la loi Climat', 'Fiche immeuble pour les appartements en copropriété', 'Artisans RGE proches pour chaque travail', 'Inclus sans limite dans l\'abonnement']}
                    media={
                        <div className="grid grid-cols-3 gap-3">
                            <Screen src="/demo/rapport_1.webp" alt="Rapport PDF, page 1 : synthèse et analyse" width={900} height={1273} chrome={false} />
                            <Screen src="/demo/rapport_immeuble.webp" alt="Rapport PDF : l'immeuble et ses travaux à venir" width={900} height={1273} chrome={false} />
                            <Screen src="/demo/rapport_rge.webp" alt="Rapport PDF : les artisans RGE près du logement" width={900} height={1273} chrome={false} />
                        </div>
                    }>
                    <p>Un document clair et sourcé, qui reste chez le propriétaire et qui porte votre travail : chaque chiffre est expliqué, de la valeur du bien aux artisans à appeler.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step kicker="Pour votre communication" title="L'observatoire de la valeur verte" reverse
                    points={['Mis à jour chaque mois', 'France entière et 90 départements', 'Des chiffres à citer en rendez-vous et sur vos réseaux']}
                    media={<Screen src="/demo/observatoire.webp" alt="Observatoire : écart de prix par classe DPE, maisons et appartements" width={1600} height={1000} />}>
                    <p>Une maison classée G se vend 18 % moins cher qu'une maison classée D, à emplacement et surface comparables. Montrez-le à vos vendeurs.</p>
                </Step>

                <div className="border-t border-line/60" />
                <Step id="equipe" kicker="Pour les agences et les réseaux" title="Toute l'agence sur le même outil"
                    points={['Un abonnement, autant de places que d\'agents, une seule facture', 'Invitation par lien, rôles titulaire, responsable et agent', 'Contacts et alertes partagés : aucun propriétaire ne se perd', 'Console réseau pour suivre toutes les agences']}
                    media={<Screen src="/demo/team.webp" alt="Page Équipe : membres de l'agence, rôles, invitations et nombre de places" width={1400} height={1281} />}>
                    <p>Chaque agent prospecte son secteur, et le responsable voit qui rappelle qui. Quand un agent part, ses contacts restent à l'agence.</p>
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
                            <ShieldCheck size={16} className="text-sage" /> Mensuel ou annuel · engagement 12 mois · facture avec TVA
                        </p>
                        <p className="mt-8 text-xs text-faint">Captures réalisées avec des données d'exemple, sauf la carte (DPE publics, adresses masquées).</p>
                    </div>
                </section>
            </main>
            <SiteFooter />
        </div>
    );
}
