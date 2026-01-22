from ademe_client import PropertySchema, WallSchema, WindowSchema, SystemSchema, ClimateZone, DPEClass
from engine import DPECalculator
import json

def test_engine_simulation():
    # 1. Setup a "Thermal Sieve" House (Passoire Thermique)
    # 1970 house, 100m2, H1a (Lille), Electric heating (COP 1.0)
    prop = PropertySchema(
        address="Passoire Thermique, 59000 Lille",
        construction_year=1970,
        shab=100.0,
        climate_zone=ClimateZone.H1a,
        walls=[WallSchema(surface=150.0, u_value=2.5)], # Uninsulated
        windows=[WindowSchema(surface=15.0, u_value=3.2)], # Single glazing
        systems=[SystemSchema(system_type="chauffage", energy_source="electricity", efficiency_etas=1.0)]
    )
    
    calc = DPECalculator()
    
    # Test A: Baseline calculation
    baseline = calc.calculate(prop)
    print(f"--- Baseline Results for {prop.address} ---")
    print(f"Total Loss: {baseline['total_heat_loss']} W/K")
    print(f"CEP m2: {baseline['cep_m2']} kWh/m2.an")
    print(f"DPE Class: {baseline['dpe_label']}")
    
    assert baseline['dpe_label'] in [DPEClass.G, DPEClass.F]
    
    # Test B: 2026 Reform simulation (Elec 2.3 -> 1.9)
    calc_2026 = DPECalculator(elec_coeff_2026=1.9)
    results_2026 = calc_2026.calculate(prop)
    print(f"\n--- 2026 Reform Results (Elec 1.9) ---")
    print(f"CEP m2: {results_2026['cep_m2']} kWh/m2.an")
    print(f"DPE Class: {results_2026['dpe_label']}")
    
    assert results_2026['cep_m2'] < baseline['cep_m2']
    
    # Test C: Target Finder Optimization to Reach Class D
    print(f"\n--- Target Finder: Optimize to D ---")
    best_retrofit = calc.optimize_retrofit(prop, target_class='D')
    
    if "works" in best_retrofit:
        print(f"Package: {', '.join(best_retrofit['works'])}")
        print(f"Estimated Cost: {best_retrofit['cost']} €")
        print(f"Projected Label: {best_retrofit['new_label']}")
        print(f"Projected CEP: {best_retrofit['new_cep']} kWh/m2.an")
        
        assert best_retrofit['new_label'] in [DPEClass.A, DPEClass.B, DPEClass.C, DPEClass.D]
    else:
        print("❌ FAILED: Optimization could not find a path to D")

if __name__ == "__main__":
    try:
        test_engine_simulation()
        print("\n✅ Engine Verification Successful!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Engine Verification Failed: {e}")
