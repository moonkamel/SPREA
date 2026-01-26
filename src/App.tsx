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
    AlertTriangle
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
    loss_breakdown?: {
        walls: number;
        windows: number;
        ventilation: number;
    }
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


const getRegion = (postcode?: string) => {
    if (!postcode) return 'METROPOLE';
    return postcode.startsWith('97') ? 'OUTRE_MER' : 'METROPOLE';
};

const getRentalBanDate = (label: DPEClass, consumption: number, region: 'METROPOLE' | 'OUTRE_MER') => {
    if (region === 'METROPOLE' && consumption > 450) {
        return new Date('2023-01-01');
    }
    const banSchedule: Record<string, Partial<Record<DPEClass, string>>> = {
        'METROPOLE': { 'G': '2025-01-01', 'F': '2028-01-01', 'E': '2034-01-01' },
        'OUTRE_MER': { 'G': '2028-01-01', 'F': '2031-01-01' }
    };
    const dateStr = banSchedule[region]?.[label];
    return dateStr ? new Date(dateStr) : null;
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
    const [dpeSearchQuery, setDpeSearchQuery] = useState("");
    const [downloading, setDownloading] = useState(false);
    const [compareMode, setCompareMode] = useState(false);
    const [activeScenario, setActiveScenario] = useState<'A' | 'B'>('A');
    const [userProfile, setUserProfile] = useState<'propriétaire' | 'investisseur'>('propriétaire');

    // Investor States
    const [isInvestor, setIsInvestor] = useState(false);
    const [monthlyRent, setMonthlyRent] = useState(800);
    const [purchasePrice, setPurchasePrice] = useState(150000);
    const [tmi, setTmi] = useState(30);

    const [actionsA, setActionsA] = useState<RetrofitAction[]>([
        { id: 'iti', name: 'ITI (Murs Intérieurs)', defaultCost: 85, impactKwh: 120, impactGes: 6, description: 'Isolation thermique par l\'intérieur. Réduit les déperditions mais impacte la surface habitable (~1.5% de perte).', active: false },
        { id: 'roof', name: 'Isolation Toiture', defaultCost: 65, impactKwh: 65, impactGes: 4, description: 'Isolation des combles ou de la toiture pour les maisons individuelles.', active: false },
        { id: 'floor_ceiling', name: 'Isolation Plafond/Plancher', defaultCost: 55, impactKwh: 45, impactGes: 4, description: 'Isolation des plafonds ou planchers bas (garage, grenier).', active: false },
        { id: 'vmc', name: 'Ventilation (VMC)', defaultCost: 1100, impactKwh: 35, impactGes: 3, description: 'Installation d\'une VMC simple ou double flux pour une meilleure qualité d\'air et moins d\'humidité.', active: false },
        { id: 'heating', name: 'Radiateur inertie', defaultCost: 650, impactKwh: 60, impactGes: 15, description: 'Remplacement des radiateurs énergivores par des modèles à inertie haute performance.', active: false },
        { id: 'ecs', name: 'Ballon Thermo-dynamique', defaultCost: 3500, impactKwh: 80, impactGes: 20, description: 'Système de chauffe-eau thermodynamique pour une production d\'eau chaude économique.', active: false },
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
            const res = await fetch(`/api/search-address?q=${encodeURIComponent(addressQuery)}`);
            if (!res.ok) throw new Error(`Serveur Error: ${res.status}`);
            const data = await res.json();

            if (data.results && data.results.length > 0) {
                setSearchResults(data.results.map((r: any) => ({
                    address: r.address,
                    ademe_dpe_number: r.ademe_dpe_number,
                    surface: r.shab,
                    year: r.construction_year,
                    initialCep: r.consumption_level || 350,
                    label: r.dpe_class_current,
                    buildingType: r.building_type,
                    heatingType: r.systems?.[0]?.energy_source,
                    gesValue: r.ges_value || 10,
                    postcode: r.postcode || "59000",
                    recommended_works: r.recommended_works,
                    loss_breakdown: r.loss_breakdown
                })));
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
                setSearchResults(data.results.map((r: any) => ({
                    address: r.address,
                    ademe_dpe_number: r.ademe_dpe_number,
                    surface: r.shab,
                    year: r.construction_year,
                    initialCep: r.consumption_level || 350,
                    label: r.dpe_class_current,
                    buildingType: r.building_type,
                    heatingType: r.systems?.[0]?.energy_source,
                    gesValue: r.ges_value || 10,
                    postcode: r.postcode || "59000",
                    recommended_works: r.recommended_works,
                    loss_breakdown: r.loss_breakdown
                })));
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

    const selectProperty = (p: PropertyData & { recommended_works?: any[] }) => {
        // Full State Reset
        setActionsA(prev => prev.map(a => ({ ...a, active: false })));
        setActionsB(prev => prev.map(a => ({ ...a, active: false })));
        setActiveScenario('A');
        setCompareMode(false);
        setIsInvestor(false);
        setIncomeLevel('intermediaire');
        setTmi(30);
        setMonthlyRent(800);
        setPurchasePrice(p.surface * 4200);

        const year = p.year || 1970;
        const inferred = { ...p };
        if (!p.wallMaterials || p.wallMaterials === "Inconnu") {
            if (year < 1948) inferred.wallMaterials = "Pierre";
            else if (year < 1975) inferred.wallMaterials = "Béton non isolé";
            else inferred.wallMaterials = "Isolé RT2005";
        }
        setProperty(inferred);

        // Intelligent Recommendations Logic
        if (p.recommended_works && p.recommended_works.length > 0) {
            const recIds = p.recommended_works.map(r => r.id);
            const applier = (a: RetrofitAction) => {
                const isActive = recIds.includes(a.id);
                return { ...a, suggested: isActive, active: isActive };
            };
            setActionsA(prev => prev.map(applier));
            setActionsB(prev => prev.map(applier));
        } else {
            // Fallback to local logic
            const suggester = (a: RetrofitAction) => ({ ...a, suggested: false, active: false });
            setActionsA(prev => prev.map(suggester));
            setActionsB(prev => prev.map(suggester));
        }

        setView('dashboard');
    };

    // --- Simulation Logic ---

    const heatLoss = useMemo(() => {
        if (!property) return null;

        if (property.loss_breakdown) {
            const b = property.loss_breakdown;
            const total = b.walls + b.windows + b.ventilation + 15; // + floor/ceiling fallback
            return [
                { id: 'roof', name: 'Toiture', val: (5 / total) * 100, color: '#3b82f6' },
                { id: 'walls', name: 'Murs', val: (b.walls / total) * 100, color: '#60a5fa' },
                { id: 'windows', name: 'Vitrage', val: (b.windows / total) * 100, color: '#93c5fd' },
                { id: 'floor', name: 'Sols', val: (10 / total) * 100, color: '#bfdbfe' },
                { id: 'vent', name: 'Air', val: (b.ventilation / total) * 100, color: '#dbeafe' },
            ];
        }

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

        // Smart Estimation: S_mur = 8 * sqrt(SHAB)
        const sMur = 8 * Math.sqrt(property.surface);

        // Zone Coefficient (Simplified département based)
        const dept = property.postcode?.substring(0, 2) || "00";
        let zoneCoeff = 1.0;
        if (['75', '77', '78', '91', '92', '93', '94', '95'].includes(dept)) zoneCoeff = 1.2; // IDF
        if (['23', '36', '15'].includes(dept)) zoneCoeff = 0.9; // Rural examples

        activeActions.forEach(a => {
            let itemCost = a.defaultCost;
            let eff = 1.0;

            if (a.id === 'iti') {
                // Base cost + zone adjustment
                itemCost = a.defaultCost * sMur * zoneCoeff;
                // Preparation cost (+15€/m²) if wall not isolated
                if (property.wallMaterials?.toLowerCase().includes('non isolé')) {
                    itemCost += 15 * sMur;
                }
            } else if (a.id === 'roof') {
                // Roof area estimation: surface area
                itemCost = a.defaultCost * property.surface * zoneCoeff;
            } else if (a.id === 'floor_ceiling') {
                itemCost = a.defaultCost * property.surface * zoneCoeff;
            } else if (a.id === 'heating') {
                // Estimate 1 radiator per 15m²
                const count = Math.ceil(property.surface / 15);
                itemCost = a.defaultCost * count;
            } else if (a.id === 'vmc' || a.id === 'ecs') {
                itemCost = a.defaultCost * zoneCoeff;
            }

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

        const region = getRegion(property.postcode);
        const banDate = getRentalBanDate(current.label, property.initialCep, region);

        // Detailed work costs for UI
        const activeDetailedCosts = activeActions.map(a => {
            let itemCost = a.defaultCost;
            if (a.id === 'iti') {
                itemCost = a.defaultCost * sMur * zoneCoeff;
                if (property.wallMaterials?.toLowerCase().includes('non isolé')) itemCost += 15 * sMur;
            } else if (a.id === 'roof') {
                itemCost = a.defaultCost * property.surface * zoneCoeff;
            } else if (a.id === 'floor_ceiling') {
                itemCost = a.defaultCost * property.surface * zoneCoeff;
            } else if (a.id === 'heating') {
                itemCost = a.defaultCost * Math.ceil(property.surface / 15);
            } else if (a.id === 'vmc' || a.id === 'ecs') {
                itemCost = a.defaultCost * zoneCoeff;
            }
            return { name: a.name, cost: itemCost, suggested: a.suggested };
        });

        // Investor Metrics
        const taxBenefit = isInvestor ? rest * (tmi / 100 + 0.172) : 0;
        const totalInvestment = purchasePrice + cost;
        const annualRent = monthlyRent * 12;
        const yieldBrut = (annualRent / totalInvestment) * 100;
        const cashflow = isInvestor ? (monthlyRent - (rest > 0 ? (rest * (0.045 / 12) * Math.pow(1 + (0.045 / 12), 84)) / (Math.pow(1 + (0.045 / 12), 84) - 1) : 0)) : 0;

        // Waterfall Logic & Financing
        const ceeEst = activeActions.length * 800; // Rough estimation
        const rac = Math.max(0, cost - sub - ceeEst);

        // Eco-PTZ Logic
        const activeCats = activeActions.filter(a => {
            // Filter out roof for apartments just in case
            if (a.id === 'roof' && property.buildingType !== 'MAISON') return false;
            return true;
        });

        const cats = new Set(activeCats.map(a => {
            if (['iti', 'roof', 'floor_ceiling'].includes(a.id)) return 'isolation';
            if (a.id === 'heating' || a.id === 'ecs') return 'heating';
            return 'other';
        })).size;

        let ecoPTZLimit = 0;
        if (cats === 1) {
            ecoPTZLimit = 15000;
        } else if (cats === 2) {
            ecoPTZLimit = 25000;
        } else if (cats >= 3) {
            ecoPTZLimit = 30000;
        }

        const ecoPTZAmount = Math.min(rac, ecoPTZLimit);
        const remainingAfterPTZ = rac - ecoPTZAmount;
        console.log("Remaining after PTZ:", remainingAfterPTZ); // Avoid unused warning

        return {
            newCep, newGes, cost, sub, rest, taxBenefit,
            activeDetailedCosts,
            yieldBrut, cashflow, purchasePrice,
            banDate, ecoPTZAmount, ecoPTZLimit, ceeEst,
            pamAmount: 0, pamDebt15y: 0, pamEligible: false, // Disabled for now to simplify
            netInvestorCost: rest - taxBenefit,
            savings: (cepRed * property.surface) * 0.228,
            roi: (cost - sub - taxBenefit) / ((cepRed * property.surface) * 0.228 || 1),
            gain: property.surface * 4200 * (steps * 0.045),
            currentLabel: current.label,
            newLabel: target.label,
            newCepLabel: target.cepL,
            newGesLabel: target.gesL,
            currentCepLabel: current.cepL,
            currentGesLabel: current.gesL,
            hasITI: activeActions.some(a => a.id === 'iti')
        };
    };

    const simA = useMemo(() => compute(actionsA.filter(a => a.active)), [actionsA, property, incomeLevel, tmi, isInvestor, monthlyRent, purchasePrice]);
    const simB = useMemo(() => compute(actionsB.filter(a => a.active)), [actionsB, property, incomeLevel, tmi, isInvestor, monthlyRent, purchasePrice]);

    const activeSim = activeScenario === 'A' ? simA : simB;

    const handleDownloadPDF = async () => {
        if (!property || !activeSim) return;
        setDownloading(true);
        try {
            const res = await fetch(`/api/generate-report`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    address: property.address || "Adresse inconnue",
                    surface: property.surface || 0,
                    year: property.year || "N/A",
                    ademe_dpe_number: property.ademe_dpe_number || "N/A",
                    current_label: activeSim.currentLabel || "G",
                    new_label: activeSim.newLabel || "G",
                    initial_cep: property.initialCep || 0,
                    new_cep: activeSim.newCep || 0,
                    ges_value: property.gesValue || 0,
                    new_ges: activeSim.newGes || 0,
                    total_cost: activeSim.cost || 0,
                    subsidies: activeSim.sub || 0,
                    rest_to_pay: Math.max(0, (activeSim.cost || 0) - (activeSim.sub || 0) - (activeSim.ceeEst || 0) - (activeSim.ecoPTZAmount || 0)),
                    latent_gain: activeSim.gain || 0,
                    annual_savings: activeSim.savings || 0,
                    roi_years: Math.round(activeSim.roi || 0),
                    detailed_costs: activeSim.activeDetailedCosts || [],
                    yield_brut: activeSim.yieldBrut || 0,
                    cashflow: activeSim.cashflow || 0,
                    purchase_price: purchasePrice || 0,
                    ban_date: activeSim.banDate?.toLocaleDateString('fr-FR') || null,
                    cee_est: activeSim.ceeEst || 0,
                    eco_ptz_amount: activeSim.ecoPTZAmount || 0,
                    pam_amount: activeSim.pamAmount || 0,
                    tax_benefit: activeSim.taxBenefit || 0,
                    has_iti: activeSim.hasITI || false,
                    user_profile: userProfile
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

                        <div className="flex items-center bg-slate-100 rounded-2xl px-6 h-16 border-2 border-transparent focus-within:border-emerald-600 focus-within:bg-white transition-all mt-4">
                            <FileText size={24} className="text-slate-400 mr-4" />
                            <input
                                type="text"
                                placeholder="Numéro DPE ADEME (Ex: 2134E...)"
                                className="flex-1 bg-transparent text-lg font-bold outline-none text-slate-900 placeholder:text-slate-400"
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
                        <p className="text-sm font-bold text-slate-400">
                            {property?.buildingType || 'Logement'} • {property?.surface} m² • {property?.year ? `Période ${property.year}` : 'Année Inconnue'}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2 p-2 bg-slate-50 rounded-2xl border border-slate-100">
                        {activeSim?.banDate && (
                            <div className="hidden md:flex flex-col items-end px-3 border-r border-slate-200">
                                <p className="text-[8px] font-black uppercase text-red-500">Loi Climat</p>
                                <p className="text-[10px] font-black text-slate-700">
                                    {(activeSim?.banDate || new Date()) <= new Date() ? 'INTERDIT' : `Interdiction en ${activeSim?.banDate?.getFullYear()}`}
                                </p>
                            </div>
                        )}
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
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">Objectif du Rapport</p>
                            <div className="flex gap-2 p-1 bg-white rounded-xl border border-slate-100">
                                <button
                                    onClick={() => setUserProfile('propriétaire')}
                                    className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${userProfile === 'propriétaire' ? 'bg-blue-600 text-white shadow-md' : 'text-slate-400 hover:bg-slate-50'}`}
                                >
                                    Patrimoine
                                </button>
                                <button
                                    onClick={() => setUserProfile('investisseur')}
                                    className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${userProfile === 'investisseur' ? 'bg-slate-900 text-white shadow-md' : 'text-slate-400 hover:bg-slate-50'}`}
                                >
                                    Performance
                                </button>
                            </div>
                        </div>

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
                            {(activeScenario === 'A' ? actionsA : actionsB)
                                .filter(a => a.id !== 'roof' || property?.buildingType === 'MAISON')
                                .map(a => (
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
                                            <span className="px-3 py-1 bg-blue-50 text-blue-700 font-extrabold text-[10px] rounded-lg tracking-widest uppercase">{activeSim?.currentLabel} ➔ {activeSim?.newLabel}</span>
                                            <span className="px-3 py-1 bg-green-50 text-green-700 font-extrabold text-[10px] rounded-lg tracking-widest uppercase">{activeSim?.currentCepLabel} ➔ {activeSim?.newCepLabel}</span>
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
                                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-6">Plan de Financement Stratégique</p>
                                    <div className="space-y-4">
                                        <div className="space-y-2 pb-4 border-b border-slate-50">
                                            {activeSim?.activeDetailedCosts.map((item: any, idx: number) => (
                                                <div key={idx} className="flex justify-between text-xs font-bold text-slate-600">
                                                    <span>{item.name}{item.suggested && " (Conseillé)"}</span>
                                                    <span>{Math.round(item.cost).toLocaleString()} €</span>
                                                </div>
                                            ))}
                                            <div className="flex justify-between text-base font-black pt-2 text-slate-800">
                                                <span>Investissement Brut</span>
                                                <span>{Math.round(activeSim?.cost || 0).toLocaleString()} €</span>
                                            </div>
                                        </div>

                                        <div className="space-y-2 pb-4 border-b border-slate-50">
                                            <div className="flex justify-between text-xs font-bold">
                                                <span className="text-slate-500">Subvention MaPrimeRénov'</span>
                                                <span className="text-green-600">-{Math.round(activeSim?.sub || 0).toLocaleString()} €</span>
                                            </div>
                                            <div className="flex justify-between text-xs font-bold">
                                                <span className="text-slate-500">Prime CEE (Estimation)</span>
                                                <span className="text-green-600">-{Math.round(activeSim?.ceeEst || 0).toLocaleString()} €</span>
                                            </div>
                                        </div>

                                        <div className="space-y-2 pb-4 border-b border-slate-50">
                                            <div className="flex justify-between text-xs font-bold">
                                                <span className="text-slate-500 flex items-center gap-1">Éco-PTZ (Bouquet {Math.round((activeSim?.ecoPTZLimit || 0) / 1000)}k)</span>
                                                <span className="text-blue-600">-{Math.round(activeSim?.ecoPTZAmount || 0).toLocaleString()} €</span>
                                            </div>
                                            {(activeSim?.pamAmount || 0) > 0 && (
                                                <div className="group relative">
                                                    <div className="flex justify-between text-xs font-bold p-2 bg-blue-100/30 rounded-lg cursor-help">
                                                        <span className="text-blue-700 flex items-center gap-1">Prêt Avance Mutation (PAM)</span>
                                                        <span className="text-blue-700">-{Math.round(activeSim?.pamAmount || 0).toLocaleString()} €</span>
                                                    </div>
                                                    <div className="absolute bottom-full left-0 mb-2 w-48 p-3 bg-slate-900 text-[9px] font-bold text-white rounded-xl shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                                                        Différé total pendant 10 ans. Intérêts cumulés proj. à 15 ans : {Math.round((activeSim?.pamDebt15y || 0) - (activeSim?.pamAmount || 0)).toLocaleString()} €.
                                                    </div>
                                                </div>
                                            )}
                                            {isInvestor && (
                                                <div className="flex justify-between text-xs font-bold">
                                                    <span className="text-slate-500">Gain Fiscal (Déficit Foncier)</span>
                                                    <span className="text-blue-600">-{Math.round(activeSim?.taxBenefit || 0).toLocaleString()} €</span>
                                                </div>
                                            )}
                                        </div>

                                        <div className="flex justify-between text-2xl font-black pt-4">
                                            <span className="text-slate-800">Cout Final</span>
                                            <span className="text-slate-900">{Math.round(Math.max(0, (activeSim?.cost || 0) - (activeSim?.sub || 0) - (activeSim?.ceeEst || 0) - (activeSim?.ecoPTZAmount || 0))).toLocaleString()} €</span>
                                        </div>
                                        {activeSim?.hasITI && (
                                            <div className="mt-4 p-4 bg-amber-50 rounded-2xl border border-amber-100 flex items-start gap-3">
                                                <AlertTriangle size={16} className="text-amber-600 shrink-0 mt-0.5" />
                                                <p className="text-[10px] font-bold text-amber-800 leading-relaxed">
                                                    <b>Attention :</b> L'isolation des murs par l'intérieur (ITI) fera perdre environ 1.5% de surface Carrez.
                                                </p>
                                            </div>
                                        )}
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
                                        Estimation de la plus-value immobilière générée par l'amélioration du DPE. Un saut de classe énergétique augmente généralement le prix de vente de 4.5% par saut de classe.
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
                                            <p className="italic">Cashflow = Loyer - Mensualité Crédit (Travaux sur 84 mois à 4.5%).</p>
                                        </div>
                                    </div>
                                )}

                            </div>
                        </div>
                    )}
                </main>
            </div>
        </div>
    );
}

export function AGVoteSimulator() {
    const [votes, setVotes] = useState({ pour: 650, contre: 200, abstention: 150 });
    const isAcceptedArt25 = votes.pour > 500;
    const canLeverageArt25_1 = !isAcceptedArt25 && votes.pour >= 333;

    return (
        <div className="p-8 bg-slate-900 rounded-[2.5rem] text-white shadow-2xl">
            <h3 className="text-xl font-black text-blue-400 mb-6 flex items-center gap-3">
                <TrendingUp size={24} /> Simulateur de Vote AG
            </h3>
            <div className="space-y-6">
                <div className="flex gap-2 h-4 bg-white/10 rounded-full overflow-hidden">
                    <div className="bg-green-500 h-full transition-all" style={{ width: `${votes.pour / 10}%` }} />
                    <div className="bg-red-500 h-full transition-all" style={{ width: `${votes.contre / 10}%` }} />
                    <div className="bg-slate-500 h-full transition-all" style={{ width: `${votes.abstention / 10}%` }} />
                </div>
                <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                        <p className="text-[10px] font-black text-slate-400 uppercase">Pour</p>
                        <input type="number" value={votes.pour} onChange={e => setVotes({ ...votes, pour: Number(e.target.value) })} className="w-full bg-transparent text-xl font-black text-green-400 text-center outline-none" />
                    </div>
                    <div>
                        <p className="text-[10px] font-black text-slate-400 uppercase">Contre</p>
                        <input type="number" value={votes.contre} onChange={e => setVotes({ ...votes, contre: Number(e.target.value) })} className="w-full bg-transparent text-xl font-black text-red-400 text-center outline-none" />
                    </div>
                    <div>
                        <p className="text-[10px] font-black text-slate-400 uppercase">Abst.</p>
                        <input type="number" value={votes.abstention} onChange={e => setVotes({ ...votes, abstention: Number(e.target.value) })} className="w-full bg-transparent text-xl font-black text-slate-400 text-center outline-none" />
                    </div>
                </div>
                <div className={`p-4 rounded-2xl border-2 font-bold text-xs text-center ${isAcceptedArt25 ? 'bg-green-500/10 border-green-500 text-green-400' : canLeverageArt25_1 ? 'bg-blue-500/10 border-blue-500 text-blue-400' : 'bg-red-500/10 border-red-500 text-red-400'}`}>
                    {isAcceptedArt25 ? "Adopté (Majorité Art. 25)" : canLeverageArt25_1 ? "Passerelle Art. 25-1 possible (Majorité Simple)" : "Rejeté"}
                </div>
                <p className="text-[8px] text-slate-500 italic mt-2 text-center">Simule les tantièmes (sur 1000) requis pour la rénovation énergétique.</p>
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
