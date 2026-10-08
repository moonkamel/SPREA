import type { ReactNode } from 'react';
import { AccountButton, useAccount } from '../account';
import { isLegalIncomplete, LEGAL } from '../legal';
import { Link, navigate } from '../router';

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
            <span className="hidden sm:inline text-xs text-faint tracking-wide">Rénovation énergétique</span>
        </a>
    );
}

function ContactsLink() {
    const { me } = useAccount();
    if (!me?.is_pro) return null;
    return (
        <>
            <Link to="/alertes" className="hidden sm:inline px-3 py-2 text-sm text-muted hover:text-ink transition-colors">Alertes</Link>
            <Link to="/contacts" className="hidden sm:inline px-3 py-2 text-sm text-muted hover:text-ink transition-colors">Contacts</Link>
        </>
    );
}

export function SiteHeader({ onHome }: { onHome?: () => void }) {
    return (
        <header className="border-b border-line/70 bg-canvas/90 backdrop-blur sticky top-0 z-40">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
                <Logo onClick={onHome} />
                <nav className="flex items-center gap-1 sm:gap-3">
                    <Link to="/prospection" className="hidden sm:inline px-3 py-2 text-sm text-muted hover:text-ink transition-colors">Prospection</Link>
                    <ContactsLink />
                    <Link to="/tarifs" className="px-3 py-2 text-sm text-muted hover:text-ink transition-colors">Tarifs</Link>
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
                <span>© {new Date().getFullYear()} {LEGAL.brand} · Estimations indicatives, sans valeur de DPE, d'audit ni de devis.</span>
                <nav className="flex flex-wrap gap-x-5 gap-y-2">
                    <Link to="/tarifs" className="hover:text-ink">Tarifs</Link>
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

export function LegalPage({ title, updated, children }: { title: string; updated?: string; children: ReactNode }) {
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
