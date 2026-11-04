import { useEffect, useRef, useState, type ReactNode } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import {
    ArrowLeft, ArrowRight, Building2, Check, CheckCircle2, ChevronDown, Crown, FileText, Flame, Gauge, Hammer,
    Home as HomeIcon, Loader2, Lock, MapPin, Phone, Radar, ShieldCheck, Sparkles, Target, Users, Wind, X,
} from 'lucide-react';
import { SiteFooter, SiteHeader } from './site';
import { useSeo } from '../seo';
import { Counter, GlowButton, KineticLine, Reveal, RotatingWord, TiltCard } from '../views/home/fx';

// Landing page for building firms (TCE / RGE): the worksite dossiers SPREA prepares, sold as a free
// trial, a 3-dossier pack or an exclusive zone. The order funnel posts to /api/chantiers/demande.
// How the worksites are found stays out of the page: the method is SPREA's edge.

type Offer = 'essai' | 'pack' | 'zone';

const OFFERS: { id: Offer; name: string; price: string; unit: string; tag?: string; points: string[]; cta: string }[] = [
    {
        id: 'essai', name: "Dossier d'essai", price: 'Gratuit', unit: '1 dossier',
        points: ['Un chantier près de votre entreprise', 'Le dossier PDF complet', 'Sans engagement, sans carte bancaire'],
        cta: 'Recevoir mon dossier gratuit',
    },
    {
        id: 'pack', name: 'Pack Découverte', price: '99 €', unit: 'HT · 3 dossiers', tag: 'Le plus choisi',
        points: ['3 chantiers choisis dans votre zone', 'Sélectionnés selon votre métier', 'Exclusifs : proposés à vous seul', 'Paiement unique, sans abonnement'],
        cta: 'Commander le Pack',
    },
    {
        id: 'zone', name: 'Zone exclusive', price: '349 €', unit: 'HT · par mois',
        points: ['Tous les chantiers de votre zone, à vous seul', 'Les nouvelles opportunités chaque semaine', "Jusqu'à 10 communes au choix", 'Sans engagement après 3 mois'],
        cta: 'Réserver ma zone',
    },
];

const TRADES: { label: string; icon: typeof Hammer }[] = [
    { label: 'Isolation', icon: HomeIcon }, { label: 'Menuiseries', icon: Building2 },
    { label: 'Chauffage / PAC', icon: Flame }, { label: 'Ventilation', icon: Wind },
    { label: 'Rénovation globale', icon: Hammer }, { label: 'Autre', icon: Sparkles },
];

const FAQ = [
    {
        q: 'Comment trouver des chantiers quand on est artisan du bâtiment ?',
        a: "Les plateformes de mise en relation revendent la même demande de devis à plusieurs entreprises, qui se battent ensuite sur le prix. SPREA prend le problème à l'envers : nous repérons les propriétaires qui vont devoir rénover, et vous donnons le dossier chiffré pour les contacter les premiers.",
    },
    {
        q: 'Comment repérez-vous ces chantiers ?',
        a: "Grâce à notre moteur d'analyse du parc immobilier, développé avec une expertise technique du bâtiment : il croise performance énergétique, réglementation et profil du propriétaire pour isoler les biens où des travaux deviennent inévitables. Chaque dossier distingue ce qui est mesuré de ce qui est estimé.",
    },
    {
        q: 'Le propriétaire a-t-il demandé des travaux ?',
        a: "Non, et c'est tout l'intérêt : vous arrivez avant la mise en concurrence. Le dossier montre pourquoi il doit agir (logements G interdits à la location depuis 2025, F en 2028, loyers gelés) et chiffre le chantier. Nous ne contactons jamais les propriétaires : le contact est à vous.",
    },
    {
        q: "Mon métier est-il concerné si je ne fais pas tous corps d'état ?",
        a: "Oui. Une passoire thermique, c'est souvent une isolation, des menuiseries, un chauffage ou une ventilation à refaire. Nous choisissons les chantiers selon votre métier : un chauffagiste ne reçoit pas un dossier de façade.",
    },
    {
        q: 'Les dossiers sont-ils exclusifs ?',
        a: "Avec le Pack Découverte et la Zone exclusive, oui : un dossier acheté n'est proposé à aucune autre entreprise. C'est la grande différence avec une demande de devis partagée.",
    },
    {
        q: 'Pourquoi le statut RGE compte ?',
        a: "Les primes CEE ne sont versées que pour des travaux réalisés par une entreprise RGE, y compris quand le propriétaire est une société. Le dossier met cet argument en avant face au propriétaire.",
    },
];

export default function ChantiersPage() {
    useSeo({
        title: 'Trouver des chantiers de rénovation énergétique : dossiers exclusifs pour artisans RGE | SPREA',
        description: "Des chantiers de rénovation repérés avant vos concurrents, près de votre entreprise, avec le dossier chiffré et le contact du maître d'ouvrage. 1 dossier d'essai gratuit, Pack Découverte 99 € HT.",
        path: '/trouver-des-chantiers',
    });
    const [offer, setOffer] = useState<Offer>('essai');
    const funnel = useRef<HTMLElement>(null);
    const order = (o: Offer) => {
        setOffer(o);
        funnel.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    return (
        <div className="min-h-screen flex flex-col bg-canvas text-ink overflow-x-clip">
            <SiteHeader />
            <main className="flex-1">
                <Hero onStart={() => order('essai')} />
                <Trades />
                <Figures />
                <Compare />
                <Steps />
                <Contents />
                <Roi onStart={() => order('pack')} />
                <Offers onPick={order} />
                <section ref={funnel} id="commande" className="scroll-mt-20">
                    <Funnel offer={offer} setOffer={setOffer} />
                </section>
                <Faq />
                <FinalCta onStart={() => order('essai')} />
            </main>
            <SiteFooter />
            <StickyCta onStart={() => order('essai')} />
        </div>
    );
}

function Kicker({ children }: { children: ReactNode }) {
    return <p className="text-xs sm:text-sm text-brass tracking-[0.2em] uppercase">{children}</p>;
}

// --- Hero ---

function Hero({ onStart }: { onStart: () => void }) {
    return (
        <section className="relative overflow-hidden">
            <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(ellipse_45%_55%_at_75%_45%,rgba(40,120,255,0.20),transparent_70%),radial-gradient(ellipse_60%_50%_at_12%_25%,rgba(201,164,92,0.12),transparent_70%)]" />
            <div aria-hidden="true" className="absolute inset-0 opacity-[0.07] bg-[linear-gradient(rgba(255,255,255,0.6)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.6)_1px,transparent_1px)] bg-[size:72px_72px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
            <div className="relative max-w-7xl mx-auto px-4 sm:px-6 pt-12 pb-16 lg:pt-20 lg:pb-24 grid gap-12 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] items-center">
                <div>
                    <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
                        className="inline-flex items-center gap-2 rounded-full border border-brass/30 bg-brass/[0.06] px-4 py-1.5 text-xs sm:text-sm text-brass-light tracking-wide backdrop-blur">
                        <span className="h-1.5 w-1.5 rounded-full bg-brass-light animate-pulse" /> Pour les entreprises du bâtiment · RGE
                    </motion.p>
                    <h1 className="mt-5 text-[2.1rem] leading-[1.08] sm:text-5xl xl:text-[3.6rem] text-ink [perspective:800px]">
                        <span className="block"><KineticLine text="Vos prochains chantiers," delay={0.15} /></span>
                        <span className="block mt-2 text-brass-light [text-shadow:0_0_40px_rgba(201,164,92,0.45)]">
                            <KineticLine text="repérés avant" delay={0.55} />
                        </span>
                        <span className="block mt-1 text-brass-light [text-shadow:0_0_40px_rgba(201,164,92,0.45)]">
                            <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.95, duration: 0.5 }}>
                                {'les '}<RotatingWord words={['concurrents.', 'plateformes.', 'autres.']} />
                            </motion.span>
                        </span>
                    </h1>
                    <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.1, duration: 0.7 }}
                        className="mt-6 max-w-xl text-[15px] sm:text-base text-ink-soft/90 leading-relaxed">
                        Des propriétaires qui vont devoir rénover, près de chez vous, repérés par notre moteur d'analyse.
                        Pour chacun : le chantier chiffré poste par poste et le contact du décideur.
                        Pas une demande de devis revendue à cinq entreprises : <span className="text-ink">un chantier à vous.</span>
                    </motion.p>
                    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.3, duration: 0.7 }}
                        className="mt-8 flex flex-col sm:flex-row gap-3">
                        <GlowButton onClick={onStart}>Recevoir un dossier gratuit <ArrowRight size={18} /></GlowButton>
                        <GlowButton variant="ghost" onClick={() => document.getElementById('offres')?.scrollIntoView({ behavior: 'smooth' })}>
                            Voir les offres
                        </GlowButton>
                    </motion.div>
                    <motion.ul initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.6 }}
                        className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-xs text-faint">
                        {['Sans carte bancaire', 'Réponse sous 24 h ouvrées', 'Toute la France'].map(t => (
                            <li key={t} className="flex items-center gap-1.5"><Check size={14} className="text-sage" />{t}</li>
                        ))}
                    </motion.ul>
                </div>
                <motion.div initial={{ opacity: 0, y: 40, rotate: 2 }} animate={{ opacity: 1, y: 0, rotate: 0 }} transition={{ delay: 0.5, duration: 1, ease: [0.2, 0.8, 0.2, 1] }}>
                    <DossierPreview />
                </motion.div>
            </div>
        </section>
    );
}

// A worksite dossier as the firm receives it. Illustrative: no real address or owner.
const PREVIEW_UNITS = [
    { label: 'G', n: 3, color: 'bg-[#D7263D]' },
    { label: 'F', n: 2, color: 'bg-[#F46036]' },
    { label: 'E', n: 1, color: 'bg-[#F2A541]' },
];
const PREVIEW_WORKS = [
    ["Isolation des murs par l'extérieur", 'Façadier · ITE', 46],
    ['Remplacement des menuiseries', 'Menuisier', 24],
    ['Pompe à chaleur air / eau', 'Chauffagiste', 21],
    ['VMC hygroréglable', 'Ventilation', 9],
] as const;

function DossierPreview() {
    const reduce = useReducedMotion();
    return (
        <TiltCard className="rounded-[28px]">
            <div className="relative rounded-[28px] border border-white/10 bg-gradient-to-br from-panel via-panel to-canvas p-5 sm:p-7 shadow-[0_40px_120px_-30px_rgba(0,0,0,0.9),0_0_0_1px_rgba(227,201,143,0.06)]">
                <div aria-hidden="true" className="absolute -top-24 -right-16 h-64 w-64 rounded-full bg-brass/15 blur-[90px]" />
                <div className="relative flex items-start justify-between gap-3">
                    <div>
                        <p className="text-[11px] tracking-[0.2em] uppercase text-brass">Dossier chantier</p>
                        <p className="mt-1.5 font-serif text-xl sm:text-2xl text-ink">Immeuble de 6 logements</p>
                        <p className="mt-1 text-sm text-muted flex items-center gap-1.5"><MapPin size={14} className="text-brass" />À 4 km de votre entreprise · 390 m²</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-coral/40 bg-coral/10 px-3 py-1 text-xs font-semibold text-coral">Classé G</span>
                </div>

                <div className="relative mt-6">
                    <p className="text-xs text-faint">Performance des logements</p>
                    <div className="mt-2 flex h-3 overflow-hidden rounded-full bg-raised gap-[2px]">
                        {PREVIEW_UNITS.map((u, i) => (
                            <motion.div key={u.label} className={`${u.color} h-full`}
                                initial={reduce ? false : { width: 0 }} animate={{ width: `${(u.n / 6) * 100}%` }}
                                transition={{ delay: 1.1 + i * 0.15, duration: 0.8, ease: [0.2, 0.8, 0.2, 1] }} />
                        ))}
                    </div>
                    <div className="mt-2 flex gap-4 text-xs text-muted">
                        {PREVIEW_UNITS.map(u => <span key={u.label}><span className="text-ink font-semibold">{u.n}</span> classé{u.n > 1 ? 's' : ''} {u.label}</span>)}
                    </div>
                </div>

                <div className="relative mt-6 space-y-2.5">
                    {PREVIEW_WORKS.map(([name, trade, share], i) => (
                        <motion.div key={name} initial={reduce ? false : { opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 1.4 + i * 0.12, duration: 0.6 }}
                            className="rounded-xl border border-white/[0.06] bg-raised/60 px-3.5 py-2.5">
                            <div className="flex items-center justify-between gap-3 text-sm">
                                <span className="text-ink truncate">{name}</span>
                                <span className="shrink-0 text-xs text-faint">{trade}</span>
                            </div>
                            <div className="mt-2 h-1 rounded-full bg-white/[0.05] overflow-hidden">
                                <motion.div className="h-full rounded-full bg-gradient-to-r from-brass-dark to-brass-light"
                                    initial={reduce ? false : { width: 0 }} animate={{ width: `${share * 2}%` }}
                                    transition={{ delay: 1.6 + i * 0.12, duration: 0.9 }} />
                            </div>
                        </motion.div>
                    ))}
                </div>

                <div className="relative mt-6 grid grid-cols-2 gap-3">
                    <div className="rounded-2xl border border-brass/25 bg-brass/[0.06] p-3.5">
                        <p className="text-[11px] text-faint">Budget travaux estimé</p>
                        <p className="mt-1 font-serif text-lg sm:text-xl text-brass-light">135 – 175 k€</p>
                    </div>
                    <div className="rounded-2xl border border-white/[0.08] bg-raised/60 p-3.5">
                        <p className="text-[11px] text-faint">Décideur</p>
                        <p className="mt-1 text-sm text-ink flex items-center gap-1.5"><Lock size={13} className="text-brass shrink-0" />Société · dirigeant</p>
                    </div>
                </div>
                <p className="relative mt-4 text-[11px] text-faint">Aperçu illustratif. Le vrai dossier : un PDF de deux pages, chiffré logement par logement.</p>
            </div>
        </TiltCard>
    );
}

// --- Trades band ---

function Trades() {
    const reduce = useReducedMotion();
    const items = ['Isolation thermique', "Isolation par l'extérieur", 'Menuiseries', 'Pompe à chaleur', 'Chaudière', 'Ventilation', 'Toiture', 'Rénovation globale', 'Électricité', 'Plâtrerie'];
    return (
        <div className="border-y border-white/[0.06] bg-panel/40 py-4 [mask-image:linear-gradient(90deg,transparent,black_8%,black_92%,transparent)] overflow-hidden">
            <div className={`flex w-max gap-10 pr-10 ${reduce ? '' : 'animate-[daymarquee_40s_linear_infinite]'}`}>
                {[...items, ...items].map((t, i) => (
                    <span key={i} aria-hidden={i >= items.length} className="flex items-center gap-3 text-sm text-muted whitespace-nowrap">
                        <span className="h-1 w-1 rounded-full bg-brass" />{t}
                    </span>
                ))}
            </div>
        </div>
    );
}

// --- Figures: the stock of the database and the law, no conversion claim ---

function Figures() {
    const items = [
        { node: <Counter to={2600} suffix="+" />, label: 'maisons et immeubles à rénover déjà repérés par notre moteur' },
        { node: <>2025 · <span className="text-brass-light">2028</span></>, label: 'logements G interdits à la location, puis F : les propriétaires doivent agir' },
        { node: <Counter to={1} />, label: 'seul décideur par chantier : pas de syndic, pas de copropriété' },
        { node: <Counter to={2} suffix=" pages" />, label: 'un dossier clair, prêt à joindre à votre courrier' },
    ];
    return (
        <section className="max-w-7xl mx-auto px-4 sm:px-6 py-12 sm:py-14 grid gap-8 grid-cols-2 lg:grid-cols-4">
            {items.map((it, i) => (
                <Reveal key={i} delay={i * 0.08}>
                    <p className="font-serif text-2xl sm:text-[2rem] text-ink tabular-nums">{it.node}</p>
                    <p className="mt-2 text-[13px] text-muted leading-relaxed max-w-[16rem]">{it.label}</p>
                </Reveal>
            ))}
        </section>
    );
}

// --- Shared quote requests vs a SPREA dossier ---

function Compare() {
    const rows: [string, string, string][] = [
        ['Qui reçoit le contact', "Plusieurs entreprises", 'Vous seul'],
        ['Quand vous arrivez', 'Après la mise en concurrence', 'Avant toute consultation'],
        ['Ce que vous savez', 'Un formulaire de trois lignes', 'Le chantier chiffré poste par poste'],
        ['Le décideur', 'Un particulier qui compare les prix', 'Une société qui doit agir'],
        ['Ce que vous payez', 'Chaque contact, même perdu', 'Un dossier, à vous pour de bon'],
    ];
    return (
        <section className="max-w-6xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
            <Reveal>
                <Kicker>Le problème des plateformes</Kicker>
                <h2 className="mt-3 text-2xl sm:text-4xl max-w-3xl leading-tight">Arrêtez d'acheter des contacts que d'autres entreprises ont aussi.</h2>
            </Reveal>
            <Reveal delay={0.1}>
                <div className="mt-10 rounded-3xl border border-white/10 bg-panel/60 overflow-hidden">
                    <div className="grid grid-cols-[1fr_1fr_1fr] sm:grid-cols-[1.1fr_1fr_1fr] text-xs sm:text-sm">
                        <div className="p-3 sm:p-5" />
                        <div className="p-3 sm:p-5 text-muted flex items-center gap-2"><Users size={16} className="hidden sm:block" />Demande de devis partagée</div>
                        <div className="p-3 sm:p-5 text-brass-light font-semibold flex items-center gap-2 bg-brass/[0.07] border-l border-brass/25"><Crown size={16} className="hidden sm:block" />Dossier SPREA</div>
                        {rows.map(([k, a, b]) => (
                            <div key={k} className="contents">
                                <div className="px-3 sm:px-5 py-3.5 border-t border-white/[0.06] text-ink-soft">{k}</div>
                                <div className="px-3 sm:px-5 py-3.5 border-t border-white/[0.06] text-muted flex gap-2"><X size={16} className="text-coral shrink-0 mt-0.5 hidden sm:block" />{a}</div>
                                <div className="px-3 sm:px-5 py-3.5 border-t border-brass/15 bg-brass/[0.07] border-l border-l-brass/25 text-ink flex gap-2"><Check size={16} className="text-sage shrink-0 mt-0.5 hidden sm:block" />{b}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </Reveal>
        </section>
    );
}

// --- How it works (no method detail) ---

function Steps() {
    const steps = [
        { icon: Radar, title: 'Nous repérons le chantier', text: "Notre moteur d'analyse passe au crible le parc immobilier autour de votre entreprise et isole les biens où la rénovation devient inévitable." },
        { icon: FileText, title: 'Nous préparons le dossier', text: "Le chantier chiffré poste par poste et par corps d'état, la situation réglementaire du bien et le maître d'ouvrage. Deux pages, prêtes à joindre à votre courrier." },
        { icon: Target, title: 'Vous signez le chantier', text: "Vous contactez le propriétaire avec un dossier solide, avant qu'il ne lance une consultation. Un seul décideur, pas d'assemblée générale." },
    ];
    return (
        <section className="relative border-y border-white/[0.06] bg-gradient-to-b from-panel/50 to-canvas">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
                <Reveal>
                    <Kicker>Comment ça marche</Kicker>
                    <h2 className="mt-3 text-2xl sm:text-4xl max-w-2xl leading-tight">Du chantier repéré au chantier signé.</h2>
                </Reveal>
                <div className="relative mt-12 grid gap-10 md:gap-6 md:grid-cols-3">
                    <div aria-hidden="true" className="hidden md:block absolute top-6 left-[16%] right-[16%] h-px bg-gradient-to-r from-transparent via-brass/50 to-transparent" />
                    {steps.map((s, i) => (
                        <Reveal key={s.title} delay={i * 0.12}>
                            <div className="relative text-center md:px-4">
                                <span className="relative mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-canvas text-brass-light ring-1 ring-brass/40 shadow-[0_0_30px_rgba(201,164,92,0.35)]">
                                    <s.icon size={21} />
                                    <span className="absolute -top-2 -right-2 h-5 w-5 rounded-full bg-brass text-[11px] font-bold text-canvas flex items-center justify-center">{i + 1}</span>
                                </span>
                                <h3 className="mt-5 text-xl">{s.title}</h3>
                                <p className="mt-2 text-sm text-muted leading-relaxed max-w-sm mx-auto">{s.text}</p>
                            </div>
                        </Reveal>
                    ))}
                </div>
            </div>
        </section>
    );
}

function Contents() {
    const items: [typeof Building2, string, string][] = [
        [Building2, 'Le chantier, poste par poste', "Isolation, menuiseries, chauffage, ventilation : le constat, le corps d'état concerné et un budget TTC, logement par logement."],
        [Gauge, 'La performance et la loi', "La classe énergétique de chaque logement, ce qui est mesuré et ce qui est estimé, et les interdictions de louer qui pèsent sur le propriétaire."],
        [ShieldCheck, 'Vos arguments de vente', "La décote du bien et sa valeur après travaux quand le marché le justifie, les primes CEE réservées aux entreprises RGE, l'urgence du calendrier."],
        [Lock, "Le maître d'ouvrage", "La société propriétaire, son siège et son dirigeant, ses autres biens, et la meilleure façon de la contacter."],
    ];
    return (
        <section className="max-w-7xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
            <Reveal>
                <Kicker>Dans chaque dossier</Kicker>
                <h2 className="mt-3 text-2xl sm:text-4xl max-w-3xl leading-tight">Tout ce qu'il faut pour décrocher le rendez-vous.</h2>
            </Reveal>
            <div className="mt-10 grid gap-4 sm:grid-cols-2">
                {items.map(([Icon, title, text], i) => (
                    <Reveal key={title} delay={i * 0.08}>
                        <TiltCard className="h-full rounded-3xl">
                            <div className="group h-full rounded-3xl border border-white/10 bg-panel/60 p-6 transition-colors hover:border-brass/40">
                                <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-brass/10 text-brass-light ring-1 ring-brass/30 group-hover:shadow-[0_0_30px_rgba(201,164,92,0.45)] transition-shadow">
                                    <Icon size={20} />
                                </span>
                                <h3 className="mt-5 text-xl">{title}</h3>
                                <p className="mt-2 text-sm text-muted leading-relaxed">{text}</p>
                            </div>
                        </TiltCard>
                    </Reveal>
                ))}
            </div>
        </section>
    );
}

// --- Return on investment: the firm's own figures, no signing rate assumed ---

function Roi({ onStart }: { onStart: () => void }) {
    const [amount, setAmount] = useState(30000);
    const [margin, setMargin] = useState(20);
    const gross = Math.round((amount * margin) / 100);
    const times = Math.floor(gross / 99);
    const eur = (v: number) => v.toLocaleString('fr-FR') + ' €';
    return (
        <section className="relative overflow-hidden border-y border-white/[0.06] bg-[#050913]">
            <div aria-hidden="true" className="absolute right-0 top-1/2 -translate-y-1/2 h-[480px] w-[480px] rounded-full bg-[rgba(40,120,255,0.12)] blur-[120px]" />
            <div className="relative max-w-6xl mx-auto px-4 sm:px-6 py-16 sm:py-20 grid gap-10 lg:grid-cols-2 items-center">
                <Reveal>
                    <Kicker>Faites le calcul</Kicker>
                    <h2 className="mt-3 text-2xl sm:text-4xl leading-tight">Un seul chantier signé rembourse le pack, et bien plus.</h2>
                    <p className="mt-4 text-sm sm:text-[15px] text-muted leading-relaxed max-w-lg">
                        Indiquez le montant moyen de vos chantiers et votre marge. Le calcul est le vôtre : nous ne promettons pas de taux de signature,
                        nous vous donnons le dossier qui vous fait passer devant.
                    </p>
                    <div className="mt-8 space-y-6 max-w-lg">
                        <Slider label="Montant moyen d'un chantier" value={eur(amount)} min={5000} max={150000} step={1000} v={amount} set={setAmount} />
                        <Slider label="Votre marge" value={`${margin} %`} min={5} max={40} step={1} v={margin} set={setMargin} />
                    </div>
                </Reveal>
                <Reveal delay={0.1}>
                    <div className="rounded-3xl border border-brass/30 bg-gradient-to-b from-brass/[0.10] to-panel p-7 sm:p-9 text-center shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)]">
                        <p className="text-sm text-muted">Marge sur un seul chantier signé</p>
                        <p className="mt-2 font-serif text-5xl sm:text-6xl text-brass-light tabular-nums [text-shadow:0_0_40px_rgba(201,164,92,0.4)]">{eur(gross)}</p>
                        <div className="mt-6 h-px bg-gradient-to-r from-transparent via-brass/40 to-transparent" />
                        <p className="mt-6 text-ink-soft">
                            soit <span className="font-serif text-3xl text-ink tabular-nums">{times}</span> fois le prix du Pack Découverte (99 € HT)
                        </p>
                        <GlowButton className="mt-8" onClick={onStart}>Commander le Pack <ArrowRight size={18} /></GlowButton>
                    </div>
                </Reveal>
            </div>
        </section>
    );
}

function Slider({ label, value, min, max, step, v, set }: { label: string; value: string; min: number; max: number; step: number; v: number; set: (n: number) => void }) {
    const pct = ((v - min) / (max - min)) * 100;
    return (
        <label className="block">
            <span className="flex justify-between text-sm"><span className="text-ink-soft">{label}</span><span className="text-brass-light font-semibold tabular-nums">{value}</span></span>
            <input type="range" min={min} max={max} step={step} value={v} onChange={e => set(Number(e.target.value))}
                className="mt-3 w-full h-1.5 cursor-pointer appearance-none rounded-full accent-[#C9A45C]"
                style={{ background: `linear-gradient(90deg,#C9A45C ${pct}%,#25324C ${pct}%)` }} />
        </label>
    );
}

// --- Offers ---

function Offers({ onPick }: { onPick: (o: Offer) => void }) {
    return (
        <section id="offres" className="scroll-mt-20 max-w-6xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
            <Reveal>
                <div className="text-center">
                    <Kicker>Les offres</Kicker>
                    <h2 className="mt-3 text-2xl sm:text-4xl leading-tight">Commencez gratuitement. Jugez sur pièce.</h2>
                </div>
            </Reveal>
            <div className="mt-12 grid gap-5 md:grid-cols-3 items-stretch">
                {OFFERS.map((o, i) => (
                    <Reveal key={o.id} delay={i * 0.08} className="h-full">
                        <TiltCard className="h-full rounded-3xl">
                            <div className={`relative h-full flex flex-col rounded-3xl border p-7 ${o.tag
                                ? 'border-brass/60 bg-gradient-to-b from-brass/[0.12] to-panel shadow-[0_0_60px_-15px_rgba(201,164,92,0.45)]'
                                : 'border-white/10 bg-panel/60'}`}>
                                {o.tag && <span className="absolute -top-3 left-7 rounded-full bg-gradient-to-r from-brass-light to-brass px-3 py-0.5 text-xs font-semibold text-canvas">{o.tag}</span>}
                                <h3 className="text-lg">{o.name}</h3>
                                <p className="mt-4 font-serif text-5xl text-ink">{o.price}</p>
                                <p className="mt-1 text-xs text-muted">{o.unit}</p>
                                <ul className="mt-6 space-y-2.5 flex-1">
                                    {o.points.map(p => <li key={p} className="flex gap-2 text-sm text-ink-soft"><Check size={16} className="text-sage shrink-0 mt-0.5" />{p}</li>)}
                                </ul>
                                <GlowButton variant={o.tag ? 'primary' : 'ghost'} className="mt-8 w-full" onClick={() => onPick(o.id)}>{o.cta} <ArrowRight size={16} /></GlowButton>
                            </div>
                        </TiltCard>
                    </Reveal>
                ))}
            </div>
            <p className="mt-6 text-center text-xs text-faint">Prix hors taxes. Dossiers indicatifs : ni expertise, ni audit énergétique, ni devis.</p>
        </section>
    );
}

// --- The order funnel: trade, zone, offer, contact ---

type Place = { label: string; insee: string };

function Funnel({ offer, setOffer }: { offer: Offer; setOffer: (o: Offer) => void }) {
    const [step, setStep] = useState(0);
    const [trades, setTrades] = useState<string[]>([]);
    const [place, setPlace] = useState<Place | null>(null);
    const [radius, setRadius] = useState(20);
    const [form, setForm] = useState({ first_name: '', last_name: '', company: '', siret: '', email: '', phone: '', website: '' });
    const [consent, setConsent] = useState(false);
    const [state, setState] = useState<'idle' | 'sending' | 'done'>('idle');
    const [error, setError] = useState('');
    const steps = ['Votre métier', 'Votre zone', 'Votre formule', 'Vos coordonnées'];
    const ok = [trades.length > 0, !!place, true,
        !!(form.first_name.trim() && form.last_name.trim() && form.company.trim().length >= 2 && /\S+@\S+\.\S+/.test(form.email)
            && form.phone.replace(/\D/g, '').length >= 10 && consent)];
    const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }));
    const submit = async () => {
        if (!place) return;
        setState('sending'); setError('');
        try {
            const res = await fetch('/api/chantiers/demande', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ offer, trades, city: place.label, insee: place.insee, radius, ...form, siret: form.siret || null }),
            });
            if (!res.ok) {
                const d = await res.json().catch(() => ({}));
                throw new Error(res.status === 429 ? 'Trop de demandes depuis cette connexion. Réessayez dans une heure ou écrivez à contact@sprea.app.'
                    : typeof d.detail === 'string' ? d.detail : 'Vérifiez les champs du formulaire.');
            }
            setState('done');
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Envoi impossible.');
            setState('idle');
        }
    };
    const chosen = OFFERS.find(o => o.id === offer)!;
    const card = (on: boolean) => on
        ? 'border-brass/70 bg-brass/[0.10] shadow-[0_0_30px_-8px_rgba(201,164,92,0.6)]'
        : 'border-white/10 bg-raised/50 hover:border-white/25';
    return (
        <div className="relative overflow-hidden py-16 sm:py-20">
            <div aria-hidden="true" className="absolute left-1/2 top-1/3 -translate-x-1/2 h-[420px] w-[620px] max-w-full rounded-full bg-brass/10 blur-[130px]" />
            <div className="relative max-w-3xl mx-auto px-4 sm:px-6">
                <Reveal>
                    <div className="text-center">
                        <Kicker>Votre commande</Kicker>
                        <h2 className="mt-3 text-2xl sm:text-4xl leading-tight">Vos chantiers en 4 étapes, en moins d'une minute.</h2>
                    </div>
                </Reveal>
                <div className="mt-10 rounded-[28px] border border-white/10 bg-panel/80 backdrop-blur p-5 sm:p-8 shadow-[0_40px_120px_-30px_rgba(0,0,0,0.9)]">
                    {state === 'done' ? (
                        <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="text-center py-8">
                            <CheckCircle2 size={56} className="mx-auto text-sage" />
                            <h3 className="mt-5 text-2xl">Demande reçue, merci {form.first_name.trim()} !</h3>
                            <p className="mt-3 text-muted max-w-md mx-auto leading-relaxed">
                                {offer === 'essai'
                                    ? 'Nous sélectionnons un chantier près de votre entreprise et vous envoyons le dossier par email sous 24 h ouvrées.'
                                    : 'Nous vous rappelons sous 24 h ouvrées pour valider votre zone et vous envoyer la facture. Vos dossiers suivent dès le règlement.'}
                            </p>
                            <p className="mt-6 text-sm text-faint flex items-center justify-center gap-2"><Phone size={14} />Une question : contact@sprea.app</p>
                        </motion.div>
                    ) : (
                        <>
                            <div className="flex items-center gap-2">
                                {steps.map((s, i) => (
                                    <button key={s} type="button" disabled={!ok.slice(0, i).every(Boolean)} onClick={() => setStep(i)}
                                        className="flex-1 text-left disabled:cursor-not-allowed">
                                        <span className="block h-1.5 rounded-full bg-raised overflow-hidden">
                                            <motion.span className="block h-full bg-gradient-to-r from-brass-dark to-brass-light"
                                                initial={false} animate={{ width: i < step ? '100%' : i === step ? '50%' : '0%' }} transition={{ duration: 0.5 }} />
                                        </span>
                                        <span className={`mt-2 hidden sm:block text-xs ${i === step ? 'text-brass-light' : 'text-faint'}`}>{i + 1}. {s}</span>
                                    </button>
                                ))}
                            </div>
                            <p className="mt-4 sm:hidden text-xs text-brass-light">Étape {step + 1} sur 4 · {steps[step]}</p>
                            <div className="mt-6 min-h-[16rem]">
                                <AnimatePresence mode="wait">
                                    <motion.div key={step} initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -30 }} transition={{ duration: 0.3 }}>
                                        {step === 0 && (
                                            <>
                                                <h3 className="text-xl">Quels travaux réalisez-vous ?</h3>
                                                <p className="mt-1 text-sm text-muted">Plusieurs choix possibles : nous sélectionnons les chantiers selon votre métier.</p>
                                                <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-3">
                                                    {TRADES.map(({ label, icon: Icon }) => {
                                                        const on = trades.includes(label);
                                                        return (
                                                            <button key={label} type="button" aria-pressed={on}
                                                                onClick={() => setTrades(t => on ? t.filter(x => x !== label) : [...t, label])}
                                                                className={`relative rounded-2xl border p-4 text-left transition-all ${card(on)}`}>
                                                                <Icon size={20} className={on ? 'text-brass-light' : 'text-muted'} />
                                                                <span className="mt-3 block text-sm text-ink">{label}</span>
                                                                {on && <Check size={16} className="absolute top-3 right-3 text-brass-light" />}
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                            </>
                                        )}
                                        {step === 1 && (
                                            <>
                                                <h3 className="text-xl">Où intervenez-vous ?</h3>
                                                <p className="mt-1 text-sm text-muted">La commune de votre entreprise et votre rayon d'intervention.</p>
                                                <CityInput place={place} setPlace={setPlace} />
                                                <div className="mt-6">
                                                    <Slider label="Rayon d'intervention" value={`${radius} km`} min={5} max={100} step={5} v={radius} set={setRadius} />
                                                </div>
                                            </>
                                        )}
                                        {step === 2 && (
                                            <>
                                                <h3 className="text-xl">Quelle formule ?</h3>
                                                <p className="mt-1 text-sm text-muted">Vous pourrez passer au Pack ou à la Zone après votre dossier d'essai.</p>
                                                <div className="mt-5 grid gap-3">
                                                    {OFFERS.map(o => (
                                                        <button key={o.id} type="button" onClick={() => setOffer(o.id)} aria-pressed={offer === o.id}
                                                            className={`flex items-center justify-between gap-4 rounded-2xl border p-4 text-left transition-all ${card(offer === o.id)}`}>
                                                            <span className="flex items-center gap-3 min-w-0">
                                                                <span className={`h-5 w-5 shrink-0 rounded-full border-2 flex items-center justify-center ${offer === o.id ? 'border-brass-light' : 'border-white/25'}`}>
                                                                    {offer === o.id && <span className="h-2.5 w-2.5 rounded-full bg-brass-light" />}
                                                                </span>
                                                                <span className="min-w-0">
                                                                    <span className="block text-ink">{o.name}{o.tag && <span className="ml-2 text-[11px] text-brass-light">{o.tag}</span>}</span>
                                                                    <span className="block text-xs text-muted">{o.points[0]}</span>
                                                                </span>
                                                            </span>
                                                            <span className="text-right shrink-0"><span className="block font-serif text-xl">{o.price}</span><span className="block text-[11px] text-faint">{o.unit}</span></span>
                                                        </button>
                                                    ))}
                                                </div>
                                            </>
                                        )}
                                        {step === 3 && (
                                            <>
                                                <h3 className="text-xl">Où vous envoyer {offer === 'essai' ? 'votre dossier' : 'vos dossiers'} ?</h3>
                                                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                                                    <Field label="Prénom" value={form.first_name} onChange={set('first_name')} autoComplete="given-name" />
                                                    <Field label="Nom" value={form.last_name} onChange={set('last_name')} autoComplete="family-name" />
                                                    <Field label="Entreprise" value={form.company} onChange={set('company')} autoComplete="organization" />
                                                    <Field label="SIRET (facultatif)" value={form.siret} onChange={set('siret')} inputMode="numeric" />
                                                    <Field label="Email" type="email" value={form.email} onChange={set('email')} autoComplete="email" />
                                                    <Field label="Téléphone" type="tel" value={form.phone} onChange={set('phone')} autoComplete="tel" />
                                                </div>
                                                <input type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" className="hidden" value={form.website} onChange={set('website')} />
                                                <label className="mt-4 flex gap-3 text-xs text-muted leading-relaxed cursor-pointer">
                                                    <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} className="mt-0.5 accent-[#C9A45C]" />
                                                    J'accepte que SPREA me contacte par email ou par téléphone au sujet de ma demande. Mes coordonnées ne sont ni revendues ni partagées.
                                                </label>
                                                <div className="mt-4 rounded-2xl border border-white/[0.08] bg-raised/50 px-4 py-3 text-sm flex flex-wrap gap-x-4 gap-y-1 text-muted">
                                                    <span><span className="text-ink">{chosen.name}</span> · {chosen.price}{chosen.id !== 'essai' && ' HT'}</span>
                                                    <span>{trades.join(', ')}</span>
                                                    <span>{place?.label}, {radius} km</span>
                                                </div>
                                                {error && <p className="mt-3 text-sm text-coral">{error}</p>}
                                            </>
                                        )}
                                    </motion.div>
                                </AnimatePresence>
                            </div>
                            <div className="mt-8 flex items-center justify-between gap-3">
                                {step > 0
                                    ? <button type="button" onClick={() => setStep(s => s - 1)} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"><ArrowLeft size={16} />Retour</button>
                                    : <span />}
                                {step < 3
                                    ? <GlowButton disabled={!ok[step]} onClick={() => setStep(s => s + 1)}>Continuer <ArrowRight size={16} /></GlowButton>
                                    : <GlowButton disabled={!ok[3] || state === 'sending'} onClick={submit}>
                                        {state === 'sending'
                                            ? <><Loader2 size={16} className="animate-spin" />Envoi…</>
                                            : <>{offer === 'essai' ? 'Recevoir mon dossier' : 'Valider ma commande'} <ArrowRight size={16} /></>}
                                    </GlowButton>}
                            </div>
                        </>
                    )}
                </div>
                <div className="mt-6 flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-faint">
                    <span className="flex items-center gap-1.5"><ShieldCheck size={14} className="text-sage" />Aucun paiement en ligne</span>
                    <span className="flex items-center gap-1.5"><Lock size={14} className="text-sage" />Coordonnées jamais revendues</span>
                    <span className="flex items-center gap-1.5"><Phone size={14} className="text-sage" />Un interlocuteur, pas un robot</span>
                </div>
            </div>
        </div>
    );
}

function Field({ label, ...props }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
    return (
        <label className="block">
            <span className="text-xs text-muted">{label}</span>
            <input {...props} className="mt-1.5 w-full h-12 rounded-xl border border-white/10 bg-raised px-4 text-ink placeholder:text-faint focus:outline-none focus:border-brass/60 focus:ring-2 focus:ring-brass/20 transition" />
        </label>
    );
}

function CityInput({ place, setPlace }: { place: Place | null; setPlace: (p: Place | null) => void }) {
    const [q, setQ] = useState(place?.label ?? '');
    const [list, setList] = useState<Place[]>([]);
    const [open, setOpen] = useState(false);
    useEffect(() => {
        if (q.trim().length < 2 || q === place?.label) { setList([]); return; }
        const ctl = new AbortController();
        const t = setTimeout(async () => {
            try {
                const res = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&type=municipality&limit=6&autocomplete=1`, { signal: ctl.signal });
                const d = await res.json();
                setList((d.features ?? []).map((f: { properties: { city: string; postcode: string; citycode: string } }) => ({
                    label: `${f.properties.city} (${f.properties.postcode})`, insee: f.properties.citycode,
                })));
                setOpen(true);
            } catch { /* aborted or offline */ }
        }, 200);
        return () => { clearTimeout(t); ctl.abort(); };
    }, [q, place?.label]);
    return (
        <div className="relative mt-5">
            <MapPin size={18} className="absolute left-4 top-[1.75rem] -translate-y-1/2 text-brass" />
            <input value={q} placeholder="Commune de votre entreprise" autoComplete="address-level2"
                onChange={e => { setQ(e.target.value); setPlace(null); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
                className="w-full h-14 rounded-2xl border border-white/10 bg-raised pl-11 pr-11 text-ink placeholder:text-faint focus:outline-none focus:border-brass/60 focus:ring-2 focus:ring-brass/20 transition" />
            {place && <Check size={18} className="absolute right-4 top-[1.75rem] -translate-y-1/2 text-sage" />}
            {open && list.length > 0 && (
                <ul className="absolute z-20 mt-2 w-full overflow-hidden rounded-2xl border border-white/10 bg-panel shadow-2xl">
                    {list.map(p => (
                        <li key={p.insee + p.label}>
                            <button type="button" onMouseDown={e => e.preventDefault()} onClick={() => { setPlace(p); setQ(p.label); setOpen(false); }}
                                className="w-full px-4 py-3 text-left text-sm text-ink hover:bg-raised">{p.label}</button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

// --- FAQ and closing ---

function Faq() {
    const [open, setOpen] = useState<number | null>(0);
    return (
        <section className="max-w-3xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
            <Reveal>
                <Kicker>Questions fréquentes</Kicker>
                <h2 className="mt-3 text-2xl sm:text-4xl leading-tight">Tout ce que vous voulez savoir.</h2>
            </Reveal>
            <div className="mt-8 space-y-3">
                {FAQ.map((f, i) => (
                    <div key={f.q} className={`rounded-2xl border transition-colors ${open === i ? 'border-brass/40 bg-panel' : 'border-white/10 bg-panel/50'}`}>
                        <button type="button" onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i}
                            className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left">
                            <span className="text-ink">{f.q}</span>
                            <ChevronDown size={18} className={`shrink-0 text-brass transition-transform duration-300 ${open === i ? 'rotate-180' : ''}`} />
                        </button>
                        <AnimatePresence initial={false}>
                            {open === i && (
                                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.3 }} className="overflow-hidden">
                                    <p className="px-5 pb-5 text-sm text-muted leading-relaxed">{f.a}</p>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                ))}
            </div>
        </section>
    );
}

function FinalCta({ onStart }: { onStart: () => void }) {
    return (
        <section className="relative overflow-hidden py-20 sm:py-24 border-t border-white/[0.06]">
            <div aria-hidden="true" className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-[520px] w-[520px] max-w-full rounded-full bg-brass/20 blur-[120px]" />
            <div className="relative max-w-3xl mx-auto px-4 sm:px-6 text-center">
                <Reveal>
                    <h2 className="text-3xl sm:text-[2.75rem] leading-[1.1]">Le prochain chantier de votre secteur sera signé par quelqu'un. <span className="text-brass-light">Autant que ce soit vous.</span></h2>
                    <p className="mt-5 text-[15px] sm:text-base text-muted">Un dossier d'essai gratuit, sans carte bancaire, sous 24 h ouvrées.</p>
                    <div className="mt-9 flex justify-center">
                        <GlowButton onClick={onStart}>Recevoir mon dossier gratuit <ArrowRight size={18} /></GlowButton>
                    </div>
                </Reveal>
            </div>
        </section>
    );
}

// Mobile: a call to action stays at hand once the hero is past, hidden while the funnel is on screen.
function StickyCta({ onStart }: { onStart: () => void }) {
    const [show, setShow] = useState(false);
    useEffect(() => {
        const onScroll = () => {
            const f = document.getElementById('commande')?.getBoundingClientRect();
            const inFunnel = !!f && f.top < window.innerHeight && f.bottom > 0;
            setShow(window.scrollY > 600 && !inFunnel);
        };
        onScroll();
        window.addEventListener('scroll', onScroll, { passive: true });
        return () => window.removeEventListener('scroll', onScroll);
    }, []);
    return (
        <AnimatePresence>
            {show && (
                <motion.div initial={{ y: 100 }} animate={{ y: 0 }} exit={{ y: 100 }} transition={{ duration: 0.3 }}
                    className="md:hidden fixed inset-x-0 bottom-0 z-40 p-3 bg-canvas/90 backdrop-blur border-t border-white/10">
                    <GlowButton className="w-full" onClick={onStart}>Recevoir un dossier gratuit <ArrowRight size={16} /></GlowButton>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
