import { useState, useMemo, useEffect } from 'react';
import {
    TrendingUp,
    Home,
    Search,
    Loader2,
    MapPin,
    Building2,
    Building,
    FileText,
    PieChart,
    Layers,
    Copy,
} from 'lucide-react';

// --- Types & Constants ---

type DPEClass = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';
type IncomeLevel = 'tres_modeste' | 'modeste' | 'intermediaire' | 'superieur';

interface RetrofitAction {
    id: string;
    name: string;
    defaultCost: number;
    impactKwh: number;
    impactGes: number;
    description: string;
    active: boolean;
    suggested?: boolean;
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
    ademe_dpe_number?: string;
    postcode?: string;
    city?: string;
}

const DPE_COLORS: Record<DPEClass, string> = {
    A: '#31a354', B: '#74c476', C: '#a1d99b', D: '#feb24c', E: '#fd8d3c', F: '#f03b20', G: '#bd0026',
};

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
    const [incomeLevel, setIncomeLevel] = useState<IncomeLevel>('intermediaire');
    const [downloading, setDownloading] = useState(false);
    const [compareMode, setCompareMode] = useState(false);
    const [activeScenario, setActiveScenario] = useState<'A' | 'B'>('A');

    // Investor States
    const [isInvestor, setIsInvestor] = useState(false);
    const [monthlyRent, setMonthlyRent] = useState(800);
    const [purchasePrice, setPurchasePrice] = useState(150000);
    const [tmi, setTmi] = useState(30);

    const [actionsA, setActionsA] = useState<RetrofitAction[]>([
        { id: 'iti', name: 'Isolation Toiture', defaultCost: 45, impactKwh: 65, impactGes: 4, description: 'Isolation des combles ou de la toiture (~45€/m²) pour réduire les déperditions par le haut.', active: false },
        { id: 'ite', name: 'Isolation Murs (ITE)', defaultCost: 180, impactKwh: 140, impactGes: 8, description: 'Isolation par l\'extérieur (~180€/m²) pour supprimer les ponts thermiques et protéger la façade.', active: false },
        { id: 'floor', name: 'Isolation Plancher', defaultCost: 60, impactKwh: 25, impactGes: 2, description: 'Isolation des planchers bas (~60€/m²) pour éviter les remontées de froid.', active: false },
        { id: 'windows', name: 'Menuiseries', defaultCost: 800, impactKwh: 35, impactGes: 2, description: 'Remplacement des fenêtres (~800€/unité) par du double ou triple vitrage haute performance.', active: false },
        { id: 'heatpump', name: 'Pompe à Chaleur', defaultCost: 14000, impactKwh: 220, impactGes: 35, description: 'Installation d\'un système Air-Eau (~14k€) pour un chauffage écologique et très économe.', active: false },
        { id: 'vmc', name: 'VMC Double Flux', defaultCost: 6500, impactKwh: 40, impactGes: 3, description: 'Système de ventilation (~6.5k€) récupérant les calories de l\'air extrait.', active: false },
        { id: 'solar', name: 'Solaire PV', defaultCost: 8500, impactKwh: 50, impactGes: 5, description: 'Installation de panneaux photovoltaïques (~8.5k€) pour l\'autoconsommation.', active: false },
    ]);

    const [actionsB, setActionsB] = useState<RetrofitAction[]>([...actionsA]);

    const toggleAction = (id: string) => {
        const updater = activeScenario === 'A' ? setActionsA : setActionsB;
        const currentActions = activeScenario === 'A' ? actionsA : actionsB;
        updater(currentActions.map(a => a.id === id ? { ...a, active: !a.active } : a));
    };

    const copyAToB = () => setActionsB([...actionsA.map(a => ({ ...a }))]);

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

    const handleSearch = async (addressQuery: string) => {
        setLoading(true);
        setError(null);
        setSuggestions([]);
        try {
            const banRes = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(addressQuery)}&limit=1`);
            const banData = await banRes.json();
            if (!banData.features || banData.features.length === 0) {
                setError("Adresse non reconnue.");
                return;
            }
            const props = banData.features[0].properties;
            const postcode = props.postcode;
            const housenumber = props.housenumber || "";
            const street = props.street || props.name;

            const cleanText = (text: string) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/rue |boulevard |avenue /g, "").replace(/-/g, " ");
            const streetClean = cleanText(street);

            const ademeUrl = `https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines?q=${encodeURIComponent(streetClean)}&qs=code_postal_brut:${postcode}${housenumber ? ` AND numero_voie_ban:"${housenumber}"` : ''}&size=100`;
            const ademeRes = await fetch(ademeUrl);
            const ademeData = await ademeRes.json();

            if (ademeData.results && ademeData.results.length > 0) {
                const mapped = ademeData.results.map((r: any) => ({
                    address: r.adresse_brut || r.adresse_complete_brut || "Inconnue",
                    ademe_dpe_number: r.numero_dpe,
                    surface: parseFloat(r.surface_habitable_logement || "0"),
                    year: parseInt(r.annee_construction || "0"),
                    initialCep: parseFloat(r.conso_5_usages_par_m2_ep || r.consommation_energie_primaire_logement) || 250,
                    label: (r.etiquette_dpe as DPEClass) || 'G',
                    buildingType: r.type_batiment || 'Maison',
                    heatingType: r.type_energie_principale_chauffage || "Inconnu",
                    gesLabel: r.etiquette_ges || "N/A",
                    gesValue: parseFloat(r.emission_ges_5_usages_par_m2 || "0"),
                    wallMaterials: r.qualite_isolation_murs || "Inconnu",
                    glassType: r.qualite_isolation_menuiseries || "Inconnu",
                    roofIsolation: r.qualite_isolation_plancher_haut_comble_perdu || "Non spécifié",
                    floorIsolation: r.qualite_isolation_plancher_bas || "Non spécifié",
                    heatingDetail: r.description_installation_chauffage_n1 || "",
                    date_etablissement: r.date_etablissement_dpe,
                    postcode: postcode,
                    city: props.city || props.town || ""
                }));
                setSearchResults(mapped);
                setView('results');
            } else {
                setError("Aucun DPE trouvé.");
            }
        } catch (err) {
            setError("Erreur réseau ADEME.");
        } finally {
            setLoading(false);
        }
    };

    const selectProperty = (p: PropertyData) => {
        // Full State Reset
        setActionsA(prev => prev.map(a => ({ ...a, active: false })));
        setActionsB(prev => prev.map(a => ({ ...a, active: false })));
        setActiveScenario('A');
        setCompareMode(false);
        setIsInvestor(false);
        setIncomeLevel('intermediaire');
        setTmi(30);
        setMonthlyRent(800);
        setPurchasePrice(p.surface * 4200); // Dynamic baseline, user can edit

        const year = p.year || 1970;
        const inferred = { ...p };
        if (!p.wallMaterials || p.wallMaterials === "Inconnu") {
            if (year < 1948) inferred.wallMaterials = "Pierre";
            else if (year < 1975) inferred.wallMaterials = "Béton non isolé";
            else inferred.wallMaterials = "Isolé RT2005";
        }
        setProperty(inferred);

        // Intelligent Recommendations Logic
        let pRoof = 0.30, pWalls = 0.25, pWindows = 0.15, pFloor = 0.10, pAir = 0.20;
        if (inferred.roofIsolation?.toLowerCase().includes('bonne')) pRoof *= 0.35;
        if (inferred.wallMaterials?.toLowerCase().includes('bonne')) pWalls *= 0.40;
        if (inferred.glassType?.toLowerCase().includes('performant')) pWindows *= 0.50;
        const total = pRoof + pWalls + pWindows + pFloor + pAir;

        const losses = {
            iti: (pRoof / total) * 100,
            ite: (pWalls / total) * 100,
            windows: (pWindows / total) * 100,
            floor: (pFloor / total) * 100,
            vmc: (pAir / total) * 100
        };

        const suggester = (a: RetrofitAction) => {
            let isSuggested = false;
            if (a.id === 'iti' && losses.iti > 20) isSuggested = true;
            if (a.id === 'ite' && losses.ite > 20) isSuggested = true;
            if (a.id === 'windows' && losses.windows > 15) isSuggested = true;
            if (a.id === 'floor' && losses.floor > 10) isSuggested = true;
            if (a.id === 'vmc' && losses.vmc > 15) isSuggested = true;
            return { ...a, suggested: isSuggested, active: isSuggested };
        };

        setActionsA(prev => prev.map(suggester));
        setActionsB(prev => prev.map(suggester));

        setView('dashboard');
    };

    // --- Simulation Logic ---

    const heatLoss = useMemo(() => {
        if (!property) return null;
        let pRoof = 0.30, pWalls = 0.25, pWindows = 0.15, pFloor = 0.10, pAir = 0.20;
        if (property.roofIsolation?.toLowerCase().includes('bonne')) pRoof *= 0.35;
        if (property.wallMaterials?.toLowerCase().includes('bonne')) pWalls *= 0.40;
        if (property.glassType?.toLowerCase().includes('performant')) pWindows *= 0.50;
        const total = pRoof + pWalls + pWindows + pFloor + pAir;
        return [
            { id: 'roof', name: 'Toiture', val: (pRoof / total) * 100, color: '#3b82f6' },
            { id: 'walls', name: 'Murs', val: (pWalls / total) * 100, color: '#60a5fa' },
            { id: 'windows', name: 'Vitrage', val: (pWindows / total) * 100, color: '#93c5fd' },
            { id: 'floor', name: 'Sols', val: (pFloor / total) * 100, color: '#bfdbfe' },
            { id: 'vent', name: 'Air', val: (pAir / total) * 100, color: '#dbeafe' },
        ];
    }, [property]);

    const compute = (activeActions: RetrofitAction[]) => {
        if (!property) return null;
        let cost = 0, cepRed = 0, gesRed = 0;
        const thresholds = getAdjustedThresholds(property.surface);

        activeActions.forEach(a => {
            let eff = 1.0;
            if (a.id === 'ite' && property.wallMaterials?.includes('Isolé')) eff = 0.4;

            let itemCost = a.defaultCost;
            if (a.id === 'ite') itemCost = a.defaultCost * property.surface * 1.1 + 3500;
            else if (a.id === 'iti') itemCost = a.defaultCost * property.surface + 1200;
            else if (a.id === 'floor') itemCost = a.defaultCost * property.surface;
            else if (a.id === 'windows') itemCost = (a.defaultCost + 150) * 6;
            else if (a.id === 'heatpump') itemCost = a.defaultCost + 1500;

            cost += itemCost;
            cepRed += a.impactKwh * eff;
            gesRed += a.impactGes * eff;
        });

        const newCep = Math.max(35, property.initialCep - cepRed);
        const newGes = Math.max(2, (property.gesValue || 20) - gesRed);

        const getInfos = (cep: number, ges: number) => {
            const labels: DPEClass[] = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
            const cIdx = thresholds.findIndex(t => cep <= t.max);
            const gIdx = thresholds.findIndex(t => ges <= t.maxGes);
            const fIdx = Math.max(cIdx === -1 ? 6 : cIdx, gIdx === -1 ? 6 : gIdx);
            return { label: labels[fIdx], cepL: labels[cIdx === -1 ? 6 : cIdx], gesL: labels[gIdx === -1 ? 6 : gIdx] };
        };

        const current = getInfos(property.initialCep, property.gesValue || 20);
        const target = getInfos(newCep, newGes);
        const steps = Math.max(0, ['G', 'F', 'E', 'D', 'C', 'B', 'A'].indexOf(target.label) - ['G', 'F', 'E', 'D', 'C', 'B', 'A'].indexOf(current.label));
        const rate = steps >= 2 ? { tres_modeste: 0.8, modeste: 0.6, intermediaire: 0.45, superieur: 0.3 }[incomeLevel] : 0.25;
        const sub = cost * rate;
        const rest = cost - sub;

        // Detailed work costs for UI
        const activeDetailedCosts = activeActions.map(a => {
            let itemCost = a.defaultCost;
            if (a.id === 'ite') itemCost = a.defaultCost * property.surface * 1.1 + 3500;
            else if (a.id === 'iti') itemCost = a.defaultCost * property.surface + 1200;
            else if (a.id === 'floor') itemCost = a.defaultCost * property.surface;
            else if (a.id === 'windows') itemCost = (a.defaultCost + 150) * 6;
            else if (a.id === 'heatpump') itemCost = a.defaultCost + 1500;
            return { name: a.name, cost: itemCost, suggested: a.suggested };
        });

        // Investor Metrics
        const taxBenefit = isInvestor ? rest * (tmi / 100 + 0.172) : 0;
        const totalInvestment = purchasePrice + cost;
        const annualRent = monthlyRent * 12;
        const yieldBrut = (annualRent / totalInvestment) * 100;
        const cashflow = monthlyRent - (rest / 240); // Simple 20y financing sim for cashflow feel

        return {
            newCep, newGes, cost, sub, rest, taxBenefit,
            activeDetailedCosts,
            yieldBrut, cashflow, purchasePrice,
            netInvestorCost: rest - taxBenefit,
            savings: (cepRed * property.surface) * 0.228,
            roi: (cost - sub - taxBenefit) / ((cepRed * property.surface) * 0.228 || 1),
            gain: property.surface * 4200 * (steps * 0.045),
            currentLabel: current.label,
            newLabel: target.label,
            newCepLabel: target.cepL,
            newGesLabel: target.gesL,
            currentCepLabel: current.cepL,
            currentGesLabel: current.gesL
        };
    };

    const simA = useMemo(() => compute(actionsA.filter(a => a.active)), [actionsA, property, incomeLevel, tmi, isInvestor, monthlyRent]);
    const simB = useMemo(() => compute(actionsB.filter(a => a.active)), [actionsB, property, incomeLevel, tmi, isInvestor, monthlyRent]);

    const activeSim = activeScenario === 'A' ? simA : simB;

    const handleDownloadPDF = async () => {
        if (!property || !activeSim) return;
        setDownloading(true);
        try {
            const res = await fetch('/api/generate-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    address: property.address, surface: property.surface, year: property.year,
                    ademe_dpe_number: property.ademe_dpe_number, current_label: activeSim.currentLabel,
                    new_label: activeSim.newLabel, initial_cep: property.initialCep, new_cep: activeSim.newCep,
                    ges_value: property.gesValue || 0, new_ges: activeSim.newGes, total_cost: activeSim.cost,
                    subsidies: activeSim.sub, rest_to_pay: activeSim.rest, latent_gain: activeSim.gain,
                    annual_savings: activeSim.savings, roi_years: Math.round(activeSim.roi),
                    detailed_costs: activeSim.activeDetailedCosts,
                    yield_brut: activeSim.yieldBrut, cashflow: activeSim.cashflow,
                    purchase_price: purchasePrice
                })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Erreur lors de la génération du rapport.");
            }
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a'); a.href = url; a.download = `Rapport_SPREA.pdf`;
            document.body.appendChild(a); a.click(); a.remove();
        } finally { setDownloading(false); }
    };

    // --- Views ---

    if (view === 'landing') return (
        <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 font-sans">
            <div className="max-w-2xl w-full text-center">
                <div className="mb-12">
                    <div className="flex items-center gap-3 px-6 py-3 bg-white rounded-2xl shadow-sm border border-slate-100 mb-8 mx-auto w-fit">
                        <Building2 className="text-blue-600" size={24} />
                        <span className="text-xs font-black text-slate-400 uppercase tracking-widest">SPREA Intelligent Property</span>
                    </div>
                    <h1 className="text-4xl md:text-5xl font-black text-slate-800 tracking-tighter leading-none mb-6">
                        L'intelligence DPE au service de votre <span className="text-blue-600">rénovation.</span>
                    </h1>
                </div>
                <div className="bg-white rounded-[2.5rem] p-10 shadow-2xl border border-slate-100 relative z-10">
                    <div className="relative">
                        <div className="flex items-center bg-slate-100 rounded-2xl px-6 h-16 border-2 border-transparent focus-within:border-blue-600 focus-within:bg-white transition-all">
                            <Search size={24} className="text-slate-400 mr-4" />
                            <input
                                type="text"
                                placeholder="Adresse (ex: 43 rue Brule Maison, Lille)..."
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
                                        <MapPin size={18} className="text-slate-400" />
                                        <p className="font-bold text-slate-800">{s.properties.label}</p>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
                {error && <p className="mt-4 text-red-600 font-bold">{error}</p>}
            </div>
        </div>
    );

    if (view === 'results') return (
        <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 font-sans">
            <div className="max-w-2xl w-full">
                <h2 className="text-3xl font-black text-slate-800 mb-8">Résultats ADEME</h2>
                <div className="space-y-4">
                    {searchResults.map((res, idx) => (
                        <button key={idx} onClick={() => selectProperty(res)} className="w-full text-left p-6 bg-white rounded-3xl border-2 border-slate-50 hover:border-blue-600 transition-all shadow-sm flex items-center justify-between group">
                            <div className="flex-1">
                                <p className="font-bold text-slate-800 text-lg flex items-center gap-2">
                                    {res.address}
                                    {res.city && <span className="text-[10px] font-black uppercase text-slate-400 bg-slate-50 px-2 py-0.5 rounded-lg">{res.city}</span>}
                                </p>
                                <div className="flex items-center gap-4 mt-2">
                                    <span className="text-xs font-bold text-slate-400 flex items-center gap-1"><Home size={12} /> {res.surface} m²</span>
                                    <span className="text-xs font-bold text-slate-400 flex items-center gap-1"><Building size={12} /> {res.year}</span>
                                    {res.ademe_dpe_number && <span className="text-xs font-bold text-slate-400 flex items-center gap-1"><FileText size={12} /> {res.ademe_dpe_number}</span>}
                                </div>
                            </div>
                            <div className={`px-4 py-2 rounded-lg text-xl font-black text-white ml-4 flex flex-col items-center justify-center min-w-[50px] shadow-sm`} style={{ backgroundColor: DPE_COLORS[res.label as DPEClass] }}>
                                {res.label}
                                <span className="text-[8px] opacity-60">DPE</span>
                            </div>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );

    return (
        <div className="min-h-screen bg-slate-50 p-8 font-sans text-slate-900">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4 rounded-3xl bg-white p-6 shadow-sm border border-slate-100">
                <div className="flex items-center gap-6">
                    <div className="rounded-xl bg-slate-900 p-4 text-white shadow-lg">
                        {property?.buildingType?.includes('Appartement') ? <Building size={32} /> : <Home size={32} />}
                    </div>
                    <div>
                        <h1 className="text-2xl font-black text-slate-800 truncate max-w-lg">{property?.address}</h1>
                        <p className="text-sm font-bold text-slate-400">{property?.surface} m² • {property?.year}</p>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2 p-2 bg-slate-50 rounded-2xl border border-slate-100">
                        <div className="text-right px-2">
                            <p className="text-[8px] font-black uppercase text-slate-400">Énergie</p>
                            <p className="text-sm font-black text-slate-600">{activeSim?.currentCepLabel}</p>
                        </div>
                        <div className="w-px h-6 bg-slate-200" />
                        <div className="text-right px-2">
                            <p className="text-[8px] font-black uppercase text-slate-400">Climat</p>
                            <p className="text-sm font-black text-slate-600">{activeSim?.currentGesLabel}</p>
                        </div>
                        <div className={`flex items-center justify-center rounded-xl h-12 w-12 text-2xl font-black text-white shadow-lg ml-2`} style={{ backgroundColor: DPE_COLORS[activeSim?.currentLabel || 'G'] }}>
                            {activeSim?.currentLabel}
                        </div>
                    </div>
                    <button onClick={handleDownloadPDF} disabled={downloading} className="h-14 px-6 rounded-2xl bg-white border border-slate-200 text-blue-600 font-black hover:bg-blue-50 transition-all flex items-center gap-3">
                        {downloading ? <Loader2 className="animate-spin" /> : <FileText size={18} />} PDF
                    </button>
                    <button onClick={() => setView('landing')} className="h-14 px-6 rounded-2xl bg-slate-100 text-slate-500 font-black hover:bg-blue-600 hover:text-white transition-all text-xs uppercase tracking-widest">Retour</button>
                </div>
            </header>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <aside className="lg:col-span-4 space-y-6">
                    <div className="rounded-3xl bg-slate-900 p-8 text-white shadow-xl">
                        <div className="flex items-center justify-between mb-6">
                            <h3 className="flex items-center gap-3 text-xl font-black text-blue-400"><PieChart size={24} /> Déperditions Thermiques</h3>
                            <div className="group relative">
                                <span className="cursor-help text-slate-500 text-[10px] font-black uppercase border border-slate-700 px-2 py-1 rounded-lg hover:border-blue-400 hover:text-blue-400 transition-colors">?</span>
                                <div className="absolute right-0 top-full mt-2 w-48 p-3 bg-slate-800 text-[10px] font-bold text-slate-300 rounded-xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 border border-white/5">
                                    Répartition des pertes de chaleur par éléments. Plus le % est élevé, plus l'isolation de cette paroi est prioritaire.
                                </div>
                            </div>
                        </div>
                        <div className="space-y-4">
                            {heatLoss?.map(item => (
                                <div key={item.id}>
                                    <div className="flex justify-between text-[10px] font-black uppercase tracking-widest mb-1">
                                        <span>{item.name}</span>
                                        <span>{Math.round(item.val)}%</span>
                                    </div>
                                    <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                                        <div className="h-full rounded-full transition-all" style={{ width: `${item.val}%`, backgroundColor: item.color }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="rounded-3xl bg-white p-8 shadow-sm border border-slate-100">
                        <div className="flex items-center justify-between mb-8">
                            <h3 className="flex items-center gap-4 text-xl font-black text-slate-800"><Layers size={24} className="text-blue-600" /> Scénarios</h3>
                            <button onClick={() => setCompareMode(!compareMode)} className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${compareMode ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-400'}`}>Comparatif</button>
                        </div>

                        {compareMode && (
                            <div className="flex gap-2 mb-6 p-2 bg-slate-100 rounded-2xl">
                                <button onClick={() => setActiveScenario('A')} className={`flex-1 py-3 rounded-xl font-black text-xs uppercase tracking-widest transition-all ${activeScenario === 'A' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-400'}`}>Scénario A</button>
                                <button onClick={() => setActiveScenario('B')} className={`flex-1 py-3 rounded-xl font-black text-xs uppercase tracking-widest transition-all ${activeScenario === 'B' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-400'}`}>Scénario B</button>
                                <button onClick={copyAToB} title="Copier A vers B" className="p-3 bg-white rounded-xl text-slate-400 hover:text-blue-600"><Copy size={16} /></button>
                            </div>
                        )}

                        <div className="mb-6 p-6 bg-slate-50 rounded-[1.5rem] border border-slate-100">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1">Revenus du Ménage</p>
                            <p className="text-[8px] font-bold text-blue-500 uppercase mb-3">Impacte le taux MaPrimeRénov'</p>
                            <div className="grid grid-cols-2 gap-2">
                                {(['tres_modeste', 'modeste', 'intermediaire', 'superieur'] as IncomeLevel[]).map(l => (
                                    <button key={l} onClick={() => setIncomeLevel(l)} className={`px-2 py-2 rounded-xl text-[8px] font-black uppercase transition-all border-2 ${incomeLevel === l ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-400 border-slate-50'}`}>{l.replace('_', ' ')}</button>
                                ))}
                            </div>
                        </div>

                        <div className="mb-8 p-6 bg-blue-50/30 rounded-[1.5rem] border border-blue-100">
                            <div className="flex items-center justify-between mb-4">
                                <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Profil Investisseur</p>
                                <button
                                    onClick={() => setIsInvestor(!isInvestor)}
                                    className={`w-12 h-6 rounded-full relative transition-colors ${isInvestor ? 'bg-blue-600' : 'bg-slate-200'}`}
                                >
                                    <div className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform ${isInvestor ? 'translate-x-6' : ''}`} />
                                </button>
                            </div>

                            {isInvestor && (
                                <div className="space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
                                    <div>
                                        <p className="text-[9px] font-bold text-slate-400 uppercase mb-1">Taux d'imposition (TMI)</p>
                                        <div className="flex gap-1">
                                            {[0, 11, 30, 41, 45].map(v => (
                                                <button
                                                    key={v}
                                                    onClick={() => setTmi(v)}
                                                    className={`flex-1 py-1 rounded-lg text-[10px] font-black border ${tmi === v ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-400 border-slate-100'}`}
                                                >
                                                    {v}%
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    <div>
                                        <p className="text-[9px] font-bold text-slate-400 uppercase mb-1">Prix d'Achat du Bien (€)</p>
                                        <input
                                            type="number"
                                            value={purchasePrice}
                                            onChange={(e) => setPurchasePrice(Number(e.target.value))}
                                            className="w-full bg-white border border-slate-100 rounded-xl px-3 py-2 text-sm font-black text-slate-700 outline-none focus:border-blue-600"
                                        />
                                    </div>
                                    <div>
                                        <p className="text-[9px] font-bold text-slate-400 uppercase mb-1">Loyer Mensuel Estimé</p>
                                        <input
                                            type="number"
                                            value={monthlyRent}
                                            onChange={(e) => setMonthlyRent(Number(e.target.value))}
                                            className="w-full bg-white border border-slate-100 rounded-xl px-3 py-2 text-sm font-black text-slate-700 outline-none focus:border-blue-600"
                                        />
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="space-y-3">
                            {(activeScenario === 'A' ? actionsA : actionsB).map(a => (
                                <div key={a.id} className="group relative">
                                    <button onClick={() => toggleAction(a.id)} className={`w-full flex items-center justify-between p-5 rounded-2xl border-2 transition-all ${a.active ? 'border-blue-600 bg-blue-50/50' : 'border-slate-50 bg-white hover:border-slate-200'}`}>
                                        <div className="flex flex-col items-start gap-1">
                                            <span className={`font-bold ${a.active ? 'text-blue-700' : 'text-slate-700'}`}>{a.name}</span>
                                            {a.suggested && <span className="text-[8px] font-black uppercase tracking-widest text-blue-500 bg-blue-100/50 px-2 py-0.5 rounded-md">Conseillé</span>}
                                        </div>
                                        <div className={`h-6 w-10 rounded-full shrink-0 transition-colors ${a.active ? 'bg-blue-600' : 'bg-slate-200'}`} />
                                    </button>
                                    <div className="hidden group-hover:block absolute left-full ml-3 top-0 w-48 p-4 bg-white border border-slate-100 rounded-2xl shadow-2xl z-50 animate-in fade-in slide-in-from-left-2 duration-200">
                                        <p className="text-[10px] font-bold text-slate-500 leading-relaxed italic">{a.description}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </aside>

                <main className="lg:col-span-8">
                    {compareMode ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <ComparisonCard title="Scénario A" sim={simA} active={activeScenario === 'A'} onSelect={() => setActiveScenario('A')} />
                            <ComparisonCard title="Scénario B" sim={simB} active={activeScenario === 'B'} onSelect={() => setActiveScenario('B')} />
                        </div>
                    ) : (
                        <div className="space-y-6">
                            <section className="rounded-3xl bg-white p-10 shadow-sm border border-slate-100 relative overflow-hidden">
                                <div className="mb-10 flex items-center justify-between relative z-10">
                                    <div>
                                        <h3 className="text-2xl font-black text-slate-800">Objectif Performance</h3>
                                        <div className="flex gap-2 mt-2">
                                            <span className="px-3 py-1 bg-blue-50 text-blue-700 font-extrabold text-[10px] rounded-lg tracking-widest uppercase">E: {activeSim?.newCepLabel}</span>
                                            <span className="px-3 py-1 bg-green-50 text-green-700 font-extrabold text-[10px] rounded-lg tracking-widest uppercase">C: {activeSim?.newGesLabel}</span>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-5xl font-black text-blue-600 tracking-tighter">{Math.round(activeSim?.newCep || 0)}</p>
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">kWh/m².an</p>
                                    </div>
                                </div>
                                <div className="grid grid-cols-7 gap-2 h-16 relative z-10">
                                    {getAdjustedThresholds(property?.surface || 100).map(t => (
                                        <div key={t.label} className="relative flex items-center justify-center font-black text-white text-xl rounded-lg shadow-md" style={{ backgroundColor: DPE_COLORS[t.label as DPEClass] }}>
                                            {t.label}
                                            {activeSim?.currentLabel === t.label && <div className="absolute -top-10 flex flex-col items-center"><div className="w-2 h-2 rounded-full bg-slate-800" /><div className="h-4 w-0.5 bg-slate-800" /></div>}
                                            {activeSim?.newLabel === t.label && <div className="absolute -bottom-12 flex flex-col items-center animate-bounce"><div className="h-4 w-0.5 bg-blue-600" /><div className="w-2 h-2 rounded-full bg-blue-600" /></div>}
                                        </div>
                                    ))}
                                </div>
                            </section>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div className="p-8 bg-white rounded-3xl border-l-[12px] border-l-green-500 shadow-sm">
                                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-6">Simulation Financement</p>
                                    <div className="space-y-4">
                                        <div className="space-y-2 pb-4 border-b border-slate-50">
                                            {activeSim?.activeDetailedCosts.map((item: any, idx: number) => (
                                                <div key={idx} className="flex justify-between text-xs font-bold text-slate-600">
                                                    <span>{item.name}</span>
                                                    <span>{Math.round(item.cost).toLocaleString()} €</span>
                                                </div>
                                            ))}
                                            <div className="flex justify-between text-base font-black pt-2 text-slate-800">
                                                <span>Investissement Brut</span>
                                                <span>{Math.round(activeSim?.cost || 0).toLocaleString()} €</span>
                                            </div>
                                        </div>
                                        <div className="flex justify-between font-bold text-sm">
                                            <span>Subventions (MaPrimeRénov')</span>
                                            <span className="text-green-600">+{Math.round(activeSim?.sub || 0).toLocaleString()} €</span>
                                        </div>
                                        {isInvestor && (
                                            <div className="flex justify-between font-bold text-sm text-blue-600">
                                                <span>Gain Fiscal (TMI {tmi}%)</span>
                                                <span>+{Math.round(activeSim?.taxBenefit || 0).toLocaleString()} €</span>
                                            </div>
                                        )}
                                        <div className="flex justify-between text-2xl font-black pt-4 border-t border-slate-900 mt-4">
                                            <span>{isInvestor ? 'Cout Net Final' : 'Reste à Charge'}</span>
                                            <span>{Math.round(isInvestor ? (activeSim?.netInvestorCost || 0) : (activeSim?.rest || 0)).toLocaleString()} €</span>
                                        </div>
                                    </div>
                                </div>
                                <div className="p-8 bg-white rounded-3xl border-l-[12px] border-l-blue-600 shadow-sm relative group">
                                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-6 flex items-center justify-between">
                                        Valeur Verte (Resantise)
                                        <span className="cursor-help opacity-40 hover:opacity-100 transition-opacity">?</span>
                                    </p>
                                    <div className="text-4xl font-black text-blue-700 tracking-tighter">+{Math.round(activeSim?.gain || 0).toLocaleString()} €</div>
                                    <p className="text-xs font-bold text-slate-400 mt-4 italic">Gain de valeur IMMO estimé</p>
                                    <div className="absolute bottom-full left-0 mb-4 w-64 p-4 bg-slate-900 text-white text-[10px] font-bold rounded-2xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                                        Estimation de la plus-value immobilière générée par l'amélioration du DPE. Un saut de classe énergétique augmente généralement le prix de vente de 3% à 7%.
                                    </div>
                                </div>

                                {isInvestor && (
                                    <div className="p-8 bg-slate-900 rounded-3xl border-l-[12px] border-l-blue-400 shadow-xl relative group">
                                        <p className="text-[10px] font-black text-blue-300 uppercase tracking-widest mb-6 flex items-center justify-between">
                                            Rentabilité Brut
                                            <span className="cursor-help opacity-40 hover:opacity-100 transition-opacity">?</span>
                                        </p>
                                        <div className="text-4xl font-black text-white tracking-tighter">{activeSim?.yieldBrut.toFixed(1)} %</div>
                                        <p className="text-xs font-bold text-blue-400 mt-4 italic">Cashflow : {Math.round(activeSim?.cashflow || 0)} €/mois</p>
                                        <div className="absolute bottom-full left-0 mb-4 w-64 p-4 bg-white text-slate-900 text-[10px] font-bold rounded-2xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 border border-slate-100">
                                            <p className="font-black text-blue-600 mb-2 uppercase">Méthodologie :</p>
                                            <p className="mb-2 italic">Rendement = (Loyer × 12) / (Prix Achat + Travaux)</p>
                                            <p className="italic">Cashflow = Loyer - Mensualité Crédit (Travaux sur 20 ans)</p>
                                        </div>
                                    </div>
                                )}
                                tunic                            </div>
                        </div>
                    )}
                </main>
            </div>
        </div>
    );
}

function ComparisonCard({ title, sim, active, onSelect }: any) {
    return (
        <button onClick={onSelect} className={`w-full text-left p-8 bg-white rounded-[2.5rem] border-4 transition-all ${active ? 'border-blue-600 shadow-xl scale-[1.02]' : 'border-white opacity-60 hover:opacity-100 shadow-sm'}`}>
            <div className="flex justify-between items-center mb-10">
                <h4 className="text-xl font-black text-slate-800">{title}</h4>
                <div className="px-4 py-2 rounded-xl text-2xl font-black text-white" style={{ backgroundColor: DPE_COLORS[(sim?.newLabel || 'G') as DPEClass] }}>{sim?.newLabel}</div>
            </div>
            <div className="space-y-4">
                <div className="flex justify-between text-sm font-bold"><span>Investissement Brut</span><span>{Math.round(sim?.cost || 0).toLocaleString()} €</span></div>
                <div className="flex justify-between text-sm font-bold text-green-600"><span>Subventions</span><span>+{Math.round(sim?.sub || 0).toLocaleString()} €</span></div>
                <div className="flex justify-between text-lg font-black pt-4 border-t border-slate-100"><span>Reste à Charge</span><span>{Math.round(sim?.rest || 0).toLocaleString()} €</span></div>
                <div className="mt-6 flex items-center gap-2 p-3 bg-blue-50 rounded-xl text-blue-600 font-black text-[10px] uppercase tracking-widest">
                    <TrendingUp size={14} /> Économies : {Math.round(sim?.savings || 0).toLocaleString()} €/an
                </div>
            </div>
        </button>
    );
}
