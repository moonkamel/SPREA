"""Single retrofit simulation engine used by the UI, the API and the PDF report.

The simulation starts from the official DPE consumption (ADEME), split by
usage (heating, hot water, other). Insulation works reduce the heating need
according to the dwelling's own heat losses (api/envelope.py); heating and
hot water systems then change the energy used. The result is scaled on the
official DPE figures, so the starting label matches the real certificate.
"""
import math
from datetime import date
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

try:
    from api.aids import RULES_LABEL, ResourceProfile, compute_aids, get_profile
    from api.envelope import Envelope
    from api.green_value import department, estimate as green_value_estimate, kind_of
except ImportError:
    from aids import RULES_LABEL, ResourceProfile, compute_aids, get_profile
    from envelope import Envelope
    from green_value import department, estimate as green_value_estimate, kind_of

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

# Primary energy conversion coefficients (DPE)
ENERGY_CONVERSION = {
    "electricity": 1.9,  # Since 1 January 2026 (2.3 before)
    "gas": 1.0,
    "oil": 1.0,
    "wood": 1.0,
    "district_heating": 1.0,
}

# Average 2025-2026 prices per kWh of final energy, TTC, excluding subscription.
# Check yearly (CRE regulated tariff for electricity, prix repère for gas).
ENERGY_PRICES_EUR_KWH = {
    "electricity": 0.20,
    "gas": 0.11,
    "oil": 0.12,
    "wood": 0.09,
    "district_heating": 0.12,
}

# GHG emission factors, kgCO2e per kWh of final energy (DPE 3CL-2021 method)
EMISSION_FACTORS = {
    "electricity": 0.079,
    "gas": 0.227,
    "oil": 0.324,
    "wood": 0.030,
    "district_heating": 0.150,
}

# Seasonal efficiency of the heating system being replaced
CURRENT_HEATING_EFFICIENCY = {
    "electricity": 1.0,   # Joule effect convectors
    "gas": 0.85,
    "oil": 0.80,
    "wood": 0.70,
    "district_heating": 1.0,
}

# Works that replace the heating system: new energy and seasonal efficiency
HEATING_SYSTEMS = {
    # Conservative SCOP for an air/water heat pump in an existing house
    "pac_air_eau": {"energy": "electricity", "efficiency": 2.9},
    # Better regulation than old convectors: ~10% saving on electric heating
    "heating": {"energy": "electricity", "efficiency": 1.1},
}
# Hot water production being replaced, and the thermodynamic water heater
CURRENT_HOT_WATER_EFFICIENCY = {
    "electricity": 0.9,
    "gas": 0.75,
    "oil": 0.70,
    "wood": 0.60,
    "district_heating": 0.9,
}
HEAT_PUMP_WATER_HEATER_COP = 2.5

# Wall preparation before interior insulation of uninsulated walls (EUR/m2)
WALL_PREPARATION_COST = 15

DEFAULT_PRICE_PER_M2 = 4500
SOCIAL_CHARGES = 0.172
LOAN_RATE = 0.045
LOAN_MONTHS = 84

# unit: how the default cost scales
#   m2_wall  -> insulated wall area (envelope geometry)
#   m2_roof  -> roof / top floor area
#   m2_floor -> lowest floor area
#   window   -> per window (price per dwelling given for a typical 8 windows)
#   radiator -> one per 15 m2
#   flat     -> one per dwelling
# range: low / high multipliers around the central cost (quotes vary with the
# building, access and the craftsman; heat pumps and ventilation vary most)
WORKS_CATALOG = [
    {"id": "iti", "range": (0.85, 1.25), "name": "Isolation des murs (par l'intérieur)", "cost": 85, "unit": "m2_wall", "zone": True, "days": 5,
     "description": "Doublage isolant posé côté intérieur des murs donnant sur l'extérieur. Efficace, mais réduit un peu la surface habitable."},
    {"id": "roof", "range": (0.85, 1.25), "name": "Isolation de la toiture", "cost": 65, "unit": "m2_roof", "zone": True, "days": 7,
     "description": "Isolation des combles ou des rampants. Souvent le geste le plus rentable dans une maison : la chaleur monte."},
    {"id": "floor_ceiling", "range": (0.85, 1.3), "name": "Isolation du plancher bas", "cost": 55, "unit": "m2_floor", "zone": True, "days": 3,
     "description": "Isolant posé sous le plancher, côté cave, garage ou vide sanitaire. Supprime l'effet « sol froid »."},
    {"id": "vmc", "range": (0.8, 1.35), "name": "Ventilation mécanique (VMC)", "cost": 1100, "unit": "flat", "zone": True, "days": 1,
     "description": "Renouvelle l'air en continu et en limitant les pertes de chaleur. Indispensable après isolation pour éviter l'humidité."},
    {"id": "pac_air_eau", "range": (0.85, 1.25), "name": "Pompe à chaleur air/eau", "cost": 13000, "unit": "flat", "zone": True, "days": 3,
     "description": "Remplace une chaudière gaz ou fioul : environ trois fois moins d'énergie consommée. Utilise vos radiateurs à eau ou votre plancher chauffant."},
    {"id": "heating", "range": (0.85, 1.2), "name": "Radiateurs électriques à inertie", "cost": 650, "unit": "radiator", "zone": False, "days": 2,
     "description": "Remplacent d'anciens convecteurs électriques, ou une chaudière gaz ou fioul dans un appartement : chaleur plus douce et mieux régulée, plus d'émissions de CO₂ sur place. À combiner avec l'isolation."},
    {"id": "ecs", "range": (0.85, 1.2), "name": "Chauffe-eau thermodynamique", "cost": 3500, "unit": "flat", "zone": True, "days": 1,
     "description": "Produit l'eau chaude avec une petite pompe à chaleur : deux à trois fois moins d'électricité qu'un ballon classique."},
    {"id": "windows", "range": (0.8, 1.3), "name": "Fenêtres double vitrage", "cost": 812.5, "unit": "window", "zone": False, "days": 2,
     "description": "Remplacement des fenêtres anciennes ou en simple vitrage. Plus de confort, moins de courants d'air et de bruit."},
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
    """Dwelling as described by its DPE."""
    surface: float = Field(..., gt=0, le=10000)
    initial_cep: float = Field(..., ge=0)
    ges_value: Optional[float] = None
    # Label and date of the official DPE, when known
    official_label: Optional[str] = None
    dpe_date: Optional[str] = None
    building_type: Optional[str] = None
    postcode: Optional[str] = None
    construction_year: Optional[int] = None
    construction_period: Optional[str] = None
    price_per_m2: Optional[float] = Field(None, gt=0, le=100000)
    # Where price_per_m2 comes from (e.g. "prix médian DVF de 212 ventes..."), shown in the report
    price_source: Optional[str] = Field(None, max_length=250)
    insee_code: Optional[str] = Field(None, max_length=5)
    heating_energy: Optional[str] = None  # ADEME label, e.g. "Gaz naturel", "Électricité"
    final_consumption: Optional[float] = Field(None, ge=0)  # kWh EF/m2/year, from ADEME
    # DPE insulation quality per element (walls, roof, floor, windows): insuffisante, moyenne, bonne, très bonne
    insulation_quality: Optional[Dict[str, Optional[str]]] = None
    # DPE heat losses per element (walls, roof, floor, windows, air, bridges), used as weights
    dpe_losses: Optional[Dict[str, Optional[float]]] = None


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

def small_surface_factor(surface: float) -> float:
    """Approximation of the relaxed thresholds for dwellings under 40 m2
    (arrêté du 25 mars 2024: +2 % at 35 m2, much more under 15 m2)."""
    if surface >= 40:
        return 1.0
    factor = 1 + 0.004 * (40 - surface)
    if surface < 15:
        factor += 0.015 * (15 - max(surface, 8))
    return factor


def adjusted_thresholds(surface: float, factor: Optional[float] = None) -> List[Dict]:
    """Small dwellings (< 40 m2) get relaxed consumption thresholds."""
    factor = small_surface_factor(surface) if factor is None else factor
    return [{"label": label, "max": round(cep * factor), "max_ges": ges} for label, cep, ges in DPE_THRESHOLDS]


# DPE established with the 2021 method, and with the small-surface thresholds
DPE_2021 = "2021-07-01"
SMALL_SURFACE_RULE = "2024-07-01"


def calibrated_thresholds(surface: float, cep: float, ges: float, official: Optional[str],
                          dpe_date: Optional[str]) -> Tuple[List[Dict], Optional[str]]:
    """Thresholds, and the current label to show. A recent DPE already applies
    the rules in force: its label is the reference, and the small-surface
    factor is calibrated so that it gives that label."""
    default = small_surface_factor(surface)
    official = official if official in LABELS else None
    if not official or not dpe_date or dpe_date < DPE_2021:
        return adjusted_thresholds(surface, default), None
    if surface < 40:
        # Older DPE of a small dwelling: today's thresholds can improve its label
        if dpe_date < SMALL_SURFACE_RULE:
            return adjusted_thresholds(surface, default), None
        matching = [f / 100 for f in range(100, 201) if get_labels(cep, ges, adjusted_thresholds(surface, f / 100))["label"] == official]
        if matching:
            return adjusted_thresholds(surface, min(matching, key=lambda f: abs(f - default))), official
    return adjusted_thresholds(surface, default), official


def get_labels(cep: float, ges: float, thresholds: List[Dict]) -> Dict[str, str]:
    cep_idx = next((i for i, t in enumerate(thresholds) if cep <= t["max"]), 6)
    ges_idx = next((i for i, t in enumerate(thresholds) if ges <= t["max_ges"]), 6)
    return {"label": LABELS[max(cep_idx, ges_idx)], "cep_label": LABELS[cep_idx], "ges_label": LABELS[ges_idx]}


def rental_ban_date(label: str, final_consumption: float, postcode: Optional[str]) -> Optional[date]:
    """Loi Climat & Résilience rental ban schedule (the 450 kWh rule is in final energy)."""
    overseas = bool(postcode) and postcode.startswith("97")
    if not overseas and final_consumption > 450:
        return date(2023, 1, 1)
    schedule = {"G": date(2028, 1, 1), "F": date(2031, 1, 1)} if overseas else \
        {"G": date(2025, 1, 1), "F": date(2028, 1, 1), "E": date(2034, 1, 1)}
    return schedule.get(label)


def rental_status(ban: Optional[date], today: Optional[date] = None) -> str:
    """Plain-language rental status under the Loi Climat schedule."""
    today = today or date.today()
    if ban is None:
        return "Louable sans limite de date"
    if ban <= today:
        return f"Location interdite depuis le {ban.strftime('%d/%m/%Y')}"
    return f"Louable jusqu'au {ban.strftime('%d/%m/%Y')}"


def normalize_energy(source: Optional[str]) -> str:
    """Map ADEME labels (French, e.g. 'Électricité', 'Gaz naturel') to ENERGY_CONVERSION keys."""
    s = (source or "gas").lower()
    if s in ENERGY_CONVERSION: return s
    if "lectri" in s: return "electricity"
    if "gaz" in s or "gpl" in s or "propane" in s: return "gas"
    if "fioul" in s: return "oil"
    if "bois" in s or "granul" in s: return "wood"
    if "seau" in s: return "district_heating"
    return "gas"


def build_envelope(prop: "SimulationProperty", works: List[str] = ()) -> Envelope:
    # An apartment insulating its roof or floor is on the top or ground floor
    exposed = {element for work, element in (("roof", "roof"), ("floor_ceiling", "floor")) if work in works}
    return Envelope(prop.surface, prop.building_type, prop.construction_year, prop.construction_period,
                    prop.insulation_quality, prop.dpe_losses, exposed_elements=exposed)


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


def initial_final_consumption(prop: "SimulationProperty", energy: str) -> float:
    if prop.final_consumption:
        return prop.final_consumption
    return prop.initial_cep / ENERGY_CONVERSION[energy]


def energy_balance(prop: "SimulationProperty", env: Envelope, energy: str, works: List[str]) -> Dict:
    """Final consumption per usage (kWh/m2/year) and its energy, before and after the works."""
    final = initial_final_consumption(prop, energy)
    heating = final * env.heating_share
    hot_water = final * env.hot_water_share
    before = {
        "heating": (heating, energy),
        "hot_water": (hot_water, energy),
        "other": (final - heating - hot_water, energy),
    }

    # 1. Insulation reduces the heating need
    need_factor = 1 - env.heating_reduction(works)
    heating_after = (heating * need_factor, energy)

    # 2. A new heating system replaces the current one (best one if several are selected)
    options = [
        (heating_after[0] * CURRENT_HEATING_EFFICIENCY[energy] / HEATING_SYSTEMS[w]["efficiency"], HEATING_SYSTEMS[w]["energy"])
        for w in works if w in HEATING_SYSTEMS
    ]
    if options:
        heating_after = min(options, key=lambda o: o[0] * ENERGY_CONVERSION[o[1]])

    # 3. Thermodynamic water heater
    hot_water_after = (hot_water, energy)
    if "ecs" in works:
        hot_water_after = (hot_water * CURRENT_HOT_WATER_EFFICIENCY[energy] / HEAT_PUMP_WATER_HEATER_COP, "electricity")

    after = {"heating": heating_after, "hot_water": hot_water_after, "other": before["other"]}
    return {"before": before, "after": after}


def _total(usages: Dict, factors: Dict[str, float]) -> float:
    return sum(kwh * factors[e] for kwh, e in usages.values())


def projected_performance(prop: "SimulationProperty", works: List[str]) -> Dict:
    """New primary consumption and GHG, scaled on the official DPE values."""
    energy = normalize_energy(prop.heating_energy)
    env = build_envelope(prop, works)
    balance = energy_balance(prop, env, energy, works)
    ges = prop.ges_value or 20
    primary_before = _total(balance["before"], ENERGY_CONVERSION)
    ghg_before = _total(balance["before"], EMISSION_FACTORS)
    cep_ratio = _total(balance["after"], ENERGY_CONVERSION) / primary_before if primary_before > 0 else 1.0
    ges_ratio = _total(balance["after"], EMISSION_FACTORS) / ghg_before if ghg_before > 0 else 1.0
    return {
        "energy": energy,
        "envelope": env,
        "balance": balance,
        "new_cep": prop.initial_cep * cep_ratio,
        "new_ges": ges * ges_ratio,
    }


# --- Simulation ---

def simulate(data: SimulationInput) -> Dict:
    prop = data.property
    surface = prop.surface
    ges = prop.ges_value or 20
    thresholds, official = calibrated_thresholds(surface, prop.initial_cep, ges, prop.official_label, prop.dpe_date)
    works = [WORKS_BY_ID[w] for w in dict.fromkeys(data.works) if w in WORKS_BY_ID]
    work_ids = [w["id"] for w in works]
    perf = projected_performance(prop, work_ids)
    env = perf["envelope"]
    energy = perf["energy"]

    # Cost coefficients
    index_ratio = INDEX_BT01_CURRENT / INDEX_BT01_CATALOG
    coeff_access = 1.0 + (data.nb_etages * 0.05 if data.nb_etages > 0 and not data.has_ascenseur else 0)
    coeff_urban = 1.10 if data.is_urban_dense else 1.0
    zone = zone_coefficient(prop.postcode)
    duration = sum(w["days"] for w in works) or 1
    logistics = data.parking_cost * duration if data.is_urban_dense else 0.0

    quantities = {
        "m2_wall": env.wall_area,
        "m2_roof": env.areas["roof"],
        "m2_floor": env.areas["floor"],
        "window": env.window_count,
        "radiator": math.ceil(surface / 15),
        "flat": 1,
    }

    detailed_costs = []
    aid_works = []
    for w in works:
        quantity = quantities[w["unit"]]
        item = w["cost"] * quantity
        if w["unit"] == "m2_wall" and env.walls_uninsulated:
            item += WALL_PREPARATION_COST * quantity
        if w["zone"]:
            item *= zone
        item *= index_ratio * coeff_access * coeff_urban
        low, high = w["range"]
        detailed_costs.append({"id": w["id"], "name": w["name"], "cost": item, "cost_low": item * low,
                               "cost_high": item * high, "quantity": quantity, "unit": w["unit"],
                               "days": w["days"], "suggested": w["id"] in data.suggested_works})
        aid_works.append({"id": w["id"], "cost_ttc": item, "quantity": quantity})

    if logistics > 0:
        detailed_costs.append({"id": "parking", "name": "Stationnement des artisans", "cost": logistics,
                               "cost_low": logistics, "cost_high": logistics, "quantity": duration, "unit": "day",
                               "days": 0, "suggested": False})
    cost = sum(d["cost"] for d in detailed_costs)
    cost_low = sum(d["cost_low"] for d in detailed_costs)
    cost_high = sum(d["cost_high"] for d in detailed_costs)

    new_cep = perf["new_cep"]
    new_ges = perf["new_ges"]
    balance = perf["balance"]
    final_before = sum(kwh for kwh, _ in balance["before"].values())
    final_after = sum(kwh for kwh, _ in balance["after"].values())
    bill_before = _total(balance["before"], ENERGY_PRICES_EUR_KWH) * surface
    bill_after = _total(balance["after"], ENERGY_PRICES_EUR_KWH) * surface
    current = get_labels(prop.initial_cep, ges, thresholds)
    if official:
        current["label"] = official
    target = get_labels(new_cep, new_ges, thresholds)
    steps = max(0, LABELS.index(current["label"]) - LABELS.index(target["label"]))

    # Aids
    if data.rfr is not None:
        profile = get_profile(data.rfr, data.occupants, prop.postcode)
    else:
        profile = INCOME_LEVELS.get(data.income_level, ResourceProfile.VIOLET)
    house = is_house(prop.building_type)
    aids = compute_aids(aid_works, profile, current["label"], target["label"], house, energy)
    rest = max(0.0, cost - aids["mpr"] - aids["cee"])

    # Range: the same works priced low / high (aids follow the cost in rénovation d'ampleur)
    def rest_for(bound: str) -> float:
        scaled = [{**a, "cost_ttc": d[bound]} for a, d in zip(aid_works, detailed_costs)]
        res = compute_aids(scaled, profile, current["label"], target["label"], house, energy)
        total = sum(d[bound] for d in detailed_costs)
        return max(0.0, total - res["mpr"] - res["cee"])
    rest_low, rest_high = rest_for("cost_low"), rest_for("cost_high")

    # Éco-PTZ: ceiling depends on the number of work categories
    categories = set()
    for w in works:
        if w["id"] == "roof" and not is_house(prop.building_type):
            continue
        if w["id"] in ("iti", "roof", "floor_ceiling"):
            categories.add("isolation")
        elif w["id"] in ("heating", "ecs", "pac_air_eau"):
            categories.add("heating")
        else:
            categories.add("other")
    if aids["pathway"] == "accompagne":
        # Éco-PTZ "performance énergétique globale", paired with MaPrimeRénov'
        eco_ptz_limit, eco_ptz_months = 50000, 240
    else:
        eco_ptz_limit = {0: 0, 1: 15000, 2: 25000}.get(len(categories), 30000)
        eco_ptz_months = 180
    eco_ptz_amount = min(rest, eco_ptz_limit)

    # Savings on the energy bill, in final energy at current prices
    savings = max(0.0, bill_before - bill_after)

    # Investor metrics
    tax_benefit = rest * (data.tmi / 100 + SOCIAL_CHARGES) if data.is_investor else 0.0
    total_investment = data.purchase_price + cost
    yield_brut = (data.monthly_rent * 12 / total_investment * 100) if total_investment > 0 else 0.0
    cashflow = data.monthly_rent - monthly_payment(rest) if data.is_investor else 0.0

    price_per_m2 = prop.price_per_m2 or DEFAULT_PRICE_PER_M2
    green = green_value_estimate(current["label"], target["label"], surface, price_per_m2,
                                 kind_of(prop.building_type), department(prop.insee_code, prop.postcode))
    ban = rental_ban_date(current["label"], final_before, prop.postcode)
    new_ban = rental_ban_date(target["label"], final_after, prop.postcode)

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
        "cost_low": cost_low,
        "cost_high": cost_high,
        "detailed_costs": detailed_costs,
        "duration_days": duration,
        "subsidies": aids["mpr"],
        "cee_est": aids["cee"],
        "aid_pathway": aids["pathway"],
        "aid_notes": aids["notes"],
        "aid_blockers": aids["blockers"],
        "aid_per_work": aids["per_work"],
        "aid_rules": RULES_LABEL,
        "income_profile": profile.value,
        "rest_to_pay": rest,
        "rest_to_pay_low": rest_low,
        "rest_to_pay_high": rest_high,
        "eco_ptz_limit": eco_ptz_limit,
        "eco_ptz_amount": eco_ptz_amount,
        "eco_ptz_months": eco_ptz_months if eco_ptz_amount else 0,
        "eco_ptz_monthly": eco_ptz_amount / eco_ptz_months if eco_ptz_amount else 0.0,
        "heating_energy": energy,
        "initial_final_consumption": final_before,
        "new_final_consumption": final_after,
        "annual_bill_before": bill_before,
        "annual_bill_after": bill_after,
        "annual_savings": savings,
        "heating_need_reduction": env.heating_reduction(work_ids),
        "loss_shares": env.shares(),
        # None when the works bring no bill saving
        "roi_years": (rest - tax_benefit) / savings if savings > 0 else None,
        "latent_gain": green["value"],
        "latent_gain_low": green["low"],
        "latent_gain_high": green["high"],
        "green_value_method": green["method"],
        "green_value_basis": green["basis"],
        "green_value_premium_pct": green.get("premium_pct"),
        "price_per_m2_used": price_per_m2,
        "tax_benefit": tax_benefit,
        "net_investor_cost": rest - tax_benefit,
        "yield_brut": yield_brut,
        "cashflow": cashflow,
        "ban_date": ban.isoformat() if ban else None,
        "new_ban_date": new_ban.isoformat() if new_ban else None,
        "rental_status": rental_status(ban),
        "new_rental_status": rental_status(new_ban),
        "has_iti": any(w["id"] == "iti" for w in works),
    }


def single_work_effects(data: SimulationInput) -> Dict[str, Dict[str, float]]:
    """Effect of each selected work on its own: primary consumption and bill
    saving. Used by the report to explain what each work brings."""
    prop = data.property
    energy = normalize_energy(prop.heating_energy)
    base = projected_performance(prop, [])
    bill_before = _total(base["balance"]["before"], ENERGY_PRICES_EUR_KWH) * prop.surface
    effects = {}
    for work in dict.fromkeys(data.works):
        if work not in WORKS_BY_ID:
            continue
        perf = projected_performance(prop, [work])
        bill_after = _total(perf["balance"]["after"], ENERGY_PRICES_EUR_KWH) * prop.surface
        effects[work] = {
            "cep_saved": max(0.0, prop.initial_cep - perf["new_cep"]),
            "bill_saving": max(0.0, bill_before - bill_after),
            "heating_need_reduction": perf["envelope"].heating_reduction([work]),
        }
    return effects


# --- Work suggestions ---

def suggest_works(prop: SimulationProperty, label: Optional[str]) -> Dict[str, List[str]]:
    """Works to suggest for this dwelling, and a default selection aiming at
    class C (or D for a G), computed with the simulation model."""
    house = is_house(prop.building_type)
    energy = normalize_energy(prop.heating_energy)
    env = build_envelope(prop)
    shares = env.shares()
    label = label or "G"
    poor_label = label in ("E", "F", "G")

    suggested = set()
    if shares["walls"] >= 0.18 and env.u["walls"] > 0.45:
        suggested.add("iti")
    # Roof: houses, and flats whose DPE puts most losses through the roof (top floor)
    if (house or shares["roof"] >= 0.35) and shares["roof"] >= 0.10 and env.u["roof"] > 0.3:
        suggested.add("roof")
    if house and shares["floor"] >= 0.08 and env.u["floor"] > 0.5:
        suggested.add("floor_ceiling")
    if env.u["windows"] > 2.0:
        suggested.add("windows")
    if shares["air"] >= 0.20 and env.period <= 2:
        suggested.add("vmc")
    # Heating: heat pump for houses heated with fossil fuels; electric heating
    # and a thermodynamic water heater for electric dwellings, and for flats
    # heated with fossil fuels (GHG emissions often make the label)
    if house and energy in ("gas", "oil") and poor_label:
        suggested.add("pac_air_eau")
    if poor_label and (energy == "electricity" or (not house and energy in ("gas", "oil"))):
        suggested.update({"heating", "ecs"})

    # Default selection: the works that bring the label down the most (both
    # consumption and emissions count), one at a time, until class C (D for a G)
    preselected: List[str] = []
    if poor_label or label == "D":
        ges = prop.ges_value or 20
        thresholds, _ = calibrated_thresholds(prop.surface, prop.initial_cep, ges, prop.official_label or label, prop.dpe_date)
        target = LABELS.index("D" if label == "G" else "C")

        def score(works: List[str]) -> Tuple[int, float]:
            perf = projected_performance(prop, works)
            return LABELS.index(get_labels(perf["new_cep"], perf["new_ges"], thresholds)["label"]), perf["new_cep"]

        current = score([])
        while current[0] > target:
            options = [(score(preselected + [w]), w) for w in sorted(suggested) if w not in preselected]
            if not options:
                break
            best, work = min(options)
            if best >= current:
                break
            preselected.append(work)
            current = best

    return {
        "suggested": [w["id"] for w in WORKS_CATALOG if w["id"] in suggested],
        "preselected": preselected,
    }
