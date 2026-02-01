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
    Zap
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
    pricePerM2?: number; // Added for gain calculation
    glassType?: string;
    roofIsolation?: string;
    floorIsolation?: string;
    heatingDetail?: string;
    ademe_dpe_number?: string;
    postcode?: string;
    city?: string;
    constructionPeriod?: string;
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

    // Simplified Duration Mapping (days per work)
    const DURATION_MAP: Record<string, number> = {
        iti: 5,
        roof: 7,
        floor_ceiling: 3,
        heating: 2,
        vmc: 1,
        ecs: 1,
        windows: 2
    };

    // New Precision Parameters
    const [nbEtages, setNbEtages] = useState(0);
    const [hasAscenseur, setHasAscenseur] = useState(true);
    const [isUrbanDense, setIsUrbanDense] = useState(false);
    const [parkingCost, setParkingCost] = useState(35.0);
    const [chantierDuration, setChantierDuration] = useState(5); // Now auto-updated

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
        { id: 'windows', name: 'Menuiseries PVC', defaultCost: 6500, impactKwh: 45, impactGes: 4, description: 'Remplacement des fenêtres simple vitrage par du double vitrage PVC haute performance.', active: false },
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
                    constructionPeriod: r.construction_period,
                    initialCep: r.consumption_level || 350,
                    label: r.dpe_class_current,
                    buildingType: r.building_type || "Logement",
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
                    constructionPeriod: r.construction_period,
                    initialCep: r.consumption_level || 350,
                    label: r.dpe_class_current,
                    buildingType: r.building_type || "Logement",
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

        const year = p.year || (p.constructionPeriod?.includes('1948') ? 1940 : 1970);
        const inferred = { ...p };
        if (!p.wallMaterials || p.wallMaterials === "Inconnu") {
            const period = (p.constructionPeriod || "").toLowerCase();
            if (year < 1948 || period.includes('1948')) inferred.wallMaterials = "Pierre";
            else if (year < 1975 || period.includes('1948-1974')) inferred.wallMaterials = "Béton non isolé";
            else inferred.wallMaterials = "Isolé RT2005";
        }
        setProperty(inferred);

        // Precise Auto-Selection with Greedy Grade Capping & Condo-Awareness
        const initialCep = p.initialCep || 350;
        const currentGrade = p.label || 'G';
        const isApartment = p.buildingType?.toLowerCase().includes('appartement');

        // Define Target: C (150) for D/E/F, D (230) for G
        let targetCep = 150;
        if (currentGrade === 'G') targetCep = 230;
        if (['A', 'B', 'C'].includes(currentGrade)) targetCep = initialCep;

        let remainingReduction = initialCep - targetCep;
        const recIds = p.recommended_works ? p.recommended_works.map(r => r.id) : [];
        const breakdown = p.loss_breakdown;

        const processedActions = [...actionsA].map(a => {
            // Roof works are only for houses
            if (a.id === 'roof' && isApartment) return { ...a, suggested: false, active: false };

            // Check if suggested by backend OR technical loss
            let isSuggested = recIds.includes(a.id) ||
                (a.id === 'iti' && recIds.includes('iti_ossature')) ||
                (a.id === 'heating' && recIds.includes('pac_air_eau')) ||
                (a.id === 'roof' && recIds.includes('combles'));

            if (breakdown) {
                if (a.id === 'iti' && (breakdown.walls > 40)) isSuggested = true;
                if (a.id === 'windows' && (breakdown.windows > 20)) isSuggested = true;
                if (a.id === 'vmc' && (breakdown.ventilation > 30)) isSuggested = true;
            }
            return { ...a, suggested: !!isSuggested, active: false };
        });

        // Greedy Selection: Isolation first, then heating
        // Use roof only for houses, prioritize ITI and others for apartments
        const priorityOrder = isApartment
            ? ['iti', 'floor_ceiling', 'heating', 'windows', 'vmc']
            : ['roof', 'iti', 'floor_ceiling', 'heating', 'windows', 'vmc'];

        const sortedActions = [...processedActions].sort((a, b) => {
            const idxA = priorityOrder.indexOf(a.id);
            const idxB = priorityOrder.indexOf(b.id);
            return (idxA === -1 ? 99 : idxA) - (idxB === -1 ? 99 : idxB);
        });

        const activeActions = sortedActions.map(a => {
            if (remainingReduction > 0 && a.suggested) {
                remainingReduction -= a.impactKwh;
                return { ...a, active: true };
            }
            return a;
        });

        setActionsA(activeActions);
        setActionsB(activeActions.map(a => ({ ...a, active: false })));

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

        // --- Technical Precision logic (Automated) ---
        const safeIndex = 131.0; // BT01 2024/2025 auto-selected
        const safeEtages = (nbEtages || 0);
        const safeParkingCost = (parkingCost || 0);

        // Intelligent duration calculation
        const autoDuration = activeActions.reduce((sum, a) => sum + (DURATION_MAP[a.id] || 0), 0);
        const safeDuration = autoDuration || 1;

        const indexRatio = safeIndex / 120.0;

        // Accessibility coefficient: +5% per floor if no elevator
        let coeffAccessibilite = 1.0;
        if (safeEtages > 0 && !hasAscenseur) {
            coeffAccessibilite += (safeEtages * 0.05);
        }

        // Urban Density coefficient (+10%)
        const coeffUrban = isUrbanDense ? 1.10 : 1.0;

        // Logistics (Stationnement)
        const logisticsCosts = isUrbanDense ? (safeParkingCost * safeDuration) : 0;

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

            cost += (itemCost * indexRatio * coeffAccessibilite * coeffUrban);
            cepRed += a.impactKwh * eff;
            gesRed += a.impactGes * eff;
        });

        cost += logisticsCosts;

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

        // Auto-update duration state for UI (optional, but keep for logistics)
        if (safeDuration !== chantierDuration) setChantierDuration(safeDuration);

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
            return { name: a.name, cost: itemCost * indexRatio * coeffAccessibilite * coeffUrban, suggested: a.suggested };
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
            gain: steps * (property.surface * (property.pricePerM2 || 4500) * 0.045), // 4.5% gain per DPE step
            currentLabel: current.label,
            newLabel: target.label,
            newCepLabel: target.cepL,
            newGesLabel: target.gesL,
            currentCepLabel: current.cepL,
            currentGesLabel: current.gesL,
            hasITI: activeActions.some(a => a.id === 'iti')
        };
    };

    const simA = useMemo(() => compute(actionsA.filter(a => a.active)), [actionsA, property, incomeLevel, tmi, isInvestor, monthlyRent, purchasePrice, nbEtages, hasAscenseur, isUrbanDense, parkingCost]);
    const simB = useMemo(() => compute(actionsB.filter(a => a.active)), [actionsB, property, incomeLevel, tmi, isInvestor, monthlyRent, purchasePrice, nbEtages, hasAscenseur, isUrbanDense, parkingCost]);

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
                    user_profile: isInvestor ? "investisseur" : "propriétaire",
                    building_type: property.buildingType || "Logement",
                    construction_period: property.constructionPeriod || "N/A"
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
                            {property?.label !== activeSim?.currentLabel && (
                                <span className="px-3 py-1 bg-amber-50 text-amber-600 text-[10px] font-black rounded-lg border border-amber-100 uppercase tracking-tighter shadow-sm animate-pulse">Source ADEME: {property?.label}</span>
                            )}
                        </div>
                        <div className="flex items-center gap-4 mt-1">
                            <p className="text-sm font-bold text-slate-400">
                                {property?.buildingType} • {property?.surface} m² • {property?.constructionPeriod}
                            </p>
                            <div className="h-4 w-px bg-slate-200" />
                            <div className="flex items-center gap-2 px-3 py-1 bg-blue-600 rounded-full text-white shadow-lg shadow-blue-200">
                                <TrendingUp size={14} className="animate-bounce" />
                                <span className="text-[11px] font-black uppercase tracking-tight">Plus-value IMMO: +{Math.round(activeSim?.gain || 0).toLocaleString()} €</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2 p-3 bg-slate-50 rounded-[1.5rem] border border-slate-100">
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
                                <p className="text-[9px] font-black uppercase text-slate-400">Énergie</p>
                                <p className="text-xs font-black text-slate-600">{activeSim?.currentCepLabel}</p>
                            </div>
                            <div className="text-right">
                                <p className="text-[9px] font-black uppercase text-slate-400">Climat</p>
                                <p className="text-xs font-black text-slate-600">{activeSim?.currentGesLabel}</p>
                            </div>
                        </div>
                        <div className={`flex items-center justify-center rounded-2xl h-14 w-14 text-3xl font-black text-white shadow-xl ml-2 scale-105 active:scale-95 transition-transform`} style={{ backgroundColor: DPE_COLORS[activeSim?.currentLabel || 'G'] }}>
                            {activeSim?.currentLabel}
                        </div>
                    </div>
                    <div className="flex gap-3">
                        <button onClick={handleDownloadPDF} disabled={downloading} className="h-14 px-8 rounded-2xl bg-blue-50 text-blue-600 font-bold hover:bg-blue-600 hover:text-white transition-all flex items-center gap-3 border border-blue-100 shadow-sm">
                            {downloading ? <Loader2 className="animate-spin" /> : <FileText size={20} />}
                            <span className="uppercase text-xs tracking-widest">PDF</span>
                        </button>
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
                                        <span className="text-[8px] bg-blue-100 px-2 py-0.5 rounded text-blue-500">{chantierDuration} j.</span>
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
                                        <button key={p} onClick={() => setUserProfile(p)} className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${userProfile === p ? 'bg-blue-600 text-white shadow-md' : 'text-slate-400 hover:bg-slate-50'}`}>{p === 'propriétaire' ? 'Patrimoine' : 'Performance'}</button>
                                    ))}
                                </div>
                            </div>
                            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1 ml-1">Revenus du Ménage</p>
                                <p className="text-[8px] font-bold text-blue-500 uppercase mb-3 ml-1">Taux MaPrimeRénov'</p>
                                <div className="grid grid-cols-2 gap-2">
                                    {(['tres_modeste', 'modeste', 'intermediaire', 'superieur'] as IncomeLevel[]).map(l => (
                                        <button key={l} onClick={() => setIncomeLevel(l)} className={`px-2 py-2 rounded-xl text-[8px] font-black uppercase transition-all border-2 ${incomeLevel === l ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-400 border-slate-50'}`}>{l.replace('_', ' ')}</button>
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
                        </div>
                    </section>
                </aside>

                <main className="lg:col-span-9 space-y-8 order-1 lg:order-2">
                    {/* 1. DPE Chart Section */}
                    <section className="rounded-[2.5rem] bg-white p-10 shadow-sm border border-slate-100 relative overflow-hidden group">
                        <div className="mb-10 flex items-center justify-between relative z-10">
                            <div>
                                <h3 className="text-2xl font-black text-slate-800 tracking-tight">Objectif Amélioration Énergétique</h3>
                                <div className="flex gap-2 mt-2">
                                    <span className="px-3 py-1.5 bg-blue-50 text-blue-700 font-extrabold text-[10px] rounded-lg tracking-widest uppercase border border-blue-100 shadow-sm">{activeSim?.currentLabel} ➔ {activeSim?.newLabel}</span>
                                    <span className="px-3 py-1.5 bg-green-50 text-green-700 font-extrabold text-[10px] rounded-lg tracking-widest uppercase border border-green-100 shadow-sm">{Math.round(activeSim?.newCep || 0)} kWh/m².an</span>
                                </div>
                            </div>
                            <div className="text-right p-4 bg-slate-50 rounded-3xl border border-slate-100">
                                <p className="text-4xl font-black text-slate-900 tracking-tighter">Budget {Math.round(activeSim?.rest || 0).toLocaleString()} €</p>
                                <p className="text-[8px] font-black text-slate-400 uppercase tracking-widest mt-1 italic italic">Reste à charge estimé</p>
                            </div>
                        </div>
                        <div className="grid grid-cols-7 gap-3 h-20 relative z-10">
                            {getAdjustedThresholds(property?.surface || 100).map(t => (
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
                                <button onClick={() => setCompareMode(!compareMode)} className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${compareMode ? 'bg-blue-600 text-white ring-4 ring-blue-50' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}>Comparatif {compareMode ? 'ON' : 'OFF'}</button>
                            </div>

                            {compareMode && (
                                <div className="flex gap-2 mb-6 p-1.5 bg-slate-100 rounded-2xl">
                                    {(['A', 'B'] as const).map(s => (
                                        <button key={s} onClick={() => setActiveScenario(s)} className={`flex-1 py-2.5 rounded-xl font-black text-[10px] uppercase tracking-widest transition-all ${activeScenario === s ? 'bg-white text-blue-600 shadow-sm ring-1 ring-slate-200' : 'text-slate-400'}`}>Scénario {s}</button>
                                    ))}
                                    <button onClick={copyAToB} title="Copier A vers B" className="p-2 bg-white rounded-xl text-slate-400 hover:text-blue-600 transition-colors shadow-sm"><Copy size={16} /></button>
                                </div>
                            )}

                            <div className="grid grid-cols-1 gap-3 overflow-y-auto max-h-[500px] pr-2 custom-scrollbar">
                                {(activeScenario === 'A' ? actionsA : actionsB)
                                    .filter(a => a.id !== 'roof' || property?.buildingType === 'MAISON')
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
                                * Ces données proviennent du rapport ADEME et indiquent les zones de pertes de chaleur prioritaires avant travaux.
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
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm font-bold text-slate-500">MaPrimeRénov'</span>
                                        <span className="text-lg font-black text-green-600">-{Math.round(activeSim?.sub || 0).toLocaleString()} €</span>
                                    </div>
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm font-bold text-slate-500">Primes CEE (Est.)</span>
                                        <span className="text-lg font-black text-green-600">-{Math.round(activeSim?.ceeEst || 0).toLocaleString()} €</span>
                                    </div>
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm font-bold text-slate-500">Éco-PTZ (Capped)</span>
                                        <span className="text-lg font-black text-blue-600">-{Math.round(activeSim?.ecoPTZAmount || 0).toLocaleString()} €</span>
                                    </div>
                                </div>
                            </div>

                            <div className="lg:col-span-1 flex flex-col justify-center items-center text-center p-8 bg-blue-600 rounded-[2.5rem] shadow-2xl shadow-blue-200">
                                <p className="text-[11px] font-black text-blue-100 uppercase tracking-widest mb-4">Reste à Charge Final</p>
                                <p className="text-5xl font-black text-white tracking-tighter mb-2">{Math.round(activeSim?.rest || 0).toLocaleString()} €</p>
                                <p className="text-[9px] font-bold text-blue-200 uppercase tracking-tight italic opacity-80">Soit {Math.round(((activeSim?.rest || 0) / (activeSim?.cost || 1)) * 100)}% de l'investissement initial</p>
                                <button className="mt-8 w-full py-4 bg-white text-blue-600 rounded-2xl font-black uppercase text-xs tracking-widest hover:bg-blue-50 transition-all shadow-xl">Simuler Financier</button>
                            </div>
                        </div>
                    </section>
                </main>
            </div>
        </div>
    );
}

