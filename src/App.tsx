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
    Zap
} from 'lucide-react';
import { AccountButton, AccountProvider, useAccount } from './account';
import { Link, usePath } from './router';
import CgvPage from './pages/Cgv';
import ConfidentialitePage from './pages/Confidentialite';
import MentionsLegalesPage from './pages/MentionsLegales';
import PricingPage from './pages/Pricing';
import { SiteFooter } from './pages/site';

type IncomeLevel = 'tres_modeste' | 'modeste' | 'intermediaire' | 'superieur';

// --- Types & Constants ---

type DPEClass = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';

interface RetrofitAction {
    id: string;
    name: string;
    description: string;
    active: boolean;
    suggested?: boolean;
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
    pricePerM2?: number; // Added for gain calculation
    suggestedWorks?: string[];
    finalConsumption?: number;
    preselectedWorks?: string[];
    heatingDetail?: string;
    ademe_dpe_number?: string;
    postcode?: string;
    city?: string;
    constructionPeriod?: string;
    lossShares?: Record<string, number>;
    insulationQuality?: Record<string, string | null>;
    dpeLosses?: Record<string, number | null> | null;
}

const DPE_COLORS: Record<DPEClass, string> = {
    A: '#31a354', B: '#74c476', C: '#a1d99b', D: '#feb24c', E: '#fd8d3c', F: '#f03b20', G: '#bd0026',
};

// Simulation results, computed by the API (api/simulation.py is the single engine)
interface Simulation {
    currentLabel: DPEClass;
    newLabel: DPEClass;
    newCep: number;
    newGes: number;
    thresholds: { label: DPEClass; max: number; max_ges: number }[];
    cost: number;
    activeDetailedCosts: { id: string; name: string; cost: number; suggested: boolean }[];
    durationDays: number;
    sub: number;
    ceeEst: number;
    aidPathway: 'accompagne' | 'geste' | 'none';
    aidNotes: string[];
    rest: number;
    ecoPTZAmount: number;
    ecoPTZLimit: number;
    savings: number;
    billBefore: number;
    billAfter: number;
    roi: number | null;
    gain: number;
    taxBenefit: number;
    netInvestorCost: number;
    yieldBrut: number;
    cashflow: number;
    banDate: Date | null;
    hasITI: boolean;
}

const toSimulation = (r: any): Simulation => ({
    currentLabel: r.current_label,
    newLabel: r.new_label,
    newCep: r.new_cep,
    newGes: r.new_ges,
    thresholds: r.thresholds,
    cost: r.cost,
    activeDetailedCosts: r.detailed_costs,
    durationDays: r.duration_days,
    sub: r.subsidies,
    ceeEst: r.cee_est,
    aidPathway: r.aid_pathway,
    aidNotes: r.aid_notes,
    rest: r.rest_to_pay,
    ecoPTZAmount: r.eco_ptz_amount,
    ecoPTZLimit: r.eco_ptz_limit,
    savings: r.annual_savings,
    billBefore: r.annual_bill_before,
    billAfter: r.annual_bill_after,
    roi: r.roi_years,
    gain: r.latent_gain,
    taxBenefit: r.tax_benefit,
    netInvestorCost: r.net_investor_cost,
    yieldBrut: r.yield_brut,
    cashflow: r.cashflow,
    banDate: r.ban_date ? new Date(r.ban_date) : null,
    hasITI: r.has_iti,
});

// Maps an API search result to the UI property model
const toProperty = (r: any): PropertyData => ({
    address: r.address,
    ademe_dpe_number: r.ademe_dpe_number,
    surface: r.shab,
    year: r.construction_year,
    constructionPeriod: r.construction_period,
    initialCep: r.consumption_level || 350,
    label: r.dpe_class_current,
    buildingType: r.building_type || "Logement",
    heatingType: r.systems?.[0]?.energy_source,
    finalConsumption: r.final_consumption || undefined,
    gesValue: r.ges_value || 10,
    postcode: r.postcode || undefined,
    lossShares: r.loss_shares,
    insulationQuality: r.insulation_quality,
    dpeLosses: r.dpe_losses,
    suggestedWorks: r.suggested_works || [],
    preselectedWorks: r.preselected_works || [],
});

// Debounced server-side simulation; the previous result stays displayed meanwhile
function useSimulation(input: object | null, setSim: (s: Simulation) => void) {
    useEffect(() => {
        if (!input) return;
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            try {
                const res = await fetch('/api/simulate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(input),
                    signal: controller.signal,
                });
                if (!res.ok) throw new Error(`Simulation error: ${res.status}`);
                setSim(toSimulation(await res.json()));
            } catch (err) {
                if ((err as Error).name !== 'AbortError') console.error(err);
            }
        }, 250);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [input, setSim]);
}

const LOSS_ELEMENTS = [
    { id: 'roof', name: 'Toiture', color: '#3b82f6' },
    { id: 'walls', name: 'Murs', color: '#60a5fa' },
    { id: 'windows', name: 'Vitrage', color: '#93c5fd' },
    { id: 'floor', name: 'Sols', color: '#bfdbfe' },
    { id: 'air', name: 'Air', color: '#dbeafe' },
    { id: 'bridges', name: 'Ponts thermiques', color: '#e0e7ff' },
];

const isHouse = (buildingType?: string) => (buildingType || '').toLowerCase().includes('maison');

// --- Main Component ---

export default function App() {
    return (
        <AccountProvider>
            <Pages />
        </AccountProvider>
    );
}

function Pages() {
    const path = usePath();
    const pages: Record<string, JSX.Element> = {
        '/tarifs': <PricingPage />,
        '/cgv': <CgvPage />,
        '/mentions-legales': <MentionsLegalesPage />,
        '/confidentialite': <ConfidentialitePage />,
    };
    const page = pages[path] ?? null;
    return (
        <>
            {page}
            {/* Kept mounted so the current simulation survives a visit to the other pages */}
            <div hidden={page !== null}><Simulator /></div>
        </>
    );
}

function Simulator() {
    const { requestReport, config, me } = useAccount();
    const [view, setView] = useState<'landing' | 'results' | 'dashboard'>('landing');
    const [loading, setLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [suggestions, setSuggestions] = useState<any[]>([]);
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const [property, setProperty] = useState<PropertyData | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [incomeLevel, setIncomeLevel] = useState<IncomeLevel>('intermediaire');
    const [dpeSearchQuery, setDpeSearchQuery] = useState("");
    const [downloading, setDownloading] = useState(false);
    const [activeScenario, setActiveScenario] = useState<'A' | 'B'>('A');
    const [userProfile, setUserProfile] = useState<'propriétaire' | 'investisseur'>('propriétaire');

    // New Precision Parameters
    const [nbEtages, setNbEtages] = useState(0);
    const [hasAscenseur, setHasAscenseur] = useState(true);
    const [isUrbanDense, setIsUrbanDense] = useState(false);
    const [parkingCost, setParkingCost] = useState(35.0);

    // Investor States
    const [isInvestor, setIsInvestor] = useState(false);
    const [monthlyRent, setMonthlyRent] = useState(800);
    const [purchasePrice, setPurchasePrice] = useState(150000);
    const [tmi, setTmi] = useState(30);

    const [actionsA, setActionsA] = useState<RetrofitAction[]>([]);
    const [actionsB, setActionsB] = useState<RetrofitAction[]>([]);
    const [simA, setSimA] = useState<Simulation | null>(null);
    const [simB, setSimB] = useState<Simulation | null>(null);

    useEffect(() => {
        fetch('/api/works')
            .then(res => res.json())
            .then(data => {
                const actions = (data.works || []).map((w: any) => ({ id: w.id, name: w.name, description: w.description, active: false }));
                setActionsA(actions);
                setActionsB(actions);
            })
            .catch(err => console.error("Works catalog error:", err));
    }, []);

    const toggleAction = (id: string) => {
        const updater = activeScenario === 'A' ? setActionsA : setActionsB;
        const currentActions = activeScenario === 'A' ? actionsA : actionsB;
        updater(currentActions.map(a => a.id === id ? { ...a, active: !a.active } : a));
    };


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
            const res = await fetch(`/api/search-address?q=${encodeURIComponent(addressQuery)}`);
            if (!res.ok) throw new Error(`Serveur Error: ${res.status}`);
            const data = await res.json();

            if (data.results && data.results.length > 0) {
                setSearchResults(data.results.map(toProperty));
                setView('results');
            } else if (data.error) {
                setError("Le service ADEME est lent ou indisponible. Veuillez patienter 10s et réessayer.");
            } else {
                setError("Aucun DPE trouvé pour cette adresse.");
            }
        } catch (err) {
            setError("Erreur réseau API SPREA.");
        } finally {
            setLoading(false);
        }
    };

    const handleDpeSearch = async () => {
        if (!dpeSearchQuery) return;
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`/api/search-dpe/${encodeURIComponent(dpeSearchQuery)}`);
            if (!res.ok) throw new Error(`Serveur Error: ${res.status}`);
            const data = await res.json();
            if (data.results && data.results.length > 0) {
                setSearchResults(data.results.map(toProperty));
                setView('results');
            } else {
                setError("Aucun DPE trouvé pour ce numéro.");
            }
        } catch (err) {
            setError("Erreur réseau API.");
        } finally {
            setLoading(false);
        }
    };

    const selectProperty = (p: PropertyData) => {
        // Full State Reset
        setActiveScenario('A');
        setIsInvestor(false);
        setIncomeLevel('intermediaire');
        setTmi(30);
        setMonthlyRent(800);
        setPurchasePrice(p.surface * 4200);

        // Reset Precision/Urban parameters
        setNbEtages(0);
        setHasAscenseur(true);
        setIsUrbanDense(false);
        setParkingCost(35.0);

        setProperty(p);
        setSimA(null);
        setSimB(null);

        const suggested = new Set(p.suggestedWorks || []);
        const preselected = new Set(p.preselectedWorks || []);
        setActionsA(prev => prev.map(a => ({ ...a, suggested: suggested.has(a.id), active: preselected.has(a.id) })));
        setActionsB(prev => prev.map(a => ({ ...a, suggested: suggested.has(a.id), active: false })));

        setView('dashboard');
    };

    // --- Simulation Logic ---

    // Heat losses before works, from the envelope model (api/envelope.py)
    const heatLoss = useMemo(() => {
        const shares = property?.lossShares;
        if (!shares) return null;
        return LOSS_ELEMENTS.map(e => ({ ...e, val: (shares[e.id] || 0) * 100 }));
    }, [property]);

    const buildSimulationInput = (actions: RetrofitAction[]) => property && ({
        property: {
            surface: property.surface,
            initial_cep: property.initialCep,
            ges_value: property.gesValue ?? null,
            building_type: property.buildingType,
            postcode: property.postcode ?? null,
            construction_year: property.year || null,
            construction_period: property.constructionPeriod ?? null,
            price_per_m2: property.pricePerM2 ?? null,
            heating_energy: property.heatingType ?? null,
            final_consumption: property.finalConsumption ?? null,
            insulation_quality: property.insulationQuality ?? null,
            dpe_losses: property.dpeLosses ?? null,
        },
        works: actions.filter(a => a.active).map(a => a.id),
        suggested_works: actions.filter(a => a.suggested).map(a => a.id),
        income_level: incomeLevel,
        nb_etages: nbEtages || 0,
        has_ascenseur: hasAscenseur,
        is_urban_dense: isUrbanDense,
        parking_cost: parkingCost || 0,
        is_investor: isInvestor,
        monthly_rent: monthlyRent || 0,
        purchase_price: purchasePrice || 0,
        tmi: tmi || 0,
    });

    const inputA = useMemo(() => buildSimulationInput(actionsA), [actionsA, property, incomeLevel, tmi, isInvestor, monthlyRent, purchasePrice, nbEtages, hasAscenseur, isUrbanDense, parkingCost]);
    const inputB = useMemo(() => buildSimulationInput(actionsB), [actionsB, property, incomeLevel, tmi, isInvestor, monthlyRent, purchasePrice, nbEtages, hasAscenseur, isUrbanDense, parkingCost]);

    useSimulation(inputA, setSimA);
    useSimulation(inputB, setSimB);

    const activeSim = activeScenario === 'A' ? simA : simB;

    const handleDownloadPDF = async () => {
        const simulation = activeScenario === 'A' ? inputA : inputB;
        if (!property || !simulation) return;
        setDownloading(true);
        try {
            await requestReport({
                meta: {
                    address: property.address || "Adresse inconnue",
                    year: property.year || null,
                    ademe_dpe_number: property.ademe_dpe_number || null,
                    building_type: property.buildingType || null,
                    construction_period: property.constructionPeriod || null,
                },
                simulation,
            });
        } finally { setDownloading(false); }
    };

    // --- Views ---

    if (view === 'landing') return (
        <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 font-sans relative">
            <div className="absolute top-6 right-6 flex items-center gap-3">
                <Link to="/tarifs" className="text-[10px] font-black uppercase tracking-widest text-slate-500 hover:text-slate-900 px-3">Tarifs</Link>
                <AccountButton />
            </div>
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
                <div className="bg-white rounded-[2.5rem] p-5 sm:p-10 shadow-2xl border border-slate-100 relative z-10">
                    <div className="relative">
                        <div className="flex items-center bg-slate-100 rounded-2xl px-4 sm:px-6 h-16 border-2 border-transparent focus-within:border-blue-600 focus-within:bg-white transition-all">
                            <Search size={24} className="text-slate-400 mr-4 shrink-0" />
                            <input
                                type="text"
                                placeholder="Adresse (ex: 43 rue Brule Maison, Lille)..."
                                className="flex-1 min-w-0 bg-transparent text-lg font-bold outline-none text-slate-900 placeholder:text-slate-400"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                            {loading && <Loader2 className="animate-spin text-blue-600" size={24} />}
                        </div>

                        <div className="flex items-center bg-slate-100 rounded-2xl px-4 sm:px-6 h-16 border-2 border-transparent focus-within:border-emerald-600 focus-within:bg-white transition-all mt-4">
                            <FileText size={24} className="text-slate-400 mr-4 shrink-0" />
                            <input
                                type="text"
                                placeholder="Numéro DPE ADEME (Ex: 2134E...)"
                                className="flex-1 min-w-0 bg-transparent text-lg font-bold outline-none text-slate-900 placeholder:text-slate-400"
                                value={dpeSearchQuery}
                                onChange={(e) => setDpeSearchQuery(e.target.value)}
                            />
                            <button onClick={handleDpeSearch} className="bg-emerald-600 text-white px-4 py-2 rounded-xl text-xs font-black hover:bg-emerald-700 transition-colors">Vérifier</button>
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
            <SiteFooter className="absolute bottom-0 inset-x-0" />
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
                                <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mt-0.5">DPE N° {res.ademe_dpe_number}</p>
                                <div className="flex items-center gap-4 mt-2">
                                    <span className="text-xs font-bold text-slate-400 flex items-center gap-1">
                                        {res.buildingType?.toLowerCase().includes('appartement') ? <Building size={12} /> : <Home size={12} />}
                                        {res.buildingType}
                                    </span>
                                    <span className="text-xs font-bold text-slate-400 flex items-center gap-1">
                                        <TrendingUp size={12} /> {res.surface} m²
                                    </span>
                                    <span className="text-xs font-bold text-slate-400 flex items-center gap-1">
                                        <Layers size={12} /> {res.constructionPeriod || (res.year ? `Période ${res.year}` : 'Inconnu')}
                                    </span>
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
            <header className="mb-6 flex flex-col xl:flex-row xl:items-center justify-between gap-6 rounded-[2.5rem] bg-white p-8 shadow-sm border border-slate-100">
                <div className="flex items-center gap-6">
                    <div className="rounded-2xl bg-slate-900 p-5 text-white shadow-xl rotate-[-2deg]">
                        {property?.buildingType?.includes('Appartement') ? <Building size={36} /> : <Home size={36} />}
                    </div>
                    <div>
                        <div className="flex items-center gap-3">
                            <h1 className="text-3xl font-black text-slate-800 tracking-tight">{property?.address}</h1>
                        </div>
                        <div className="flex items-center gap-4 mt-1">
                            <p className="text-sm font-bold text-slate-400">
                                {property?.buildingType} • {property?.surface} m² • {property?.constructionPeriod}
                            </p>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2 p-3 bg-slate-50 rounded-[1.5rem] border border-slate-100">
                        <div className="flex items-center gap-2 px-2 border-r border-slate-200">
                            <div className={`flex items-center justify-center rounded-xl h-10 w-10 text-xl font-black text-white shadow-lg`} style={{ backgroundColor: DPE_COLORS[activeSim?.currentLabel || 'G'] }}>
                                {activeSim?.currentLabel}
                            </div>
                            <div className="flex items-center gap-2">
                                {property?.label !== activeSim?.currentLabel && (
                                    <div className="group relative">
                                        <span className="px-3 py-1 bg-amber-50 text-amber-600 text-[10px] font-black rounded-lg border border-amber-100 uppercase tracking-tighter shadow-sm cursor-help animate-pulse inline-block">ADEME: {property?.label}</span>
                                        <div className="absolute top-full right-0 mt-2 w-64 p-3 bg-slate-900 text-[10px] font-bold text-white rounded-xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                                            L'écart entre le DPE ADEME et notre calcul est dû à l'actualisation des tarifs énergétiques et du mode de calcul de la Loi Climat (re-calculé en temps réel).
                                        </div>
                                    </div>
                                )}
                                <div className="group relative">
                                    <div className="flex items-center gap-2 px-3 py-1 bg-blue-600 rounded-full text-white shadow-lg shadow-blue-200 cursor-help">
                                        <TrendingUp size={12} className="animate-bounce" />
                                        <span className="text-[10px] font-black uppercase tracking-tight">+{Math.round(activeSim?.gain || 0).toLocaleString()} €</span>
                                    </div>
                                    <div className="absolute top-full right-0 mt-2 w-64 p-3 bg-slate-900 text-[10px] font-bold text-white rounded-xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                                        <b>Plus-value estimée :</b> Gain de valeur du bien lié à l'amélioration de sa performance énergétique.
                                    </div>
                                </div>
                            </div>
                        </div>
                        {activeSim?.banDate && (
                            <div className="flex flex-col items-end px-4 border-r border-slate-200">
                                <p className="text-[9px] font-black uppercase text-red-500 tracking-widest">Loi Climat</p>
                                <p className="text-[11px] font-extrabold text-slate-800">
                                    {(activeSim?.banDate || new Date()) <= new Date() ? 'INTERDIT' : `Interdiction en ${activeSim?.banDate?.getFullYear()}`}
                                </p>
                            </div>
                        )}
                        <div className="flex gap-4 px-2">
                            <div className="text-right">
                                <p className="text-[9px] font-black uppercase text-slate-400">Cible</p>
                                <div className={`flex items-center justify-center rounded-lg h-7 w-7 text-sm font-black text-white shadow-md mx-auto`} style={{ backgroundColor: DPE_COLORS[activeSim?.newLabel || 'A'] }}>
                                    {activeSim?.newLabel}
                                </div>
                            </div>
                        </div>
                    </div>
                    <div className="flex flex-wrap gap-3">
                        <button onClick={handleDownloadPDF} disabled={downloading} className="h-14 px-8 rounded-2xl bg-blue-50 text-blue-600 font-bold hover:bg-blue-600 hover:text-white transition-all flex items-center gap-3 border border-blue-100 shadow-sm">
                            {downloading ? <Loader2 className="animate-spin" /> : <FileText size={20} />}
                            <span className="uppercase text-xs tracking-widest">
                                Rapport PDF{!me?.is_pro && config?.report_price ? ` · ${config.report_price}` : ''}
                            </span>
                        </button>
                        <AccountButton />
                        <button onClick={() => setView('landing')} className="h-14 px-6 rounded-2xl bg-slate-100 text-slate-500 font-black hover:bg-slate-900 hover:text-white transition-all text-[10px] uppercase tracking-widest border border-slate-200">Retour</button>
                    </div>
                </div>
            </header>

            <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 max-w-[1600px] mx-auto">
                {/* Sidebar: Secondary Settings */}
                <aside className="lg:col-span-3 space-y-6 order-2 lg:order-1">
                    <section className="rounded-3xl bg-white p-8 shadow-sm border border-slate-100">
                        <h3 className="mb-6 flex items-center gap-3 text-xl font-black text-slate-800 uppercase tracking-tight">
                            <Zap size={24} className="text-blue-500" />
                            Précision
                        </h3>
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="group relative">
                                    <label className="flex items-center gap-2 text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">
                                        Nombre d'étages
                                        <span className="cursor-help text-slate-300">?</span>
                                    </label>
                                    <input
                                        type="number"
                                        value={nbEtages}
                                        onChange={(e) => setNbEtages(e.target.value === '' ? '' as any : parseInt(e.target.value))}
                                        className="w-full h-12 bg-slate-50 border-2 border-slate-100 rounded-2xl px-4 text-sm font-black focus:border-blue-600 transition-all outline-none"
                                    />
                                </div>
                                <div className="flex flex-col justify-end">
                                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Ascenseur</label>
                                    <button
                                        onClick={() => setHasAscenseur(!hasAscenseur)}
                                        className={`w-full h-12 rounded-2xl border-2 font-black text-[10px] uppercase transition-all ${hasAscenseur ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white border-slate-100 text-slate-400'}`}
                                    >
                                        {hasAscenseur ? 'OUI' : 'NON'}
                                    </button>
                                </div>
                            </div>
                            <div className="flex items-center justify-between p-4 bg-slate-50 rounded-2xl border-2 border-slate-100">
                                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Zone Urbaine</span>
                                <button
                                    onClick={() => setIsUrbanDense(!isUrbanDense)}
                                    className={`w-12 h-6 rounded-full relative transition-all ${isUrbanDense ? 'bg-blue-600' : 'bg-slate-300'}`}
                                >
                                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${isUrbanDense ? 'left-7' : 'left-1'}`} />
                                </button>
                            </div>
                            {isUrbanDense && (
                                <div className="p-4 bg-blue-50/50 rounded-2xl border border-blue-100 animate-in zoom-in-95 duration-200">
                                    <label className="block text-[10px] font-black text-blue-600 uppercase tracking-widest mb-2 flex items-center justify-between">
                                        Stationnement (€/j)
                                        <span className="text-[8px] bg-blue-100 px-2 py-0.5 rounded text-blue-500">{activeSim?.durationDays ?? 1} j.</span>
                                    </label>
                                    <input
                                        type="number"
                                        value={parkingCost}
                                        onChange={(e) => setParkingCost(e.target.value === '' ? '' as any : parseFloat(e.target.value))}
                                        className="w-full h-10 bg-white border-2 border-slate-100 rounded-xl px-4 text-sm font-black focus:border-blue-600 transition-all outline-none"
                                    />
                                </div>
                            )}
                        </div>
                    </section>

                    <section className="rounded-3xl bg-white p-8 shadow-sm border border-slate-100">
                        <div className="space-y-6">
                            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3 ml-1">Profil du Rapport</p>
                                <div className="flex gap-2 p-1 bg-white rounded-xl border border-slate-100">
                                    {(['propriétaire', 'investisseur'] as const).map(p => (
                                        <button
                                            key={p}
                                            onClick={() => {
                                                setUserProfile(p);
                                                setIsInvestor(p === 'investisseur');
                                            }}
                                            className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${userProfile === p ? 'bg-blue-600 text-white shadow-md' : 'text-slate-400 hover:bg-slate-50'}`}
                                        >
                                            {p === 'propriétaire' ? 'Patrimoine' : 'Investisseur'}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            {userProfile === 'investisseur' && (
                                <div className="p-4 bg-blue-50/30 rounded-2xl border border-blue-100 animate-in slide-in-from-top-2">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-blue-600 mb-4 ml-1">Paramètres Locatifs</p>
                                    <div className="space-y-4">
                                        <div>
                                            <p className="text-[8px] font-bold text-slate-400 uppercase mb-1 ml-1">TMI (%)</p>
                                            <div className="flex gap-1">
                                                {[0, 11, 30, 41, 45].map(v => <button key={v} onClick={() => setTmi(v)} className={`flex-1 py-1.5 rounded-lg text-[10px] font-black border transition-all ${tmi === v ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-400 border-slate-50'}`}>{v}%</button>)}
                                            </div>
                                        </div>
                                        <div>
                                            <p className="text-[8px] font-bold text-slate-400 uppercase mb-1 ml-1">Prix d'Achat (€)</p>
                                            <input type="number" value={purchasePrice} onChange={(e) => setPurchasePrice(Number(e.target.value))} className="w-full h-10 bg-white border-2 border-slate-100 rounded-xl px-4 text-xs font-black focus:border-blue-600 outline-none" />
                                        </div>
                                        <div>
                                            <p className="text-[8px] font-bold text-slate-400 uppercase mb-1 ml-1">Loyer (€/mois)</p>
                                            <input type="number" value={monthlyRent} onChange={(e) => setMonthlyRent(Number(e.target.value))} className="w-full h-10 bg-white border-2 border-slate-100 rounded-xl px-4 text-xs font-black focus:border-blue-600 outline-none" />
                                        </div>
                                    </div>
                                </div>
                            )}
                            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1 ml-1">Revenus du Ménage</p>
                                <p className="text-[8px] font-bold text-blue-500 uppercase mb-3 ml-1">Aides calculées sur foyer</p>
                                <div className="grid grid-cols-2 gap-2">
                                    {(['tres_modeste', 'modeste', 'intermediaire', 'superieur'] as IncomeLevel[]).map(l => (
                                        <button key={l} onClick={() => setIncomeLevel(l)} className={`px-2 py-2 rounded-xl text-[8px] font-black uppercase transition-all border-2 ${incomeLevel === l ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-400 border-slate-50'}`}>{l.replace('_', ' ')}</button>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </section>
                </aside>

                <main className="lg:col-span-9 space-y-8 order-1 lg:order-2">
                    {/* 1. DPE Chart Section */}
                    <section className="rounded-[2.5rem] bg-white p-10 shadow-sm border border-slate-100 relative overflow-hidden group">
                        <div className="mb-10 flex items-center justify-between relative z-10">
                            <div>
                                <h3 className="text-2xl font-black text-slate-800 tracking-tight">Objectif Amélioration Énergétique</h3>
                                <div className="flex flex-wrap gap-2 mt-2">
                                    <span className="px-3 py-1.5 bg-blue-50 text-blue-700 font-extrabold text-[10px] rounded-lg tracking-widest uppercase border border-blue-100 shadow-sm">{activeSim?.currentLabel} ➔ {activeSim?.newLabel}</span>
                                    <span className="px-3 py-1.5 bg-green-50 text-green-700 font-extrabold text-[10px] rounded-lg tracking-widest uppercase border border-green-100 shadow-sm">{Math.round(activeSim?.newCep || 0)} kWh/m².an</span>
                                    {activeSim && (
                                        <span className="px-3 py-1.5 bg-slate-50 text-slate-700 font-extrabold text-[10px] rounded-lg tracking-widest uppercase border border-slate-100 shadow-sm">
                                            Facture énergie : {Math.round(activeSim.billBefore).toLocaleString()} € ➔ {Math.round(activeSim.billAfter).toLocaleString()} € / an
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                        <div className="grid grid-cols-7 gap-3 h-20 relative z-10">
                            {(activeSim?.thresholds || []).map(t => (
                                <div key={t.label} className="relative flex items-center justify-center font-black text-white text-2xl rounded-2xl shadow-lg transition-transform hover:scale-105" style={{ backgroundColor: DPE_COLORS[t.label as DPEClass] }}>
                                    {t.label}
                                    {activeSim?.currentLabel === t.label && <div className="absolute -top-12 flex flex-col items-center"><div className="w-2.5 h-2.5 rounded-full bg-slate-800 ring-4 ring-slate-100" /><div className="h-6 w-0.5 bg-slate-800" /></div>}
                                    {activeSim?.newLabel === t.label && <div className="absolute -bottom-14 flex flex-col items-center animate-bounce"><div className="h-6 w-0.5 bg-blue-600" /><div className="w-2.5 h-2.5 rounded-full bg-blue-600 ring-4 ring-blue-100" /></div>}
                                </div>
                            ))}
                        </div>
                    </section>

                    {/* 2. Middle Row: Actions + Heat Loss */}
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                        <section className="rounded-[2.5rem] bg-white p-8 shadow-sm border border-slate-100 h-full">
                            <div className="flex items-center justify-between mb-8">
                                <h3 className="text-xl font-black text-slate-800 uppercase tracking-tight flex items-center gap-3">
                                    <Layers size={24} className="text-blue-500" />
                                    Actions de Rénovation
                                </h3>
                            </div>

                            <div className="grid grid-cols-1 gap-3 overflow-y-auto max-h-[500px] pr-2 custom-scrollbar">
                                {(activeScenario === 'A' ? actionsA : actionsB)
                                    .filter(a => a.id !== 'roof' || isHouse(property?.buildingType))
                                    .map(a => (
                                        <div key={a.id} className="group relative">
                                            <button onClick={() => toggleAction(a.id)} className={`w-full flex items-center justify-between p-5 rounded-2xl border-2 transition-all ${a.active ? 'border-blue-600 bg-blue-50/30' : 'border-slate-50 bg-slate-50/50 hover:border-slate-200 hover:bg-white'}`}>
                                                <div className="flex flex-col items-start gap-1">
                                                    <span className={`font-black text-sm uppercase tracking-tight ${a.active ? 'text-blue-700' : 'text-slate-700'}`}>{a.name}</span>
                                                    {a.suggested && <span className="text-[7px] font-black uppercase tracking-widest text-blue-500 bg-blue-100 px-2 py-0.5 rounded-md">Recommandation Prioritaire</span>}
                                                </div>
                                                <div className={`h-6 w-11 rounded-full shrink-0 relative transition-all ${a.active ? 'bg-blue-600 shadow-md shadow-blue-100' : 'bg-slate-300'}`}>
                                                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${a.active ? 'left-6' : 'left-1'}`} />
                                                </div>
                                            </button>
                                        </div>
                                    ))}
                            </div>
                        </section>

                        <section className="rounded-[2.5rem] bg-slate-900 p-8 text-white shadow-2xl h-full flex flex-col border-r-[12px] border-blue-600/20">
                            <div className="flex items-center justify-between mb-8">
                                <h3 className="flex items-center gap-3 text-xl font-black text-blue-300 uppercase tracking-tight"><PieChart size={24} /> Déperditions Thermiques</h3>
                                <div className="p-2 bg-white/5 rounded-xl border border-white/10 text-[9px] font-bold text-slate-400 uppercase">Impact Direct</div>
                            </div>
                            <div className="space-y-6 flex-1">
                                {heatLoss?.map(item => (
                                    <div key={item.id} className="group cursor-default">
                                        <div className="flex justify-between text-[11px] font-black uppercase tracking-wider mb-2 text-slate-300 group-hover:text-blue-300 transition-colors">
                                            <span>{item.name}</span>
                                            <span className="text-white bg-white/10 px-2 py-0.5 rounded-lg">{Math.round(item.val)}%</span>
                                        </div>
                                        <div className="h-3 bg-white/5 rounded-full overflow-hidden p-0.5 border border-white/10">
                                            <div className="h-full rounded-full transition-all duration-700 ease-out shadow-sm" style={{ width: `${item.val}%`, backgroundColor: item.color }} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <div className="mt-8 pt-6 border-t border-white/5 text-[9px] font-medium text-slate-500 leading-relaxed italic">
                                * Répartition estimée à partir du DPE (type de logement, époque de construction, qualité d'isolation déclarée) : zones de pertes de chaleur prioritaires avant travaux.
                            </div>
                        </section>
                    </div>

                    {/* 3. Bottom Row: Strategy & Financing */}
                    <section className="rounded-[2.5rem] bg-white p-10 shadow-sm border-2 border-green-500/20 relative overflow-hidden">
                        <div className="absolute top-0 right-0 w-64 h-64 bg-green-50 rounded-full blur-[100px] -mr-32 -mt-32 opacity-50 transition-opacity" />
                        <h3 className="text-2xl font-black text-slate-800 mb-10 uppercase tracking-tighter flex items-center gap-4">
                            <div className="h-8 w-2 bg-green-500 rounded-full" />
                            Plan de Financement Stratégique
                        </h3>

                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-12 relative z-10">
                            <div className="lg:col-span-1 space-y-6">
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">Détails des Investissements</p>
                                <div className="space-y-3">
                                    {activeSim?.activeDetailedCosts.map((item: any, idx: number) => (
                                        <div key={idx} className="flex justify-between items-center group">
                                            <span className="text-sm font-bold text-slate-600 group-hover:text-slate-900 transition-colors">{item.name}{item.suggested && <span className="text-[8px] text-blue-500 ml-2 italic">*</span>}</span>
                                            <span className="text-sm font-black text-slate-800">{Math.round(item.cost).toLocaleString()} €</span>
                                        </div>
                                    ))}
                                    <div className="pt-4 mt-4 border-t-2 border-slate-100 flex justify-between items-end">
                                        <span className="text-xs font-black uppercase text-slate-400">Total Investissement</span>
                                        <span className="text-2xl font-black text-slate-900">{Math.round(activeSim?.cost || 0).toLocaleString()} €</span>
                                    </div>
                                    {activeSim?.hasITI && (
                                        <div className="mt-4 p-3 bg-amber-50 rounded-xl border border-amber-100 flex items-start gap-2">
                                            <p className="text-[9px] font-bold text-amber-800 leading-tight">
                                                <b>Note ITI :</b> Prévoir une perte de ~1.5% de surface Carrez.
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div className="lg:col-span-1 space-y-6 bg-slate-50/50 p-6 rounded-[2rem] border border-slate-100">
                                <p className="text-[10px] font-black text-green-600 uppercase tracking-widest border-b border-green-100 pb-2">Aides & Subventions</p>
                                <div className="space-y-4">
                                    <div className="flex justify-between items-center group relative">
                                        <span className="text-sm font-bold text-slate-500 flex items-center gap-1 cursor-help italic">MaPrimeRénov' <span className="text-[10px]">ⓘ</span></span>
                                        <span className="text-lg font-black text-green-600">-{Math.round(activeSim?.sub || 0).toLocaleString()} €</span>
                                        <div className="absolute bottom-full left-0 mb-2 w-64 p-4 bg-slate-900 text-[10px] font-medium text-white rounded-xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 leading-relaxed">
                                            <b>MaPrimeRénov' :</b> Aide principale de l'Anah, selon la catégorie de revenus du foyer. Rénovation d'ampleur (gain de 2 classes et 2 gestes d'isolation minimum) : % du montant HT plafonné. Sinon, forfaits par geste. Barème 2025.
                                        </div>
                                    </div>
                                    <div className="flex justify-between items-center group relative">
                                        <span className="text-sm font-bold text-slate-500 flex items-center gap-1 cursor-help italic">Primes CEE (Est.) <span className="text-[10px]">ⓘ</span></span>
                                        <span className="text-lg font-black text-green-600">-{Math.round(activeSim?.ceeEst || 0).toLocaleString()} €</span>
                                        <div className="absolute bottom-full left-0 mb-2 w-64 p-4 bg-slate-900 text-[10px] font-medium text-white rounded-xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 leading-relaxed">
                                            <b>Prime CEE :</b> Versée par les fournisseurs d'énergie (EDF, Engie, etc.). Dépend du volume de kWh économisés grâce aux travaux.
                                        </div>
                                    </div>
                                    <div className="flex justify-between items-center group relative border-t border-slate-100 pt-3">
                                        <span className="text-sm font-bold text-slate-500 flex items-center gap-1 cursor-help italic">Éco-PTZ (Capped) <span className="text-[10px]">ⓘ</span></span>
                                        <span className="text-lg font-black text-blue-600">-{Math.round(activeSim?.ecoPTZAmount || 0).toLocaleString()} €</span>
                                        <div className="absolute bottom-full left-0 mb-2 w-64 p-4 bg-slate-900 text-[10px] font-medium text-white rounded-xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 leading-relaxed">
                                            <b>Éco-Prêt à Taux Zéro :</b> Prêt sans intérêts pour financer le reste à charge. Limité à 15k€ pour 1 action, 25k€ pour 2 actions et 30k€ pour 3 ou plus.
                                        </div>
                                    </div>
                                </div>
                                <p className="text-[9px] font-bold text-slate-400 uppercase tracking-tight">
                                    {activeSim?.aidPathway === 'accompagne' ? "Parcours accompagné (rénovation d'ampleur)" : activeSim?.aidPathway === 'geste' ? 'MaPrimeRénov\' par geste' : 'Aucune aide éligible'}
                                </p>
                                {activeSim?.aidNotes?.map((n: string) => (
                                    <p key={n} className="text-[9px] text-amber-600 leading-relaxed">{n}</p>
                                ))}
                            </div>

                            <div className="lg:col-span-1 flex flex-col justify-center items-center text-center p-8 bg-blue-600 rounded-[2.5rem] shadow-2xl shadow-blue-200">
                                <p className="text-[11px] font-black text-blue-100 uppercase tracking-widest mb-4">Reste à Charge Final</p>
                                <p className="text-5xl font-black text-white tracking-tighter mb-2">{Math.round(activeSim?.rest || 0).toLocaleString()} €</p>
                                <p className="text-[9px] font-bold text-blue-200 uppercase tracking-tight italic opacity-80">Soit {Math.round(((activeSim?.rest || 0) / (activeSim?.cost || 1)) * 100)}% de l'investissement initial</p>
                                <button
                                    onClick={() => {
                                        const el = document.getElementById('financing-details');
                                        el?.scrollIntoView({ behavior: 'smooth' });
                                    }}
                                    className="mt-8 w-full py-4 bg-white text-blue-600 rounded-2xl font-black uppercase text-xs tracking-widest hover:bg-blue-50 transition-all shadow-xl"
                                >
                                    Détails des Aides
                                </button>
                            </div>
                        </div>

                        {/* Detailed Aid Explanations Chapters */}
                        <div id="financing-details" className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-8 pt-10 border-t border-slate-100">
                            <div className="space-y-4">
                                <div className="h-1 w-10 bg-blue-600 rounded-full" />
                                <h4 className="text-sm font-black text-slate-800 uppercase">Focus MaPrimeRénov'</h4>
                                <p className="text-[10px] text-slate-500 leading-relaxed">
                                    MaPrimeRénov' est l'aide principale de l'État pour la rénovation énergétique. Pour être éligible, le logement doit être construit depuis plus de 15 ans. Le montant dépend du gain de classe DPE : une rénovation globale (au moins 2 classes) déclenche des forfaits bien plus élevés.
                                </p>
                            </div>
                            <div className="space-y-4">
                                <div className="h-1 w-10 bg-green-500 rounded-full" />
                                <h4 className="text-sm font-black text-slate-800 uppercase">Focus Primes CEE</h4>
                                <p className="text-[10px] text-slate-500 leading-relaxed">
                                    Les Certificats d'Économie d'Énergie sont financés par les "pollueurs-payeurs". Cette prime est cumulable avec MaPrimeRénov' par geste, mais pas avec le parcours accompagné (l'Anah les valorise elle-même). Elle est versée sous forme de virement bancaire ou de bon d'achat après validation des travaux par un organisme indépendant.
                                </p>
                            </div>
                            <div className="space-y-4">
                                <div className="h-1 w-10 bg-blue-400 rounded-full" />
                                <h4 className="text-sm font-black text-slate-800 uppercase">Focus Éco-PTZ</h4>
                                <p className="text-[10px] text-slate-500 leading-relaxed">
                                    L'Éco-Prêt à Taux Zéro permet de financer les travaux sans avance de trésorerie. La durée de remboursement peut aller jusqu'à 20 ans pour les rénovations globales. Il est distribué par la plupart des banques françaises sur présentation des devis RGE.
                                </p>
                            </div>
                        </div>
                    </section>
                    <p className="text-[10px] text-slate-400 leading-relaxed text-center max-w-3xl mx-auto px-4">
                        Simulation indicative fondée sur les données publiques ADEME et des coûts moyens de marché. Elle ne constitue ni un DPE, ni un audit énergétique réglementaire, ni un devis. Les montants d'aides (barème MaPrimeRénov' 2025) doivent être confirmés par France Rénov' ou un Accompagnateur Rénov' avant tout engagement.
                    </p>
                    <SiteFooter />
                </main>
            </div>
        </div>
    );
}

