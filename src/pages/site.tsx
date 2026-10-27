import { useEffect, useRef, useState, type ReactNode } from 'react';
import { HelpCircle, Menu, X } from 'lucide-react';
import { AccountButton, useAccount } from '../account';
import { isLegalIncomplete, LEGAL } from '../legal';
import { Link, navigate, usePath } from '../router';
import { useSeo } from '../seo';
import { TOURS, startTour, type TourId } from '../tour';

export function Logo({ onClick }: { onClick?: () => void }) {
    return (
        <a
            href="/"
            onClick={e => {
                e.preventDefault();
                if (onClick) onClick();
                navigate('/');
            }}
            className="flex items-baseline gap-3 group"
        >
            <span className="font-serif text-2xl tracking-tight text-ink group-hover:text-brass-light transition-colors">{LEGAL.brand}</span>
            <span className="hidden lg:inline text-xs text-faint tracking-wide">L'outil DPE des pros de l'immobilier</span>
        </a>
    );
}

const NAV_LINK = 'px-2 sm:px-3 py-2 text-sm text-muted hover:text-ink transition-colors';

// Subscribers see their tools; visitors see the showcase. On small screens,
// only the links marked as essential stay in the header, the others are in a menu.
function Nav() {
    const { me } = useAccount();
    const path = usePath();
    const [open, setOpen] = useState(false);
    const menu = useRef<HTMLDivElement>(null);
    const links: [string, string, boolean][] = me?.is_pro
        ? [['/', 'Simulateur', false], ['/prospection', 'Prospection', false], ['/documents-copro', 'PV d\'AG', false], ['/alertes', 'Alertes', false], ['/contacts', 'Contacts', false],
            me.team ? ['/equipe', 'Équipe', false] : ['/observatoire', 'Observatoire', false]]
        : [['/demo', 'Visite guidée', true], ['/estimation', 'Estimer un bien', false], ['/observatoire', 'Observatoire', false], ['/tarifs', 'Tarifs', true]];
    const hidden = links.some(([, , essential]) => !essential);

    // Closed on navigation, Escape or a click outside
    useEffect(() => setOpen(false), [path]);
    useEffect(() => {
        if (!open) return;
        const close = (e: Event) => {
            if (e.type === 'keydown' && (e as KeyboardEvent).key !== 'Escape') return;
            if (e.type === 'mousedown' && menu.current?.contains(e.target as Node)) return;
            setOpen(false);
        };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown', close);
        return () => {
            document.removeEventListener('mousedown', close);
            document.removeEventListener('keydown', close);
        };
    }, [open]);

    return (
        <>
            {links.map(([to, label, essential]) => (
                <Link key={to} to={to} className={`${essential ? '' : 'hidden md:inline '}${NAV_LINK}`}>{label}</Link>
            ))}
            {hidden && (
                <div ref={menu} className="relative md:hidden">
                    <button type="button" aria-expanded={open} aria-controls="site-menu" aria-label={open ? 'Fermer le menu' : 'Ouvrir le menu'}
                        onClick={() => setOpen(o => !o)}
                        className="h-10 w-10 flex items-center justify-center rounded-xl text-muted hover:text-ink transition-colors">
                        {open ? <X size={20} /> : <Menu size={20} />}
                    </button>
                    {open && (
                        <div id="site-menu" className="absolute right-0 top-full mt-2 w-56 rounded-xl border border-line bg-panel p-2 shadow-2xl shadow-black/50">
                            {links.map(([to, label]) => (
                                <Link key={to} to={to}
                                    className={`block rounded-lg px-3 py-2.5 text-sm transition-colors hover:bg-raised ${to === path ? 'text-brass' : 'text-ink-soft hover:text-ink'}`}>
                                    {label}
                                </Link>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </>
    );
}

// Subscribers start either journey of the guided tour again from here
function GuideMenu() {
    const { me } = useAccount();
    const [open, setOpen] = useState(false);
    const box = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (!open) return;
        const close = (e: Event) => {
            if (e.type === 'keydown' && (e as KeyboardEvent).key !== 'Escape') return;
            if (e.type === 'mousedown' && box.current?.contains(e.target as Node)) return;
            setOpen(false);
        };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown', close);
        return () => {
            document.removeEventListener('mousedown', close);
            document.removeEventListener('keydown', close);
        };
    }, [open]);
    if (!me?.is_pro) return null;
    return (
        <div ref={box} className="relative">
            <button type="button" aria-expanded={open} aria-label="Visite guidée" title="Visite guidée" onClick={() => setOpen(o => !o)}
                className="h-10 w-10 flex items-center justify-center rounded-xl text-muted hover:text-ink transition-colors">
                <HelpCircle size={19} />
            </button>
            {open && (
                <div className="absolute right-0 top-full mt-2 w-64 rounded-xl border border-line bg-panel p-2 shadow-2xl shadow-black/50 z-50">
                    <p className="px-3 pt-1 pb-2 text-xs text-faint">Visite guidée</p>
                    {(Object.keys(TOURS) as TourId[]).map(id => (
                        <button key={id} type="button" onClick={() => { setOpen(false); startTour(id); }}
                            className="block w-full text-left rounded-lg px-3 py-2.5 text-sm text-ink-soft hover:text-ink hover:bg-raised">
                            {TOURS[id].name}
                            <span className="block text-xs text-faint">{id === 'vendre' ? 'Le dossier acheteur d\'un bien sous mandat' : 'Les biens à fort potentiel et leur suivi'}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

export function SiteHeader({ onHome }: { onHome?: () => void }) {
    return (
        <header className="border-b border-line/70 bg-canvas/90 backdrop-blur sticky top-0 z-40">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
                <Logo onClick={onHome} />
                <nav className="flex items-center gap-1 sm:gap-2">
                    <Nav />
                    <GuideMenu />
                    <AccountButton />
                </nav>
            </div>
        </header>
    );
}

export function SiteFooter({ className = '' }: { className?: string }) {
    return (
        <footer className={`border-t border-line/70 ${className}`}>
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row gap-4 sm:items-center sm:justify-between text-sm text-faint">
                <span>© {new Date().getFullYear()} {LEGAL.brand} · Logiciel réservé aux professionnels. Estimations indicatives, sans valeur d'expertise, de DPE, d'audit ni de devis.</span>
                <nav className="flex flex-wrap gap-x-5 gap-y-2">
                    <Link to="/demo" className="hover:text-ink">Visite guidée</Link>
                    <Link to="/tarifs" className="hover:text-ink">Tarifs</Link>
                    <Link to="/observatoire" className="hover:text-ink">Observatoire</Link>
                    <Link to="/estimation" className="hover:text-ink">Estimation immobilière gratuite</Link>
                    <Link to="/prix-m2" className="hover:text-ink">Prix m² par commune</Link>
                    <Link to="/cgv" className="hover:text-ink">CGV</Link>
                    <Link to="/mentions-legales" className="hover:text-ink">Mentions légales</Link>
                    <Link to="/confidentialite" className="hover:text-ink">Confidentialité</Link>
                    {!LEGAL.email.startsWith('[') && <a href={`mailto:${LEGAL.email}`} className="hover:text-ink">Contact</a>}
                </nav>
            </div>
        </footer>
    );
}

// Header + footer for the content pages (pricing, legal)
export function PageShell({ children }: { children: ReactNode }) {
    return (
        <div className="min-h-screen flex flex-col">
            <SiteHeader />
            <main className="max-w-5xl w-full mx-auto px-4 sm:px-6 py-10 sm:py-14 flex-1">{children}</main>
            <SiteFooter />
        </div>
    );
}

export function LegalIncompleteBanner() {
    if (!isLegalIncomplete()) return null;
    return (
        <div className="rounded-xl border border-brass/40 bg-brass/10 p-4 text-sm text-brass-light">
            Informations légales à compléter dans <code className="text-ink">src/legal.ts</code> (raison sociale, SIREN, médiateur…) avant toute vente.
        </div>
    );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
    return (
        <section className="space-y-3">
            <h2 className="text-xl text-ink">{title}</h2>
            <div className="space-y-3 text-[15px] text-ink-soft leading-relaxed">{children}</div>
        </section>
    );
}

export function LegalPage({ title, updated, description, children }: { title: string; updated?: string; description?: string; children: ReactNode }) {
    useSeo({
        title: `${title} · SPREA`,
        description: description || `${title} de ${LEGAL.brand}, l'outil DPE des professionnels de l'immobilier : prospection, valeur verte et avis de valeur.`,
        path: window.location.pathname,
    });
    return (
        <PageShell>
            <article className="max-w-3xl mx-auto space-y-10">
                <LegalIncompleteBanner />
                <header className="border-b border-line pb-8">
                    <h1 className="text-4xl text-ink">{title}</h1>
                    {updated && <p className="text-sm text-faint mt-3">{updated}</p>}
                </header>
                {children}
            </article>
        </PageShell>
    );
}

// Unknown address
export function NotFound() {
    useSeo({ title: 'Page introuvable · SPREA', noindex: true });
    return (
        <PageShell>
            <div className="max-w-xl mx-auto text-center py-12">
                <p className="text-sm text-brass tracking-wide">Erreur 404</p>
                <h1 className="mt-3 text-4xl text-ink">Page introuvable</h1>
                <p className="mt-4 text-muted">Cette adresse ne correspond à aucune page. Elle a peut-être changé, ou le lien est incomplet.</p>
                <Link to="/" className="mt-8 inline-flex items-center justify-center rounded-xl px-5 h-12 font-semibold text-sm bg-brass text-canvas hover:bg-brass-light transition-colors">
                    Revenir à l'accueil
                </Link>
            </div>
        </PageShell>
    );
}
