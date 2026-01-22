import React, { useState, useMemo, useEffect } from 'react';
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
    ArrowRight,
    MapPin,
    AlertTriangle,
    Building2,
    Building
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
    buildingType: string;
}

const DPE_COLORS: Record<DPEClass, string> = {
    A: '#31a354', B: '#74c476', C: '#a1d99b', D: '#feb24c', E: '#fd8d3c', F: '#f03b20', G: '#bd0026',
};

const DPE_THRESHOLDS: { label: DPEClass; max: number }[] = [
    { label: 'A', max: 70 }, { label: 'B', max: 110 }, { label: 'C', max: 180 },
    { label: 'D', max: 250 }, { label: 'E', max: 330 }, { label: 'F', max: 420 }, { label: 'G', max: 999 },
];

const API_BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8001";

// --- Main Component ---

export default function App() {
    const [view, setView] = useState<'landing' | 'results' | 'dashboard'>('landing');
    const [loading, setLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [suggestions, setSuggestions] = useState<any[]>([]);
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const [property, setProperty] = useState<PropertyData | null>(null);
    const [error, setError] = useState<string | null>(null);

    const [actions, setActions] = useState<RetrofitAction[]>([
        { id: 'iti', name: 'Isolation Combles', defaultCost: 35, impactKwh: 45, active: false },
        { id: 'ite', name: 'Isolation Murs (ITE)', defaultCost: 160, impactKwh: 120, active: false },
        { id: 'windows', name: 'Double Vitrage', defaultCost: 450, impactKwh: 30, active: false },
        { id: 'heatpump', name: 'Changement -> PAC', defaultCost: 12000, impactKwh: 210, active: false },
    ]);

    // --- Autocomplete Logic ---
    useEffect(() => {
        if (searchQuery.length < 3) {
            setSuggestions([]);
            return;
        }
        const timer = setTimeout(async () => {
            try {
                const res = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(searchQuery)}&limit=5`);
                const data = await res.json();
                setSuggestions(data.features || []);
            } catch (err) {
                console.error("Autocomplete error:", err);
            }
        }, 300);
        return () => clearTimeout(timer);
    }, [searchQuery]);

    // --- API Handlers ---

    const handleSearch = async (address: string) => {
        setLoading(true);
        setError(null);
        setSuggestions([]);
        console.log("[SPREA] Searching address:", address);
        try {
            const res = await fetch(`${API_BASE}/search-address?q=${encodeURIComponent(address)}`, {
                mode: 'cors'
            });
            if (!res.ok) throw new Error(`Backend Error: ${res.statusText}`);

            const data = await res.json();
            console.log("[SPREA] Search results count:", data.count);

            if (data.results && data.results.length > 0) {
                setSearchResults(data.results);
                setView('results');
            } else {
                setError("Aucun bien trouvé pour cette adresse dans la base ADEME.");
            }
        } catch (err: any) {
            console.error("[SPREA] Search API failed:", err);
            setError(`Le serveur de simulation est injoignable (${err.message}). Assurez-vous que pdf_parser.py tourne sur le port 8000.`);
        } finally {
            setLoading(false);
        }
    };

    const selectProperty = (raw: any) => {
        setProperty({
            address: raw.address,
            surface: raw.shab || 100,
            year: raw.construction_year || 1980,
            initialCep: raw.consumption_level || 420,
            label: (raw.dpe_class_current as DPEClass) || 'G',
            buildingType: raw.building_type || 'Maison'
        });
        setView('dashboard');
    };

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setLoading(true);
        setError(null);
        console.log("[SPREA] Uploading PDF:", file.name);
        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch(`${API_BASE}/analyze-dpe`, {
                method: 'POST',
                body: formData,
                mode: 'cors'
            });
            if (!res.ok) throw new Error(`Upload Error: ${res.statusText}`);

            const result = await res.json();
            console.log("[SPREA] PDF result:", result);
            const d = result.data;

            setProperty({
                address: "Données extraites du PDF",
                surface: d.surface_habitable || 100,
                year: d.chauffage?.annee_installation || 1990,
                initialCep: d.consommation_primaire || 450,
                label: (d.etiquette_actuelle as DPEClass) || 'G',
                buildingType: 'Maison' // Default from PDF if not found
            });
            setView('dashboard');
        } catch (err: any) {
            console.error("[SPREA] PDF API failed:", err);
            setError(`Échec de l'analyse du PDF (${err.message}).`);
        } finally {
            setLoading(false);
        }
    };

    // --- Simulation Logic ---

    const filteredActions = useMemo(() => {
        if (!property) return actions;
        // If it's an apartment, "Isolation Combles" is only relevant for top floor.
        // We don't have floor info yet, so let's just mark it as "Condo-aware"
        if (property.buildingType.toLowerCase().includes('appartement')) {
            return actions.map(a => a.id === 'iti' ? { ...a, name: 'Isolation Toiture (Copropriété)' } : a);
        }
        return actions;
    }, [actions, property]);

    const simulation = useMemo(() => {
        if (!property) return null;
        let totalCost = 0;
        let cepReduction = 0;

        filteredActions.filter(a => a.active).forEach(a => {
            const cost = a.costOverride || a.defaultCost;
            if (a.id === 'ite') totalCost += cost * (property.surface * 1.2);
            else if (a.id === 'iti') totalCost += cost * property.surface;
            else if (a.id === 'windows') totalCost += cost * 15;
            else totalCost += cost;
            cepReduction += a.impactKwh;
        });

        const newCep = Math.max(35, property.initialCep - cepReduction);
        const subsidies = totalCost * 0.35;
        const latentGain = property.surface * 250 * (filteredActions.filter(a => a.active).length);

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
    }, [filteredActions, property]);

    // --- UI Views ---

    if (view === 'landing') {
        return (
            <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 font-sans">
                <div className="max-w-4xl w-full">
                    <header className="text-center mb-16">
                        <h1 className="text-7xl font-black text-slate-900 mb-6 tracking-tight">SPREA</h1>
                        <p className="text-2xl text-slate-500 font-medium tracking-tight">L'intelligence énergétique au service de l'immobilier.</p>
                    </header>

                    {error && (
                        <div className="mb-8 p-6 bg-red-50 border border-red-100 rounded-2xl flex items-start gap-4 text-red-700 font-medium">
                            <AlertTriangle size={24} className="shrink-0 mt-0.5" />
                            <div>
                                <p className="font-bold">Erreur de connexion</p>
                                <p className="text-sm opacity-90">{error}</p>
                            </div>
                        </div>
                    )}

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                        <div className="bg-white rounded-[2.5rem] p-10 shadow-xl shadow-slate-200/50 border border-slate-100 flex flex-col justify-between">
                            <div>
                                <div className="bg-blue-600 w-16 h-16 rounded-2xl flex items-center justify-center text-white mb-8 shadow-lg shadow-blue-200">
                                    <MapPin size={32} />
                                </div>
                                <h2 className="text-3xl font-bold text-slate-800 mb-4">Par adresse</h2>
                                <p className="text-lg text-slate-500 mb-10 leading-relaxed">
                                    Récupérez les données ADEME officielles pour n'importe quel bien en France.
                                </p>
                            </div>

                            <div className="relative">
                                <div className="flex items-center bg-slate-100 rounded-2xl px-6 h-16 border-2 border-transparent focus-within:border-blue-600 focus-within:bg-white transition-all">
                                    <Search size={24} className="text-slate-400 mr-4" />
                                    <input
                                        type="text"
                                        placeholder="Tapez l'adresse..."
                                        className="flex-1 bg-transparent text-lg font-bold outline-none text-slate-900"
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                    />
                                    {loading && <Loader2 className="animate-spin text-blue-600" size={24} />}
                                </div>

                                {suggestions.length > 0 && (
                                    <div className="absolute top-full left-0 right-0 mt-3 bg-white border border-slate-100 rounded-2xl shadow-2xl overflow-hidden z-20">
                                        {suggestions.map((s, idx) => (
                                            <button
                                                key={idx}
                                                onClick={() => handleSearch(s.properties.label)}
                                                className="w-full text-left px-6 py-4 hover:bg-slate-50 flex items-center gap-4 transition-colors border-b border-slate-50 last:border-0"
                                            >
                                                <MapPin size={18} className="text-slate-400" />
                                                <div>
                                                    <p className="font-bold text-slate-800">{s.properties.label}</p>
                                                    <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{s.properties.context}</p>
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="bg-slate-900 rounded-[2.5rem] p-10 shadow-2xl shadow-slate-900/20 flex flex-col justify-between relative overflow-hidden group">
                            <div className="relative z-10">
                                <div className="bg-white/10 w-16 h-16 rounded-2xl flex items-center justify-center text-blue-400 mb-8 border border-white/10">
                                    <FileText size={32} />
                                </div>
                                <h2 className="text-3xl font-bold text-white mb-4">Analyse PDF</h2>
                                <p className="text-lg text-slate-400 mb-10 leading-relaxed">
                                    Importez votre rapport DPE. Notre IA extrait les valeurs techniques instantanément.
                                </p>
                            </div>

                            <label className="relative z-10 cursor-pointer h-16 bg-blue-600 rounded-2xl flex items-center justify-center gap-3 text-white text-xl font-black hover:bg-blue-700 transition-all shadow-lg shadow-blue-900/40 active:scale-95">
                                <Upload size={24} />
                                {loading ? "Chargement..." : "Upload DPE"}
                                <input type="file" className="hidden" accept="application/pdf" onChange={handleFileUpload} disabled={loading} />
                            </label>

                            <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/10 blur-[100px] -mr-32 -mt-32 rounded-full" />
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    if (view === 'results') {
        return (
            <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 font-sans">
                <div className="max-w-2xl w-full">
                    <div className="mb-8 flex items-center justify-between">
                        <h2 className="text-3xl font-black text-slate-800">Résultats ADEME</h2>
                        <button onClick={() => setView('landing')} className="text-blue-600 font-bold hover:underline">Nouvelle recherche</button>
                    </div>
                    <p className="text-slate-500 mb-6 font-medium">Plusieurs logements trouvés à cette adresse. Choisissez le vôtre :</p>
                    <div className="space-y-4">
                        {searchResults.map((res, idx) => (
                            <button
                                key={idx}
                                onClick={() => selectProperty(res)}
                                className="w-full bg-white p-6 rounded-3xl border border-slate-100 shadow-sm hover:shadow-md hover:border-blue-200 transition-all text-left flex items-start justify-between group"
                            >
                                <div className="flex items-start gap-4">
                                    <div className="bg-slate-50 p-3 rounded-xl group-hover:bg-blue-50">
                                        {res.building_type?.toLowerCase().includes('appartement') ? <Building size={24} className="text-slate-400 group-hover:text-blue-600" /> : <Home size={24} className="text-slate-400 group-hover:text-blue-600" />}
                                    </div>
                                    <div>
                                        <p className="font-bold text-slate-800 text-lg leading-tight">{res.address}</p>
                                        <p className="text-sm font-bold text-slate-400 mt-1 uppercase tracking-wider">{res.building_type || 'Bâtiment'} • {res.shab} m² • {res.construction_year || 'Année inconnue'}</p>
                                        <p className="text-xs font-medium text-slate-400 mt-2 italic">DPE n° {res.ademe_dpe_number || 'N/A'}</p>
                                    </div>
                                </div>
                                <div className={`px-4 py-2 rounded-lg text-xl font-black text-white shadow-lg`} style={{ backgroundColor: DPE_COLORS[res.dpe_class_current as DPEClass] || '#cbd5e1' }}>
                                    {res.dpe_class_current || '?'}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 p-8 font-sans text-slate-900">
            <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-6 rounded-[2.5rem] bg-white p-10 shadow-sm border border-slate-100">
                <div className="flex items-center gap-8">
                    <div className="rounded-2xl bg-slate-900 p-6 text-white shadow-2xl">
                        {property?.buildingType.toLowerCase().includes('appartement') ? <Building2 size={40} /> : <Home size={40} />}
                    </div>
                    <div>
                        <h1 className="text-3xl font-black text-slate-800 tracking-tight truncate max-w-xl">{property?.address}</h1>
                        <div className="mt-3 flex items-center gap-5 text-slate-400 font-bold text-lg">
                            <span className="flex items-center gap-2"><MapPin size={18} /> {property?.buildingType}</span>
                            <span className="h-1.5 w-1.5 rounded-full bg-slate-200" />
                            <span>{property?.surface} m²</span>
                            <span className="h-1.5 w-1.5 rounded-full bg-slate-200" />
                            <span>Construit en {property?.year}</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-10">
                    <div className="text-right">
                        <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">Classe Actuelle</p>
                        <div className={`flex items-center justify-center rounded-2xl px-10 py-4 text-5xl font-black text-white shadow-xl transition-all hover:scale-105`} style={{ backgroundColor: DPE_COLORS[property?.label || 'G'] }}>
                            {property?.label}
                        </div>
                    </div>
                    <button onClick={() => setView('landing')} className="h-16 px-8 rounded-2xl bg-slate-100 text-slate-500 font-bold hover:bg-blue-50 hover:text-blue-600 transition-all border border-transparent hover:border-blue-100">Nouvelle recherche</button>
                </div>
            </header>

            <div className="grid grid-cols-1 gap-10 lg:grid-cols-12">
                <aside className="lg:col-span-4 space-y-10">
                    <div className="rounded-[2.5rem] bg-white p-10 shadow-sm border border-slate-100">
                        <h3 className="mb-10 flex items-center gap-4 text-2xl font-black text-slate-800">
                            <Hammer size={28} className="text-blue-600" />
                            Simuler des travaux
                        </h3>
                        <div className="space-y-4">
                            {filteredActions.map((action) => (
                                <button
                                    key={action.id}
                                    onClick={() => setActions(actions.map(a => a.id === action.id ? { ...a, active: !a.active } : a))}
                                    className={`w-full flex items-center justify-between p-7 rounded-3xl border-2 transition-all duration-300 ${action.active ? 'border-blue-600 bg-blue-50/50 shadow-inner' : 'border-slate-50 bg-white hover:border-slate-200'}`}
                                >
                                    <div className="flex flex-col items-start gap-1">
                                        <span className={`text-xl font-bold ${action.active ? 'text-blue-700' : 'text-slate-700'}`}>{action.name}</span>
                                        <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">{action.defaultCost} € base</span>
                                    </div>
                                    <div className={`h-9 w-16 rounded-full relative transition-colors ${action.active ? 'bg-blue-600' : 'bg-slate-200'}`}>
                                        <div className={`absolute top-1 left-1 h-7 w-7 rounded-full bg-white transition-transform duration-300 shadow-md ${action.active ? 'translate-x-7' : ''}`} />
                                    </div>
                                </button>
                            ))}
                        </div>
                        <div className="mt-12 rounded-3xl bg-slate-900 p-10 text-white shadow-2xl relative overflow-hidden">
                            <div className="relative z-10">
                                <div className="text-xs font-black uppercase tracking-widest opacity-50 mb-3">Total Investissement</div>
                                <div className="text-5xl font-black tracking-tighter">{simulation?.totalCost.toLocaleString()} €</div>
                            </div>
                            <ChevronRight className="absolute -right-4 -bottom-4 text-white opacity-5 w-48 h-48" />
                        </div>
                    </div>
                </aside>

                <main className="lg:col-span-8 space-y-10">
                    <section className="rounded-[2.5rem] bg-white p-14 shadow-sm border border-slate-100 relative overflow-hidden">
                        <div className="mb-14 flex items-center justify-between relative z-10">
                            <div>
                                <h3 className="text-3xl font-black text-slate-800">Cible Énergétique</h3>
                                <p className="text-slate-400 font-bold mt-1">Estimation 3CL basée sur vos choix.</p>
                            </div>
                            <div className="flex flex-col items-end">
                                <span className="text-6xl font-black text-blue-600 tracking-tighter">{Math.round(simulation?.newCep || 0)}</span>
                                <span className="text-sm font-black text-slate-400 tracking-widest uppercase mt-1">kWh/m².an</span>
                            </div>
                        </div>
                        <div className="relative mt-20 grid grid-cols-7 gap-3 h-24 z-10">
                            {DPE_THRESHOLDS.map((t) => (
                                <div key={t.label} className="relative flex items-center justify-center font-black text-white text-3xl rounded-xl shadow-lg transition-transform hover:scale-105" style={{ backgroundColor: DPE_COLORS[t.label as DPEClass] }}>
                                    {t.label}
                                    {simulation?.currentLabel === t.label && (
                                        <div className="absolute -top-14 flex flex-col items-center">
                                            <span className="rounded-full bg-slate-800 px-5 py-2 text-xs font-black text-white shadow-xl">ACTUEL</span>
                                            <div className="h-5 w-1.5 bg-slate-800" />
                                        </div>
                                    )}
                                    {simulation?.newLabel === t.label && (
                                        <div className="absolute -bottom-16 flex flex-col items-center animate-bounce">
                                            <div className="h-5 w-1.5 bg-blue-600" />
                                            <span className="rounded-full bg-blue-600 px-5 py-2 text-xs font-black text-white shadow-2xl">CIBLE</span>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                        <div className="absolute top-0 right-0 w-96 h-96 bg-slate-50 rounded-full blur-[120px] -mr-48 -mt-48" />
                    </section>

                    <section className="grid grid-cols-1 gap-10 md:grid-cols-2">
                        <div className="rounded-[2.5rem] bg-white p-12 shadow-sm border border-slate-100 border-l-[16px] border-l-green-500 flex flex-col justify-between">
                            <div className="flex items-center gap-4 text-slate-400 mb-12"><Euro size={32} /><span className="text-sm font-black uppercase tracking-widest">Plan de Financement</span></div>
                            <div className="space-y-8">
                                <div className="flex justify-between items-center bg-slate-50 p-8 rounded-[2rem] border border-slate-100">
                                    <span className="text-xl font-bold text-slate-600">Subvention estimée</span>
                                    <span className="text-3xl font-black text-green-600">+{simulation?.subsidies.toLocaleString()} €</span>
                                </div>
                                <div className="flex justify-between items-center bg-slate-900 p-10 rounded-[2rem] shadow-2xl">
                                    <span className="text-xl font-bold text-slate-400">Reste à charge</span>
                                    <span className="text-4xl font-black text-white">{simulation?.restToPay.toLocaleString()} €</span>
                                </div>
                            </div>
                        </div>

                        <div className="rounded-[2.5rem] bg-white p-12 shadow-sm border border-slate-100 border-l-[16px] border-l-blue-600 flex flex-col justify-between">
                            <div className="flex items-center gap-4 text-slate-400 mb-12"><TrendingUp size={32} /><span className="text-sm font-black uppercase tracking-widest">Plus-value Immobilière</span></div>
                            <div className="mb-10">
                                <div className="text-7xl font-black text-blue-700 tracking-tighter">+{simulation?.latentGain.toLocaleString()} €</div>
                                <p className="mt-6 text-xl font-bold text-slate-500 leading-relaxed italic opacity-80">
                                    "Estimation de la valorisation de votre patrimoine suite à l'amélioration du label."
                                </p>
                            </div>
                            <div className="mt-auto p-5 bg-blue-50 rounded-2xl flex items-center gap-4 text-blue-600 font-black text-sm uppercase">
                                <Info size={20} /> Retour sur investissement : ~8 ans (TRI)
                            </div>
                        </div>
                    </section>
                </main>
            </div>
        </div>
    );
}
