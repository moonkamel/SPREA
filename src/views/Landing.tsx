import { useEffect, useState } from 'react';
import { ArrowRight, Bell, Building2, Loader2, MapPin, Radar, Search, ShieldCheck, Users } from 'lucide-react';
import { Button, Card, Help, Segmented } from '../ui';
import { TourHost, useAutoTour } from '../tour';
import { SiteFooter, SiteHeader } from '../pages/site';
import { Link, navigate } from '../router';

interface Props {
    loading: boolean;
    error: string | null;
    onSearchAddress: (address: string) => void;
    onSearchDpe: (dpeNumber: string) => void;
}

const SHORTCUTS = [
    { to: '/prospection?mode=potentiel', icon: MapPin, title: 'Biens à fort potentiel', text: 'Les passoires de votre secteur chiffrées et classées, avec tous les outils pour chaque adresse.' },
    { to: '/alertes', icon: Bell, title: 'Alertes', text: 'Chaque matin, les nouveaux DPE publiés dans vos zones.' },
    { to: '/contacts', icon: Users, title: 'Contacts', text: 'Les propriétaires qui ont répondu à vos courriers.' },
]

export default function Landing({ loading, error, onSearchAddress, onSearchDpe }: Props) {
    // Shown to subscribers only: their first visit starts with SPREA Command
    useAutoTour('command', true);
    const [mode, setMode] = useState<'address' | 'dpe'>('address');
    const [query, setQuery] = useState('');
    const [dpeNumber, setDpeNumber] = useState('');
    const [suggestions, setSuggestions] = useState<{ label: string }[]>([]);
    const [picked, setPicked] = useState('');

    // Address autocomplete (Base Adresse Nationale)
    useEffect(() => {
        if (mode !== 'address' || query.length < 3 || query === picked) { setSuggestions([]); return; }
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            try {
                const res = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(query)}&limit=5`, { signal: controller.signal });
                const data = await res.json();
                setSuggestions((data.features || []).map((f: any) => ({ label: f.properties.label })));
            } catch { /* autocomplete is optional */ }
        }, 250);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [query, mode, picked]);

    const searchAddress = (address: string) => {
        if (!address.trim()) return;
        setSuggestions([]);
        setPicked(address);
        setQuery(address);
        onSearchAddress(address);
    };

    return (
        <div className="min-h-screen flex flex-col">
            <SiteHeader />
            <TourHost screen="simulateur" />

            <main className="flex-1">
                {/* Prospecting first: the cockpit of the day */}
                <section className="relative overflow-hidden border-b border-line">
                    <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_70%_0%,rgba(201,164,92,0.16),transparent_60%)] pointer-events-none" />
                    <div className="relative max-w-6xl mx-auto px-4 sm:px-6 py-10 sm:py-14 grid gap-8 lg:grid-cols-[1fr_1.25fr] items-center">
                        <div>
                            <p className="text-sm text-brass tracking-wide flex items-center gap-2"><Radar size={16} />SPREA Command</p>
                            <h1 className="mt-4 text-3xl sm:text-[2.6rem] leading-[1.1] text-ink">Vos mandats du jour, <span className="text-brass-light">sur un seul écran.</span></h1>
                            <p className="mt-4 text-muted">
                                Le radar de votre secteur chiffre chaque DPE récent et classe les biens par score. Le briefing vous dit qui contacter
                                en premier ; un clic, et le courrier, le nom du propriétaire et le dossier sont prêts.
                            </p>
                            <div className="mt-6 flex flex-wrap gap-3">
                                <Button className="h-12 px-6" onClick={() => navigate('/command')}>Ouvrir SPREA Command <ArrowRight size={18} /></Button>
                                <Button variant="secondary" className="h-12 px-5" onClick={() => navigate('/prospection')}><MapPin size={16} />Carte de prospection</Button>
                            </div>
                        </div>
                        <button type="button" data-tour="home-command" onClick={() => navigate('/command')} aria-label="Ouvrir SPREA Command"
                            className="group relative rounded-2xl overflow-hidden border border-brass/30 shadow-[0_30px_80px_-20px_rgba(201,164,92,0.35)] hover:border-brass/60 transition-colors">
                            <img src="/demo/command_radar.webp" alt="SPREA Command : radar du secteur, cibles classées par score et briefing du matin" width={1600} height={1000} className="block w-full h-auto" />
                            <span className="absolute inset-0 bg-gradient-to-t from-canvas/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                        </button>
                    </div>
                </section>

                {/* Hero */}
                <section className="relative overflow-hidden">
                    <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(201,164,92,0.10),transparent_60%)] pointer-events-none" />
                    <div className="relative max-w-3xl mx-auto px-4 sm:px-6 pt-12 sm:pt-16 pb-14 text-center">
                        <p className="text-sm text-brass tracking-wide mb-5">Simulateur</p>
                        <h2 className="text-4xl sm:text-5xl leading-[1.1] text-ink">
                            Quel logement étudions-nous ?
                        </h2>
                        <p className="mt-6 text-lg text-muted max-w-2xl mx-auto">
                            Le bien que vous vendez ou celui d'un propriétaire à convaincre : travaux, aides, valeur après rénovation, avis de valeur et dossier acheteur en quelques secondes.
                        </p>

                        <div data-tour="sell-address" className="mt-10">
                        <Card className="p-4 sm:p-6 text-left shadow-2xl shadow-black/40">
                            <div className="mb-4">
                                <Segmented
                                    ariaLabel="Type de recherche"
                                    value={mode}
                                    onChange={setMode}
                                    options={[
                                        { value: 'address', label: 'Par adresse' },
                                        { value: 'dpe', label: 'Par numéro de DPE' },
                                    ]}
                                />
                            </div>

                            {mode === 'address' ? (
                                <form className="relative" onSubmit={e => { e.preventDefault(); searchAddress(query); }}>
                                    <div className="flex flex-col sm:flex-row gap-3">
                                        <label className="flex-1 flex items-center gap-3 rounded-xl border border-line bg-raised px-4 h-14 focus-within:border-brass/70 transition-colors">
                                            <Search size={20} className="text-faint shrink-0" />
                                            <input
                                                autoFocus
                                                aria-label="Adresse du logement"
                                                placeholder="Ex. 12 rue de la Paix, Lille"
                                                value={query}
                                                onChange={e => setQuery(e.target.value)}
                                                className="flex-1 min-w-0 bg-transparent text-base text-ink placeholder:text-faint outline-none"
                                            />
                                        </label>
                                        <Button type="submit" disabled={loading || !query.trim()} className="h-14 sm:w-44">
                                            {loading ? <Loader2 className="animate-spin" size={18} /> : <>Rechercher <ArrowRight size={18} /></>}
                                        </Button>
                                    </div>
                                    {suggestions.length > 0 && (
                                        <ul className="absolute left-0 right-0 top-full mt-2 z-30 rounded-xl border border-line bg-raised shadow-2xl shadow-black/50 overflow-hidden">
                                            {suggestions.map(s => (
                                                <li key={s.label}>
                                                    <button type="button" onClick={() => searchAddress(s.label)}
                                                        className="w-full flex items-center gap-3 px-4 py-3 text-left text-ink-soft hover:bg-panel hover:text-ink transition-colors">
                                                        <MapPin size={16} className="text-brass shrink-0" /> {s.label}
                                                    </button>
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </form>
                            ) : (
                                <form onSubmit={e => { e.preventDefault(); if (dpeNumber.trim()) onSearchDpe(dpeNumber.trim()); }}>
                                    <div className="flex flex-col sm:flex-row gap-3">
                                        <label className="flex-1 flex items-center gap-3 rounded-xl border border-line bg-raised px-4 h-14 focus-within:border-brass/70 transition-colors">
                                            <Building2 size={20} className="text-faint shrink-0" />
                                            <input
                                                aria-label="Numéro de DPE"
                                                placeholder="Ex. 2359E1234567A"
                                                value={dpeNumber}
                                                onChange={e => setDpeNumber(e.target.value.toUpperCase())}
                                                className="flex-1 min-w-0 bg-transparent text-base text-ink placeholder:text-faint outline-none tracking-wide"
                                            />
                                            <Help topic="dpeNumber" />
                                        </label>
                                        <Button type="submit" disabled={loading || !dpeNumber.trim()} className="h-14 sm:w-44">
                                            {loading ? <Loader2 className="animate-spin" size={18} /> : <>Rechercher <ArrowRight size={18} /></>}
                                        </Button>
                                    </div>
                                </form>
                            )}

                            {error && <p role="alert" className="mt-4 text-sm text-coral">{error}</p>}
                            <p className="mt-4 text-xs text-faint flex items-center gap-2">
                                <ShieldCheck size={14} className="text-sage shrink-0" />
                                Données publiques : DPE de l'ADEME, ventes DVF de la DGFiP.
                            </p>
                        </Card>
                        </div>
                    </div>
                </section>

                {/* The other tools */}
                <section className="max-w-6xl mx-auto px-4 sm:px-6 py-14 border-t border-line/60">
                    <div className="grid gap-5 md:grid-cols-3">
                        {SHORTCUTS.map(t => (
                            <Link key={t.to} to={t.to} className="block">
                                <Card className="p-6 h-full hover:border-brass/50 transition-colors">
                                    <t.icon size={20} className="text-brass mb-4" />
                                    <h2 className="text-lg text-ink mb-2">{t.title}</h2>
                                    <p className="text-sm text-muted leading-relaxed">{t.text}</p>
                                </Card>
                            </Link>
                        ))}
                    </div>
                </section>
            </main>

            <SiteFooter />
        </div>
    );
}
