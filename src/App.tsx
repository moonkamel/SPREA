import { useState, useMemo, useEffect } from 'react';
import {
    TrendingUp,
    Euro,
    Home,
    ChevronRight,
    Info,
    Search,
    Loader2,
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
    impactGes: number; // kgCO2 reduction per m2 per year
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
    heatingType?: string;
    gesLabel?: string;
    gesValue?: number;
    wallMaterials?: string;
    glassType?: string;
    roofIsolation?: string;
    floorIsolation?: string;
    heatingDetail?: string;
}

const DPE_COLORS: Record<DPEClass, string> = {
    A: '#31a354', B: '#74c476', C: '#a1d99b', D: '#feb24c', E: '#fd8d3c', F: '#f03b20', G: '#bd0026',
};
const DPE_COLORS_BG: Record<string, string> = DPE_COLORS;

const DPE_THRESHOLDS_BASE: { label: DPEClass; cep: number; ges: number }[] = [
    { label: 'A', cep: 70, ges: 6 },
    { label: 'B', cep: 110, ges: 11 },
    { label: 'C', cep: 180, ges: 30 },
    { label: 'D', cep: 250, ges: 50 },
    { label: 'E', cep: 330, ges: 70 },
    { label: 'F', cep: 420, ges: 100 },
    { label: 'G', cep: 999, ges: 999 },
];

const getAdjustedThresholds = (surface: number) => {
    // July 2024 Small Surface Adjustment (simplified approximation for <40m2)
    const factor = surface < 40 ? 1 + (40 - surface) * 0.04 : 1;
    return DPE_THRESHOLDS_BASE.map(t => ({
        label: t.label,
        max: Math.round(t.cep * factor),
        maxGes: t.ges
    }));
};


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
        { id: 'iti', name: 'Isolation Toiture', defaultCost: 45, impactKwh: 65, impactGes: 4, active: false },
        { id: 'ite', name: 'Isolation Murs (ITE)', defaultCost: 180, impactKwh: 140, impactGes: 8, active: false },
        { id: 'floor', name: 'Isolation Plancher', defaultCost: 60, impactKwh: 25, impactGes: 2, active: false },
        { id: 'windows', name: 'Menuiseries', defaultCost: 800, impactKwh: 35, impactGes: 2, active: false },
        { id: 'heatpump', name: 'Pompe à Chaleur', defaultCost: 14000, impactKwh: 220, impactGes: 35, active: false },
        { id: 'vmc', name: 'VMC Double Flux', defaultCost: 6500, impactKwh: 40, impactGes: 3, active: false },
        { id: 'solar', name: 'Solaire PV', defaultCost: 8500, impactKwh: 50, impactGes: 5, active: false },
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

    // --- API Handlers ---

    const handleSearch = async (addressQuery: string) => {
        setLoading(true);
        setError(null);
        setSuggestions([]);
        console.log("[SPREA] Initiating direct search for:", addressQuery);

        try {
            // 1. Geocoding via BAN to get normalized street and house number
            const banRes = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(addressQuery)}&limit=1`);
            const banData = await banRes.json();

            if (!banData.features || banData.features.length === 0) {
                setError("Adresse non reconnue par le service national (BAN).");
                return;
            }

            const props = banData.features[0].properties;
            const postcode = props.postcode;
            const housenumber = props.housenumber || "";
            const street = props.street || props.name;

            // Normalize street name (strip accents, lowercase, common words)
            const cleanText = (text: string) => {
                return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
                    .toLowerCase()
                    .replace("rue ", "").replace("boulevard ", "").replace("avenue ", "")
                    .replace(/-/g, " ");
            };

            const streetClean = cleanText(street);
            console.log("[SPREA] Normalized BAN - Street:", streetClean, "Number:", housenumber, "CP:", postcode);

            // 2. Direct ADEME Hyper-Precision Search
            // We use the same pivot strategy confirmed in my backend tests
            const ademeQuery = streetClean;
            const ademeFilters = [];
            if (postcode) ademeFilters.push(`code_postal_brut:${postcode}`);
            if (housenumber) ademeFilters.push(`numero_voie_ban:"${housenumber}"`);

            const qs = ademeFilters.join(" AND ");
            const ademeUrl = `https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines?q=${encodeURIComponent(ademeQuery)}&qs=${encodeURIComponent(qs)}&size=100`;

            console.log("[SPREA] Calling ADEME Directly:", ademeUrl);
            const ademeRes = await fetch(ademeUrl);
            const ademeData = await ademeRes.json();

            const labelToCep = (l: string): number => {
                const thresholds: Record<string, number> = { A: 50, B: 90, C: 150, D: 215, E: 290, F: 375, G: 500 };
                return thresholds[l] || 420;
            };

            if (ademeData.results && ademeData.results.length > 0) {
                // Map ADEME results with STRICT STREET FILTERING
                const mappedResults = ademeData.results
                    .filter((r: any) => {
                        const ademeStreet = cleanText(r.nom_rue_ban || r.adresse_brut || "");
                        return ademeStreet.includes(streetClean) || streetClean.includes(ademeStreet);
                    })
                    .map((r: any) => {
                        const dpeLabel = (r.etiquette_dpe as DPEClass) || 'G';
                        return {
                            address: r.adresse_brut || r.adresse_complete_brut || "Inconnue",
                            ademe_dpe_number: r.numero_dpe,
                            surface: parseFloat(r.surface_habitable_logement || "0"),
                            year: parseInt(r.annee_construction || "0"),
                            initialCep: parseFloat(r.conso_5_usages_par_m2_ep || r.consommation_energie_primaire_logement) || labelToCep(dpeLabel),
                            label: dpeLabel,
                            buildingType: r.type_batiment || 'Maison',
                            heatingType: r.type_energie_principale_chauffage || "Inconnu",
                            gesLabel: r.etiquette_ges || "N/A",
                            gesValue: parseFloat(r.emission_ges_5_usages_par_m2 || "0"),
                            wallMaterials: r.qualite_isolation_murs || "Inconnu",
                            glassType: r.qualite_isolation_menuiseries || "Inconnu",
                            roofIsolation: r.qualite_isolation_plancher_haut_comble_perdu || "Non spécifié",
                            floorIsolation: r.qualite_isolation_plancher_bas || "Non spécifié",
                            heatingDetail: r.description_installation_chauffage_n1 || "",
                            date_etablissement: r.date_etablissement_dpe
                        };
                    });

                if (mappedResults.length === 0) {
                    setError("Aucun DPE trouvé pour cette rue exacte (Vérifiez l'orthographe).");
                    return;
                }

                // Sort by date (most recent first)
                mappedResults.sort((a: any, b: any) => (b.date_etablissement || "").localeCompare(a.date_etablissement || ""));

                setSearchResults(mappedResults);
                setView('results');
            } else {
                setError("Aucun DPE trouvé pour cette adresse exacte dans la base ADEME (depuis juillet 2021).");
            }
        } catch (err: any) {
            console.error("[SPREA] Direct ADEME Search failed:", err);
            setError(`Erreur lors de la recherche ADEME : ${err.message}.`);
        } finally {
            setLoading(false);
        }
    };

    const selectProperty = (p: PropertyData) => {
        setProperty(p);
        setView('dashboard');
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
        let gesReduction = 0;
        const currentThresholds = getAdjustedThresholds(property.surface);

        filteredActions.filter(a => a.active).forEach(a => {
            const cost = a.costOverride || a.defaultCost;
            let efficiency = 1.0;

            // Reduce impact if already well isolated
            if (a.id === 'ite' && (property.wallMaterials?.toLowerCase().includes('bonne') || property.wallMaterials?.toLowerCase().includes('moyenne'))) {
                efficiency = property.wallMaterials.toLowerCase().includes('bonne') ? 0.15 : 0.5;
            }
            if (a.id === 'iti' && (property.roofIsolation?.toLowerCase().includes('bonne') || property.roofIsolation?.toLowerCase().includes('moyenne'))) {
                efficiency = property.roofIsolation.toLowerCase().includes('bonne') ? 0.15 : 0.5;
            }
            if (a.id === 'windows' && (property.glassType?.toLowerCase().includes('bonne') || property.glassType?.toLowerCase().includes('moyenne'))) {
                efficiency = property.glassType.toLowerCase().includes('bonne') ? 0.15 : 0.5;
            }

            // Calculations for Energy & Cost
            if (a.id === 'ite') totalCost += cost * (property.surface * 1.1) + 2500; // Induced costs: scaffolding + finishes
            else if (a.id === 'iti') totalCost += cost * property.surface;
            else if (a.id === 'floor') totalCost += cost * property.surface;
            else if (a.id === 'windows') totalCost += cost * (property.surface > 80 ? 8 : 4);
            else totalCost += cost;

            cepReduction += a.impactKwh * efficiency;
            gesReduction += a.impactGes * efficiency;
        });

        const newCep = Math.max(35, property.initialCep - cepReduction);
        const newGes = Math.max(2, (property.gesValue || 20) - gesReduction);

        // Double-Seuil Logic (Energy vs Climate)
        const getLabel = (cep: number, ges: number): DPEClass => {
            const labelOrder: DPEClass[] = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
            const cepIdx = currentThresholds.findIndex(t => cep <= t.max);
            const gesIdx = currentThresholds.findIndex(t => ges <= t.maxGes);
            return labelOrder[Math.max(cepIdx === -1 ? 6 : cepIdx, gesIdx === -1 ? 6 : gesIdx)];
        };

        const currentLabel = property.label;
        const newLabel = getLabel(newCep, newGes);

        // Subsidies (MaPrimeRénov' - simplified ampleur model)
        const labelSteps = Math.max(0, ['G', 'F', 'E', 'D', 'C', 'B', 'A'].indexOf(newLabel) - ['G', 'F', 'E', 'D', 'C', 'B', 'A'].indexOf(currentLabel));
        const subsidyRate = labelSteps >= 2 ? 0.55 : 0.30;
        const subsidies = totalCost * subsidyRate;

        // Valeur Verte (Market-based Lille/Hauts-de-France)
        // Gain per DPE class step (source rapport matrices)
        const valVertePerStepRange = 4.5; // % per step in "Marché Tendu"
        const latentGain = property.surface * 4200 * (labelSteps * (valVertePerStepRange / 100));

        return {
            newCep, newGes, totalCost, subsidies,
            restToPay: totalCost - subsidies,
            latentGain,
            currentLabel,
            newLabel,
        };
    }, [filteredActions, property]);

    // --- UI Views ---

    if (view === 'landing') {
        return (
            <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 md:p-12 font-sans">
                <div className="max-w-2xl w-full text-center">
                    <div className="mb-12 inline-block">
                        <div className="flex items-center gap-3 px-6 py-3 bg-white rounded-2xl shadow-sm border border-slate-100 mb-8 mx-auto w-fit">
                            <Building2 className="text-blue-600" size={24} />
                            <span className="text-xs font-black text-slate-400 uppercase tracking-widest">SPREA Intelligent Property</span>
                        </div>
                        <h1 className="text-4xl md:text-5xl font-black text-slate-800 tracking-tighter leading-none mb-6">
                            L'intelligence DPE au service de votre <span className="text-blue-600">rénovation.</span>
                        </h1>
                        <p className="text-lg text-slate-500 font-bold max-w-lg mx-auto leading-relaxed">
                            Récupérez les données ADEME officielles et simulez vos gains énergétiques instantanément.
                        </p>
                    </div>

                    {error && (
                        <div className="mb-8 p-6 bg-red-50 border border-red-100 rounded-[2rem] text-red-600 flex items-center gap-4 text-left animate-in fade-in slide-in-from-top-4 duration-300">
                            <AlertTriangle className="shrink-0" size={24} />
                            <div>
                                <p className="font-bold">Information</p>
                                <p className="text-sm opacity-90">{error}</p>
                            </div>
                        </div>
                    )}

                    <div className="bg-white rounded-[2.5rem] p-8 md:p-10 shadow-2xl shadow-slate-200/50 border border-slate-100 relative z-10">
                        <div className="relative">
                            <div className="flex items-center bg-slate-100 rounded-2xl px-6 h-16 border-2 border-transparent focus-within:border-blue-600 focus-within:bg-white transition-all">
                                <Search size={24} className="text-slate-400 mr-4" />
                                <input
                                    type="text"
                                    placeholder="Entrez une adresse (ex: 43 rue Brule Maison, Lille)..."
                                    className="flex-1 bg-transparent text-lg font-bold outline-none text-slate-900 placeholder:text-slate-400"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                />
                                {loading && <Loader2 className="animate-spin text-blue-600" size={24} />}
                            </div>

                            {suggestions.length > 0 && (
                                <div className="absolute top-full left-0 right-0 mt-3 bg-white border border-slate-100 rounded-3xl shadow-2xl overflow-hidden z-20 text-left">
                                    {suggestions.map((s, idx) => (
                                        <button
                                            key={idx}
                                            onClick={() => handleSearch(s.properties.label)}
                                            className="w-full text-left px-8 py-5 hover:bg-slate-50 flex items-center gap-5 transition-colors border-b border-slate-50 last:border-0 group"
                                        >
                                            <div className="bg-slate-100 p-2 rounded-lg group-hover:bg-blue-50">
                                                <MapPin size={18} className="text-slate-400 group-hover:text-blue-600" />
                                            </div>
                                            <div>
                                                <p className="font-bold text-slate-800 leading-tight">{s.properties.label}</p>
                                                <p className="text-xs font-black text-slate-400 uppercase tracking-widest mt-1 opacity-70">{s.properties.context}</p>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                        <div className="mt-8 flex items-center justify-center gap-6 opacity-40 grayscale pointer-events-none overflow-hidden py-2 shrink-0">
                            <span className="font-black text-xs uppercase tracking-widest">ADEME API</span>
                            <span className="font-black text-xs uppercase tracking-widest">BAN Data</span>
                            <span className="font-black text-xs uppercase tracking-widest">v2.5</span>
                        </div>
                    </div>
                </div>
            </div>
        );
    }
    if (view === 'results') {
        return (
            <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 md:p-12 font-sans">
                <div className="max-w-2xl w-full">
                    <div className="mb-8 flex items-center justify-between">
                        <h2 className="text-3xl font-black text-slate-800 tracking-tight">Résultats ADEME</h2>
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
                                        {res.buildingType?.toLowerCase().includes('appartement') ? <Building size={24} className="text-slate-400 group-hover:text-blue-600" /> : <Home size={24} className="text-slate-400 group-hover:text-blue-600" />}
                                    </div>
                                    <div>
                                        <p className="font-bold text-slate-800 text-lg leading-tight">{res.address}</p>
                                        <p className="text-sm font-bold text-slate-400 mt-1 uppercase tracking-wider">
                                            {res.buildingType || 'Bâtiment'} • {res.surface} m² • {res.year || 'Année inconnue'}
                                        </p>
                                        <div className="flex items-center gap-3 mt-2">
                                            <p className="text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">Fait le : {res.date_etablissement ? new Date(res.date_etablissement).toLocaleDateString('fr-FR') : 'Date inconnue'}</p>
                                            <p className="text-xs font-medium text-slate-400 italic">DPE n° {res.ademe_dpe_number || 'N/A'}</p>
                                        </div>
                                    </div>
                                </div>
                                <div className={`px-4 py-2 rounded-lg text-xl font-black text-white shadow-lg`} style={{ backgroundColor: DPE_COLORS[res.label as DPEClass] || '#cbd5e1' }}>
                                    {res.label || '?'}
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
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4 rounded-3xl bg-white p-6 shadow-sm border border-slate-100">
                <div className="flex items-center gap-6">
                    <div className="rounded-xl bg-slate-900 p-4 text-white shadow-lg">
                        {property?.buildingType?.toLowerCase().includes('appartement') ? <Building2 size={32} /> : <Home size={32} />}
                    </div>
                    <div>
                        <h1 className="text-2xl font-black text-slate-800 tracking-tight truncate max-w-lg">{property?.address}</h1>
                        <div className="mt-1 flex items-center gap-4 text-slate-400 font-bold text-sm">
                            <span className="flex items-center gap-1.5"><MapPin size={16} /> {property?.buildingType}</span>
                            <span className="h-1 w-1 rounded-full bg-slate-200" />
                            <span>{property?.surface} m²</span>
                            <span className="h-1 w-1 rounded-full bg-slate-200" />
                            <span>Construit en {property?.year}</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-6">
                    <div className="text-right">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1">Classe Actuelle</p>
                        <div className={`flex items-center justify-center rounded-xl px-6 py-2 text-3xl font-black text-white shadow-md`} style={{ backgroundColor: DPE_COLORS_BG[property?.label || 'G'] }}>
                            {property?.label}
                        </div>
                    </div>
                    <button onClick={() => setView('landing')} className="h-12 px-6 rounded-xl bg-slate-100 text-slate-500 font-bold hover:bg-blue-50 hover:text-blue-600 transition-all text-sm">Nouvelle recherche</button>
                </div>
            </header>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <aside className="lg:col-span-4 space-y-6">
                    {/* Technical Identity Card */}
                    <div className="rounded-3xl bg-slate-900 p-8 text-white shadow-xl relative overflow-hidden">
                        <h3 className="mb-6 flex items-center gap-3 text-xl font-black text-blue-400">
                            <Info size={24} />
                            Fiche Technique
                        </h3>
                        <div className="space-y-5 relative z-10">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">Émissions GES</p>
                                <div className="flex items-center gap-3">
                                    <span className="text-2xl font-black">{property?.gesValue ?? 0}</span>
                                    <span className="text-xs font-bold text-slate-400">kg CO₂/m².an</span>
                                    <span className="ml-auto px-2 py-0.5 rounded bg-white/10 text-xs font-black">{property?.gesLabel ?? 'N/A'}</span>
                                </div>
                            </div>
                            <div className="h-px bg-white/10" />
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">Chauffage</p>
                                    <p className="text-xs font-bold text-slate-200 leading-tight">
                                        {property?.heatingType}
                                        {property?.heatingDetail && <span className="block mt-1 opacity-50 font-medium text-[9px]">{property.heatingDetail.substring(0, 40)}...</span>}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">Isolation Murs</p>
                                    <p className="text-sm font-bold text-slate-200 truncate capitalize">{property?.wallMaterials}</p>
                                </div>
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">Isolation Vitrage</p>
                                    <p className="text-sm font-bold text-slate-200 capitalize">{property?.glassType}</p>
                                </div>
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">Isolation Toiture</p>
                                    <p className="text-sm font-bold text-slate-200 capitalize">{property?.roofIsolation}</p>
                                </div>
                                <div className="col-span-2">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">Isolation Plancher</p>
                                    <p className="text-sm font-bold text-slate-200 capitalize">{property?.floorIsolation}</p>
                                </div>
                            </div>
                        </div>
                        <div className="absolute -right-8 -bottom-8 w-32 h-32 bg-blue-500/10 rounded-full blur-2xl" />
                    </div>

                    <div className="rounded-3xl bg-white p-8 shadow-sm border border-slate-100">
                        <h3 className="mb-8 flex items-center gap-4 text-xl font-black text-slate-800">
                            <TrendingUp size={24} className="text-blue-600" />
                            Simuler des travaux
                        </h3>
                        <div className="space-y-3">
                            {filteredActions.map((action) => (
                                <button
                                    key={action.id}
                                    onClick={() => setActions(actions.map(a => a.id === action.id ? { ...a, active: !a.active } : a))}
                                    className={`w-full flex items-center justify-between p-5 rounded-2xl border-2 transition-all duration-300 ${action.active ? 'border-blue-600 bg-blue-50/50 shadow-inner' : 'border-slate-50 bg-white hover:border-slate-200'}`}
                                >
                                    <div className="flex flex-col items-start gap-0.5">
                                        <span className={`text-base font-bold ${action.active ? 'text-blue-700' : 'text-slate-700'}`}>{action.name}</span>
                                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none">{action.defaultCost} € base</span>
                                    </div>
                                    <div className={`h-8 w-14 rounded-full relative transition-colors shrink-0 ${action.active ? 'bg-blue-600' : 'bg-slate-200'}`}>
                                        <div className={`absolute top-1 left-1 h-6 w-6 rounded-full bg-white transition-transform duration-300 shadow-md ${action.active ? 'translate-x-6' : ''}`} />
                                    </div>
                                </button>
                            ))}
                        </div>
                        <div className="mt-8 rounded-2xl bg-slate-900 p-8 text-white shadow-xl relative overflow-hidden hover:scale-[1.02] transition-transform">
                            <div className="relative z-10">
                                <div className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-2">Investissement Estimé</div>
                                <div className="text-4xl font-black tracking-tighter">{(simulation?.totalCost ?? 0).toLocaleString()} €</div>
                            </div>
                            <ChevronRight className="absolute -right-2 -bottom-2 text-white opacity-5 w-24 h-24" />
                        </div>
                    </div>
                </aside>

                <main className="lg:col-span-8 space-y-6">
                    <section className="rounded-3xl bg-white p-10 shadow-sm border border-slate-100 relative overflow-hidden">
                        <div className="mb-10 flex items-center justify-between relative z-10">
                            <div>
                                <h3 className="text-2xl font-black text-slate-800 letter-tight">Objectif Performance</h3>
                                <p className="text-slate-400 font-bold text-sm mt-0.5">Estimation basée sur l'algorithme SPREA.</p>
                            </div>
                            <div className="flex flex-col items-end">
                                <span className="text-5xl font-black text-blue-600 tracking-tighter">{Math.round(simulation?.newCep ?? 0)}</span>
                                <span className="text-[10px] font-black text-slate-400 tracking-widest uppercase mt-0.5">kWh/m².an</span>
                            </div>
                        </div>
                        <div className="relative mt-4 grid grid-cols-7 gap-2 h-16 z-10">
                            {getAdjustedThresholds(property?.surface || 100).map((t) => (
                                <div key={t.label} className="relative flex items-center justify-center font-black text-white text-xl rounded-lg shadow-md transition-transform" style={{ backgroundColor: DPE_COLORS[t.label as DPEClass] }}>
                                    {t.label}
                                    {simulation?.currentLabel === t.label && (
                                        <div className="absolute -top-10 flex flex-col items-center">
                                            <div className="w-2 h-2 rounded-full bg-slate-800 shadow-lg" />
                                            <div className="h-4 w-0.5 bg-slate-800" />
                                        </div>
                                    )}
                                    {simulation?.newLabel === t.label && (
                                        <div className="absolute -bottom-12 flex flex-col items-center animate-bounce">
                                            <div className="h-4 w-0.5 bg-blue-600" />
                                            <div className="w-2 h-2 rounded-full bg-blue-600 shadow-lg" />
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                        <div className="absolute top-0 right-0 w-64 h-64 bg-slate-50 rounded-full blur-[80px] -mr-32 -mt-32" />
                    </section>

                    <section className="grid grid-cols-1 gap-6 md:grid-cols-2">
                        <div className="rounded-3xl bg-white p-8 shadow-sm border border-slate-100 border-l-[12px] border-l-green-500 flex flex-col justify-between">
                            <div className="flex items-center gap-3 text-slate-400 mb-8"><Euro size={24} /><span className="text-[10px] font-black uppercase tracking-widest">Plan de Financement</span></div>
                            <div className="space-y-4">
                                <div className="flex justify-between items-center bg-slate-50 p-6 rounded-2xl border border-slate-100">
                                    <span className="text-sm font-bold text-slate-600">Subvention estimée</span>
                                    <span className="text-xl font-black text-green-600">+{(simulation?.subsidies ?? 0).toLocaleString()} €</span>
                                </div>
                                <div className="flex justify-between items-center bg-slate-900 p-8 rounded-2xl shadow-xl">
                                    <span className="text-sm font-bold text-slate-400">Reste à charge</span>
                                    <span className="text-2xl font-black text-white">{(simulation?.restToPay ?? 0).toLocaleString()} €</span>
                                </div>
                            </div>
                        </div>

                        <div className="rounded-3xl bg-white p-8 shadow-sm border border-slate-100 border-l-[12px] border-l-blue-600 flex flex-col justify-between">
                            <div className="flex items-center gap-3 text-slate-400 mb-8"><TrendingUp size={24} /><span className="text-[10px] font-black uppercase tracking-widest">Plus-value Immobilière</span></div>
                            <div className="mb-6">
                                <div className="text-5xl font-black text-blue-700 tracking-tighter">+{(simulation?.latentGain ?? 0).toLocaleString()} €</div>
                                <p className="mt-4 text-sm font-bold text-slate-500 leading-relaxed italic opacity-80">
                                    "Valorisation estimée suite à l'amélioration du label."
                                </p>
                            </div>
                            <div className="mt-auto p-4 bg-blue-50 rounded-xl flex items-center gap-3 text-blue-600 font-black text-[10px] uppercase">
                                <Info size={16} /> ROI : ~8 ans (TRI)
                            </div>
                        </div>
                    </section>
                </main>
            </div>
        </div>
    );
}
