import type { DPEClass } from './ui';

export type IncomeLevel = 'tres_modeste' | 'modeste' | 'intermediaire' | 'superieur';

export const INCOME_LEVELS: { value: IncomeLevel; label: string }[] = [
    { value: 'tres_modeste', label: 'Très modestes' },
    { value: 'modeste', label: 'Modestes' },
    { value: 'intermediaire', label: 'Intermédiaires' },
    { value: 'superieur', label: 'Supérieurs' },
];

export interface RetrofitAction {
    id: string;
    name: string;
    description: string;
    active: boolean;
    suggested?: boolean;
}

export interface PropertyData {
    address: string;
    surface: number;
    year?: number;
    initialCep: number;
    label: DPEClass;
    gesLabel?: DPEClass;
    buildingType: string;
    heatingType?: string;
    gesValue?: number;
    pricePerM2?: number;
    // Origin of pricePerM2 (local DVF sales), shown with the green value
    priceSource?: string;
    priceLookupDone?: boolean;
    inseeCode?: string;
    latitude?: number;
    longitude?: number;
    finalConsumption?: number;
    suggestedWorks?: string[];
    preselectedWorks?: string[];
    ademe_dpe_number?: string;
    dpeDate?: string;
    postcode?: string;
    constructionPeriod?: string;
    lossShares?: Record<string, number>;
    insulationQuality?: Record<string, string | null>;
    dpeLosses?: Record<string, number | null> | null;
    usageConsumption?: Record<string, number | null> | null;
    city?: string;
    // Equipment labels from the DPE (heating, hot water, ventilation...)
    details?: Record<string, string | null>;
}

// Simulation results, computed by the API (api/simulation.py is the single engine)
export interface Simulation {
    currentLabel: DPEClass;
    newLabel: DPEClass;
    gainClasses: number;
    newCep: number;
    initialGes: number;
    newGes: number;
    thresholds: { label: DPEClass; max: number; max_ges: number }[];
    cost: number;
    costLow: number;
    costHigh: number;
    detailedCosts: { id: string; name: string; cost: number; cost_low: number; cost_high: number; suggested: boolean }[];
    durationDays: number;
    sub: number;
    ceeEst: number;
    aidPathway: 'accompagne' | 'geste' | 'none';
    aidNotes: string[];
    aidBlockers: string[];
    aidRules: string;
    incomeProfile: string;
    rest: number;
    restLow: number;
    restHigh: number;
    ecoPTZAmount: number;
    ecoPTZLimit: number;
    savings: number;
    billBefore: number;
    billAfter: number;
    roi: number | null;
    gain: number;
    gainLow: number;
    gainHigh: number;
    greenValueBasis: string | null;
    greenValueMethod: string;
    taxBenefit: number;
    netInvestorCost: number;
    yieldBrut: number;
    cashflow: number;
    banDate: Date | null;
    newBanDate: Date | null;
    rentalStatus: string;
    newRentalStatus: string;
    hasITI: boolean;
}

const round = (v: number | null | undefined, step = 100) => Math.round((v || 0) / step) * step;

// Cost, aids, rest to pay and loan as every PDF shows them (api/figures.py
// display_figures): rounded once, so that cost - aids = rest on screen too.
// 47 rue de Bourgogne showed 12 946 € of aids and 17 400 € to pay where the
// documents said 12 900 € and 17 500 €.
function shownFigures(r: any) {
    const cost = round(r.cost);
    const costLow = lineSum(r.detailed_costs, 'cost_low') ?? round(r.cost_low);
    const costHigh = lineSum(r.detailed_costs, 'cost_high') ?? round(r.cost_high);
    const ampleur = r.aid_pathway === 'accompagne';
    const sub = ampleur ? round(r.subsidies) : round(r.subsidies, 10);
    const ceeEst = ampleur ? 0 : round(r.cee_est, 10);
    const aids = sub + ceeEst;
    const aidsLow = ampleur ? round(r.aids_low ?? r.subsidies) : aids;
    const aidsHigh = ampleur ? round(r.aids_high ?? r.subsidies) : aids;
    const rest = Math.max(0, cost - aids);
    return {
        cost, costLow, costHigh, sub, ceeEst, rest,
        restLow: Math.max(0, costLow - aidsLow),
        restHigh: Math.max(0, costHigh - aidsHigh),
        ecoPTZAmount: r.eco_ptz_amount ? Math.min(round(r.eco_ptz_amount), Math.floor(rest / 100) * 100) : 0,
    };
}

function lineSum(lines: { id: string; cost_low: number; cost_high: number }[] | undefined, key: 'cost_low' | 'cost_high'): number | null {
    if (!lines?.length) return null;
    return lines.reduce((sum, d) => { const step = d.id === 'parking' ? 10 : 100; return sum + Math.round(d[key] / step) * step; }, 0);
}

export const toSimulation = (r: any): Simulation => ({ ...toSimulationRaw(r), ...shownFigures(r) });

const toSimulationRaw = (r: any): Simulation => ({
    currentLabel: r.current_label,
    newLabel: r.new_label,
    gainClasses: r.gain_classes,
    newCep: r.new_cep,
    initialGes: r.initial_ges,
    newGes: r.new_ges,
    thresholds: r.thresholds,
    cost: r.cost,
    // Sum of the lines, each rounded as the PDFs round them (api/figures.py cost_range)
    costLow: lineSum(r.detailed_costs, 'cost_low') ?? r.cost_low,
    costHigh: lineSum(r.detailed_costs, 'cost_high') ?? r.cost_high,
    detailedCosts: r.detailed_costs,
    durationDays: r.duration_days,
    sub: r.subsidies,
    ceeEst: r.cee_est,
    aidPathway: r.aid_pathway,
    aidNotes: r.aid_notes,
    aidBlockers: r.aid_blockers || [],
    aidRules: r.aid_rules,
    incomeProfile: r.income_profile,
    rest: r.rest_to_pay,
    restLow: r.rest_to_pay_low,
    restHigh: r.rest_to_pay_high,
    ecoPTZAmount: r.eco_ptz_amount,
    ecoPTZLimit: r.eco_ptz_limit,
    savings: r.annual_savings,
    billBefore: r.annual_bill_before,
    billAfter: r.annual_bill_after,
    roi: r.roi_years,
    gain: r.latent_gain,
    gainLow: r.latent_gain_low,
    gainHigh: r.latent_gain_high,
    greenValueBasis: r.green_value_basis,
    greenValueMethod: r.green_value_method,
    taxBenefit: r.tax_benefit,
    netInvestorCost: r.net_investor_cost,
    yieldBrut: r.yield_brut,
    cashflow: r.cashflow,
    banDate: r.ban_date ? new Date(r.ban_date) : null,
    newBanDate: r.new_ban_date ? new Date(r.new_ban_date) : null,
    rentalStatus: r.rental_status,
    newRentalStatus: r.new_rental_status,
    hasITI: r.has_iti,
});

// The dwelling as sent to /api/simulate
export const propertyInput = (property: PropertyData) => ({
    surface: property.surface,
    initial_cep: property.initialCep,
    ges_value: property.gesValue ?? null,
    official_label: property.label ?? null,
    dpe_date: property.dpeDate ? property.dpeDate.slice(0, 10) : null,
    building_type: property.buildingType,
    postcode: property.postcode ?? null,
    construction_year: property.year || null,
    construction_period: property.constructionPeriod ?? null,
    price_per_m2: property.pricePerM2 ?? null,
    price_source: property.priceSource ?? null,
    insee_code: property.inseeCode ?? null,
    heating_energy: property.heatingType ?? null,
    final_consumption: property.finalConsumption ?? null,
    insulation_quality: property.insulationQuality ?? null,
    dpe_losses: property.dpeLosses ?? null,
    // Existing equipment: works already done are not proposed again
    heating_generator: property.details?.heating_system ?? null,
    heating_installation: property.details?.heating_installation ?? null,
    hot_water_system: property.details?.hot_water_system ?? null,
    hot_water_installation: property.details?.hot_water_installation ?? null,
    ventilation: property.details?.ventilation ?? null,
    hot_water_energy: property.details?.hot_water_energy ?? null,
    roof_kind: property.details?.roof_kind ?? null,
    usage_consumption: property.usageConsumption ?? null,
});

// Maps an API search result to the UI property model
export const toProperty = (r: any): PropertyData => ({
    address: r.address,
    ademe_dpe_number: r.ademe_dpe_number,
    dpeDate: r.date_etablissement || undefined,
    surface: r.shab,
    year: r.construction_year || undefined,
    constructionPeriod: r.construction_period || undefined,
    initialCep: r.consumption_level || 350,
    label: r.dpe_class_current,
    gesLabel: r.ges_class_current || undefined,
    buildingType: r.building_type || 'Logement',
    heatingType: r.systems?.[0]?.energy_source,
    finalConsumption: r.final_consumption || undefined,
    gesValue: r.ges_value || 10,
    postcode: r.postcode || undefined,
    lossShares: r.loss_shares,
    insulationQuality: r.insulation_quality,
    dpeLosses: r.dpe_losses,
    usageConsumption: r.usage_consumption ?? null,
    suggestedWorks: r.suggested_works || [],
    preselectedWorks: r.preselected_works || [],
    city: r.city || undefined,
    details: r.details || undefined,
    inseeCode: r.insee_code || undefined,
    latitude: r.latitude ?? undefined,
    longitude: r.longitude ?? undefined,
});

export const isHouse = (buildingType?: string) => (buildingType || '').toLowerCase().includes('maison');

export const formatDate = (iso?: string) =>
    iso ? new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' }) : null;

export const capitalize = (s?: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '');
