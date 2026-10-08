import type { ReactNode } from 'react';
import { Building2 } from 'lucide-react';
import { AccountButton } from '../account';
import { isLegalIncomplete, LEGAL } from '../legal';
import { Link } from '../router';

export function SiteFooter({ className = '' }: { className?: string }) {
    return (
        <footer className={`text-[11px] text-slate-400 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 py-6 ${className}`}>
            <span>© {new Date().getFullYear()} {LEGAL.brand}</span>
            <Link to="/tarifs" className="hover:text-slate-900">Tarifs</Link>
            <Link to="/cgv" className="hover:text-slate-900">Conditions générales de vente</Link>
            <Link to="/mentions-legales" className="hover:text-slate-900">Mentions légales</Link>
            <Link to="/confidentialite" className="hover:text-slate-900">Confidentialité</Link>
            {!LEGAL.email.startsWith('[') && <a href={`mailto:${LEGAL.email}`} className="hover:text-slate-900">Contact</a>}
        </footer>
    );
}

// Header + footer for the content pages (pricing, CGV)
export function PageShell({ children }: { children: ReactNode }) {
    return (
        <div className="min-h-screen bg-slate-50 font-sans flex flex-col">
            <header className="max-w-5xl w-full mx-auto px-4 sm:px-6 py-6 flex items-center justify-between gap-4">
                <Link to="/" className="flex items-center gap-3">
                    <Building2 className="text-blue-600" size={24} />
                    <span className="text-xs font-black text-slate-500 uppercase tracking-widest">{LEGAL.brand}</span>
                </Link>
                <nav className="flex items-center gap-3">
                    <Link to="/tarifs" className="hidden sm:inline text-[10px] font-black uppercase tracking-widest text-slate-500 hover:text-slate-900 px-3">Tarifs</Link>
                    <AccountButton />
                </nav>
            </header>
            <main className="max-w-5xl w-full mx-auto px-4 sm:px-6 flex-1">{children}</main>
            <SiteFooter className="mt-12" />
        </div>
    );
}

export function LegalIncompleteBanner() {
    if (!isLegalIncomplete()) return null;
    return (
        <div className="mb-8 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">
            Informations légales à compléter dans <code>src/legal.ts</code> (raison sociale, SIREN, médiateur…) avant toute vente.
        </div>
    );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
    return (
        <section className="space-y-3">
            <h2 className="text-lg font-black text-slate-800 tracking-tight">{title}</h2>
            <div className="space-y-3 text-sm text-slate-600 leading-relaxed">{children}</div>
        </section>
    );
}

export function LegalPage({ title, updated, children }: { title: string; updated?: string; children: ReactNode }) {
    return (
        <PageShell>
            <article className="max-w-3xl mx-auto bg-white rounded-[2rem] border border-slate-100 shadow-sm p-6 sm:p-10 space-y-8">
                <LegalIncompleteBanner />
                <header>
                    <h1 className="text-3xl font-black text-slate-800 tracking-tighter">{title}</h1>
                    {updated && <p className="text-xs text-slate-400 mt-2">{updated}</p>}
                </header>
                {children}
            </article>
        </PageShell>
    );
}
