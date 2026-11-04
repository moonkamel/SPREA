import { ArrowRight, Building2, Check, ChevronDown, FileText, Home as HomeIcon, MapPin, ShieldCheck, Target } from 'lucide-react';
import { useState } from 'react';
import { SiteFooter, SiteHeader } from './site';
import { useSeo } from '../seo';
import { Backdrop, Eyebrow, GlowButton, Reveal } from '../views/home/fx';

// Landing page for building firms (TCE / RGE): « trouver des chantiers », the worksite dossiers
// SPREA prepares from public data. Figures stated here are those of the database (59 and 62).

const MAIL = 'contact@sprea.app';
const mailto = (subject: string, body: string) =>
    `mailto:${MAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
const FREE = mailto('Un dossier chantier gratuit', "Bonjour,\n\nJe souhaite recevoir un dossier chantier gratuit près de mon entreprise.\n\nEntreprise :\nCommune :\nCorps de métier :\nTéléphone :\n");

const STEPS = [
    { icon: Target, title: 'Nous repérons le chantier', text: "Maisons et immeubles détenus par une société (SCI, SARL…) dont les DPE publiés sont classés F ou G, près de votre entreprise. Un propriétaire qui ne pourra bientôt plus louer, ou plus du tout." },
    { icon: FileText, title: 'Nous préparons le dossier', text: "Budget poste par poste et corps d'état, DPE de chaque logement, règles de location qui s'appliquent, et le maître d'ouvrage : société, siège, dirigeant. Un PDF de deux pages, prêt à joindre à votre courrier." },
    { icon: MapPin, title: 'Vous prenez contact', text: "Vous écrivez au propriétaire avec un dossier chiffré, avant qu'il ne lance une consultation. Un seul décideur : pas de syndic, pas d'assemblée générale." },
];

const OFFERS = [
    {
        name: 'Dossier d\'essai', price: 'Gratuit', unit: '1 dossier', highlighted: false,
        points: ['Un chantier F/G près de votre entreprise', 'Le dossier PDF complet', 'Sans engagement, sans carte'],
        cta: { label: 'Recevoir mon dossier gratuit', href: FREE },
    },
    {
        name: 'Pack Découverte', price: '99 €', unit: 'HT · 3 dossiers', highlighted: true,
        points: ['3 chantiers choisis dans votre zone', 'Maisons ou immeubles selon votre métier', 'Exclusif : proposés à vous seul', 'Paiement unique, sans abonnement'],
        cta: { label: 'Commander le Pack Découverte', href: mailto('Pack Découverte (99 € HT)', "Bonjour,\n\nJe souhaite commander le Pack Découverte : 3 dossiers chantier exclusifs dans ma zone.\n\nEntreprise :\nSIRET :\nCommune et rayon d'intervention :\nCorps de métier :\nTéléphone :\n") },
    },
    {
        name: 'Zone exclusive', price: '349 €', unit: 'HT · par mois', highlighted: false,
        points: ['Tous les chantiers F/G de votre zone, à vous seul', 'Les nouveaux DPE F/G chaque semaine', 'Jusqu\'à 10 communes au choix', 'Sans engagement après 3 mois'],
        cta: { label: 'Réserver ma zone', href: mailto('Zone exclusive (349 € HT / mois)', "Bonjour,\n\nJe souhaite réserver une zone exclusive.\n\nEntreprise :\nSIRET :\nCommunes souhaitées :\nCorps de métier :\nTéléphone :\n") },
    },
];

const FAQ = [
    {
        q: 'Comment trouver des chantiers quand on est artisan du bâtiment ?',
        a: "Les plateformes de mise en relation vendent la même demande de devis à plusieurs entreprises, qui se battent ensuite sur le prix. SPREA prend le problème à l'envers : nous repérons les propriétaires qui devront faire des travaux, à cause de la loi Climat et Résilience, et vous donnons le dossier chiffré pour les contacter les premiers.",
    },
    {
        q: "D'où viennent les informations ?",
        a: "De données publiques : DPE publiés par l'ADEME, base nationale des bâtiments (CSTB), fichier des locaux détenus par des personnes morales (DGFiP), ventes DVF, Annuaire des entreprises. Chaque dossier cite ses sources et dit ce qui est mesuré et ce qui est estimé.",
    },
    {
        q: 'Le propriétaire a-t-il demandé des travaux ?',
        a: "Non, et c'est tout l'intérêt : vous arrivez avant la mise en concurrence. Le dossier montre pourquoi il doit agir (logements G interdits à la location depuis 2025, F en 2028, loyers gelés) et chiffre le chantier. À vous de le convaincre ; nous ne contactons jamais les propriétaires.",
    },
    {
        q: 'Mon métier est-il concerné si je ne fais pas tous corps d\'état ?',
        a: "Oui. Une maison classée G, c'est souvent une isolation, des menuiseries, un chauffage ou une ventilation à refaire. Nous choisissons les chantiers selon vos qualifications RGE : un chauffagiste ne reçoit pas un dossier de façade.",
    },
    {
        q: "Les dossiers sont-ils exclusifs ?",
        a: "Avec le Pack Découverte et la Zone exclusive, oui : un dossier acheté n'est proposé à aucune autre entreprise. C'est la grande différence avec une demande de devis partagée.",
    },
    {
        q: 'Pourquoi le statut RGE compte ?',
        a: "Les primes CEE ne sont versées que pour des travaux réalisés par une entreprise RGE, propriétaire société compris. C'est un argument que le dossier met en avant face au propriétaire.",
    },
];

export default function ChantiersPage() {
    useSeo({
        title: 'Trouver des chantiers de rénovation énergétique : dossiers exclusifs pour artisans RGE | SPREA',
        description: "Maisons et immeubles F/G détenus par des SCI près de votre entreprise, avec le dossier chantier chiffré (postes, corps d'état, propriétaire). 1 dossier d'essai gratuit, Pack Découverte 99 € HT.",
        path: '/trouver-des-chantiers',
    });
    const [open, setOpen] = useState<number | null>(0);
    return (
        <div className="min-h-screen bg-canvas text-ink">
            <SiteHeader />
            <main>
                <section className="relative overflow-hidden">
                    <Backdrop />
                    <div className="relative mx-auto max-w-5xl px-4 sm:px-6 pt-16 pb-14 text-center">
                        <Reveal><Eyebrow>Pour les entreprises du bâtiment · RGE</Eyebrow></Reveal>
                        <Reveal delay={0.05}>
                            <h1 className="mt-5 text-[2rem] sm:text-5xl leading-[1.08]">
                                Trouvez des chantiers de rénovation
                                <span className="block text-brass-light">avant vos concurrents.</span>
                            </h1>
                        </Reveal>
                        <Reveal delay={0.1}>
                            <p className="mx-auto mt-5 max-w-2xl text-ink-soft leading-relaxed">
                                Des maisons et immeubles classés F ou G, détenus par une société, près de chez vous. Pour chacun, un dossier chantier chiffré
                                et le contact du maître d'ouvrage. Pas une demande de devis revendue à cinq entreprises : un chantier à vous.
                            </p>
                        </Reveal>
                        <Reveal delay={0.15}>
                            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
                                <a href={FREE}><GlowButton>Recevoir un dossier gratuit <ArrowRight size={16} /></GlowButton></a>
                                <a href="#offres" className="text-sm text-muted hover:text-ink underline underline-offset-4">Voir les offres</a>
                            </div>
                            <p className="mt-4 text-xs text-faint">Nord et Pas-de-Calais aujourd'hui · Aisne, Oise et Somme bientôt</p>
                        </Reveal>
                    </div>
                </section>

                <section className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
                    <div className="grid gap-4 sm:grid-cols-3">
                        {[
                            ['2 600+', 'maisons et immeubles F ou G détenus par une société, Nord et Pas-de-Calais'],
                            ['2025 · 2028', 'logements G interdits à la location, puis F : les propriétaires doivent agir'],
                            ['1', 'seul décideur par chantier : pas de syndic, pas de copropriété'],
                        ].map(([n, t]) => (
                            <Reveal key={n}>
                                <div className="rounded-3xl border border-white/10 bg-panel/60 p-6">
                                    <p className="font-serif text-3xl text-brass-light">{n}</p>
                                    <p className="mt-2 text-sm text-muted leading-relaxed">{t}</p>
                                </div>
                            </Reveal>
                        ))}
                    </div>
                </section>

                <section className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
                    <h2 className="text-2xl sm:text-3xl">Comment ça marche</h2>
                    <div className="mt-6 grid gap-4 sm:grid-cols-3">
                        {STEPS.map(({ icon: Icon, title, text }, i) => (
                            <Reveal key={title} delay={i * 0.05}>
                                <div className="h-full rounded-3xl border border-white/10 bg-panel/60 p-6">
                                    <Icon className="text-brass" size={22} />
                                    <h3 className="mt-3 text-lg">{title}</h3>
                                    <p className="mt-2 text-sm text-muted leading-relaxed">{text}</p>
                                </div>
                            </Reveal>
                        ))}
                    </div>
                </section>

                <section className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
                    <h2 className="text-2xl sm:text-3xl">Ce que contient un dossier chantier</h2>
                    <div className="mt-6 grid gap-4 sm:grid-cols-2">
                        {[
                            [Building2, 'Le chantier, poste par poste', "Isolation, menuiseries, chauffage, ventilation : le constat de chaque DPE, le corps d'état concerné et un coût TTC. Les logements sont chiffrés au coût de leur propre classe."],
                            [HomeIcon, 'Les DPE et la loi', "La classe de chaque logement, ce qui est mesuré et ce qui est estimé, et les interdictions de louer qui s'appliquent au propriétaire."],
                            [ShieldCheck, 'Vos arguments', "La décote liée au DPE et la valeur après travaux quand le marché le justifie, les primes CEE réservées aux entreprises RGE, un seul décideur."],
                            [MapPin, "Le maître d'ouvrage", "La société propriétaire, son siège et son dirigeant (Annuaire des entreprises), ses autres biens, et comment la contacter."],
                        ].map(([Icon, title, text]) => {
                            const I = Icon as typeof Building2;
                            return (
                                <Reveal key={title as string}>
                                    <div className="h-full rounded-3xl border border-white/10 bg-panel/60 p-6 flex gap-4">
                                        <I className="text-brass shrink-0 mt-1" size={20} />
                                        <div><h3 className="text-lg">{title as string}</h3><p className="mt-1 text-sm text-muted leading-relaxed">{text as string}</p></div>
                                    </div>
                                </Reveal>
                            );
                        })}
                    </div>
                </section>

                <section id="offres" className="scroll-mt-24 mx-auto max-w-5xl px-4 sm:px-6 py-12">
                    <h2 className="text-2xl sm:text-3xl text-center">Les offres</h2>
                    <p className="mt-2 text-center text-sm text-muted">Commencez par un dossier gratuit : vous jugez sur pièce.</p>
                    <div className="mt-8 grid gap-4 md:grid-cols-3">
                        {OFFERS.map(o => (
                            <div key={o.name} className={`relative flex flex-col rounded-3xl border p-6 ${o.highlighted ? 'border-brass/60 bg-gradient-to-b from-brass/[0.10] to-panel' : 'border-white/10 bg-panel/60'}`}>
                                {o.highlighted && <span className="absolute -top-3 left-6 rounded-full bg-brass px-3 py-0.5 text-xs font-semibold text-canvas">Le plus choisi</span>}
                                <h3 className="text-lg">{o.name}</h3>
                                <p className="mt-3 font-serif text-4xl text-ink">{o.price}</p>
                                <p className="text-xs text-muted">{o.unit}</p>
                                <ul className="mt-5 space-y-2 flex-1">
                                    {o.points.map(p => <li key={p} className="flex gap-2 text-sm text-ink-soft"><Check size={16} className="text-sage shrink-0 mt-0.5" />{p}</li>)}
                                </ul>
                                <a href={o.cta.href} className="mt-6"><GlowButton variant={o.highlighted ? 'primary' : 'ghost'} className="w-full">{o.cta.label}</GlowButton></a>
                            </div>
                        ))}
                    </div>
                    <p className="mt-4 text-center text-xs text-faint">Prix hors taxes. Dossiers indicatifs établis sur données publiques : ni expertise, ni audit énergétique, ni devis.</p>
                </section>

                <section className="mx-auto max-w-3xl px-4 sm:px-6 py-12">
                    <h2 className="text-2xl sm:text-3xl">Questions fréquentes</h2>
                    <div className="mt-6 divide-y divide-white/10 rounded-3xl border border-white/10 bg-panel/60">
                        {FAQ.map((f, i) => (
                            <div key={f.q}>
                                <button type="button" onClick={() => setOpen(open === i ? null : i)} className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left">
                                    <span className="text-ink">{f.q}</span>
                                    <ChevronDown size={18} className={`shrink-0 text-muted transition-transform ${open === i ? 'rotate-180' : ''}`} />
                                </button>
                                {open === i && <p className="px-5 pb-5 text-sm text-muted leading-relaxed">{f.a}</p>}
                            </div>
                        ))}
                    </div>
                    <div className="mt-10 text-center">
                        <a href={FREE}><GlowButton>Recevoir un dossier gratuit <ArrowRight size={16} /></GlowButton></a>
                    </div>
                </section>
            </main>
            <SiteFooter />
        </div>
    );
}

