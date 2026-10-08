"""MaPrimeRénov' rules (barème 2025, Anah). Keep in sync with src/aids.ts.

These figures change every year: check them against the official Anah guide
before each update.
"""
from enum import Enum
from typing import Dict, List, Optional


class ResourceProfile(str, Enum):
    BLEU = "Très Modeste"
    JAUNE = "Modeste"
    VIOLET = "Intermédiaire"
    ROSE = "Supérieur"


LABELS = ["A", "B", "C", "D", "E", "F", "G"]

# Energy renovation works are invoiced with 5.5% VAT; Anah ceilings are HT.
TVA_RENOVATION = 0.055

IDF_DEPARTMENTS = {"75", "77", "78", "91", "92", "93", "94", "95"}

# Revenu fiscal de référence ceilings for households of 1 to 5 people
# (Très modeste, Modeste, Intermédiaire), then the increment per extra person.
RFR_CEILINGS = {
    "province": {
        "table": [
            (17173, 22015, 30844),
            (25115, 32197, 45340),
            (30206, 38719, 54592),
            (35285, 45234, 63844),
            (40388, 51775, 73098),
        ],
        "per_extra": (5094, 6525, 9254),
    },
    "idf": {
        "table": [
            (23768, 28933, 40404),
            (34884, 42463, 59394),
            (41893, 51000, 71060),
            (48914, 59549, 83637),
            (55961, 68123, 95758),
        ],
        "per_extra": (7038, 8568, 12122),
    },
}

ACCOMPAGNE_RATES = {
    ResourceProfile.BLEU: 0.80,
    ResourceProfile.JAUNE: 0.60,
    ResourceProfile.VIOLET: 0.45,
    ResourceProfile.ROSE: 0.10,
}

# Bonus when a "passoire" (F/G) reaches at least class D.
PASSOIRE_BONUS = 0.10

# Total public aid cannot exceed this share of the TTC cost.
ACCOMPAGNE_ECRETEMENT = {
    ResourceProfile.BLEU: 1.0,
    ResourceProfile.JAUNE: 0.8,
    ResourceProfile.VIOLET: 0.6,
    ResourceProfile.ROSE: 0.5,
}

GESTURE_ECRETEMENT = {
    ResourceProfile.BLEU: 0.9,
    ResourceProfile.JAUNE: 0.75,
    ResourceProfile.VIOLET: 0.6,
    ResourceProfile.ROSE: 0.4,
}

# Fixed amounts per unit (Très modeste, Modeste, Intermédiaire, Supérieur).
# Works with no entry are not funded by MaPrimeRénov' par geste.
GESTURE_FORFAITS = {
    "iti": {"unit": "m2", "amounts": (25, 20, 15, 0), "max_units": 100},
    "iti_ossature": {"unit": "m2", "amounts": (25, 20, 15, 0), "max_units": 100},
    "ite_pse": {"unit": "m2", "amounts": (75, 60, 40, 0), "max_units": 100},
    "ite_bois": {"unit": "m2", "amounts": (75, 60, 40, 0), "max_units": 100},
    "roof": {"unit": "m2", "amounts": (25, 20, 15, 0), "max_units": 100},
    "windows": {"unit": "unit", "amounts": (100, 80, 40, 0)},
    "windows_pvc": {"unit": "unit", "amounts": (100, 80, 40, 0)},
    "ecs": {"unit": "flat", "amounts": (1200, 800, 400, 0)},
    "pac_air_eau": {"unit": "flat", "amounts": (5000, 4000, 3000, 0)},
}

# Works counted as "isolation" for the parcours accompagné requirement.
INSULATION_WORKS = {"iti", "iti_ossature", "ite_pse", "ite_bois", "roof", "combles", "floor_ceiling", "windows", "windows_pvc"}

PROFILE_ORDER = [ResourceProfile.BLEU, ResourceProfile.JAUNE, ResourceProfile.VIOLET, ResourceProfile.ROSE]


def is_idf(postcode: Optional[str]) -> bool:
    return bool(postcode) and postcode[:2] in IDF_DEPARTMENTS


def get_profile(rfr: float, occupants: int = 1, postcode: Optional[str] = None) -> ResourceProfile:
    zone = RFR_CEILINGS["idf" if is_idf(postcode) else "province"]
    occupants = max(1, int(occupants or 1))
    if occupants <= 5:
        ceilings = zone["table"][occupants - 1]
    else:
        base = zone["table"][4]
        ceilings = tuple(b + (occupants - 5) * e for b, e in zip(base, zone["per_extra"]))
    for profile, ceiling in zip(PROFILE_ORDER, ceilings):
        if rfr <= ceiling:
            return profile
    return ResourceProfile.ROSE


def accompagne_ceiling_ht(class_gain: int) -> float:
    if class_gain >= 4:
        return 70000
    if class_gain == 3:
        return 55000
    if class_gain == 2:
        return 40000
    return 0


def class_gain(current: str, target: str) -> int:
    return max(0, LABELS.index(current) - LABELS.index(target))


def compute_aids(works: List[Dict], profile: ResourceProfile, current_label: str, target_label: str) -> Dict:
    """works: list of {"id", "cost_ttc", "quantity"}. Returns MPR and CEE amounts."""
    notes: List[str] = []
    total_ttc = sum(w["cost_ttc"] for w in works)
    if total_ttc <= 0:
        return {"mpr": 0.0, "cee": 0.0, "pathway": "none", "notes": notes}

    gain = class_gain(current_label, target_label)
    insulation_count = sum(1 for w in works if w["id"] in INSULATION_WORKS)

    if gain >= 2:
        if insulation_count >= 2:
            eligible_ht = min(total_ttc / (1 + TVA_RENOVATION), accompagne_ceiling_ht(gain))
            passoire_exit = current_label in ("F", "G") and LABELS.index(target_label) <= LABELS.index("D")
            rate = ACCOMPAGNE_RATES[profile] + (PASSOIRE_BONUS if passoire_exit else 0)
            mpr = min(eligible_ht * rate, total_ttc * ACCOMPAGNE_ECRETEMENT[profile])
            # CEE are valued by the Anah inside the parcours accompagné: not cumulable.
            return {"mpr": mpr, "cee": 0.0, "pathway": "accompagne", "notes": notes}
        notes.append("Le parcours accompagné exige au moins deux gestes d'isolation : aides calculées par geste.")

    idx = PROFILE_ORDER.index(profile)
    mpr = 0.0
    cee = 0.0
    for w in works:
        forfait = GESTURE_FORFAITS.get(w["id"])
        if not forfait:
            continue
        qty = 1 if forfait["unit"] == "flat" else min(w["quantity"], forfait.get("max_units", float("inf")))
        mpr += forfait["amounts"][idx] * qty
        cee += 800  # Rough CEE estimate per eligible work
    cap = total_ttc * GESTURE_ECRETEMENT[profile]
    mpr = min(mpr, cap)
    cee = min(cee, max(0.0, cap - mpr))
    if profile == ResourceProfile.ROSE:
        notes.append("Les ménages aux revenus supérieurs ne sont pas éligibles à MaPrimeRénov' par geste.")
    return {"mpr": mpr, "cee": cee, "pathway": "geste" if mpr + cee > 0 else "none", "notes": notes}
