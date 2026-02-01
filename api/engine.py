import logging
import copy
import math
from typing import Dict, List, Optional, Any
from enum import Enum
try:
    from api.ademe_client import PropertySchema, WallSchema, WindowSchema, SystemSchema, ClimateZone, DPEClass
except ImportError:
    from ademe_client import PropertySchema, WallSchema, WindowSchema, SystemSchema, ClimateZone, DPEClass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 2025 Reference Data ---

CLIMATE_DATA = {
    "H1a": 2800, "H1b": 2900, "H1c": 3000,
    "H2a": 2400, "H2b": 2200, "H2c": 2500, "H2d": 2600,
    "H3": 1900,
}

ENERGY_CONVERSION = {
    "electricity": 2.3,  # Millésime 2025 standard
    "gas": 1.0,
    "oil": 1.0,
    "wood": 1.0,
    "district_heating": 1.0,
}

DPE_THRESHOLDS = [
    (70, DPEClass.A), (110, DPEClass.B), (180, DPEClass.C),
    (250, DPEClass.D), (330, DPEClass.E), (420, DPEClass.F),
    (float('inf'), DPEClass.G)
]

K_REGION = {
    "75": 1.30, "92": 1.30, "93": 1.30, "94": 1.30,  # Paris & Petite Couronne
    "77": 1.15, "91": 1.15, "78": 1.15, "95": 1.15,  # Grande Couronne
    "69": 1.12, "74": 1.12, "01": 1.12,              # AURA (Lyon, Annecy)
    "06": 1.15, "83": 1.15, "13": 1.08,              # PACA
    "33": 1.05, "44": 1.05, "35": 1.05,              # Atlantique
    "67": 1.05,                                      # Grand Est
    "59": 1.00, "62": 1.00, "80": 1.00,              # Nord
    "2A": 1.20, "2B": 1.20,                          # Corse
    "971": 1.35, "972": 1.35, "973": 1.35, "974": 1.35, "976": 1.35, # DOM
}

DEFAULT_K_REGION = 1.00
K_LOGISTIQUE = {
    "urbain_dense": 1.15,
    "pavillonnaire": 1.00,
    "rural_isole": 1.05
}

class ResourceProfile(str, Enum):
    BLEU = "Très Modeste"
    JAUNE = "Modeste"
    VIOLET = "Intermédiaire"
    ROSE = "Supérieur"

# Simplified ANAH Plafonds 2025 (Hauts-de-France / Province basis)
ANAH_PLAFONDS_PROVINCE = {
    ResourceProfile.BLEU: 17000,
    ResourceProfile.JAUNE: 22000,
    ResourceProfile.VIOLET: 30000,
}

# --- Calculation Classes ---

class GeographicWeighting:
    @staticmethod
    def get_localized_cost(base_cost: float, postcode: str, typo: str = "pavillonnaire") -> float:
        dept = postcode[:2] if postcode else "59"
        k_reg = K_REGION.get(dept, DEFAULT_K_REGION)
        k_log = K_LOGISTIQUE.get(typo, 1.00)
        return base_cost * k_reg * k_log

class MaPrimeRenov2025:
    @staticmethod
    def get_profile(rfr: float, occupants: int = 1) -> ResourceProfile:
        # Scale thresholds roughly based on occupants (demo logic)
        multiplier = 1 + (occupants - 1) * 0.5
        if rfr <= ANAH_PLAFONDS_PROVINCE[ResourceProfile.BLEU] * multiplier:
            return ResourceProfile.BLEU
        if rfr <= ANAH_PLAFONDS_PROVINCE[ResourceProfile.JAUNE] * multiplier:
            return ResourceProfile.JAUNE
        if rfr <= ANAH_PLAFONDS_PROVINCE[ResourceProfile.VIOLET] * multiplier:
            return ResourceProfile.VIOLET
        return ResourceProfile.ROSE

    @staticmethod
    def calc_subsidies(total_ht: float, profile: ResourceProfile, class_gain: int) -> float:
        """Parcours Accompagné 2025 logic."""
        if class_gain < 2: return 0.0
        
        # Max works amount for Accompanied Pathway (gain 4 classes = 70k)
        max_works = 70000 if class_gain >= 4 else (40000 if class_gain >= 2 else 0)
        eligible_base = min(total_ht, max_works)
        
        rates = {
            ResourceProfile.BLEU: 0.90,
            ResourceProfile.JAUNE: 0.80,
            ResourceProfile.VIOLET: 0.60,
            ResourceProfile.ROSE: 0.35
        }
        return eligible_base * rates[profile]

class BuildingPhysics:
    @staticmethod
    def calc_heat_loss_ventilation(shab: float, hsp: float = 2.5, ventilation_type: str = "standard") -> float:
        volume = shab * hsp
        rates = {"vmc_sf_hygro_b": 0.4, "vmc_df": 0.15, "standard": 0.6}
        flow_rate = volume * rates.get(ventilation_type, 0.6)
        return 0.34 * flow_rate

class DPECalculator:
    def __init__(self):
        self.physics = BuildingPhysics()
        self.geo = GeographicWeighting()

    def get_dpe_class(self, cep_m2: float) -> DPEClass:
        for threshold, dpe_class in DPE_THRESHOLDS:
            if cep_m2 <= threshold: return dpe_class
        return DPEClass.G

    def calculate(self, prop: PropertySchema) -> Dict[str, Any]:
        dju = CLIMATE_DATA.get(prop.climate_zone, 2500)
        
        wall_loss = sum(w.surface * (w.u_value or 2.5) for w in prop.walls)
        window_loss = sum(win.surface * (win.u_value or 3.5) for win in prop.windows)
        vent_loss = self.physics.calc_heat_loss_ventilation(prop.shab)
        
        total_loss = wall_loss + window_loss + vent_loss

        needs = (total_loss * dju * 24 / 1000) * 0.85 # Intermittency
        
        main_sys = prop.systems[0] if prop.systems else None
        eff = (main_sys.efficiency_etas or 0.8) if main_sys else 0.8
        energy = (main_sys.energy_source or "gas").lower() if main_sys else "gas"
        
        ef = needs / eff
        ep = ef * ENERGY_CONVERSION.get(energy, 1.0)
        cep_m2 = ep / prop.shab if prop.shab > 0 else 0

        return {
            "cep_m2": round(cep_m2, 2),
            "dpe_label": self.get_dpe_class(cep_m2),
            "total_loss": round(total_loss, 2),
            "loss_breakdown": {
                "walls": round(wall_loss, 2),
                "windows": round(window_loss, 2),
                "ventilation": round(vent_loss, 2)
            }
        }

    def get_recommendations(self, prop: PropertySchema) -> List[Dict[str, Any]]:
        """Identify best works based on losses and potential gain, prioritizing ROI and respect for property type."""
        res = self.calculate(prop)
        breakdown = res["loss_breakdown"]
        dpe = res["dpe_label"]
        type_bat = (prop.building_type or "Maison").lower()
        is_house = "maison" in type_bat
        
        recos = []
        
        # Priority 1: Insulation (Cheapest gain)
        # HOUSE ONLY: Attic insulation is a classic individual house gain.
        if is_house:
            recos.append({
                "id": "combles",
                "name": "Isolation des Combles",
                "reason": "Le geste le plus rentable pour une maison individuelle afin de gagner rapidement en performance.",
                "suggested": True
            })
        
        # Priority 2: Walls (ITI for apartments, ITI or ITE for houses)
        # We suggest ITI by default as it's private.
        if breakdown["walls"] > 50: # Major loss
            recos.append({
                "id": "iti_ossature",
                "name": "Isolation des Murs (ITI)",
                "reason": "Réduction des déperditions par l'intérieur, idéal pour un contrôle total sans accord de copropriété." if not is_house else "Solution rapide et efficace pour isoler les murs.",
                "suggested": True
            })
        
        # Priority 3: Windows
        if breakdown["windows"] > breakdown["walls"] * 0.3:
            recos.append({
                "id": "windows_pvc",
                "name": "Menuiseries PVC",
                "reason": "Remplacement des fenêtres pour supprimer l'effet paroi froide et améliorer l'étanchéité.",
                "suggested": True
            })
            
        # Priority 4: Efficient Heating (if G/F)
        # For apartments, collective heating is tricky, but individual PAC is possible sometimes.
        # For houses, PAC is the way to go.
        if dpe in [DPEClass.G, DPEClass.F]:
            heating_reason = "Indispensable pour décarboner et sortir durablement de l'état de passoire."
            if not is_house:
                heating_reason = "Amélioration du système de chauffage individuel pour une meilleure efficacité énergétique."
                
            recos.append({
                "id": "pac_air_eau",
                "name": "PAC Air/Eau",
                "reason": heating_reason,
                "suggested": True
            })
            
        return recos

    def simulate_retrofit(self, prop: PropertySchema, selections: List[str], rfr: float, postcode: str, **kwargs) -> Dict[str, Any]:
        works_catalog = {
            "ite_pse": {"name": "ITE PSE", "u_new": 0.25, "cost": 170, "unit": "m2_wall", "base_index": 120.0},
            "ite_bois": {"name": "ITE Fibre Bois", "u_new": 0.28, "cost": 220, "unit": "m2_wall", "base_index": 120.0},
            "iti_ossature": {"name": "ITI Ossature", "u_new": 0.30, "cost": 75, "unit": "m2_wall", "base_index": 115.0},
            "combles": {"name": "Isolation Combles", "u_new": 0.15, "cost": 32, "unit": "m2_comble", "base_index": 110.0},
            "pac_air_eau": {"name": "PAC Air/Eau", "eff_new": 3.5, "energy_new": "electricity", "cost": 12500, "unit": "flat", "base_index": 125.0},
            "windows_pvc": {"name": "Fenêtres PVC", "u_new": 1.3, "cost": 575, "unit": "unit_win", "base_index": 118.0}
        }

        sim_prop = copy.deepcopy(prop)
        total_cost = 0.0
        applied_names = []
        
        # 1. Technical Parameters Extraction
        extra_params = kwargs.get('params', {})
        current_insee = extra_params.get('index_insee', 1.0)
        nb_etages = extra_params.get('nb_etages', 0)
        has_ascenseur = extra_params.get('has_ascenseur', True)
        is_urban_dense = extra_params.get('is_urban_dense', False)
        parking_cost_day = extra_params.get('parking_cost', 0)
        duration_days = extra_params.get('chantier_duration', 5)

        # 2. Global Multipliers
        coeff_accessibilite = 1.0
        if nb_etages > 0 and not has_ascenseur:
            coeff_accessibilite += (nb_etages * 0.05) # +5% per floor
        
        if is_urban_dense:
            coeff_accessibilite += 0.10 # +10% for dense urban
            
        frais_logistiques = 0
        if is_urban_dense: # Simplified logic: if urban, parking is likely payant
             frais_logistiques += (duration_days * parking_cost_day)

        for key in selections:
            if key not in works_catalog: continue
            w = works_catalog[key]
            applied_names.append(w["name"])
            
            # 3. New Formula Logic
            # Price = (Base_Price * (Current_Index / Base_Index)) * Coeffs
            # If current_insee is 1.0 (demo mode), we skip index ratio or assume 1.0
            index_ratio = (current_insee / w["base_index"]) if current_insee > 20 else 1.0
            
            base_unit_cost = w["cost"]
            localized_unit_cost = self.geo.get_localized_cost(base_unit_cost, postcode)
            
            # Apply INSEE and Accessibility
            final_unit_cost = (localized_unit_cost * index_ratio) * coeff_accessibilite
            
            if w["unit"] == "m2_wall":
                surf = sum(wall.surface for wall in sim_prop.walls)
                total_cost += surf * final_unit_cost
                for wall in sim_prop.walls: wall.u_value = w["u_new"]
            elif w["unit"] == "m2_comble":
                surf = sim_prop.shab # Rough estimate
                total_cost += surf * final_unit_cost
            elif w["unit"] == "flat":
                total_cost += final_unit_cost
                sim_prop.systems = [SystemSchema(system_type="chauffage", energy_source=w["energy_new"], efficiency_etas=w["eff_new"])]
            elif w["unit"] == "unit_win":
                total_cost += 10 * final_unit_cost # Assume 10 windows
                for win in sim_prop.windows: win.u_value = w["u_new"]

        total_cost += frais_logistiques

        initial_res = self.calculate(prop)
        final_res = self.calculate(sim_prop)
        
        # Labels for class gain calc
        labels = [v.value for v in DPEClass]
        gain = labels.index(initial_res["dpe_label"]) - labels.index(final_res["dpe_label"])
        
        profile = MaPrimeRenov2025.get_profile(rfr)
        subsidies = MaPrimeRenov2025.calc_subsidies(total_cost, profile, gain)

        return {
            "initial_dpe": initial_res["dpe_label"],
            "new_dpe": final_res["dpe_label"],
            "initial_cep": initial_res["cep_m2"],
            "new_cep": final_res["cep_m2"],
            "total_cost": round(total_cost, 0),
            "subsidies": round(subsidies, 0),
            "rest_to_pay": round(total_cost - subsidies, 0),
            "gain_classes": max(0, gain),
            "applied_works": applied_names,
            "profile": profile.value
        }
