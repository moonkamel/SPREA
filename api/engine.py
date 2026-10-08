import logging
from typing import Dict, List, Optional, Any
try:
    from api.ademe_client import PropertySchema, DPEClass
except ImportError:
    from ademe_client import PropertySchema, DPEClass

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
    "electricity": 1.9,  # Coefficient DPE en vigueur depuis le 1er janvier 2026 (2.3 avant)
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
        energy = normalize_energy(main_sys.energy_source) if main_sys else "gas"
        
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
                "id": "roof",
                "name": "Isolation des Combles",
                "reason": "Le geste le plus rentable pour une maison individuelle afin de gagner rapidement en performance.",
                "suggested": True
            })
        
        # Priority 2: Walls (ITI for apartments, ITI or ITE for houses)
        # We suggest ITI by default as it's private.
        if breakdown["walls"] > 50: # Major loss
            recos.append({
                "id": "iti",
                "name": "Isolation des Murs (ITI)",
                "reason": "Réduction des déperditions par l'intérieur, idéal pour un contrôle total sans accord de copropriété." if not is_house else "Solution rapide et efficace pour isoler les murs.",
                "suggested": True
            })
        
        # Priority 3: Windows
        if breakdown["windows"] > breakdown["walls"] * 0.3:
            recos.append({
                "id": "windows",
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
                "id": "heating",
                "name": "Radiateur inertie",
                "reason": heating_reason,
                "suggested": True
            })
            
        return recos
