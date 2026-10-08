"""Single retrofit simulation engine used by the UI, the API and the PDF report.

The simulation starts from the official DPE consumption (ADEME) and applies
average gains per work, so the starting label matches the real certificate.
"""
import math
from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

try:
    from api.aids import ResourceProfile, compute_aids, get_profile
except ImportError:
    from aids import ResourceProfile, compute_aids, get_profile

LABELS = ["A", "B", "C", "D", "E", "F", "G"]

# --- Reference data ---

DPE_THRESHOLDS = [
    ("A", 70, 6), ("B", 110, 11), ("C", 180, 30), ("D", 250, 50),
    ("E", 330, 70), ("F", 420, 100), ("G", 999, 999),
]

# BT01 construction cost index (2024/2025) vs the index the catalog prices were set at
INDEX_BT01_CURRENT = 131.0
INDEX_BT01_CATALOG = 120.0

IDF_DEPARTMENTS = {"75", "77", "78", "91", "92", "93", "94", "95"}
RURAL_DEPARTMENTS = {"23", "36", "15"}

ENERGY_PRICE_EUR_KWH = 0.228
GREEN_VALUE_PER_CLASS = 0.045  # Property value gain per DPE class gained
DEFAULT_PRICE_PER_M2 = 4500
SOCIAL_CHARGES = 0.172
LOAN_RATE = 0.045
LOAN_MONTHS = 84

# unit: how the default cost scales
#   m2_wall  -> estimated wall area (8 * sqrt(surface))
#   m2_floor -> living surface
#   radiator -> one per 15 m2
#   flat     -> one per dwelling
WORKS_CATALOG = [
    {"id": "iti", "name": "ITI (Murs Intérieurs)", "cost": 85, "unit": "m2_wall", "zone": True, "impact_kwh": 120, "impact_ges": 6, "days": 5,
     "description": "Isolation thermique par l'intérieur. Réduit les déperditions mais impacte la surface habitable (~1.5% de perte)."},
    {"id": "roof", "name": "Isolation Toiture", "cost": 65, "unit": "m2_floor", "zone": True, "impact_kwh": 65, "impact_ges": 4, "days": 7,
     "description": "Isolation des combles ou de la toiture pour les maisons individuelles."},
    {"id": "floor_ceiling", "name": "Isolation Plafond/Plancher", "cost": 55, "unit": "m2_floor", "zone": True, "impact_kwh": 45, "impact_ges": 4, "days": 3,
     "description": "Isolation des plafonds ou planchers bas (garage, grenier)."},
    {"id": "vmc", "name": "Ventilation (VMC)", "cost": 1100, "unit": "flat", "zone": True, "impact_kwh": 35, "impact_ges": 3, "days": 1,
     "description": "Installation d'une VMC simple ou double flux pour une meilleure qualité d'air et moins d'humidité."},
    {"id": "heating", "name": "Radiateur inertie", "cost": 650, "unit": "radiator", "zone": False, "impact_kwh": 60, "impact_ges": 15, "days": 2,
     "description": "Remplacement des radiateurs énergivores par des modèles à inertie haute performance."},
    {"id": "ecs", "name": "Ballon Thermo-dynamique", "cost": 3500, "unit": "flat", "zone": True, "impact_kwh": 80, "impact_ges": 20, "days": 1,
     "description": "Système de chauffe-eau thermodynamique pour une production d'eau chaude économique."},
    {"id": "windows", "name": "Menuiseries PVC", "cost": 6500, "unit": "flat", "zone": False, "impact_kwh": 45, "impact_ges": 4, "days": 2,
     "description": "Remplacement des fenêtres simple vitrage par du double vitrage PVC haute performance."},
]
WORKS_BY_ID = {w["id"]: w for w in WORKS_CATALOG}

INCOME_LEVELS = {
    "tres_modeste": ResourceProfile.BLEU,
    "modeste": ResourceProfile.JAUNE,
    "intermediaire": ResourceProfile.VIOLET,
    "superieur": ResourceProfile.ROSE,
}


# --- Input schema ---

class SimulationProperty(BaseModel):
    surface: float = Field(..., gt=0, le=10000)
    initial_cep: float = Field(..., ge=0)
    ges_value: Optional[float] = None
    building_type: Optional[str] = None
    postcode: Optional[str] = None
    construction_year: Optional[int] = None
    construction_period: Optional[str] = None
    price_per_m2: Optional[float] = None


class SimulationInput(BaseModel):
    property: SimulationProperty
    works: List[str] = []
    # Works flagged as recommended, shown as such in the report
    suggested_works: List[str] = []
    income_level: str = "intermediaire"
    # When given, the income category is derived from the RFR instead of income_level
    rfr: Optional[float] = None
    occupants: int = Field(1, ge=1, le=20)
    nb_etages: int = Field(0, ge=0, le=60)
    has_ascenseur: bool = True
    is_urban_dense: bool = False
    parking_cost: float = Field(35.0, ge=0)
    is_investor: bool = False
    monthly_rent: float = Field(0.0, ge=0)
    purchase_price: float = Field(0.0, ge=0)
    tmi: float = Field(30.0, ge=0, le=100)


# --- Helpers ---

def adjusted_thresholds(surface: float) -> List[Dict]:
    """Small dwellings (< 40 m2) get relaxed consumption thresholds."""
    factor = 1 + (40 - surface) * 0.04 if surface < 40 else 1
    return [{"label": label, "max": round(cep * factor), "max_ges": ges} for label, cep, ges in DPE_THRESHOLDS]


def get_labels(cep: float, ges: float, thresholds: List[Dict]) -> Dict[str, str]:
    cep_idx = next((i for i, t in enumerate(thresholds) if cep <= t["max"]), 6)
    ges_idx = next((i for i, t in enumerate(thresholds) if ges <= t["max_ges"]), 6)
    return {"label": LABELS[max(cep_idx, ges_idx)], "cep_label": LABELS[cep_idx], "ges_label": LABELS[ges_idx]}


def rental_ban_date(label: str, cep: float, postcode: Optional[str]) -> Optional[date]:
    """Loi Climat & Résilience rental ban schedule."""
    overseas = bool(postcode) and postcode.startswith("97")
    if not overseas and cep > 450:
        return date(2023, 1, 1)
    schedule = {"G": date(2028, 1, 1), "F": date(2031, 1, 1)} if overseas else \
        {"G": date(2025, 1, 1), "F": date(2028, 1, 1), "E": date(2034, 1, 1)}
    return schedule.get(label)


def infer_wall_materials(year: Optional[int], period: Optional[str]) -> str:
    period = (period or "").lower()
    if not year:
        year = 1940 if "1948" in period else 1970
    if year < 1948 or "1948" in period:
        return "Pierre"
    if year < 1975:
        return "Béton non isolé"
    return "Isolé RT2005"


def zone_coefficient(postcode: Optional[str]) -> float:
    dept = (postcode or "00")[:2]
    if dept in IDF_DEPARTMENTS:
        return 1.2
    if dept in RURAL_DEPARTMENTS:
        return 0.9
    return 1.0


def monthly_payment(principal: float, annual_rate: float = LOAN_RATE, months: int = LOAN_MONTHS) -> float:
    if principal <= 0:
        return 0.0
    r = annual_rate / 12
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def is_house(building_type: Optional[str]) -> bool:
    return "maison" in (building_type or "").lower()


# --- Simulation ---

def simulate(data: SimulationInput) -> Dict:
    prop = data.property
    surface = prop.surface
    ges = prop.ges_value or 20
    thresholds = adjusted_thresholds(surface)
    works = [WORKS_BY_ID[w] for w in dict.fromkeys(data.works) if w in WORKS_BY_ID]

    # Cost coefficients
    index_ratio = INDEX_BT01_CURRENT / INDEX_BT01_CATALOG
    coeff_access = 1.0 + (data.nb_etages * 0.05 if data.nb_etages > 0 and not data.has_ascenseur else 0)
    coeff_urban = 1.10 if data.is_urban_dense else 1.0
    zone = zone_coefficient(prop.postcode)
    duration = sum(w["days"] for w in works) or 1
    logistics = data.parking_cost * duration if data.is_urban_dense else 0.0

    wall_area = 8 * math.sqrt(surface)
    window_count = max(4, round(surface / 12))
    walls_uninsulated = "non isolé" in infer_wall_materials(prop.construction_year, prop.construction_period).lower()

    detailed_costs = []
    aid_works = []
    cep_red = 0.0
    ges_red = 0.0
    for w in works:
        unit = w["unit"]
        if unit == "m2_wall":
            item = w["cost"] * wall_area
            quantity = wall_area
            if walls_uninsulated:
                item += 15 * wall_area  # Wall preparation
        elif unit == "m2_floor":
            item = w["cost"] * surface
            quantity = surface
        elif unit == "radiator":
            quantity = math.ceil(surface / 15)
            item = w["cost"] * quantity
        else:
            item = w["cost"]
            quantity = window_count if w["id"] == "windows" else 1
        if w["zone"]:
            item *= zone
        item *= index_ratio * coeff_access * coeff_urban
        detailed_costs.append({"id": w["id"], "name": w["name"], "cost": item, "suggested": w["id"] in data.suggested_works})
        aid_works.append({"id": w["id"], "cost_ttc": item, "quantity": quantity})
        cep_red += w["impact_kwh"]
        ges_red += w["impact_ges"]

    if logistics > 0:
        detailed_costs.append({"id": "parking", "name": "Frais de Stationnement", "cost": logistics, "suggested": False})
    cost = sum(d["cost"] for d in detailed_costs)

    new_cep = max(35.0, prop.initial_cep - cep_red)
    new_ges = max(2.0, ges - ges_red)
    current = get_labels(prop.initial_cep, ges, thresholds)
    target = get_labels(new_cep, new_ges, thresholds)
    steps = max(0, LABELS.index(current["label"]) - LABELS.index(target["label"]))

    # Aids
    if data.rfr is not None:
        profile = get_profile(data.rfr, data.occupants, prop.postcode)
    else:
        profile = INCOME_LEVELS.get(data.income_level, ResourceProfile.VIOLET)
    aids = compute_aids(aid_works, profile, current["label"], target["label"])
    rest = max(0.0, cost - aids["mpr"] - aids["cee"])

    # Éco-PTZ: ceiling depends on the number of work categories
    categories = set()
    for w in works:
        if w["id"] == "roof" and not is_house(prop.building_type):
            continue
        if w["id"] in ("iti", "roof", "floor_ceiling"):
            categories.add("isolation")
        elif w["id"] in ("heating", "ecs"):
            categories.add("heating")
        else:
            categories.add("other")
    eco_ptz_limit = {0: 0, 1: 15000, 2: 25000}.get(len(categories), 30000)
    eco_ptz_amount = min(rest, eco_ptz_limit)

    # Savings use the real reduction (new_cep is floored)
    savings = (prop.initial_cep - new_cep) * surface * ENERGY_PRICE_EUR_KWH

    # Investor metrics
    tax_benefit = rest * (data.tmi / 100 + SOCIAL_CHARGES) if data.is_investor else 0.0
    total_investment = data.purchase_price + cost
    yield_brut = (data.monthly_rent * 12 / total_investment * 100) if total_investment > 0 else 0.0
    cashflow = data.monthly_rent - monthly_payment(rest) if data.is_investor else 0.0

    price_per_m2 = prop.price_per_m2 or DEFAULT_PRICE_PER_M2
    ban = rental_ban_date(current["label"], prop.initial_cep, prop.postcode)

    return {
        "current_label": current["label"],
        "current_cep_label": current["cep_label"],
        "current_ges_label": current["ges_label"],
        "new_label": target["label"],
        "new_cep_label": target["cep_label"],
        "new_ges_label": target["ges_label"],
        "initial_cep": prop.initial_cep,
        "new_cep": new_cep,
        "initial_ges": ges,
        "new_ges": new_ges,
        "gain_classes": steps,
        "thresholds": thresholds,
        "cost": cost,
        "detailed_costs": detailed_costs,
        "duration_days": duration,
        "subsidies": aids["mpr"],
        "cee_est": aids["cee"],
        "aid_pathway": aids["pathway"],
        "aid_notes": aids["notes"],
        "income_profile": profile.value,
        "rest_to_pay": rest,
        "eco_ptz_limit": eco_ptz_limit,
        "eco_ptz_amount": eco_ptz_amount,
        "annual_savings": savings,
        "roi_years": (rest - tax_benefit) / (savings or 1),
        "latent_gain": steps * surface * price_per_m2 * GREEN_VALUE_PER_CLASS,
        "tax_benefit": tax_benefit,
        "net_investor_cost": rest - tax_benefit,
        "yield_brut": yield_brut,
        "cashflow": cashflow,
        "ban_date": ban.isoformat() if ban else None,
        "has_iti": any(w["id"] == "iti" for w in works),
    }


# --- Work suggestions ---

def suggest_works(building_type: Optional[str], label: Optional[str], initial_cep: Optional[float],
                  recommended_ids: List[str], loss_breakdown: Optional[Dict]) -> Dict[str, List[str]]:
    """Works to suggest, and a default selection aiming at class C (or D for a G)."""
    apartment = "appartement" in (building_type or "").lower()
    suggested = set(recommended_ids)
    if loss_breakdown:
        if loss_breakdown.get("walls", 0) > 40: suggested.add("iti")
        if loss_breakdown.get("windows", 0) > 20: suggested.add("windows")
        if loss_breakdown.get("ventilation", 0) > 30: suggested.add("vmc")
    if apartment:
        suggested.discard("roof")

    cep = initial_cep or 350
    label = label or "G"
    if label in ("A", "B", "C"):
        target = cep
    elif label == "G":
        target = 230
    else:
        target = 150
    remaining = cep - target

    priority = ["iti", "floor_ceiling", "heating", "windows", "vmc"] if apartment else \
        ["roof", "iti", "floor_ceiling", "heating", "windows", "vmc"]
    ordered = sorted(WORKS_CATALOG, key=lambda w: priority.index(w["id"]) if w["id"] in priority else 99)
    preselected = []
    for w in ordered:
        if remaining > 0 and w["id"] in suggested:
            preselected.append(w["id"])
            remaining -= w["impact_kwh"]

    return {
        "suggested": [w["id"] for w in WORKS_CATALOG if w["id"] in suggested],
        "preselected": preselected,
    }
