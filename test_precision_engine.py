import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'api'))

from ademe_client import PropertySchema, WallSchema, SystemSchema
from engine import DPECalculator

def test_engine_precision():
    engine = DPECalculator()
    
    # 1. Base Property
    prop = PropertySchema(
        address="Test Precision",
        shab=100.0,
        walls=[WallSchema(surface=100.0, u_value=2.5)],
        windows=[],
        systems=[SystemSchema(system_type="chauffage", energy_source="gas", efficiency_etas=0.8)],
        climate_zone="H1a"
    )
    
    # 2. Base Simulation (Standard)
    res_base = engine.simulate_retrofit(prop, ["ite_pse"], 25000, "59000", params={})
    cost_base = res_base['total_cost']
    print(f"Base Cost (ITE PSE, 100m2): {cost_base} €")
    
    # 3. Test INSEE Index (BT01 = 150 vs base 120)
    res_insee = engine.simulate_retrofit(prop, ["ite_pse"], 25000, "59000", params={"index_insee": 150.0})
    cost_insee = res_insee['total_cost']
    # Ratio 150/120 = 1.25
    print(f"Cost with Index 150: {cost_insee} € (Expected ~{cost_base * 1.25})")
    
    # 4. Test Floors (Etage 2, No elevator = +10%)
    res_floors = engine.simulate_retrofit(prop, ["ite_pse"], 25000, "59000", params={"nb_etages": 2, "has_ascenseur": False})
    cost_floors = res_floors['total_cost']
    print(f"Cost with 2 Floors (no elevator): {cost_floors} € (Expected ~{cost_base * 1.10})")
    
    # 5. Test Urban Zone (+10% + parking)
    res_urban = engine.simulate_retrofit(prop, ["ite_pse"], 25000, "59000", params={"is_urban_dense": True, "parking_cost": 50, "chantier_duration": 10})
    cost_urban = res_urban['total_cost']
    # +10% + 500 parking
    print(f"Cost Urban Dense + Parking: {cost_urban} € (Expected ~{cost_base * 1.10 + 500})")

if __name__ == "__main__":
    test_engine_precision()
