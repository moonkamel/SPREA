import React, { useState, useMemo, useCallback } from 'react';
import {
    ShieldAlert,
    TrendingUp,
    Euro,
    Home,
    Zap,
    Hammer,
    ChevronRight,
    Info,
    Search,
    Upload,
    FileText,
    Loader2,
    ArrowRight
} from 'lucide-react';

// --- Types & Constants ---

type DPEClass = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';

interface RetrofitAction {
    id: string;
    name: string;
    defaultCost: number;
    impactKwh: number;
    active: boolean;
    costOverride?: number;
}

interface PropertyData {
    address: string;
    surface: number;
    year: number;
    initialCep: number;
    label: DPEClass;
}

const DPE_COLORS: Record<DPEClass, string> = {
    A: '#31a354', B: '#74c476', C: '#a1d99b', D: '#feb24c', E: '#fd8d3c', F: '#f03b20', G: '#bd0026',
};

const DPE_THRESHOLDS: { label: DPEClass; max: number }[] = [
    { label: 'A', max: 70 }, { label: 'B', max: 110 }, { label: 'C', max: 180 },
    { label: 'D', max: 250 }, { label: 'E', max: 330 }, { label: 'F', max: 420 }, { label: 'G', max: 999 },
];

const API_BASE = "http://localhost:8000";

// --- Main Component ---

export default function SimulationDashboard() {
    const [view, setView] = useState<'landing' | 'dashboard'>('landing');
    const [loading, setLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [property, setProperty] = useState<PropertyData | null>(null);
    const [actions, setActions] = useState<RetrofitAction[]>([
        { id: 'iti', name: 'Isolation Combles', defaultCost: 35, impactKwh: 45, active: false },
        { id: 'ite', name: 'Isolation Murs (ITE)', defaultCost: 160, impactKwh: 120, active: false },
        { id: 'windows', name: 'Double Vitrage', defaultCost: 450, impactKwh: 30, active: false },
        { id: 'heatpump', name: 'Changement -> PAC', defaultCost: 12000, impactKwh: 210, active: false },
    ]);

    // --- API Handlers ---

    const handleAddressSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!searchQuery) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/search-address?q=${encodeURIComponent(searchQuery)}`);
            const data = await res.json();
            if (data.results && data.results.length > 0) {
                const raw = data.results[0]; // Take first result
                setProperty({
                    address: raw.address,
                    surface: raw.shab || 100,
                    year: raw.construction_year || 1980,
                    initialCep: raw.consumption_level || 420,
                    label: raw.dpe_class_current || 'G'
                });
                setView('dashboard');
            } else {
                alert("Aucun bien trouvé pour cette adresse.");
            }
        } catch (err) {
            console.error(err);
            alert("Erreur lors de la recherche.");
        } finally {
            setLoading(false);
        }
    };

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setLoading(true);
        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch(`${API_BASE}/analyze-dpe`, {
                method: 'POST',
                body: formData,
            });
            const result = await res.json();
            const d = result.data;

            setProperty({
                address: "Données extraites du PDF",
                surface: d.surface_habitable || 100,
                year: d.chauffage?.annee_installation || 1990,
                initialCep: d.consommation_primaire || 450,
                label: d.etiquette_actuelle || 'G'
            });
            setView('dashboard');
        } catch (err) {
            console.error(err);
            alert("Erreur lors de l'analyse du PDF.");
        } finally {
            setLoading(false);
        }
    };

    // --- Simulation Logic ---

    const simulation = useMemo(() => {
        if (!property) return null;
        let totalCost = 0;
        let cepReduction = 0;

        actions.filter(a => a.active).forEach(a => {
            const cost = a.costOverride || a.defaultCost;
            if (a.id === 'ite') totalCost += cost * (property.surface * 1.2);
            else if (a.id === 'iti') totalCost += cost * property.surface;
            else if (a.id === 'windows') totalCost += cost * 15;
            else totalCost += cost;
            cepReduction += a.impactKwh;
        });

        const newCep = Math.max(35, property.initialCep - cepReduction);
        const subsidies = totalCost * 0.35;
        const latentGain = property.surface * 250 * (actions.filter(a => a.active).length);

        const getLabel = (cep: number): DPEClass => {
            return DPE_THRESHOLDS.find(t => cep <= t.max)?.label || 'G';
        };

        return {
            newCep, totalCost, subsidies,
            restToPay: totalCost - subsidies,
            latentGain,
            currentLabel: property.label,
            newLabel: getLabel(newCep),
        };
    }, [actions, property]);

    // --- UI Views ---

    if (view === 'landing') {
        return (
            <div className="min-h-screen bg-white flex flex-col items-center justify-center p-6 font-sans">
                <div className="max-w-4xl w-full">
                    <header className="text-center mb-12">
                        <h1 className="text-5xl font-black text-slate-900 mb-4 tracking-tight">SPREA Simulation</h1>
                        <p className="text-xl text-slate-500 font-medium">L'intelligence artificielle au service de votre rénovation énergétique.</p>
                    </header>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {/* Option 1: Address Search */}
                        <div className="bg-slate-50 rounded-3xl p-10 border border-slate-100 flex flex-col justify-between hover:border-blue-200 transition-colors group">
                            <div>
                                <div className="bg-blue-600 w-14 h-14 rounded-2xl flex items-center justify-center text-white mb-6 shadow-lg shadow-blue-200">
                                    <Search size={28} />
                                </div>
                                <h2 className="text-2xl font-bold text-slate-800 mb-3">Recherche par adresse</h2>
                                <p className="text-slate-500 mb-8 leading-relaxed">
                                    Entrez votre adresse pour récupérer automatiquement les caractéristiques techniques de votre bien via l'ADEME.
                                </p>
                            </div>
                            <form onSubmit={handleAddressSearch} className="relative">
                                <input
                                    type="text"
                                    placeholder="Ex: 12 Rue de la Paix, Paris..."
                                    className="w-full h-16 bg-white border border-slate-200 rounded-2xl px-6 pr-14 text-lg font-medium focus:ring-4 focus:ring-blue-100 focus:border-blue-600 transition-all outline-none"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                />
                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="absolute right-2 top-2 h-12 w-12 bg-blue-600 text-white rounded-xl flex items-center justify-center hover:bg-blue-700 transition-colors disabled:bg-slate-300"
                                >
                                    {loading ? <Loader2 className="animate-spin" size={20} /> : <ArrowRight size={20} />}
                                </button>
                            </form>
                        </div>

                        {/* Option 2: PDF Upload */}
                        <div className="bg-slate-900 rounded-3xl p-10 flex flex-col justify-between hover:bg-slate-800 transition-colors group relative overflow-hidden">
                            <div className="relative z-10">
                                <div className="bg-white/10 w-14 h-14 rounded-2xl flex items-center justify-center text-blue-400 mb-6 border border-white/10">
                                    <FileText size={28} />
                                </div>
                                <h2 className="text-2xl font-bold text-white mb-3">Analyse de PDF (DPE)</h2>
                                <p className="text-slate-400 mb-8 leading-relaxed">
                                    Déposez votre diagnostic officiel. Notre IA extrait les données techniques (U-mur, chauffage) en quelques secondes.
                                </p>
                            </div>

                            <label className="relative z-10 cursor-pointer h-16 bg-white/10 border border-white/20 rounded-2xl flex items-center justify-center gap-3 text-white font-bold hover:bg-white/20 transition-all">
                                <Upload size={20} />
                                {loading ? "Analyse en cours..." : "Importer un DPE"}
                                <input type="file" className="hidden" accept="application/pdf" onChange={handleFileUpload} disabled={loading} />
                            </label>

                            <div className="absolute top-0 right-0 w-40 h-40 bg-blue-600/20 blur-3xl -mr-20 -mt-20 rounded-full" />
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // Dashboard View (Simplified reusable version of previous implementation)
    return (
        <div className="min-h-screen bg-slate-50 p-8 font-sans text-slate-900">
            <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-6 rounded-2xl bg-white p-8 shadow-sm border border-slate-100">
                <div className="flex items-center gap-5">
                    <div className="rounded-xl bg-slate-900 p-4 text-white shadow-lg">
                        <Home size={32} />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight text-slate-800 truncate max-w-md">{property?.address}</h1>
                        <div className="mt-1 flex items-center gap-3 text-slate-500 font-medium">
                            <span>{property?.surface} m²</span>
                            <span className="h-1 w-1 rounded-full bg-slate-300" />
                            <span>Construit en {property?.year}</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-6">
                    <div className="text-right">
                        <p className="text-sm font-semibold uppercase tracking-wider text-slate-400">Classe Actuelle</p>
                        <div className={`mt-1 flex items-center justify-center rounded-lg px-6 py-2 text-3xl font-black text-white shadow-xl`} style={{ backgroundColor: DPE_COLORS[property?.label || 'G'] }}>
                            {property?.label}
                        </div>
                    </div>
                    <button onClick={() => setView('landing')} className="text-sm font-bold text-slate-400 hover:text-blue-600">Nouvelle recherche</button>
                </div>
            </header>

            <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
                <aside className="lg:col-span-4 space-y-6">
                    <div className="rounded-2xl bg-white p-6 shadow-sm border border-slate-100">
                        <h3 className="mb-6 flex items-center gap-2 text-lg font-bold text-slate-800">
                            <Hammer size={20} className="text-blue-600" />
                            Actions de Rénovation
                        </h3>
                        <div className="space-y-4">
                            {actions.map((action) => (
                                <div key={action.id} className={`flex flex-col gap-3 rounded-xl border p-4 transition-all ${action.active ? 'border-blue-200 bg-blue-50/30' : 'border-slate-100'}`}>
                                    <div className="flex items-center justify-between">
                                        <span className={`font-bold ${action.active ? 'text-blue-700' : 'text-slate-700'}`}>{action.name}</span>
                                        <button onClick={() => setActions(actions.map(a => a.id === action.id ? { ...a, active: !a.active } : a))} className={`h-6 w-11 rounded-full relative ${action.active ? 'bg-blue-600' : 'bg-slate-200'}`}>
                                            <div className={`absolute top-1 left-1 h-4 w-4 rounded-full bg-white transition-transform ${action.active ? 'translate-x-5' : ''}`} />
                                        </button>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <div className="flex flex-1 items-center gap-2 rounded-lg bg-white px-3 py-2 border border-slate-100">
                                            <Zap size={14} className="text-slate-400" />
                                            <input type="number" defaultValue={action.defaultCost} className="w-full text-sm font-bold bg-transparent outline-none" />
                                            <span className="text-xs font-bold text-slate-400">€/u</span>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="mt-8 rounded-xl bg-slate-900 p-5 text-white">
                            <div className="text-sm opacity-80">Investissement Total</div>
                            <div className="mt-1 text-3xl font-black">{simulation?.totalCost.toLocaleString()} €</div>
                        </div>
                    </div>
                </aside>

                <main className="lg:col-span-8 space-y-8">
                    <section className="rounded-2xl bg-white p-8 shadow-sm border border-slate-100 text-center">
                        <div className="mb-8 flex items-end justify-between">
                            <h3 className="text-lg font-bold text-slate-800">Impact Performance Énergétique</h3>
                            <span className="text-sm font-black text-blue-600">{Math.round(simulation?.newCep || 0)} kWh/m².an</span>
                        </div>
                        <div className="relative mt-12 grid grid-cols-7 gap-1 h-14">
                            {DPE_THRESHOLDS.map((t) => (
                                <div key={t.label} className="relative flex items-center justify-center font-black text-white" style={{ backgroundColor: DPE_COLORS[t.label] }}>
                                    {t.label}
                                    {simulation?.currentLabel === t.label && <div className="absolute -top-10 flex flex-col items-center"><span className="rounded bg-slate-800 px-2 py-1 text-[10px] text-white">Avant</span><div className="h-2 w-0.5 bg-slate-800" /></div>}
                                    {simulation?.newLabel === t.label && <div className="absolute -bottom-10 flex flex-col items-center animate-bounce"><div className="h-2 w-0.5 bg-blue-600" /><span className="rounded bg-blue-600 px-2 py-1 text-[10px] text-white">Après</span></div>}
                                </div>
                            ))}
                        </div>
                    </section>

                    <section className="grid grid-cols-1 gap-6 md:grid-cols-2">
                        <div className="rounded-2xl bg-white p-7 shadow-sm border border-slate-100 border-l-4 border-l-green-500">
                            <div className="flex items-center gap-3 text-slate-400"><Euro size={18} /><span className="text-xs font-black uppercase tracking-widest">Aides & ROI</span></div>
                            <div className="mt-8 space-y-4">
                                <div className="flex justify-between items-center bg-slate-50 p-4 rounded-xl border border-slate-100">
                                    <span className="text-sm font-bold text-slate-600">MaPrimeRénov'</span>
                                    <span className="text-lg font-black text-green-600">+{simulation?.subsidies.toLocaleString()} €</span>
                                </div>
                                <div className="flex justify-between items-center bg-slate-900 p-4 rounded-xl shadow-lg">
                                    <span className="text-sm font-bold text-slate-300">Reste à Charge</span>
                                    <span className="text-xl font-black text-white">{simulation?.restToPay.toLocaleString()} €</span>
                                </div>
                            </div>
                        </div>

                        <div className="rounded-2xl bg-white p-7 shadow-sm border border-slate-100 border-l-4 border-l-blue-600">
                            <div className="flex items-center gap-3 text-slate-400"><TrendingUp size={18} /><span className="text-xs font-black uppercase tracking-widest">Valorisation</span></div>
                            <div className="mt-auto pt-8">
                                <div className="text-4xl font-black text-blue-700">+{simulation?.latentGain.toLocaleString()} €</div>
                                <p className="mt-2 text-sm font-bold text-slate-500">Plus-value verte estimée sur le marché local.</p>
                            </div>
                        </div>
                    </section>
                </main>
            </div>
        </div>
    );
}
