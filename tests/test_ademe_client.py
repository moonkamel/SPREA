from api.ademe_client import AdemeConnector, ClimateZone, DPEClass

RAW = {
    "numero_dpe": "2134E1234567A",
    "adresse_brut": "123 Rue de la Paix, 75002 Paris",
    "code_postal_ban": "75002",
    "annee_construction": 1970,
    "surface_habitable_logement": 85.5,
    "zone_climatique": "H1a",
    "etiquette_dpe": "D",
    "etiquette_ges": "C",
    "conso_5_usages_par_m2_ep": 240,
    "conso_5_usages_par_m2_ef": 126.3,
    "_geopoint": [48.86, 2.33],
    "surface_baies_vitrees": 15.0,
    "u_baies_vitrees": 1.4,
    "type_energie_principale_chauffage": "Électricité",
    "type_batiment": "Maison",
    "qualite_isolation_murs": "insuffisante",
    "qualite_isolation_menuiseries": "bonne",
}


def test_mapping():
    prop = AdemeConnector()._map_to_internal(RAW)
    assert prop.ademe_dpe_number == "2134E1234567A"
    assert prop.shab == 85.5
    assert prop.postcode == "75002"
    assert prop.climate_zone == ClimateZone.H1a
    assert prop.dpe_class_current == DPEClass.D
    assert prop.consumption_level == 240
    assert prop.final_consumption == 126.3
    assert (prop.latitude, prop.longitude) == (48.86, 2.33)
    assert prop.systems[0].energy_source == "Électricité"
    assert prop.insulation_quality["walls"] == "insuffisante"
    assert prop.insulation_quality["windows"] == "bonne"
    assert prop.insulation_quality["roof"] is None


def test_missing_values_are_estimated():
    prop = AdemeConnector()._map_to_internal(RAW)
    # 1970 < 1974: uninsulated wall U value, wall area from the house ratio (1.5 x surface)
    assert prop.is_estimated is True
    assert prop.walls[0].u_value == 2.5
    assert prop.walls[0].surface == 128.25
    # Older DPE without final consumption / loss breakdown
    old = AdemeConnector()._map_to_internal({k: v for k, v in RAW.items() if k != "conso_5_usages_par_m2_ef"})
    assert old.final_consumption is None
    assert old.dpe_losses is None


def test_dpe_losses_with_doors_counted_as_bridges():
    raw = dict(RAW, deperditions_murs=120, deperditions_planchers_hauts=90, deperditions_planchers_bas=40,
               deperditions_baies_vitrees=35, deperditions_renouvellement_air=60,
               deperditions_ponts_thermiques=20, deperditions_portes=5)
    prop = AdemeConnector()._map_to_internal(raw)
    assert prop.dpe_losses == {"walls": 120, "roof": 90, "floor": 40, "windows": 35, "air": 60, "bridges": 25}


def test_city_and_equipment_details():
    raw = {**RAW, "nom_commune_ban": "Paris", "code_insee_ban": "75102", "type_ventilation": "VMC simple flux autoréglable",
           "type_installation_chauffage": "installation individuelle", "cout_total_5_usages": 1234.6}
    prop = AdemeConnector()._map_to_internal(raw)
    assert prop.city == "Paris"
    assert prop.insee_code == "75102"
    assert prop.details["ventilation"] == "VMC simple flux autoréglable"
    assert prop.details["dpe_annual_cost"] == "1235"
    assert AdemeConnector()._map_to_internal(RAW).details["ventilation"] is None
