// MaPrimeRénov' rules (barème 2025, Anah). Keep in sync with api/aids.py.
// These figures change every year: check them against the official Anah
// guide before each update.

export type IncomeLevel = 'tres_modeste' | 'modeste' | 'intermediaire' | 'superieur';
export type DPELabel = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';

const LABELS: DPELabel[] = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];

// Energy renovation works are invoiced with 5.5% VAT; Anah ceilings are expressed HT.
export const TVA_RENOVATION = 0.055;

// --- Parcours accompagné (global renovation, gain >= 2 classes) ---

export const ACCOMPAGNE_RATES: Record<IncomeLevel, number> = {
    tres_modeste: 0.80,
    modeste: 0.60,
    intermediaire: 0.45,
    superieur: 0.10,
};

// Bonus when a "passoire" (F/G) reaches at least class D.
export const PASSOIRE_BONUS = 0.10;

// Maximum eligible works amount (HT) by number of classes gained.
export const accompagneCeilingHT = (classGain: number): number => {
    if (classGain >= 4) return 70000;
    if (classGain === 3) return 55000;
    if (classGain === 2) return 40000;
    return 0;
};

// Total public aid cannot exceed this share of the TTC cost.
export const ACCOMPAGNE_ECRETEMENT: Record<IncomeLevel, number> = {
    tres_modeste: 1.0,
    modeste: 0.8,
    intermediaire: 0.6,
    superieur: 0.5,
};

// --- MaPrimeRénov' par geste (fixed amounts per work) ---

export type GestureUnit = 'm2' | 'unit' | 'flat';

// Amounts per unit for [tres_modeste, modeste, intermediaire, superieur].
// Works with no entry are not funded by MaPrimeRénov' par geste
// (electric radiators, simple-flow VMC, ...).
export const GESTURE_FORFAITS: Record<string, { unit: GestureUnit; amounts: Record<IncomeLevel, number>; maxUnits?: number }> = {
    iti: { unit: 'm2', amounts: { tres_modeste: 25, modeste: 20, intermediaire: 15, superieur: 0 }, maxUnits: 100 },
    roof: { unit: 'm2', amounts: { tres_modeste: 25, modeste: 20, intermediaire: 15, superieur: 0 }, maxUnits: 100 },
    windows: { unit: 'unit', amounts: { tres_modeste: 100, modeste: 80, intermediaire: 40, superieur: 0 } },
    ecs: { unit: 'flat', amounts: { tres_modeste: 1200, modeste: 800, intermediaire: 400, superieur: 0 } },
    pac_air_eau: { unit: 'flat', amounts: { tres_modeste: 5000, modeste: 4000, intermediaire: 3000, superieur: 0 } },
};

export const GESTURE_ECRETEMENT: Record<IncomeLevel, number> = {
    tres_modeste: 0.9,
    modeste: 0.75,
    intermediaire: 0.6,
    superieur: 0.4,
};

// Works that count as "isolation" for the parcours accompagné requirement
// (at least two insulation works).
export const INSULATION_WORKS = new Set(['iti', 'roof', 'floor_ceiling', 'windows']);

export const classGain = (from: DPELabel, to: DPELabel): number =>
    Math.max(0, LABELS.indexOf(from) - LABELS.indexOf(to));

export interface AidWork {
    id: string;
    costTTC: number;
    quantity: number; // m2 for surface works, number of units otherwise
}

export interface AidResult {
    mpr: number;
    cee: number;
    pathway: 'accompagne' | 'geste' | 'none';
    notes: string[];
}

// Rough CEE estimate per eligible work, only cumulable with MaPrimeRénov' par geste.
const CEE_PER_WORK = 800;

export function computeAids(
    works: AidWork[],
    income: IncomeLevel,
    currentLabel: DPELabel,
    targetLabel: DPELabel,
): AidResult {
    const notes: string[] = [];
    const totalTTC = works.reduce((s, w) => s + w.costTTC, 0);
    if (totalTTC <= 0) return { mpr: 0, cee: 0, pathway: 'none', notes };

    const gain = classGain(currentLabel, targetLabel);
    const insulationCount = works.filter(w => INSULATION_WORKS.has(w.id)).length;

    if (gain >= 2) {
        if (insulationCount >= 2) {
            const totalHT = totalTTC / (1 + TVA_RENOVATION);
            const eligibleHT = Math.min(totalHT, accompagneCeilingHT(gain));
            const passoireExit = ['F', 'G'].includes(currentLabel) && LABELS.indexOf(targetLabel) <= LABELS.indexOf('D');
            const rate = ACCOMPAGNE_RATES[income] + (passoireExit ? PASSOIRE_BONUS : 0);
            const mpr = Math.min(eligibleHT * rate, totalTTC * ACCOMPAGNE_ECRETEMENT[income]);
            // CEE are valued by the Anah inside the parcours accompagné: not cumulable.
            return { mpr, cee: 0, pathway: 'accompagne', notes };
        }
        notes.push("Le parcours accompagné exige au moins deux gestes d'isolation : aides calculées par geste.");
    }

    let mpr = 0;
    let cee = 0;
    for (const w of works) {
        const forfait = GESTURE_FORFAITS[w.id];
        if (!forfait) continue;
        const qty = forfait.unit === 'flat' ? 1 : Math.min(w.quantity, forfait.maxUnits ?? Infinity);
        mpr += forfait.amounts[income] * qty;
        cee += CEE_PER_WORK;
    }
    const cap = totalTTC * GESTURE_ECRETEMENT[income];
    mpr = Math.min(mpr, cap);
    cee = Math.min(cee, Math.max(0, cap - mpr));
    if (income === 'superieur') notes.push("Les ménages aux revenus supérieurs ne sont pas éligibles à MaPrimeRénov' par geste.");
    return { mpr, cee, pathway: mpr + cee > 0 ? 'geste' : 'none', notes };
}
