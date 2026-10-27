import { lazy, Suspense } from 'react';
import { motion, useReducedMotion, useScroll, useTransform } from 'framer-motion';
import { ArrowRight, BellRing, Clock, FileSignature, MapPinned, ShieldCheck, Store, Swords, Wallet } from 'lucide-react';
import { navigate, usePath } from '../router';
import { SiteFooter, SiteHeader } from '../pages/site';
import { useSeo } from '../seo';
import { Counter, KineticLine, GlowButton, Reveal, RotatingWord, TiltCard, useCan3D, useLite, useOnScreen } from './home/fx';

// Public home, written for independent real estate advisors (iad, Safti,
// Capifrance... and independent agents). The WebGL scenes load after the text
// and only where they can run smoothly; reduced motion gets a static page.
const House = lazy(() => import('./home/House'));
const City = lazy(() => import('./home/City'));

const DAY = [
    { time: '7 h 30', icon: BellRing, title: 'Les DPE de la veille', text: "Dans vos communes, les logements qui viennent de recevoir un DPE. Un DPE précède souvent une vente ou une mise en location.", img: '/demo/alerts.webp' },
    { time: '8 h 15', icon: MapPinned, title: 'Votre secteur, passoire par passoire', text: "Toutes les adresses classées E, F ou G sur une carte, triées par potentiel, avec le suivi de chacune.", img: '/demo/map.webp' },
    { time: '9 h 00', icon: FileSignature, title: 'Un courrier à votre nom', text: "Prêt à imprimer, avec un QR code : le propriétaire découvre la rénovation de son logement et vous laisse ses coordonnées.", img: '/demo/letter.webp' },
    { time: '14 h 00', icon: Wallet, title: "L'avis de valeur qui fait signer", text: "Travaux, aides, reste à charge et valeur avant / après rénovation, appuyée sur les ventes DVF du quartier.", img: '/demo/valuation.webp' },
    { time: '17 h 30', icon: Store, title: 'Le bien F qui ne partait pas', text: "Un dossier acheteur à vos couleurs en deux minutes : la passoire devient un projet chiffré.", img: '/demo/dossier_acheteur_1.webp' },
];

const WHY = [
    { icon: Store, title: 'Pas de vitrine ?', text: "Les vendeurs ne passent pas devant chez vous. SPREA vous mène à eux : chaque nouveau DPE est une porte à laquelle frapper." },
    { icon: Swords, title: 'Seul face aux agences du coin', text: "Les mêmes données qu'un service marketing de réseau : DPE de l'ADEME, ventes DVF de la DGFiP, barèmes d'aides en vigueur." },
    { icon: Clock, title: 'Votre temps, c\'est votre chiffre', text: "Du DPE au courrier en un clic. Du rendez-vous au dossier chiffré en deux minutes. Le reste du temps, vous êtes sur le terrain." },
    { icon: Wallet, title: 'Un outil à votre taille', text: "79 € TTC par mois en Solo, sans équipe à payer. Un seul mandat signé rembourse des années d'abonnement." },
];

export default function Home() {
    useSeo({
        title: 'SPREA · Le mandat avant les autres : l\'outil DPE des conseillers immobiliers indépendants',
        description: "Conseiller indépendant ou mandataire : recevez chaque matin les nouveaux DPE de votre secteur, envoyez un courrier en un clic et signez avec un avis de valeur avant / après travaux fondé sur les ventes DVF.",
        path: '/',
        // Kept mounted (hidden) under the other routes: only the home page sets these
        active: usePath() === '/',
    });
    const can3D = useCan3D();
    const lite = useLite();
    return (
        <div className="min-h-screen flex flex-col bg-canvas overflow-x-clip">
            <SiteHeader />
            <main className="flex-1">
                <Hero can3D={can3D} lite={lite} />
                <Figures />
                <Day />
                <Why />
                <Sector can3D={can3D} lite={lite} />
                <FinalCta />
            </main>
            <SiteFooter />
        </div>
    );
}

function Hero({ can3D, lite }: { can3D: boolean; lite: boolean }) {
    const [ref, on] = useOnScreen<HTMLElement>();
    // From the window's scroll, not the section's: the home page stays mounted (hidden)
    // under the other routes, and a progress measured while hidden would keep the
    // title faded out when coming back to it
    const { scrollY } = useScroll();
    const y = useTransform(scrollY, [0, 700], [0, 140]);
    const fade = useTransform(scrollY, [0, 560], [1, 0]);
    return (
        <section ref={ref} className="relative lg:h-[calc(100svh-4rem)] lg:min-h-[30rem] lg:max-h-[50rem] flex flex-col lg:flex-row lg:items-center overflow-hidden">
            <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(ellipse_45%_55%_at_72%_50%,rgba(40,120,255,0.20),transparent_70%),radial-gradient(ellipse_60%_50%_at_15%_30%,rgba(201,164,92,0.10),transparent_70%)]" />
            <div aria-hidden="true" className="absolute inset-0 opacity-[0.07] bg-[linear-gradient(rgba(255,255,255,0.6)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.6)_1px,transparent_1px)] bg-[size:72px_72px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
            {/* The house sits on the right on large screens, above the text on small ones */}
            <div aria-hidden="true" className="relative h-[42svh] -mb-10 lg:mb-0 lg:h-auto lg:absolute lg:inset-0 lg:left-[46%]">
                {can3D ? (
                    <Suspense fallback={null}><House active={on} lite={lite} /></Suspense>
                ) : (
                    <svg viewBox="0 0 200 160" className="absolute right-[8%] top-1/2 -translate-y-1/2 w-[46vmin] text-brass-light/80" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M30 150V75L100 25l70 50v75z" /><path d="M75 150v-40h30v40M120 95h28v22h-28zM45 95h22v22H45z" />
                    </svg>
                )}
            </div>
            <motion.div style={{ y, opacity: fade }} className="relative w-full max-w-7xl mx-auto px-4 sm:px-6 pb-14 lg:py-[3vh]">
                <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
                    className="inline-flex items-center gap-2 rounded-full border border-brass/30 bg-brass/[0.06] px-4 py-1.5 text-xs sm:text-sm text-brass-light tracking-wide backdrop-blur">
                    <span className="h-1.5 w-1.5 rounded-full bg-brass-light animate-pulse" /> Pour les conseillers immobiliers indépendants
                </motion.p>
                <h1 className="mt-5 lg:mt-[2.2vh] max-w-[36rem] xl:max-w-[42rem] text-[2.1rem] leading-[1.08] sm:text-5xl lg:text-[clamp(2.1rem,6.2vh+0.5vw,3.5rem)] text-ink [perspective:800px]">
                    <span className="block"><KineticLine text="Le prochain mandat" delay={0.15} /></span>
                    <span className="block"><KineticLine text="de votre secteur," delay={0.45} /></span>
                    <span className="block mt-2 text-brass-light [text-shadow:0_0_40px_rgba(201,164,92,0.45)]">
                        <KineticLine text="repérez-le avant" delay={0.75} />
                    </span>
                    <span className="block mt-1 text-brass-light [text-shadow:0_0_40px_rgba(201,164,92,0.45)]">
                        <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.15, duration: 0.5 }}>
                            les <RotatingWord words={['agences.', 'réseaux.', 'portails.', 'autres.']} />
                        </motion.span>
                    </span>
                </h1>
                <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.3, duration: 0.7 }}
                    className="mt-5 lg:mt-[2.2vh] max-w-xl lg:max-w-[min(36rem,42vw)] text-[15px] sm:text-base text-ink-soft/90 leading-relaxed">
                    Pas de vitrine, pas de fichier d'agence, pas de standard qui sonne : votre prospection, c'est vous.
                    SPREA vous signale chaque matin les logements qui viennent de recevoir un DPE, prépare votre courrier
                    et vous arme de chiffres pour le rendez-vous.
                </motion.p>
                <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.5, duration: 0.7 }}
                    className="mt-8 lg:mt-[3.4vh] flex flex-col sm:flex-row gap-3">
                    <GlowButton onClick={() => navigate('/demo')}>Voir la visite guidée <ArrowRight size={18} /></GlowButton>
                    <GlowButton variant="ghost" onClick={() => navigate('/tarifs')}>Solo · 79 € TTC / mois</GlowButton>
                </motion.div>
                <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.8 }}
                    className="mt-5 lg:mt-[2.2vh] text-xs text-faint flex items-center gap-2">
                    <ShieldCheck size={14} className="text-sage" /> Données publiques sourcées : ADEME, DGFiP, barèmes d'aides en vigueur
                </motion.p>
            </motion.div>
            <motion.div aria-hidden="true" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.2 }}
                className="absolute bottom-4 left-1/2 -translate-x-1/2 hidden xl:flex flex-col items-center gap-2 text-[11px] tracking-[0.25em] text-faint">
                DÉFILER
                <span className="relative h-10 w-px bg-line overflow-hidden"><span className="absolute inset-x-0 top-0 h-4 bg-brass-light animate-[scrollcue_1.8s_ease-in-out_infinite]" /></span>
            </motion.div>
        </section>
    );
}

function Figures() {
    const items = [
        { node: <Counter to={1.27} decimals={2} suffix=" million" />, label: "de ventes DVF rapprochées de leur DPE pour mesurer la valeur verte" },
        { node: <>Chaque <span className="text-brass-light">matin</span></>, label: "les DPE publiés par l'ADEME dans vos communes" },
        { node: <Counter to={30} suffix=" s" />, label: "pour passer d'une adresse à un avis de valeur complet" },
        { node: <Counter to={79} suffix=" €" />, label: 'TTC par mois en formule Solo, tous les outils inclus' },
    ];
    return (
        <section className="relative border-y border-white/[0.06] bg-gradient-to-b from-panel/50 to-canvas">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10 grid gap-8 grid-cols-2 lg:grid-cols-4">
                {items.map((it, i) => (
                    <Reveal key={i} delay={i * 0.08}>
                        <p className="font-serif text-2xl sm:text-[2rem] text-ink tabular-nums">{it.node}</p>
                        <p className="mt-2 text-[13px] text-muted leading-relaxed max-w-[16rem]">{it.label}</p>
                    </Reveal>
                ))}
            </div>
        </section>
    );
}

// A day of prospecting: the cards scroll on their own in a slow, endless
// band (paused under the cursor and off screen; scrollable by hand under
// reduced motion)
function Day() {
    const reduce = useReducedMotion();
    const [ref, on] = useOnScreen<HTMLElement>('0px');
    return (
        <section ref={ref} className="relative py-16 sm:py-20 overflow-hidden">
            <div className="max-w-7xl mx-auto px-4 sm:px-6">
                <p className="text-xs sm:text-sm text-brass tracking-[0.2em] uppercase">Une journée avec SPREA</p>
                <h2 className="mt-3 text-2xl sm:text-4xl text-ink max-w-2xl leading-tight">Du café du matin au mandat signé.</h2>
            </div>
            <div className={`group mt-8 sm:mt-10 [mask-image:linear-gradient(90deg,transparent,black_6%,black_94%,transparent)] ${reduce ? 'overflow-x-auto' : ''}`}>
                <div className={`flex w-max gap-5 pr-5 ${reduce ? '' : 'animate-[daymarquee_110s_linear_infinite] group-hover:[animation-play-state:paused]'}`}
                    style={on ? undefined : { animationPlayState: 'paused' }}>
                    {/* Twice the cards: the band loops on the second copy */}
                    {(reduce ? DAY : [...DAY, ...DAY]).map((d, i) => (
                        <div key={i} className="w-[min(84vw,44rem)] shrink-0" aria-hidden={i >= DAY.length}>
                            <DayCard d={d} />
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}

function DayCard({ d }: { d: typeof DAY[number] }) {
    return (
        <div className="rounded-3xl border border-white/10 bg-gradient-to-br from-panel to-canvas p-5 sm:p-6 shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)] grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] items-center">
            <div>
                <p className="font-serif text-4xl sm:text-[2.6rem] text-transparent bg-clip-text bg-gradient-to-b from-brass-light to-brass-dark">{d.time}</p>
                <h3 className="mt-3 text-lg sm:text-xl text-ink flex items-center gap-2.5"><d.icon size={19} className="text-brass shrink-0" />{d.title}</h3>
                <p className="mt-2 text-sm text-muted leading-relaxed">{d.text}</p>
            </div>
            <div className="rounded-xl overflow-hidden border border-white/10 bg-raised">
                <img src={d.img} alt={d.title} loading="lazy" decoding="async" className="block w-full h-[26svh] sm:h-[34svh] max-h-80 object-cover object-top" />
            </div>
        </div>
    );
}

function Why() {
    return (
        <section className="max-w-7xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
            <Reveal>
                <p className="text-xs sm:text-sm text-brass tracking-[0.2em] uppercase">Pensé pour les indépendants</p>
                <h2 className="mt-3 text-2xl sm:text-4xl text-ink max-w-3xl leading-tight">Vous êtes seul sur votre secteur. Plus avec les mêmes armes que les autres.</h2>
            </Reveal>
            <div className="mt-10 grid gap-4 sm:grid-cols-2">
                {WHY.map((w, i) => (
                    <Reveal key={w.title} delay={i * 0.08}>
                        <TiltCard className="h-full rounded-3xl">
                            <div className="group h-full rounded-3xl border border-white/10 bg-panel/60 p-6 transition-colors hover:border-brass/40">
                                <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-brass/10 text-brass-light ring-1 ring-brass/30 group-hover:shadow-[0_0_30px_rgba(201,164,92,0.45)] transition-shadow">
                                    <w.icon size={20} />
                                </span>
                                <h3 className="mt-5 text-xl text-ink">{w.title}</h3>
                                <p className="mt-2 text-sm text-muted leading-relaxed">{w.text}</p>
                            </div>
                        </TiltCard>
                    </Reveal>
                ))}
            </div>
        </section>
    );
}

function Sector({ can3D, lite }: { can3D: boolean; lite: boolean }) {
    const [ref, on] = useOnScreen<HTMLElement>();
    return (
        <section ref={ref} className="relative overflow-hidden border-y border-white/[0.06] bg-[#050913]">
            <div className="relative max-w-7xl mx-auto px-4 sm:px-6 pt-16 sm:pt-20 pointer-events-none z-10">
                <Reveal>
                    <p className="text-xs sm:text-sm text-brass tracking-[0.2em] uppercase">Votre secteur, vu d'en haut</p>
                    <h2 className="mt-3 text-2xl sm:text-4xl text-ink max-w-2xl leading-tight">Survolez la ville. Les passoires s'allument.</h2>
                    <p className="mt-3 max-w-xl text-sm sm:text-[15px] text-muted leading-relaxed">
                        Chaque maison, chaque immeuble porte la couleur de son DPE. Les orange et rouge sont les F et G :
                        des propriétaires qui devront rénover pour continuer à louer (G depuis 2025, F en 2028)… ou qui vendront.
                    </p>
                </Reveal>
            </div>
            <div className="relative h-[54vh] min-h-[340px] max-h-[600px] mt-2">
                {can3D ? (
                    <Suspense fallback={null}><City active={on} lite={lite} /></Suspense>
                ) : (
                    <div aria-hidden="true" className="absolute inset-0 bg-[linear-gradient(rgba(80,150,255,0.25)_1px,transparent_1px),linear-gradient(90deg,rgba(80,150,255,0.25)_1px,transparent_1px)] bg-[size:40px_40px] opacity-40 [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" />
                )}
            </div>
            <p className="absolute bottom-3 right-4 left-4 sm:left-auto text-center sm:text-right text-[11px] text-faint">Ville imaginaire pour l'illustration. Dans SPREA, ce sont les vraies adresses de votre secteur, sur une carte.</p>
        </section>
    );
}

function FinalCta() {
    return (
        <section className="relative overflow-hidden py-20 sm:py-24">
            <div aria-hidden="true" className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-[520px] w-[520px] rounded-full bg-brass/20 blur-[120px]" />
            <div className="relative max-w-3xl mx-auto px-4 sm:px-6 text-center">
                <Reveal>
                    <h2 className="text-3xl sm:text-[2.75rem] text-ink leading-[1.1]">Un mandat signé paie des années d'abonnement.</h2>
                    <p className="mt-5 text-[15px] sm:text-base text-muted">Solo à 79 € TTC par mois. Tous les outils inclus : alertes DPE, carte des passoires, courriers, avis de valeur, dossiers acheteur.</p>
                    <div className="mt-9 flex flex-col sm:flex-row gap-3 justify-center">
                        <GlowButton onClick={() => navigate('/demo')}>Faire la visite guidée <ArrowRight size={18} /></GlowButton>
                        <GlowButton variant="ghost" onClick={() => navigate('/tarifs')}>Voir les tarifs</GlowButton>
                    </div>
                    <p className="mt-6 text-xs text-faint">Mensuel ou annuel · engagement 12 mois · facture avec TVA</p>
                </Reveal>
            </div>
        </section>
    );
}
