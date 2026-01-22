import logging
import copy
from typing import Dict, List, Optional, Any
from api.ademe_client import PropertySchema, WallSchema, WindowSchema, SystemSchema, ClimateZone, DPEClass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Physical Constants ---

CLIMATE_DATA = {
    "H1a": 2800,
    "H1b": 2900,
    "H1c": 3000,
    "H2a": 2400,
    "H2b": 2200,
    "H2c": 2500,
    "H2d": 2600,
    "H3": 1900,
}

# Conversion factors (Final to Primary)
# Based on 3CL-2021 and future 2026 reform
ENERGY_CONVERSION = {
    "electricity": 2.3, # Current standard
    "gas": 1.0,
    "oil": 1.0,
    "wood": 1.0,
    "district_heating": 1.0,
}

# DPE Thresholds (kWh/m².year primary energy)
DPE_THRESHOLDS = [
    (70, DPEClass.A),
    (110, DPEClass.B),
    (180, DPEClass.C),
    (250, DPEClass.D),
    (330, DPEClass.E),
    (420, DPEClass.F),
    (float('inf'), DPEClass.G)
]

# --- Physics Classes ---

class BuildingPhysics:
    @staticmethod
    def calc_heat_loss_walls(area: float, u_value: float, b_coef: float = 1.0) -> float:
        """D = U * A * b (W/K)"""
        return u_value * area * b_coef

    @staticmethod
    def calc_heat_loss_windows(area: float, u_value: float, b_coef: float = 1.0) -> float:
        """D = U * A * b (W/K)"""
        return u_value * area * b_coef

    @staticmethod
    def calc_heat_loss_ventilation(shab: float, hsp: float = 2.5, ventilation_type: str = "standard") -> float:
        """
        Simplified ventilation loss (D_vent = 0.34 * Q_vent).
        Standard assumption: 0.6 volumes/hour for single flux.
        """
        volume = shab * hsp
        if ventilation_type == "vmc_sf_auto":
            air_change_rate = 0.5
        elif ventilation_type == "vmc_df":
            air_change_rate = 0.2 # Heat recovery
        else:
            air_change_rate = 0.7 # Natural or leaky
            
        flow_rate = volume * air_change_rate
        return 0.34 * flow_rate

class EnergyConsumption:
    @staticmethod
    def calc_heating_needs(total_heat_loss: float, dju: int, intermittency_factor: float = 0.8) -> float:
        """
        Q = D * DJU * 24 / 1000 (kWh/year)
        Applying intermittency (reduction for vacancy/night set-back).
        """
        return (total_heat_loss * dju * 24 / 1000) * intermittency_factor

    @staticmethod
    def calc_final_energy(needs: float, system_efficiency: float) -> float:
        """Conso Finale (kWh ef/year)"""
        return needs / system_efficiency

    @staticmethod
    def calc_primary_energy(final_energy: float, energy_type: str, elec_coeff_2026: Optional[float] = None) -> float:
        """Conso Primaire (kWh ep/year)"""
        factor = ENERGY_CONVERSION.get(energy_type.lower(), 1.0)
        
        # Apply 2026 reform parameter if heating is electric
        if energy_type.lower() == "electricity" and elec_coeff_2026 is not None:
            factor = elec_coeff_2026
            
        return final_energy * factor

# --- Orchestrator ---

class DPECalculator:
    def __init__(self, elec_coeff_2026: Optional[float] = None):
        self.elec_coeff_2026 = elec_coeff_2026
        self.physics = BuildingPhysics()
        self.consumption = EnergyConsumption()

    def get_dpe_class(self, cep_m2: float) -> DPEClass:
        for threshold, dpe_class in DPE_THRESHOLDS:
            if cep_m2 <= threshold:
                return dpe_class
        return DPEClass.G

    def calculate(self, prop: PropertySchema) -> Dict[str, Any]:
        # 1. Get DJU
        dju = CLIMATE_DATA.get(prop.climate_zone, 2500) # Fallback to national median

        # 2. Total Heat Loss
        total_loss = 0.0
        for wall in prop.walls:
            total_loss += self.physics.calc_heat_loss_walls(wall.surface, wall.u_value or 1.5)
        
        for window in prop.windows:
            total_loss += self.physics.calc_heat_loss_windows(window.surface, window.u_value or 3.0)
            
        # Add ventilation loss (assuming 2.5m ceiling)
        total_loss += self.physics.calc_heat_loss_ventilation(prop.shab)

        # 3. Heating Needs
        needs = self.consumption.calc_heating_needs(total_loss, dju)

        # 4. Final & Primary Energy
        # We simplify to 1 main heating system for the demo
        if prop.systems:
            main_sys = prop.systems[0]
            efficiency = main_sys.efficiency_etas or 0.8 # Standard boiler
            energy_type = main_sys.energy_source or "gas"
        else:
            efficiency = 0.8
            energy_type = "gas"

        ef = self.consumption.calc_final_energy(needs, efficiency)
        ep = self.consumption.calc_primary_energy(ef, energy_type, self.elec_coeff_2026)
        
        cep_m2 = ep / prop.shab if prop.shab > 0 else 0

        return {
            "total_heat_loss": round(total_loss, 2),
            "heating_needs": round(needs, 2),
            "final_energy": round(ef, 2),
            "primary_energy": round(ep, 2),
            "cep_m2": round(cep_m2, 2),
            "dpe_label": self.get_dpe_class(cep_m2)
        }

    def optimize_retrofit(self, prop: PropertySchema, target_class: str = 'D') -> Dict[str, Any]:
        """
        Logique Target Finder:
        Simulates packages of work to find the cheapest way to reach target.
        """
        # Define Possible Works
        works_catalog = [
            {"name": "Isolation Murs (ITE)", "u_new": 0.25, "cost": 150, "unit": "m2_wall", "category": "wall"},
            {"name": "Nouveaux Vitrages (Double)", "u_new": 1.1, "cost": 400, "unit": "m2_win", "category": "window"},
            {"name": "Pompe à Chaleur (PAC)", "eff_new": 3.5, "energy_new": "electricity", "cost": 12000, "unit": "flat", "category": "system"}
        ]

        def get_total_cost(works_list, property_ref):
            total = 0
            for w in works_list:
                if w["unit"] == "m2_wall":
                    surface = sum(wall.surface for wall in property_ref.walls)
                    total += surface * w["cost"]
                elif w["unit"] == "m2_win":
                    surface = sum(win.surface for win in property_ref.windows)
                    total += surface * w["cost"]
                elif w["unit"] == "flat":
                    total += w["cost"]
            return total

        best_combo = None
        min_cost = float('inf')

        # Bruteforce simple combinations (1, 2 or all 3)
        # In a real app, this would be more sophisticated (branch & bound)
        import itertools
        for r in range(1, len(works_catalog) + 1):
            for combo in itertools.combinations(works_catalog, r):
                # Deep copy property to simulate
                sim_prop = copy.deepcopy(prop)
                for work in combo:
                    if work["category"] == "wall":
                        for wall in sim_prop.walls:
                            wall.u_value = work["u_new"]
                    elif work["category"] == "window":
                        for win in sim_prop.windows:
                            win.u_value = work["u_new"]
                    elif work["category"] == "system":
                        sim_prop.systems = [SystemSchema(
                            system_type="chauffage",
                            energy_source=work["energy_new"],
                            efficiency_etas=work["eff_new"]
                        )]
                
                res = self.calculate(sim_prop)
                cost = get_total_cost(combo, prop)
                
                # Check if target reached
                current_label = res["dpe_label"].value
                target_label = DPEClass(target_class).value
                
                # DPE labels are A < B < C... so 'D' is value 'D'
                # We compare order: A=1, B=2, C=3, D=4
                label_order = {v.value: i for i, v in enumerate(DPEClass)}
                if label_order[current_label] <= label_order[target_class]:
                    if cost < min_cost:
                        min_cost = cost
                        best_combo = {
                            "works": [w["name"] for w in combo],
                            "cost": cost,
                            "new_label": res["dpe_label"],
                            "new_cep": res["cep_m2"]
                        }

        return best_combo or {"message": "Cible impossible avec ces travaux", "cost": 0}

# Example Usage (Commented)
# if __name__ == "__main__":
#    calc = DPECalculator()
#    # Load a property via connector and then run calc.calculate(prop)
