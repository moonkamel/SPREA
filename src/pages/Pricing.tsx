import { Check, ChevronDown } from 'lucide-react';
import { Button } from '../ui';
import { useAccount } from '../account';
import { navigate } from '../router';
import { PageShell } from './site';

const PLANS = [
    {
        id: 'free',
        name: 'Simulation',
        tagline: 'Pour estimer le potentiel de rénovation d\'un logement.',
        features: [
            'Recherche par adresse ou numéro de DPE',
            'Travaux recommandés selon le logement',
            'Nouvelle étiquette DPE estimée',
            'Aides estimées et reste à charge',
            'Deux scénarios comparables',
            'Sans compte',
        ],
    },
    {
        id: 'report',
        name: 'Rapport',
        tagline: 'Pour un projet précis : un document complet à garder ou à partager.',
        features: [
            'Rapport PDF détaillé du logement',
            'Analyse rédigée selon votre profil (propriétaire ou investisseur)',
            'Plan de financement : MaPrimeRénov\', CEE, Éco-PTZ',
            'Économies sur la facture et retour sur investissement',
            'Retéléchargeable à tout moment',
            'Facture fournie',
        ],
    },
    {
        id: 'pro',
        name: 'Pro',
        tagline: 'Pour les agents immobiliers, courtiers, gestionnaires et artisans.',
        features: [
            'Rapports illimités',
            'Rapports à remettre à vos clients',
            'Historique de tous vos rapports',
            'Factures mensuelles',
            'Sans engagement, résiliable à tout moment',
        ],
    },
];

const FAQ = [
    {
        q: 'Que contient le rapport ?',
        a: "L'état actuel du logement selon son DPE, les travaux retenus et leur coût estimé, la nouvelle étiquette, les aides mobilisables, le reste à charge, les économies sur la facture d'énergie et une analyse rédigée.",
    },
    {
        q: 'Les montants sont-ils garantis ?',
        a: "Non. Il s'agit d'estimations fondées sur le DPE public et des coûts moyens de marché. Le rapport ne remplace ni un audit énergétique, ni un devis, et les aides doivent être confirmées par France Rénov' ou un Accompagnateur Rénov'.",
    },
    {
        q: "Comment résilier l'abonnement Pro ?",
        a: "À tout moment depuis « Mon compte », rubrique « Factures et abonnement ». L'abonnement reste actif jusqu'à la fin de la période déjà payée.",
    },
];

export default function PricingPage() {
    const { config, me, startSubscription } = useAccount();
    const prices: Record<string, { amount: string; unit: string }> = {
        free: { amount: 'Gratuit', unit: '' },
        report: { amount: config?.report_price || '—', unit: 'par rapport' },
        pro: { amount: config?.pro_price?.replace(' / mois', '') || '—', unit: 'par mois' },
    };

    const cta = (id: string) => {
        if (id === 'pro') {
            return me?.is_pro
                ? { label: 'Abonnement actif', action: () => { }, disabled: true }
                : { label: 'Passer Pro', action: startSubscription, disabled: false };
        }
        return { label: id === 'free' ? 'Lancer une simulation' : 'Simuler puis obtenir le rapport', action: () => navigate('/'), disabled: false };
    };

    return (
        <PageShell>
            <section className="text-center max-w-2xl mx-auto mb-12">
                <p className="text-sm text-brass tracking-wide mb-4">Tarifs</p>
                <h1 className="text-4xl sm:text-5xl text-ink leading-tight">Simple et transparent</h1>
                <p className="mt-5 text-lg text-muted">La simulation est gratuite. Payez uniquement les rapports dont vous avez besoin, ou passez Pro pour un usage régulier.</p>
            </section>

            <section className="grid grid-cols-1 md:grid-cols-3 gap-5">
                {PLANS.map(plan => {
                    const { label, action, disabled } = cta(plan.id);
                    const highlighted = plan.id === 'pro';
                    return (
                        <div key={plan.id} className={`rounded-2xl p-7 flex flex-col border ${highlighted ? 'border-brass/60 bg-panel shadow-2xl shadow-black/40' : 'border-line bg-panel'}`}>
                            <div className="flex items-center justify-between">
                                <h2 className="font-sans text-sm font-semibold tracking-wide text-brass">{plan.name}</h2>
                                {highlighted && <span className="text-[11px] px-2 py-0.5 rounded-full bg-brass text-canvas font-semibold">Professionnels</span>}
                            </div>
                            <p className="mt-5 font-serif text-4xl text-ink">{prices[plan.id].amount}</p>
                            <p className="text-sm mt-1 h-5 text-faint">{prices[plan.id].unit}{prices[plan.id].unit && ' · TTC'}</p>
                            <p className="mt-4 text-sm text-muted">{plan.tagline}</p>
                            <ul className="mt-6 space-y-3 flex-1">
                                {plan.features.map(f => (
                                    <li key={f} className="flex items-start gap-2.5 text-sm text-ink-soft">
                                        <Check size={16} className="shrink-0 mt-0.5 text-brass" />
                                        <span>{f}</span>
                                    </li>
                                ))}
                            </ul>
                            <Button onClick={action} disabled={disabled} variant={highlighted ? 'primary' : 'secondary'} className="mt-8 w-full">
                                {label}
                            </Button>
                        </div>
                    );
                })}
            </section>

            <section className="max-w-3xl mx-auto mt-20 space-y-3">
                <h2 className="text-2xl text-ink mb-4">Questions fréquentes</h2>
                {FAQ.map(item => (
                    <details key={item.q} className="group rounded-xl border border-line bg-panel px-5 py-4">
                        <summary className="cursor-pointer list-none flex items-center justify-between gap-4 text-ink">
                            {item.q}
                            <ChevronDown size={18} className="shrink-0 text-faint transition-transform group-open:rotate-180" />
                        </summary>
                        <p className="text-sm text-muted mt-3 leading-relaxed">{item.a}</p>
                    </details>
                ))}
            </section>
        </PageShell>
    );
}
