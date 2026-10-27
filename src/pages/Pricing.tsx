import { useState } from 'react';
import { Check, ChevronDown, Loader2, ShieldCheck, X } from 'lucide-react';
import { errorDetail } from '../ui';
import { useAccount, type AgencyOrder, type Plan } from '../account';
import { Link } from '../router';
import { SiteFooter, SiteHeader } from './site';
import { useSeo } from '../seo';
import { Backdrop, Eyebrow, GlowButton, Reveal, TiltCard } from '../views/home/fx';

type Billing = 'monthly' | 'yearly';

const INCLUDED = [
    'Simulateur : travaux, nouvelle étiquette, aides, reste à charge',
    'Rapports PDF sans limite, rédigés pour vos clients',
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
        a: "Oui : la visite guidée présente chaque outil en images (simulateur, carte de prospection, alertes, avis de valeur, immeubles de SCI et signaux de vente, biens à fort potentiel, dossier acheteur, PV d'AG lus par l'IA). Pour une présentation en direct, écrivez-nous.",
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
        a: "Avec la formule Agence, vous payez par agent (2 agents minimum). Après le paiement, invitez vos agents par email depuis la page Équipe : chacun a son propre accès. Vous ajoutez des agents à tout moment, au prorata ; le nombre d'agents peut être réduit à la fin de l'engagement.",
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
                ? <GlowButton disabled className="mt-8 w-full">Abonnement actif</GlowButton>
                : <GlowButton onClick={() => startSubscription(plan)} className="mt-8 w-full">Démarrer maintenant</GlowButton>,
            highlighted: true,
        },
        {
            id: 'agence',
            name: 'Agence',
            tagline: 'Pour équiper une équipe de 2 à 50 agents.',
            price: billing === 'monthly' ? '59 €' : '590 €',
            unit: `par agent, ${per} · TTC`,
            note: '2 agents minimum · engagement 12 mois',
            cta: me?.is_pro
                ? <GlowButton variant="ghost" disabled className="mt-8 w-full">Abonnement actif</GlowButton>
                : <GlowButton variant="ghost" onClick={() => setAgencyOpen(true)} className="mt-8 w-full">Équiper mon agence</GlowButton>,
            highlighted: false,
        },
        {
            id: 'reseau',
            name: 'Réseau',
            tagline: 'Pour les enseignes et réseaux de plusieurs agences.',
            price: 'Sur devis',
            unit: 'à partir de 39 € par agent et par mois · TTC',
            note: 'engagement 12 mois',
            cta: <GlowButton variant="ghost" onClick={() => setQuote('reseau')} className="mt-8 w-full">Demander un devis</GlowButton>,
            highlighted: false,
        },
    ];
    const extras: Record<string, string[]> = {
        solo: ['Tout SPREA ; analyse des PV d\'AG dans la limite mensuelle indiquée'],
        agence: ['Tout SPREA pour chaque agent', 'Contacts et alertes partagés dans l\'agence', 'Une facture unique'],
        reseau: ['Console du siège : toutes les agences', 'Courriers et rapports aux couleurs du réseau', 'Accompagnement au démarrage'],
    };

    return (
        <div className="min-h-screen flex flex-col bg-canvas overflow-x-clip">
            <SiteHeader />
            <main className="flex-1">
            <section className="relative overflow-hidden">
                <Backdrop />
                <div className="relative text-center max-w-2xl mx-auto px-4 sm:px-6 pt-12 sm:pt-16 pb-10">
                    <Eyebrow>Tarifs · tous les outils inclus</Eyebrow>
                    <h1 className="mt-5 text-[2.1rem] sm:text-5xl text-ink leading-[1.08]">Un mandat signé rembourse <span className="text-brass-light [text-shadow:0_0_40px_rgba(201,164,92,0.45)]">des années d'abonnement</span></h1>
                    <p className="mt-5 text-[15px] sm:text-base text-ink-soft/90">Réservé aux professionnels de l'immobilier. Tous les outils sont inclus dans chaque formule.</p>
                    <div role="radiogroup" aria-label="Facturation" className="mt-8 inline-flex rounded-full border border-white/15 bg-panel/70 p-1 backdrop-blur">
                        {([['monthly', 'Mensuel'], ['yearly', 'Annuel −2 mois']] as [Billing, string][]).map(([v, l]) => (
                            <button key={v} type="button" role="radio" aria-checked={billing === v} onClick={() => setBilling(v)}
                                className={`rounded-full px-5 h-10 text-sm font-semibold transition-all ${billing === v ? 'bg-gradient-to-br from-brass-light via-brass to-brass-dark text-canvas shadow-[0_0_24px_-4px_rgba(201,164,92,0.7)]' : 'text-muted hover:text-ink'}`}>{l}</button>
                        ))}
                    </div>
                </div>
            </section>

            <div className="max-w-6xl mx-auto px-4 sm:px-6 pb-16">
            <section className="grid grid-cols-1 md:grid-cols-3 gap-5 items-stretch">
                {offers.map((o, i) => (
                    <Reveal key={o.id} delay={i * 0.08} className="h-full">
                    <TiltCard className="h-full rounded-3xl">
                    <div className={`relative h-full overflow-hidden rounded-3xl p-7 flex flex-col border ${o.highlighted ? 'border-brass/50 bg-gradient-to-br from-panel via-panel to-[#1a1608] shadow-[0_30px_90px_-30px_rgba(201,164,92,0.5)]' : 'border-white/10 bg-panel/60'}`}>
                        {o.highlighted && <div aria-hidden="true" className="absolute -top-20 -right-20 h-56 w-56 rounded-full bg-brass/20 blur-[70px]" />}
                        <div className="relative flex items-center justify-between">
                            <h2 className="font-sans text-xs font-semibold tracking-[0.2em] uppercase text-brass">{o.name}</h2>
                            {o.highlighted && <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-brass text-canvas font-semibold">Démarrage immédiat</span>}
                        </div>
                        <p className="relative mt-5 font-serif text-[2.6rem] leading-none text-ink">{o.price}</p>
                        <p className="relative text-sm mt-2 text-faint">{o.unit}</p>
                        <p className="relative text-xs mt-1 text-sage">{o.note}</p>
                        <p className="relative mt-4 text-sm text-muted">{o.tagline}</p>
                        <ul className="relative mt-6 space-y-3 flex-1">
                            {extras[o.id].map(f => (
                                <li key={f} className="flex items-start gap-3 text-sm text-ink">
                                    <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brass/10 ring-1 ring-brass/30"><Check size={12} className="text-brass-light" /></span><span>{f}</span>
                                </li>
                            ))}
                        </ul>
                        <div className="relative">{o.cta}</div>
                    </div>
                    </TiltCard>
                    </Reveal>
                ))}
            </section>

            <p className="mt-6 text-center text-sm text-muted flex items-center justify-center gap-2">
                <ShieldCheck size={16} className="text-sage" /> Engagement 12 mois · Paiement sécurisé par Stripe · Facture avec TVA
            </p>

            <Reveal>
            <section className="mt-14 rounded-3xl border border-white/10 bg-panel/60 p-7 sm:p-9">
                <p className="text-xs sm:text-sm text-brass tracking-[0.2em] uppercase">Tout est inclus</p>
                <h2 className="mt-2 text-2xl sm:text-3xl text-ink">Dans toutes les formules</h2>
                <ul className="mt-6 grid sm:grid-cols-2 gap-x-8 gap-y-3">
                    {INCLUDED.map(f => (
                        <li key={f} className="flex items-start gap-3 text-sm text-ink-soft">
                            <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brass/10 ring-1 ring-brass/30"><Check size={12} className="text-brass-light" /></span><span>{f}</span>
                        </li>
                    ))}
                </ul>
                <p className="mt-6 text-sm text-muted">Pas encore convaincu ? <Link to="/demo" className="text-brass-light underline">Voyez SPREA en action</Link>.</p>
            </section>
            </Reveal>

            <section className="max-w-3xl mx-auto mt-16">
                <h2 className="text-2xl sm:text-3xl text-ink mb-5">Questions fréquentes</h2>
                <div className="divide-y divide-white/[0.08] rounded-3xl border border-white/10 bg-panel/40">
                {FAQ.map(item => (
                    <details key={item.q} className="group px-5 py-4">
                        <summary className="cursor-pointer list-none flex items-center justify-between gap-4 text-ink">
                            {item.q}
                            <ChevronDown size={18} className="shrink-0 text-faint transition-transform group-open:rotate-180" />
                        </summary>
                        <p className="text-sm text-muted mt-3 leading-relaxed">{item.a}</p>
                    </details>
                ))}
                </div>
            </section>
            </div>
            </main>

            {quote && <QuoteDialog offer={quote} onClose={() => setQuote(null)} />}
            {agencyOpen && (
                <AgencyDialog billing={billing} onClose={() => setAgencyOpen(false)} onQuote={() => { setAgencyOpen(false); setQuote('agence'); }}
                    onConfirm={order => { setAgencyOpen(false); startSubscription(billing === 'monthly' ? 'agence_monthly' : 'agence_yearly', order); }} />
            )}
            <SiteFooter />
        </div>
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
            if (!res.ok) {
                throw new Error(await errorDetail(res, "L'envoi a échoué.",
                    'Vérifiez les informations saisies : nom et société (2 caractères minimum), email et téléphone.'));
            }
            setStatus('sent');
        } catch (err) {
            // A network failure (TypeError) has no French message
            setError(err instanceof TypeError ? "L'envoi a échoué. Vérifiez votre connexion et réessayez." : (err as Error).message);
            setStatus('idle');
        }
    };

    return (
        <div className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
            <div className="bg-panel border border-white/10 rounded-3xl shadow-[0_30px_90px_-20px_rgba(0,0,0,0.8)] w-full max-w-lg max-h-[90vh] overflow-y-auto p-6 sm:p-8 relative" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
                <button onClick={onClose} className="absolute top-5 right-5 text-faint hover:text-ink" aria-label="Fermer"><X size={20} /></button>
                <h2 className="text-2xl text-ink pr-8">{offer === 'agence' ? 'Équiper mon agence' : 'Devis réseau'}</h2>
                {status === 'sent' ? (
                    <p className="mt-6 text-ink-soft">Merci, votre demande est bien reçue. Nous revenons vers vous sous 24 heures ouvrées.</p>
                ) : (
                    <form onSubmit={send} className="mt-6 space-y-3">
                        <div className="grid sm:grid-cols-2 gap-3">
                            <input required minLength={2} maxLength={80} placeholder="Nom et prénom" value={form.name} onChange={set('name')} className={FIELD} aria-label="Nom et prénom" />
                            <input required minLength={2} maxLength={120} placeholder={offer === 'agence' ? 'Agence' : 'Réseau'} value={form.company} onChange={set('company')} className={FIELD} aria-label="Société" />
                            <input required type="email" placeholder="Email professionnel" value={form.email} onChange={set('email')} className={FIELD} aria-label="Email" />
                            <input type="tel" maxLength={25} placeholder="Téléphone" value={form.phone} onChange={set('phone')} className={FIELD} aria-label="Téléphone" />
                        </div>
                        <label className="flex items-center gap-3 text-sm text-ink-soft">
                            Nombre d'agents
                            <input type="number" min={1} max={5000} value={form.agents} onChange={set('agents')} className={`${FIELD} w-28`} aria-label="Nombre d'agents" />
                        </label>
                        <textarea maxLength={2000} placeholder="Votre besoin (facultatif)" value={form.message} onChange={set('message')} rows={3}
                            className="w-full px-3 py-2 rounded-xl bg-raised border border-line text-ink placeholder:text-faint outline-none focus:border-brass/70" aria-label="Message" />
                        {/* Honeypot */}
                        <input tabIndex={-1} autoComplete="off" value={form.website} onChange={set('website')} className="hidden" aria-hidden="true" />
                        {error && <p className="text-sm text-coral">{error}</p>}
                        <GlowButton type="submit" disabled={status === 'sending'} className="w-full">
                            {status === 'sending' && <Loader2 className="animate-spin" size={16} />} Envoyer ma demande
                        </GlowButton>
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
            <div className="bg-panel border border-white/10 rounded-3xl shadow-[0_30px_90px_-20px_rgba(0,0,0,0.8)] w-full max-w-md p-6 sm:p-8 relative" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
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
                    <GlowButton type="submit" disabled={!valid} className="w-full">Continuer</GlowButton>
                    <p className="text-xs text-faint">Plus de 50 agents, ou besoin d'un bon de commande ? <button type="button" onClick={onQuote} className="underline text-brass">Demandez un devis</button>.</p>
                </form>
            </div>
        </div>
    );
}
