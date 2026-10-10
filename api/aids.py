"""MaPrimeRénov' and CEE rules, as applicable to files filed from 1 September 2026.

Sources: Anah (guide des aides 2026), décret n° 2025-956 du 8 septembre 2025,
décret n° 2026-822 du 25 août 2026 and its arrêtés (JO du 27 août 2026).
Main points:
- Resource ceilings revised on 1 January 2026.
- Rénovation d'ampleur: dwellings rated E, F or G, at least 2 classes gained,
  at least 2 insulation works; 80 / 60 / 45 / 10 % of an expense ceiling of
  30 000 € HT (2 classes) or 40 000 € HT (3 classes or more). No more
  "sortie de passoire" bonus. A house may not keep gas, oil or coal heating.
  CEE are valued by the Anah inside the pathway (not cumulable).
- MaPrimeRénov' par geste: only heat pumps (other than air/air), district
  heating connection, energy audit and oil tank removal are still funded,
  and only for the Très modeste, Modeste and Intermédiaire categories.
  Insulation, windows, ventilation and water heaters only get CEE premiums.

These figures change often: check them against the Anah before each update.
"""
from enum import Enum
from typing import Dict, List, Optional

RULES_LABEL = "barème MaPrimeRénov' en vigueur au 1er septembre 2026"


class ResourceProfile(str, Enum):
    BLEU = "Très Modeste"
    JAUNE = "Modeste"
    VIOLET = "Intermédiaire"
    ROSE = "Supérieur"


LABELS = ["A", "B", "C", "D", "E", "F", "G"]

# Energy renovation works are invoiced with 5.5% VAT; Anah ceilings are HT.
TVA_RENOVATION = 0.055

IDF_DEPARTMENTS = {"75", "77", "78", "91", "92", "93", "94", "95"}

# Revenu fiscal de référence ceilings (1 January 2026) for households of 1 to 5
# people (Très modeste, Modeste, Intermédiaire), then the increment per extra person.
RFR_CEILINGS = {
    "province": {
        "table": [
            (17363, 22259, 31185),
            (25393, 32553, 45842),
            (30540, 39148, 55196),
            (35676, 45735, 64550),
            (40835, 52348, 73907),
        ],
        "per_extra": (5151, 6598, 9357),
    },
    "idf": {
        "table": [
            (24031, 29253, 40851),
            (35270, 42933, 60051),
            (42357, 51564, 71846),
            (49455, 60208, 84562),
            (56580, 68877, 96817),
        ],
        "per_extra": (7116, 8663, 12257),
    },
}

PROFILE_ORDER = [ResourceProfile.BLEU, ResourceProfile.JAUNE, ResourceProfile.VIOLET, ResourceProfile.ROSE]

# --- Rénovation d'ampleur ---

AMPLEUR_LABELS = {"E", "F", "G"}
AMPLEUR_RATES = {
    ResourceProfile.BLEU: 0.80,
    ResourceProfile.JAUNE: 0.60,
    ResourceProfile.VIOLET: 0.45,
    ResourceProfile.ROSE: 0.10,
}
# Total public aid cannot exceed this share of the TTC cost.
AMPLEUR_ECRETEMENT = {
    ResourceProfile.BLEU: 1.0,
    ResourceProfile.JAUNE: 0.8,
    ResourceProfile.VIOLET: 0.6,
    ResourceProfile.ROSE: 0.5,
}

# Works counted as "isolation" for the rénovation d'ampleur requirement.
INSULATION_WORKS = {"iti", "ite", "iti_ossature", "ite_pse", "ite_bois", "roof", "combles", "floor_ceiling", "windows", "windows_pvc"}
FOSSIL_ENERGIES = {"gas", "oil"}
# Works that remove gas or oil heating
FOSSIL_REPLACEMENTS = {"pac_air_eau"}

# --- MaPrimeRénov' par geste ---

# Fixed amounts (Très modeste, Modeste, Intermédiaire, Supérieur).
GESTURE_FORFAITS = {
    "pac_air_eau": (5000, 4000, 3000, 0),
}
GESTURE_ECRETEMENT = {
    ResourceProfile.BLEU: 0.9,
    ResourceProfile.JAUNE: 0.75,
    ResourceProfile.VIOLET: 0.6,
    ResourceProfile.ROSE: 0.4,
}

# --- CEE premiums (estimates) ---

# Indicative market values: (Très modeste / Modeste, other households), per
# unit. Actual premiums depend on the energy supplier's offer.
CEE_ESTIMATES = {
    "iti": ("m2", (14, 8)),
    "ite": ("m2", (14, 8)),
    "roof": ("m2", (14, 8)),
    "floor_ceiling": ("m2", (18, 10)),
    "windows": ("unit", (60, 35)),
    "vmc": ("flat", (300, 150)),
    "ecs": ("flat", (150, 100)),
    # "Coup de pouce chauffage": only when it replaces a gas or oil boiler
    "pac_air_eau": ("flat", (4000, 2500)),
}


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


def ampleur_ceiling_ht(class_gain: int) -> float:
    if class_gain >= 3:
        return 40000
    if class_gain == 2:
        return 30000
    return 0


def class_gain(current: str, target: str) -> int:
    return max(0, LABELS.index(current) - LABELS.index(target))


def cee_estimate(work: Dict, profile: ResourceProfile, energy: Optional[str]) -> float:
    rule = CEE_ESTIMATES.get(work["id"])
    if not rule:
        return 0.0
    if work["id"] == "pac_air_eau" and energy not in FOSSIL_ENERGIES:
        return 0.0
    unit, amounts = rule
    amount = amounts[0] if profile in (ResourceProfile.BLEU, ResourceProfile.JAUNE) else amounts[1]
    return amount * (1 if unit == "flat" else work["quantity"])


def ampleur_blockers(works: List[Dict], current_label: str, target_label: str,
                     house: bool = False, energy: Optional[str] = None) -> List[str]:
    """Reasons why the rénovation d'ampleur is not available (empty list: eligible)."""
    reasons = []
    ids = {w["id"] for w in works}
    if current_label not in AMPLEUR_LABELS:
        reasons.append(f"La rénovation d'ampleur est réservée aux logements classés E, F ou G (celui-ci est classé {current_label}).")
    gain = class_gain(current_label, target_label)
    if gain < 2:
        reasons.append("La rénovation d'ampleur exige un gain d'au moins deux classes : ce programme n'y suffit pas.")
    if sum(1 for w in works if w["id"] in INSULATION_WORKS) < 2:
        reasons.append("La rénovation d'ampleur exige au moins deux travaux d'isolation (murs, toiture, plancher ou fenêtres).")
    if house and energy in FOSSIL_ENERGIES and not ids & FOSSIL_REPLACEMENTS:
        reasons.append("Depuis le 1er septembre 2026, une maison ne peut plus conserver un chauffage au gaz ou au fioul en rénovation d'ampleur.")
    return reasons


def compute_aids(works: List[Dict], profile: ResourceProfile, current_label: str, target_label: str,
                 house: bool = False, energy: Optional[str] = None) -> Dict:
    """works: list of {"id", "cost_ttc", "quantity"}. Returns MPR and CEE amounts,
    per work for the gesture pathway, and explanations."""
    notes: List[str] = []
    total_ttc = sum(w["cost_ttc"] for w in works)
    empty = {"mpr": 0.0, "cee": 0.0, "pathway": "none", "notes": notes, "per_work": {}, "blockers": []}
    if total_ttc <= 0:
        return empty

    blockers = ampleur_blockers(works, current_label, target_label, house, energy)
    gain = class_gain(current_label, target_label)
    if not blockers:
        eligible_ht = min(total_ttc / (1 + TVA_RENOVATION), ampleur_ceiling_ht(gain))
        mpr = min(eligible_ht * AMPLEUR_RATES[profile], total_ttc * AMPLEUR_ECRETEMENT[profile])
        notes.append("CEE non cumulables : l'Anah les intègre déjà dans l'aide de la rénovation d'ampleur.")
        return {"mpr": mpr, "cee": 0.0, "pathway": "accompagne", "notes": notes, "per_work": {}, "blockers": []}

    # Gesture pathway: only heat pumps still get MaPrimeRénov', CEE for the rest
    idx = PROFILE_ORDER.index(profile)
    per_work: Dict[str, Dict[str, float]] = {}
    for w in works:
        forfait = GESTURE_FORFAITS.get(w["id"])
        mpr_w = float(forfait[idx]) if forfait else 0.0
        per_work[w["id"]] = {"mpr": mpr_w, "cee": cee_estimate(w, profile, energy)}
    mpr = sum(v["mpr"] for v in per_work.values())
    cee = sum(v["cee"] for v in per_work.values())
    cap = total_ttc * GESTURE_ECRETEMENT[profile]
    if mpr + cee > cap:
        # Écrêtement: MaPrimeRénov' is reduced first
        excess = mpr + cee - cap
        cut = min(excess, mpr)
        mpr -= cut
        cee -= excess - cut
        scale_mpr = mpr / sum(v["mpr"] for v in per_work.values()) if mpr else 0
        total_cee = sum(v["cee"] for v in per_work.values())
        scale_cee = cee / total_cee if total_cee else 0
        for v in per_work.values():
            v["mpr"] *= scale_mpr
            v["cee"] *= scale_cee

    if profile == ResourceProfile.ROSE:
        notes.append("Les ménages aux revenus supérieurs n'ont pas accès à MaPrimeRénov' par geste.")
    elif any(w["id"] in INSULATION_WORKS or w["id"] in ("vmc", "ecs") for w in works):
        notes.append("Depuis le 1er septembre 2026, l'isolation, les fenêtres, la ventilation et les chauffe-eau "
                     "ne sont plus financés par MaPrimeRénov' par geste : seules les primes CEE s'appliquent.")
    return {"mpr": mpr, "cee": cee, "pathway": "geste" if mpr + cee > 0 else "none", "notes": notes,
            "per_work": per_work, "blockers": blockers}
