import { useState } from 'react';
import { Check, ChevronDown, Loader2, ShieldCheck, X } from 'lucide-react';
import { Button, Segmented } from '../ui';
import { useAccount, type AgencyOrder, type Plan } from '../account';
import { Link } from '../router';
import { PageShell } from './site';
import { useSeo } from '../seo';

type Billing = 'monthly' | 'yearly';

const INCLUDED = [
    'Simulateur : travaux, nouvelle étiquette, aides, reste à charge',
    'Rapports PDF illimités, rédigés pour vos clients',
    'Avis de valeur avant / après travaux (ventes DVF)',
    'Carte de prospection des passoires E, F, G',
    'Alertes quotidiennes sur les nouveaux DPE',
    'Courriers avec QR code et page propriétaire à vos couleurs',
    'Suivi des contacts reçus',
    'Artisans RGE les plus proches pour chaque travail',
    'Fiche immeuble des copropriétés : registre, DPE collectif, travaux à venir',
    'Immeubles entiers détenus par des SCI, avec leur propriétaire et un dossier de cession',
    'Signaux de vente des SCI (BODACC : dissolution, liquidation…) expliqués par l\'IA',
    'Lecture des PV d\'AG par l\'IA : travaux votés, appels de fonds, procédures, points de vigilance',
];

const FAQ = [
    {
        q: 'Puis-je voir SPREA avant de m\'abonner ?',
        a: "Oui : la visite guidée présente chaque outil en images (simulateur, carte de prospection, alertes, avis de valeur, immeubles de SCI et signaux de vente, PV d'AG lus par l'IA). Pour une présentation en direct, écrivez-nous.",
    },
    {
        q: "Y a-t-il un engagement ?",
        a: "Oui, 12 mois pour toutes les formules. En paiement mensuel, l'abonnement est payé chaque mois pendant au moins 12 mois ; en annuel, les 12 mois sont payés d'avance. À l'issue de l'engagement, l'abonnement est résiliable à tout moment depuis « Mon compte » et reste actif jusqu'à la fin de la période payée.",
    },
    {
        q: 'Les prix sont-ils TTC ?',
        a: "Oui, tous les prix affichés incluent la TVA à 20 %. La facture détaille le montant hors taxes et la TVA, avec votre raison sociale et votre numéro de TVA.",
    },
    {
        q: 'Comment équiper toute mon agence ?',
        a: "Avec la formule Agence, vous payez par agent (2 agents minimum). Après le paiement, invitez vos agents par email depuis la page Équipe : chacun a son propre accès. Vous ajustez le nombre d'agents à tout moment, facturé au prorata.",
    },
    {
        q: "D'où viennent les données ?",
        a: "Des bases publiques officielles : DPE de l'ADEME (mis à jour chaque jour), ventes immobilières DVF de la DGFiP, Base Adresse Nationale. Les estimations ne remplacent ni un audit énergétique, ni un devis d'artisan.",
    },
];

export default function PricingPage() {
    useSeo({
        title: 'Tarifs SPREA : dès 79 € TTC par mois pour les agents immobiliers',
        description: "Solo 79 € TTC / mois, Agence 59 € TTC par agent, Réseau sur devis. Tous les outils inclus : prospection DPE, immeubles de rapport, alertes, avis de valeur, rapports.",
        path: '/tarifs',
    });
    const { config, me, startSubscription } = useAccount();
    const [billing, setBilling] = useState<Billing>('monthly');
    const [quote, setQuote] = useState<'agence' | 'reseau' | null>(null);
    const [agencyOpen, setAgencyOpen] = useState(false);
    const plan: Plan = billing === 'monthly' ? 'solo_monthly' : 'solo_yearly';
    const soloPrice = (config?.plans?.[plan] || (billing === 'monthly' ? '79 € / mois' : '790 € / an')).split(' / ')[0];
    const per = billing === 'monthly' ? 'par mois' : 'par an';

    const offers = [
        {
            id: 'solo',
            name: 'Solo',
            tagline: 'Pour un agent ou un mandataire indépendant.',
            price: soloPrice,
            unit: `${per} · TTC`,
            note: billing === 'yearly' ? 'soit 2 mois offerts' : 'engagement 12 mois',
            cta: me?.is_pro
                ? <Button disabled className="mt-8 w-full">Abonnement actif</Button>
                : <Button onClick={() => startSubscription(plan)} className="mt-8 w-full">Démarrer maintenant</Button>,
            highlighted: true,
        },
        {
            id: 'agence',
            name: 'Agence',
            tagline: 'Pour équiper une équipe de 2 à 15 agents.',
            price: billing === 'monthly' ? '59 €' : '590 €',
            unit: `par agent, ${per} · TTC`,
            note: '2 agents minimum · engagement 12 mois',
            cta: me?.is_pro
                ? <Button variant="secondary" disabled className="mt-8 w-full">Abonnement actif</Button>
                : <Button variant="secondary" onClick={() => setAgencyOpen(true)} className="mt-8 w-full">Équiper mon agence</Button>,
            highlighted: false,
        },
        {
            id: 'reseau',
            name: 'Réseau',
            tagline: 'Pour les enseignes et réseaux de plusieurs agences.',
            price: 'Sur devis',
            unit: 'à partir de 39 € par agent et par mois · TTC',
            note: 'engagement 12 mois',
            cta: <Button variant="secondary" onClick={() => setQuote('reseau')} className="mt-8 w-full">Demander un devis</Button>,
            highlighted: false,
        },
    ];
    const extras: Record<string, string[]> = {
        solo: ['Tout SPREA, sans limite'],
        agence: ['Tout SPREA pour chaque agent', 'Contacts et alertes partagés dans l\'agence', 'Une facture unique'],
        reseau: ['Console du siège : toutes les agences', 'Courriers et rapports aux couleurs du réseau', 'Accompagnement au démarrage'],
    };

    return (
        <PageShell>
            <section className="text-center max-w-2xl mx-auto mb-10">
                <p className="text-sm text-brass tracking-wide mb-4">Tarifs</p>
                <h1 className="text-4xl sm:text-5xl text-ink leading-tight">Un mandat signé rembourse des années d'abonnement</h1>
                <p className="mt-5 text-lg text-muted">Réservé aux professionnels de l'immobilier. Tous les outils sont inclus dans chaque formule.</p>
                <div className="mt-8 max-w-xs mx-auto">
                    <Segmented ariaLabel="Facturation" value={billing} onChange={setBilling}
                        options={[{ value: 'monthly', label: 'Mensuel' }, { value: 'yearly', label: 'Annuel −2 mois' }]} />
                </div>
            </section>

            <section className="grid grid-cols-1 md:grid-cols-3 gap-5">
                {offers.map(o => (
                    <div key={o.id} className={`rounded-2xl p-7 flex flex-col border bg-panel ${o.highlighted ? 'border-brass/60 shadow-2xl shadow-black/40' : 'border-line'}`}>
                        <div className="flex items-center justify-between">
                            <h2 className="font-sans text-sm font-semibold tracking-wide text-brass">{o.name}</h2>
                            {o.highlighted && <span className="text-[11px] px-2 py-0.5 rounded-full bg-brass text-canvas font-semibold">Démarrage immédiat</span>}
                        </div>
                        <p className="mt-5 font-serif text-4xl text-ink">{o.price}</p>
                        <p className="text-sm mt-1 text-faint">{o.unit}</p>
                        <p className="text-xs mt-1 text-sage">{o.note}</p>
                        <p className="mt-4 text-sm text-muted">{o.tagline}</p>
                        <ul className="mt-6 space-y-3 flex-1">
                            {extras[o.id].map(f => (
                                <li key={f} className="flex items-start gap-2.5 text-sm text-ink">
                                    <Check size={16} className="shrink-0 mt-0.5 text-brass" /><span>{f}</span>
                                </li>
                            ))}
                        </ul>
                        {o.cta}
                    </div>
                ))}
            </section>

            <p className="mt-6 text-center text-sm text-muted flex items-center justify-center gap-2">
                <ShieldCheck size={16} className="text-sage" /> Engagement 12 mois · Paiement sécurisé par Stripe · Facture avec TVA
            </p>

            <section className="mt-14 rounded-2xl border border-line bg-panel p-7 sm:p-9">
                <h2 className="text-2xl text-ink">Inclus dans toutes les formules</h2>
                <ul className="mt-6 grid sm:grid-cols-2 gap-x-8 gap-y-3">
                    {INCLUDED.map(f => (
                        <li key={f} className="flex items-start gap-2.5 text-sm text-ink-soft">
                            <Check size={16} className="shrink-0 mt-0.5 text-brass" /><span>{f}</span>
                        </li>
                    ))}
                </ul>
                <p className="mt-6 text-sm text-muted">Pas encore convaincu ? <Link to="/demo" className="text-brass underline">Voyez SPREA en action</Link>.</p>
            </section>

            <section className="max-w-3xl mx-auto mt-16 space-y-3">
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

            {quote && <QuoteDialog offer={quote} onClose={() => setQuote(null)} />}
            {agencyOpen && (
                <AgencyDialog billing={billing} onClose={() => setAgencyOpen(false)} onQuote={() => { setAgencyOpen(false); setQuote('agence'); }}
                    onConfirm={order => { setAgencyOpen(false); startSubscription(billing === 'monthly' ? 'agence_monthly' : 'agence_yearly', order); }} />
            )}
        </PageShell>
    );
}

const FIELD = 'w-full h-11 px-3 rounded-xl bg-raised border border-line text-ink placeholder:text-faint outline-none focus:border-brass/70';

function QuoteDialog({ offer, onClose }: { offer: 'agence' | 'reseau'; onClose: () => void }) {
    const [form, setForm] = useState({ name: '', company: '', email: '', phone: '', agents: offer === 'agence' ? '3' : '20', message: '', website: '' });
    const [status, setStatus] = useState<'idle' | 'sending' | 'sent'>('idle');
    const [error, setError] = useState<string | null>(null);
    const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm(f => ({ ...f, [k]: e.target.value }));

    const send = async (e: React.FormEvent) => {
        e.preventDefault();
        setStatus('sending');
        setError(null);
        try {
            const res = await fetch('/api/quote', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...form, offer, agents: Number(form.agents) || 1 }),
            });
            if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "L'envoi a échoué.");
            setStatus('sent');
        } catch (err) {
            setError((err as Error).message);
            setStatus('idle');
        }
    };

    return (
        <div className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
            <div className="bg-panel border border-line rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto p-6 sm:p-8 relative" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
                <button onClick={onClose} className="absolute top-5 right-5 text-faint hover:text-ink" aria-label="Fermer"><X size={20} /></button>
                <h2 className="text-2xl text-ink pr-8">{offer === 'agence' ? 'Équiper mon agence' : 'Devis réseau'}</h2>
                {status === 'sent' ? (
                    <p className="mt-6 text-ink-soft">Merci, votre demande est bien reçue. Nous revenons vers vous sous 24 heures ouvrées.</p>
                ) : (
                    <form onSubmit={send} className="mt-6 space-y-3">
                        <div className="grid sm:grid-cols-2 gap-3">
                            <input required placeholder="Nom et prénom" value={form.name} onChange={set('name')} className={FIELD} aria-label="Nom et prénom" />
                            <input required placeholder={offer === 'agence' ? 'Agence' : 'Réseau'} value={form.company} onChange={set('company')} className={FIELD} aria-label="Société" />
                            <input required type="email" placeholder="Email professionnel" value={form.email} onChange={set('email')} className={FIELD} aria-label="Email" />
                            <input placeholder="Téléphone" value={form.phone} onChange={set('phone')} className={FIELD} aria-label="Téléphone" />
                        </div>
                        <label className="flex items-center gap-3 text-sm text-ink-soft">
                            Nombre d'agents
                            <input type="number" min={1} max={5000} value={form.agents} onChange={set('agents')} className={`${FIELD} w-28`} aria-label="Nombre d'agents" />
                        </label>
                        <textarea placeholder="Votre besoin (facultatif)" value={form.message} onChange={set('message')} rows={3}
                            className="w-full px-3 py-2 rounded-xl bg-raised border border-line text-ink placeholder:text-faint outline-none focus:border-brass/70" aria-label="Message" />
                        {/* Honeypot */}
                        <input tabIndex={-1} autoComplete="off" value={form.website} onChange={set('website')} className="hidden" aria-hidden="true" />
                        {error && <p className="text-sm text-coral">{error}</p>}
                        <Button type="submit" disabled={status === 'sending'} className="w-full">
                            {status === 'sending' && <Loader2 className="animate-spin" size={16} />} Envoyer ma demande
                        </Button>
                        <p className="text-xs text-faint">Vos coordonnées servent uniquement à répondre à votre demande et sont supprimées au bout de 3 ans sans suite.</p>
                    </form>
                )}
            </div>
        </div>
    );
}

function AgencyDialog({ billing, onClose, onConfirm, onQuote }: {
    billing: Billing;
    onClose: () => void;
    onConfirm: (order: AgencyOrder) => void;
    onQuote: () => void;
}) {
    const [name, setName] = useState('');
    const [seats, setSeats] = useState(3);
    const unit = billing === 'monthly' ? 59 : 590;
    const valid = name.trim().length >= 2 && seats >= 2 && seats <= 50;
    return (
        <div className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
            <div className="bg-panel border border-line rounded-2xl shadow-2xl w-full max-w-md p-6 sm:p-8 relative" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
                <button onClick={onClose} className="absolute top-5 right-5 text-faint hover:text-ink" aria-label="Fermer"><X size={20} /></button>
                <h2 className="text-2xl text-ink pr-8">Équiper mon agence</h2>
                <form className="mt-6 space-y-4" onSubmit={e => { e.preventDefault(); if (valid) onConfirm({ agency_name: name.trim(), seats }); }}>
                    <input required autoFocus placeholder="Nom de l'agence" value={name} onChange={e => setName(e.target.value)} className={FIELD} aria-label="Nom de l'agence" />
                    <label className="flex items-center justify-between gap-3 text-sm text-ink-soft">
                        Nombre d'agents, vous compris
                        <input type="number" min={2} max={50} value={seats} onChange={e => setSeats(Math.max(0, Number(e.target.value) || 0))} className={`${FIELD} w-24`} aria-label="Nombre d'agents" />
                    </label>
                    <div className="rounded-xl border border-line bg-raised p-4 flex items-baseline justify-between">
                        <span className="text-sm text-muted">{seats} × {unit} € TTC</span>
                        <span className="font-serif text-2xl text-ink">{(seats * unit).toLocaleString('fr-FR')} € <span className="font-sans text-xs text-faint">TTC / {billing === 'monthly' ? 'mois' : 'an'}</span></span>
                    </div>
                    <Button type="submit" disabled={!valid} className="w-full">Continuer</Button>
                    <p className="text-xs text-faint">Plus de 50 agents, ou besoin d'un bon de commande ? <button type="button" onClick={onQuote} className="underline text-brass">Demandez un devis</button>.</p>
                </form>
            </div>
        </div>
    );
}
