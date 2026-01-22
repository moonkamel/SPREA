from ademe_client import AdemeConnector, ClimateZone, DPEClass
import json

def test_mapping_and_fallback():
    connector = AdemeConnector()
    
    # Mock raw ADEME data with official OpenAPI field names
    mock_raw = {
        "numero_dpe": "2134E1234567A",
        "adresse_brut": "123 Rue de la Paix, 75002 Paris",
        "annee_construction": 1970,
        "surface_habitable_logement": 85.5,
        "zone_climatique": "H1a",
        "etiquette_dpe": "D",
        "etiquette_ges": "C",
        "_geopoint": [48.86, 2.33], # [lat, lon]
        "surface_murs_exterieurs": None, # Should trigger estimation ratio
        "u_murs_exterieurs": None,     # Should trigger fallback
        "surface_baies_vitrees": 15.0,
        "u_baies_vitrees": 1.4,
        "type_energie_principale_chauffage": "Électricité",
        "type_batiment": "Maison"
    }
    
    mapped = connector._map_to_internal(mock_raw)
    
    print(f"Testing mapping for {mapped.address}...")
    
    # Assertions
    assert mapped.ademe_dpe_number == "2134E1234567A"
    assert mapped.shab == 85.5
    assert mapped.climate_zone == ClimateZone.H1a
    assert mapped.dpe_class_current == DPEClass.D
    assert mapped.is_estimated is True # Because u_murs and surface_murs were None
    assert mapped.latitude == 48.86
    assert mapped.longitude == 2.33
    
    # Wall fallback check (Year 1970 < 1974 => U=2.5)
    # Surface estimation (House ratio 1.5 * SHAB 85.5 = 128.25)
    assert len(mapped.walls) == 1
    assert mapped.walls[0].u_value == 2.5
    assert mapped.walls[0].surface == 128.25
    
    # Window check
    assert len(mapped.windows) == 1
    assert mapped.windows[0].u_value == 1.4
    
    # System check
    assert len(mapped.systems) == 1
    assert mapped.systems[0].energy_source == "Électricité"
    
    print("✅ All mapping and fallback tests passed!")

if __name__ == "__main__":
    try:
        test_mapping_and_fallback()
    except Exception as e:
        print(f"❌ Test failed: {e}")
