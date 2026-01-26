import React, { useState, useEffect } from 'react';
import {
    TrendingUp,
    Euro,
    Home,
    Zap,
    Hammer,
    Search,
    FileText,
    Loader2,
    ArrowRight,
    MapPin,
    Users
} from 'lucide-react';

// --- Types ---

type DPEClass = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';

interface PropertyData {
    address: string;
    shab: number;
    construction_year?: number;
    dpe_class_current: DPEClass;
    consumption_level?: number;
    walls: any[];
    windows: any[];
    systems: any[];
}

interface SimulationResult {
    initial_dpe: DPEClass;
    new_dpe: DPEClass;
    initial_cep: number;
    new_cep: number;
    total_cost: number;
    subsidies: number;
    rest_to_pay: number;
    gain_classes: number;
    applied_works: string[];
    profile: string;
}

const DPE_COLORS: Record<DPEClass, string> = {
    A: '#31a354', B: '#74c476', C: '#a1d99b', D: '#feb24c', E: '#fd8d3c', F: '#f03b20', G: '#bd0026',
};

const DPE_LABELS: DPEClass[] = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];

const API_BASE = import.meta.env.VITE_API_URL || "https://sprea.onrender.com";

const WORKS_CATALOG = [
    { id: 'ite_pse', name: 'ITE PSE (Standard)', category: 'Isolation' },
    { id: 'ite_bois', name: 'ITE Fibre de Bois (Eco)', category: 'Isolation' },
    { id: 'iti_ossature', name: 'ITI Ossature Métallique', category: 'Isolation' },
    { id: 'combles', name: 'Isolation Combles', category: 'Isolation' },
    { id: 'pac_air_eau', name: 'Pompe à Chaleur Air/Eau', category: 'Chauffage' },
    { id: 'windows_pvc', name: 'Fenêtres Double Vitrage PVC', category: 'Menuiserie' },
];

// --- Main Component ---

export default function SimulationDashboard() {
    const [view, setView] = useState<'landing' | 'dashboard'>('landing');
    const [loading, setLoading] = useState(false);
    const [simulating, setSimulating] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [property, setProperty] = useState<PropertyData | null>(null);
    const [rfr, setRfr] = useState(25000);
    const [postcode, setPostcode] = useState("59000");
    const [selectedWorks, setSelectedWorks] = useState<string[]>([]);
    const [simulation, setSimulation] = useState<SimulationResult | null>(null);

    // --- API Handlers ---

    const handleAddressSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!searchQuery) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/search-address?q=${encodeURIComponent(searchQuery)}`);
            const data = await res.json();
            if (data.results && data.results.length > 0) {
                const raw = data.results[0];
                setProperty(raw);
                setPostcode(raw.address.match(/\d{5}/)?.[0] || "59000");
                setView('dashboard');
            } else {
                alert("Aucun bien trouvé.");
            }
        } catch (err: any) {
            console.error(err);
            alert(`Erreur: ${err.message}`);
        } finally {
            setLoading(false);
        }
    };

    const runSimulation = async () => {
        if (!property) return;
        setSimulating(true);
        try {
            const res = await fetch(`${API_BASE}/api/simulate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    property_data: property,
                    selected_works: selectedWorks,
                    rfr: rfr,
                    postcode: postcode
                }),
            });
            const data = await res.json();
            setSimulation(data);
        } catch (err) {
            console.error(err);
        } finally {
            setSimulating(false);
        }
    };

    useEffect(() => {
        if (property && selectedWorks.length > 0) {
            runSimulation();
        } else {
            setSimulation(null);
        }
    }, [selectedWorks, rfr, postcode]);

    const toggleWork = (id: string) => {
        setSelectedWorks(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
    };

    if (view === 'landing') {
        return (
            <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 font-sans">
                <div className="max-w-4xl w-full">
                    <header className="text-center mb-12">
                        <div className="inline-block px-4 py-1.5 mb-4 bg-blue-100 text-blue-700 rounded-full text-sm font-bold tracking-wide uppercase">
                            Millésime 2025
                        </div>
                        <h1 className="text-6xl font-black text-slate-900 mb-4 tracking-tight">SPREA</h1>
                        <p className="text-xl text-slate-500 font-medium max-w-2xl mx-auto leading-relaxed">
                            Simulateur de rénovation haute fidélité. Coûts localisés, aides MaPrimeRénov' et impact DPE certifié 3CL.
                        </p>
                    </header>

                    <div className="bg-white rounded-[2.5rem] p-10 shadow-2xl shadow-blue-900/5 border border-slate-100">
                        <form onSubmit={handleAddressSearch} className="relative group">
                            <div className="absolute left-6 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors">
                                <Search size={28} />
                            </div>
                            <input
                                type="text"
                                placeholder="Entrez une adresse pour commencer..."
                                className="w-full h-20 bg-slate-50 border-2 border-slate-100 rounded-3xl px-20 text-xl font-bold focus:bg-white focus:border-blue-600 focus:ring-4 focus:ring-blue-100 transition-all outline-none"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                            <button
                                type="submit"
                                disabled={loading}
                                className="absolute right-4 top-4 h-12 px-8 bg-slate-900 text-white rounded-2xl font-bold flex items-center gap-3 hover:translate-x-1 transition-all active:scale-95 disabled:bg-slate-300 shadow-xl"
                            >
                                {loading ? <Loader2 className="animate-spin" size={20} /> : "Calculer"}
                                {!loading && <ArrowRight size={20} />}
                            </button>
                        </form>

                        <div className="mt-8 flex items-center justify-center gap-8 text-slate-400 font-bold text-sm uppercase tracking-widest">
                            <span className="flex items-center gap-2"><MapPin size={16} /> 36 000 communes</span>
                            <span className="flex items-center gap-2"><Euro size={16} /> Aides 2025</span>
                            <span className="flex items-center gap-2"><Zap size={16} /> Méthode 3CL</span>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 p-6 lg:p-10 font-sans text-slate-900">
            <header className="max-w-[1440px] mx-auto mb-10 flex flex-col md:flex-row md:items-center justify-between gap-8 rounded-[2rem] bg-white p-8 shadow-xl shadow-slate-200/50 border border-slate-100">
                <div className="flex items-center gap-6">
                    <div className="rounded-2xl bg-slate-900 p-5 text-white shadow-2xl">
                        <Home size={32} />
                    </div>
                    <div>
                        <h1 className="text-2xl font-black tracking-tight text-slate-800">{property?.address}</h1>
                        <div className="mt-2 flex items-center gap-4 text-slate-500 font-bold text-sm">
                            <span className="bg-slate-100 px-3 py-1 rounded-full">{property?.shab} m²</span>
                            <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
                            <span>Construit en {property?.construction_year || 'N/A'}</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-8 px-8 border-l border-slate-100">
                    <div className="text-right">
                        <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">Note Actuelle</p>
                        <div className="px-8 py-3 rounded-2xl text-4xl font-black text-white shadow-xl" style={{ backgroundColor: DPE_COLORS[property?.dpe_class_current || 'G'] }}>
                            {property?.dpe_class_current}
                        </div>
                    </div>
                    <button onClick={() => setView('landing')} className="h-12 w-12 rounded-full border-2 border-slate-100 flex items-center justify-center text-slate-400 hover:text-blue-600 hover:border-blue-100 transition-all">
                        <Search size={20} />
                    </button>
                </div>
            </header>

            <div className="max-w-[1440px] mx-auto grid grid-cols-1 gap-10 lg:grid-cols-12">
                {/* Controls */}
                <aside className="lg:col-span-4 space-y-8">
                    <section className="rounded-[2rem] bg-white p-8 shadow-lg border border-slate-100">
                        <h3 className="mb-6 flex items-center gap-3 text-lg font-black text-slate-800 uppercase tracking-tight">
                            <Users size={20} className="text-blue-600" />
                            Profil Client
                        </h3>
                        <div className="space-y-6">
                            <div>
                                <label className="block text-sm font-black text-slate-400 uppercase tracking-widest mb-3">Revenu Fiscal (RFR)</label>
                                <div className="relative">
                                    <input
                                        type="number"
                                        value={rfr}
                                        onChange={(e) => setRfr(parseInt(e.target.value))}
                                        className="w-full h-14 bg-slate-50 border-2 border-slate-100 rounded-xl px-4 text-lg font-black focus:border-blue-600 transition-all outline-none"
                                    />
                                    <Euro className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-300" size={20} />
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-black text-slate-400 uppercase tracking-widest mb-3">Département</label>
                                <input
                                    type="text"
                                    value={postcode}
                                    onChange={(e) => setPostcode(e.target.value)}
                                    className="w-full h-14 bg-slate-50 border-2 border-slate-100 rounded-xl px-4 text-lg font-black focus:border-blue-600 transition-all outline-none"
                                />
                            </div>
                        </div>
                    </section>

                    <section className="rounded-[2rem] bg-white p-8 shadow-lg border border-slate-100">
                        <h3 className="mb-6 flex items-center gap-3 text-lg font-black text-slate-800 uppercase tracking-tight">
                            <Hammer size={20} className="text-blue-600" />
                            Actions 2025
                        </h3>
                        <div className="space-y-3">
                            {WORKS_CATALOG.map((work) => (
                                <button
                                    key={work.id}
                                    onClick={() => toggleWork(work.id)}
                                    className={`w-full flex items-center justify-between p-5 rounded-2xl border-2 transition-all font-bold text-left ${selectedWorks.includes(work.id)
                                        ? 'border-blue-600 bg-blue-50/50 text-blue-900 shadow-md'
                                        : 'border-slate-100 hover:border-slate-200 text-slate-600'
                                        }`}
                                >
                                    <div>
                                        <p className="text-sm opacity-50 mb-0.5">{work.category}</p>
                                        {work.name}
                                    </div>
                                    <div className={`h-6 w-6 rounded-lg flex items-center justify-center border-2 transition-all ${selectedWorks.includes(work.id) ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-200'
                                        }`}>
                                        {selectedWorks.includes(work.id) && <Zap size={14} fill="white" />}
                                    </div>
                                </button>
                            ))}
                        </div>
                    </section>
                </aside>

                {/* Results */}
                <main className="lg:col-span-8 space-y-10">
                    {/* Performance Scale */}
                    <section className="rounded-[2rem] bg-white p-10 shadow-lg border border-slate-100">
                        <div className="mb-12 flex items-center justify-between">
                            <h3 className="text-xl font-black text-slate-800 tracking-tight">IMPACT PERFORMANCE</h3>
                            {simulating && <Loader2 className="animate-spin text-blue-600" size={24} />}
                        </div>

                        <div className="relative mt-20 px-4">
                            <div className="grid grid-cols-7 gap-1 h-20 rounded-2xl border-4 border-white shadow-2xl overflow-hidden">
                                {DPE_LABELS.map((label) => (
                                    <div key={label} className="relative flex items-center justify-center text-2xl font-black text-white/50" style={{ backgroundColor: DPE_COLORS[label] }}>
                                        {label}
                                        {property?.dpe_class_current === label && (
                                            <div className="absolute -top-16 left-1/2 -translate-x-1/2 flex flex-col items-center">
                                                <div className="bg-slate-800 text-white text-[10px] font-black px-2.5 py-1.5 rounded-lg mb-2 shadow-lg">INITIAL</div>
                                                <div className="h-6 w-1 bg-slate-800 rounded-full" />
                                            </div>
                                        )}
                                        {simulation?.new_dpe === label && (
                                            <div className="absolute -bottom-16 left-1/2 -translate-x-1/2 flex flex-col items-center">
                                                <div className="h-6 w-1 bg-blue-600 rounded-full mb-2" />
                                                <div className="bg-blue-600 text-white text-[10px] font-black px-2.5 py-1.5 rounded-lg shadow-xl animate-bounce">PROJETÉ</div>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="mt-24 grid grid-cols-2 gap-8">
                            <div className="bg-slate-50 p-6 rounded-2xl border border-slate-100">
                                <p className="text-xs font-black text-slate-400 uppercase mb-2">Consommation Initiale</p>
                                <p className="text-3xl font-black text-slate-800">{property?.consumption_level?.toLocaleString()} <span className="text-lg opacity-40">kWh/m².an</span></p>
                            </div>
                            <div className="bg-blue-50/50 p-6 rounded-2xl border border-blue-100">
                                <p className="text-xs font-black text-blue-400 uppercase mb-2">Consommation Projetée</p>
                                <p className="text-3xl font-black text-blue-700">{simulation?.new_cep ? Math.round(simulation.new_cep) : '---'} <span className="text-lg opacity-40">kWh/m².an</span></p>
                            </div>
                        </div>
                    </section>

                    {/* Financials */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                        <section className="rounded-[2.5rem] bg-slate-900 p-10 text-white shadow-2xl relative overflow-hidden">
                            <div className="relative z-10">
                                <div className="flex items-center gap-3 text-blue-400 mb-8">
                                    <Euro size={20} />
                                    <span className="text-sm font-black uppercase tracking-widest">INGÉNIERIE FINANCIÈRE</span>
                                </div>
                                <div className="space-y-8">
                                    <div>
                                        <p className="text-xs font-bold text-slate-400 uppercase mb-1">Montant Brut (Localisé)</p>
                                        <p className="text-4xl font-black">{simulation?.total_cost?.toLocaleString() || 0} €</p>
                                    </div>
                                    <div className="flex items-center gap-4 bg-white/10 p-4 rounded-2xl border border-white/10">
                                        <div className="h-10 w-10 rounded-xl bg-green-500 flex items-center justify-center text-white"><Zap size={20} /></div>
                                        <div>
                                            <p className="text-xs font-bold text-slate-400 uppercase">MaPrimeRénov' 2025</p>
                                            <p className="text-xl font-black text-green-400">-{simulation?.subsidies?.toLocaleString() || 0} €</p>
                                        </div>
                                    </div>
                                    <div className="pt-6 border-t border-white/10">
                                        <p className="text-xs font-bold text-slate-400 uppercase mb-1">RESTE À CHARGE</p>
                                        <p className="text-5xl font-black text-blue-400">{simulation?.rest_to_pay?.toLocaleString() || 0} €</p>
                                    </div>
                                </div>
                            </div>
                            <div className="absolute top-0 right-0 w-64 h-64 bg-blue-600/20 blur-[100px] -mr-32 -mt-32 rounded-full" />
                        </section>

                        <section className="rounded-[2.5rem] bg-white p-10 shadow-xl border border-slate-100 flex flex-col">
                            <div className="flex items-center gap-3 text-slate-400 mb-8">
                                <TrendingUp size={20} />
                                <span className="text-sm font-black uppercase tracking-widest">VALORISATION VERTE</span>
                            </div>
                            <div className="flex-1 flex flex-col justify-center">
                                <div className="text-6xl font-black text-blue-700">
                                    +{(simulation?.gain_classes ? simulation.gain_classes * 15000 : 0).toLocaleString()} €
                                </div>
                                <p className="mt-4 text-slate-500 font-bold leading-relaxed">
                                    Gain de valeur estimé pour un saut de {simulation?.gain_classes || 0} classes à {postcode}.
                                </p>
                            </div>
                            <div className="mt-8 p-6 bg-slate-50 rounded-[1.5rem] text-sm font-bold text-slate-400 flex items-start gap-3">
                                <FileText size={18} className="mt-0.5" />
                                Simulation basée sur le millésime 2025, profil ANAH {simulation?.profile || 'N/A'}.
                            </div>
                        </section>
                    </div>
                </main>
            </div>
        </div>
    );
}
