import { ArrowRight, Bell, Calculator, FileText, MapPinned, Scale, ShieldCheck } from 'lucide-react';
import { Button, Card } from '../ui';
import { navigate, Link } from '../router';
import { SiteFooter, SiteHeader } from '../pages/site';
import { Screen } from '../pages/Screen';
import { useSeo } from '../seo';

// Public home: SPREA is for real estate professionals, and only for subscribers
const PILLARS = [
    {
        icon: MapPinned,
        title: 'Prospecter',
        text: "Toutes les passoires E, F, G de votre secteur sur une carte, et chaque matin les nouveaux DPE publiés : un DPE précède presque toujours une vente ou une location.",
        anchor: 'prospecter',
    },
    {
        icon: FileText,
        title: 'Contacter',
        text: "Un courrier prêt à imprimer avec un QR code : le propriétaire découvre la rénovation de son logement à vos couleurs et vous laisse ses coordonnées.",
        anchor: 'contacter',
    },
    {
        icon: Scale,
        title: 'Convaincre',
        text: "En rendez-vous : travaux, aides, reste à charge, et surtout la valeur du bien avant et après travaux, appuyée sur les ventes DVF voisines.",
        anchor: 'convaincre',
    },
];

const PROOFS = [
    { value: '1,27 million', label: 'de ventes rapprochées de leur DPE pour mesurer la valeur verte' },
    { value: 'Chaque jour', label: 'les nouveaux DPE publiés par l\'ADEME, dans toute la France' },
    { value: '30 secondes', label: 'pour passer d\'une adresse à un rapport complet' },
];

export default function Home() {
    useSeo({
        title: "SPREA · L'outil DPE des agents immobiliers : prospection, valeur verte, avis de valeur",
        description: "Repérez les passoires thermiques de votre secteur, recevez chaque matin les nouveaux DPE et remettez à vos vendeurs un avis de valeur avant / après travaux fondé sur les ventes DVF.",
        path: '/',
    });
    return (
        <div className="min-h-screen flex flex-col">
            <SiteHeader />
            <main className="flex-1">
                <section className="relative overflow-hidden">
                    <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(201,164,92,0.12),transparent_60%)] pointer-events-none" />
                    <div className="relative max-w-4xl mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-12 text-center">
                        <p className="text-sm text-brass tracking-wide mb-5">Pour les agents et mandataires immobiliers</p>
                        <h1 className="text-4xl sm:text-6xl leading-[1.05] text-ink">
                            Trouvez les vendeurs avant les autres. Convainquez-les avec des chiffres.
                        </h1>
                        <p className="mt-6 text-lg text-muted max-w-2xl mx-auto">
                            SPREA repère chaque passoire thermique de votre secteur, vous signale les nouveaux DPE chaque matin et transforme un DPE en avis de valeur avant / après travaux.
                        </p>
                        <div className="mt-9 flex flex-col sm:flex-row gap-3 justify-center">
                            <Button onClick={() => navigate('/demo')} className="sm:w-56">Faire la visite guidée <ArrowRight size={18} /></Button>
                            <Button variant="secondary" onClick={() => navigate('/tarifs')} className="sm:w-56">Dès 79 € TTC / mois</Button>
                        </div>
                        <p className="mt-5 text-xs text-faint flex items-center justify-center gap-2">
                            <ShieldCheck size={14} className="text-sage" /> Mensuel ou annuel · engagement 12 mois · facture avec TVA
                        </p>
                    </div>
                    <div className="relative max-w-6xl mx-auto px-4 sm:px-6 pb-16">
                        <Screen src="/demo/dashboard.webp" alt="Le simulateur SPREA : étiquette actuelle, travaux, aides, reste à charge et valeur verte d'une maison" width={1600} height={1000} eager />
                    </div>
                </section>

                <section className="border-y border-line/60 bg-panel/40">
                    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10 grid gap-8 sm:grid-cols-3 text-center">
                        {PROOFS.map(p => (
                            <div key={p.value}>
                                <p className="font-serif text-3xl text-brass">{p.value}</p>
                                <p className="mt-2 text-sm text-muted">{p.label}</p>
                            </div>
                        ))}
                    </div>
                </section>

                <section className="max-w-6xl mx-auto px-4 sm:px-6 py-16">
                    <h2 className="text-3xl sm:text-4xl text-ink text-center">Du DPE au mandat</h2>
                    <div className="mt-10 grid gap-5 md:grid-cols-3">
                        {PILLARS.map(p => (
                            <Link key={p.title} to={`/demo#${p.anchor}`} className="block">
                                <Card className="p-7 h-full hover:border-brass/50 transition-colors">
                                    <p.icon size={22} className="text-brass" />
                                    <h3 className="mt-5 text-xl text-ink">{p.title}</h3>
                                    <p className="mt-3 text-sm text-muted leading-relaxed">{p.text}</p>
                                </Card>
                            </Link>
                        ))}
                    </div>
                    <div className="mt-6 grid gap-5 md:grid-cols-2">
                        <Card className="p-7 flex gap-4 items-start">
                            <Bell size={22} className="text-brass shrink-0" />
                            <p className="text-sm text-muted leading-relaxed"><span className="text-ink">Alertes quotidiennes.</span> Définissez vos secteurs : chaque matin, les DPE publiés la veille, avant que le bien n'arrive sur les portails.</p>
                        </Card>
                        <Card className="p-7 flex gap-4 items-start">
                            <Calculator size={22} className="text-brass shrink-0" />
                            <p className="text-sm text-muted leading-relaxed"><span className="text-ink">Des chiffres opposables.</span> DPE officiels de l'ADEME, ventes DVF de la DGFiP, barèmes d'aides en vigueur : chaque montant cite sa source.</p>
                        </Card>
                    </div>
                </section>

                <section className="max-w-4xl mx-auto px-4 sm:px-6 pb-20 text-center">
                    <h2 className="text-3xl text-ink">Un mandat signé rembourse des années d'abonnement</h2>
                    <p className="mt-4 text-muted">Formule Solo à 79 € TTC par mois, Agence à 59 € TTC par agent, Réseau sur devis.</p>
                    <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
                        <Button onClick={() => navigate('/demo')} className="sm:w-56">Faire la visite guidée</Button>
                        <Button variant="secondary" onClick={() => navigate('/tarifs')} className="sm:w-56">Voir les tarifs</Button>
                    </div>
                </section>
            </main>
            <SiteFooter />
        </div>
    );
}
