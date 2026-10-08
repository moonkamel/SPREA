import { useEffect, useState } from 'react';
import { ArrowRight, Bell, Building2, Loader2, MapPin, Search, ShieldCheck, Users } from 'lucide-react';
import { Button, Card, Help, Segmented } from '../ui';
import { SiteFooter, SiteHeader } from '../pages/site';
import { Link } from '../router';

interface Props {
    loading: boolean;
    error: string | null;
    onSearchAddress: (address: string) => void;
    onSearchDpe: (dpeNumber: string) => void;
}

const SHORTCUTS = [
    { to: '/prospection', icon: MapPin, title: 'Carte de prospection', text: 'Les passoires E, F, G de votre secteur, adresse par adresse.' },
    { to: '/alertes', icon: Bell, title: 'Alertes', text: 'Chaque matin, les nouveaux DPE publiés dans vos zones.' },
    { to: '/contacts', icon: Users, title: 'Contacts', text: 'Les propriétaires qui ont répondu à vos courriers.' },
]

export default function Landing({ loading, error, onSearchAddress, onSearchDpe }: Props) {
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

            <main className="flex-1">
                {/* Hero */}
                <section className="relative overflow-hidden">
                    <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(201,164,92,0.10),transparent_60%)] pointer-events-none" />
                    <div className="relative max-w-3xl mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-14 text-center">
                        <p className="text-sm text-brass tracking-wide mb-5">Simulateur</p>
                        <h1 className="text-4xl sm:text-5xl leading-[1.1] text-ink">
                            Quel logement étudions-nous ?
                        </h1>
                        <p className="mt-6 text-lg text-muted max-w-2xl mx-auto">
                            Adresse ou numéro de DPE : travaux, nouvelle étiquette, aides, reste à charge, valeur verte et avis de valeur en quelques secondes.
                        </p>

                        <Card className="mt-10 p-4 sm:p-6 text-left shadow-2xl shadow-black/40">
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
                                Données officielles : DPE de l'ADEME, ventes DVF de la DGFiP.
                            </p>
                        </Card>
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
