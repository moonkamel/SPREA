import { Check } from 'lucide-react';
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
                <h1 className="text-3xl sm:text-4xl font-black text-slate-800 tracking-tighter mb-4">Tarifs</h1>
                <p className="text-slate-500">La simulation est gratuite. Payez uniquement les rapports dont vous avez besoin, ou passez Pro pour un usage régulier.</p>
            </section>

            <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {PLANS.map(plan => {
                    const { label, action, disabled } = cta(plan.id);
                    const highlighted = plan.id === 'pro';
                    return (
                        <div key={plan.id} className={`rounded-[2rem] p-8 flex flex-col border ${highlighted ? 'bg-slate-900 text-white border-slate-900 shadow-2xl' : 'bg-white border-slate-100 shadow-sm'}`}>
                            <h2 className={`text-xs font-black uppercase tracking-widest ${highlighted ? 'text-blue-300' : 'text-blue-600'}`}>{plan.name}</h2>
                            <p className="mt-4 text-4xl font-black tracking-tighter">{prices[plan.id].amount}</p>
                            <p className={`text-xs mt-1 h-4 ${highlighted ? 'text-slate-400' : 'text-slate-400'}`}>{prices[plan.id].unit}{prices[plan.id].unit && ' · TTC'}</p>
                            <p className={`mt-4 text-sm ${highlighted ? 'text-slate-300' : 'text-slate-500'}`}>{plan.tagline}</p>
                            <ul className="mt-6 space-y-3 flex-1">
                                {plan.features.map(f => (
                                    <li key={f} className="flex items-start gap-2 text-sm">
                                        <Check size={16} className={`shrink-0 mt-0.5 ${highlighted ? 'text-blue-300' : 'text-blue-600'}`} />
                                        <span>{f}</span>
                                    </li>
                                ))}
                            </ul>
                            <button
                                onClick={action}
                                disabled={disabled}
                                className={`mt-8 h-12 rounded-xl font-black uppercase text-[10px] tracking-widest transition-all disabled:opacity-60 ${highlighted ? 'bg-blue-600 hover:bg-blue-500 text-white' : 'bg-slate-100 hover:bg-slate-900 hover:text-white text-slate-700'}`}
                            >
                                {label}
                            </button>
                        </div>
                    );
                })}
            </section>

            <section className="max-w-3xl mx-auto mt-16 space-y-6">
                <h2 className="text-xl font-black text-slate-800 tracking-tight">Questions fréquentes</h2>
                {FAQ.map(item => (
                    <div key={item.q}>
                        <h3 className="font-bold text-slate-800">{item.q}</h3>
                        <p className="text-sm text-slate-500 mt-1 leading-relaxed">{item.a}</p>
                    </div>
                ))}
            </section>
        </PageShell>
    );
}
