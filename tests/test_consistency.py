"""Cases a craftsman, an agent or a France Rénov' adviser would spot at once
(review of 10/10/2026): works already done proposed again, heating systems
that do not fit the dwelling, wrong éco-PTZ ceilings, rental rules shown to
an owner-occupier, expired DPE."""
from datetime import date

import pytest

from api.report_content import dpe_validity, pathway_label, regulatory
from api.simulation import (SimulationInput, SimulationProperty, available_works, normalize_energy, simulate,
                            suggest_works)

HOUSE = {"surface": 90, "initial_cep": 380, "ges_value": 80, "building_type": "Maison", "postcode": "62000",
         "construction_year": 1965, "heating_energy": "Gaz naturel", "official_label": "F"}
FLAT = {"surface": 60, "initial_cep": 380, "ges_value": 80, "building_type": "Appartement", "postcode": "59000",
        "construction_year": 1965, "heating_energy": "Gaz naturel", "official_label": "F"}


def prop(base, **kw):
    return SimulationProperty(**{**base, **kw})


def works_of(p):
    return set(available_works(p)["works"])


def test_existing_equipment_is_not_proposed_again():
    p = prop(HOUSE, heating_energy="Électricité", heating_generator="PAC air/eau installée après 2015",
             hot_water_system="Chauffe-eau thermodynamique sur air extérieur", ventilation="VMC SF Hygro B après 2012")
    w = works_of(p)
    assert not {"pac_air_eau", "heating", "ecs", "vmc"} & w
    s = suggest_works(p, "F")
    assert not {"pac_air_eau", "heating", "ecs", "vmc"} & set(s["suggested"] + s["preselected"])


def test_heat_pump_only_for_a_boiler_and_never_with_radiators():
    assert "pac_air_eau" in works_of(prop(HOUSE))
    # Electric convectors: no water circuit for a heat pump, inertia radiators instead
    convectors = prop(HOUSE, heating_energy="Électricité", heating_generator="Convecteur électrique NFC")
    assert "pac_air_eau" not in works_of(convectors) and "heating" in works_of(convectors)
    # Electric boiler: the heat pump uses its radiators
    boiler = prop(HOUSE, heating_energy="Électricité", heating_generator="Chaudière électrique")
    assert "pac_air_eau" in works_of(boiler) and "heating" not in works_of(boiler)
    # District heating and wood: no heat pump
    assert "pac_air_eau" not in works_of(prop(HOUSE, heating_energy="Réseau de Chauffage urbain"))
    assert "pac_air_eau" not in works_of(prop(HOUSE, heating_energy="Bois – Bûches"))
    # Never both in the default selection
    for p in (prop(HOUSE), convectors, boiler):
        sel = suggest_works(p, "F")["preselected"]
        assert not {"pac_air_eau", "heating"} <= set(sel)


def test_collective_heating_gets_no_individual_system():
    p = prop(FLAT, heating_installation="Installation de chauffage collectif",
             hot_water_installation="Installation d'ECS collective")
    assert not {"pac_air_eau", "heating", "ecs"} & works_of(p)


def test_gas_flat_radiators_only_when_they_improve_the_label():
    p = prop(FLAT)
    sel = suggest_works(p, "F")
    assert "heating" not in sel["suggested"]
    if "heating" in sel["preselected"]:
        base = simulate(SimulationInput(property=p, works=[w for w in sel["preselected"] if w != "heating"]))
        full = simulate(SimulationInput(property=p, works=sel["preselected"]))
        assert "ABCDEFG".index(full["new_label"]) < "ABCDEFG".index(base["new_label"])


def test_unknown_energy_is_read_from_the_generator_and_never_guessed():
    assert normalize_energy(None, "PAC air/eau installée après 2015") == "electricity"
    assert normalize_energy(None, "Chaudière gaz à condensation") == "gas"
    unknown = prop(HOUSE, heating_energy=None)
    assert not available_works(unknown)["systems"]


def test_hot_water_has_its_own_energy():
    # Gas heating, electric tank: hot water billed as electricity
    gas_only = simulate(SimulationInput(property=prop(HOUSE)))
    tank = simulate(SimulationInput(property=prop(HOUSE, hot_water_system="Ballon électrique à accumulation vertical")))
    assert tank["annual_bill_before"] > gas_only["annual_bill_before"]


def test_eco_ptz_counts_each_eligible_action():
    def limit(works):
        return simulate(SimulationInput(property=prop(HOUSE, initial_cep=200, official_label="D"),
                                        works=works, income_level="superieur"))["eco_ptz_limit"]
    assert limit(["iti", "roof", "floor_ceiling"]) == 30000
    assert limit(["iti", "roof"]) == 25000
    assert limit(["windows"]) == 7000
    assert limit(["vmc"]) == 0
    assert limit(["heating"]) == 0


def test_rental_rules_for_an_owner_occupier():
    sim = {"current_label": "G", "rental_status": "Location interdite depuis le 01/01/2025",
           "new_rental_status": "Louable sans limite de date"}
    occupant = {i["label"]: i["value"] for i in regulatory(sim, True, None, "62000", is_investor=False)["items"]}
    assert "Loyer" not in occupant and "Si vous mettez en location" in occupant
    investor = {i["label"]: i["value"] for i in regulatory(sim, True, None, "62000", is_investor=True)["items"]}
    assert "Loyer" in investor and "Location aujourd'hui" in investor
    # Sale audit: houses and single-owner buildings, not flats
    flat = {i["label"] for i in regulatory(sim, False, None, "62000", building_type="Appartement")["items"]}
    building = {i["label"] for i in regulatory(sim, False, None, "62000", building_type="Immeuble")["items"]}
    assert "Vente" not in flat and "Vente" in building


def test_dpe_validity():
    today = date(2026, 10, 10)
    assert dpe_validity(date(2019, 5, 2), today).startswith("Périmé")
    assert dpe_validity(date(2021, 7, 31), today) == "Jusqu'au 31/07/2031"
    assert dpe_validity(date(2024, 2, 29), today) == "Jusqu'au 28/02/2034"


@pytest.mark.parametrize("mpr,cee,expected", [(3000, 3200, "MaPrimeRénov' par geste et primes CEE"),
                                              (0, 3200, "primes CEE"), (3000, 0, "MaPrimeRénov' par geste"),
                                              (0, 0, "aucune aide")])
def test_pathway_label_names_the_aids_counted(mpr, cee, expected):
    assert pathway_label({"aid_pathway": "geste" if mpr or cee else "none", "subsidies": mpr, "cee_est": cee}) == expected


def test_bill_uses_the_dpe_consumption_per_usage():
    """Live case (Dainville): the typical split put 75 % of the consumption on
    heating and billed the electric tank as gas; the DPE gives each usage."""
    dpe = prop(HOUSE, surface=93.7, initial_cep=360, ges_value=69, final_consumption=330,
               hot_water_energy="Électricité", usage_consumption={"heating": 27860.2, "hot_water": 2097.9, "other": 991.6})
    sim = simulate(SimulationInput(property=dpe))
    # 27 860 kWh of gas at 0.11 € + 3 090 kWh of electricity at 0.20 €
    assert sim["annual_bill_before"] == pytest.approx(27860.2 * 0.11 + (2097.9 + 991.6) * 0.20, rel=1e-6)


def test_narrative_amounts_get_the_thousands_space():
    from api.ai_service import thousands
    assert thousands("estimée à 3680 € par an, de 7400 à 10 900 €") == "estimée à 3 680 € par an, de 7 400 à 10 900 €"
    # Years and consumptions below 1 000 stay as they are
    assert thousands("construite entre 1948 et 1974, après 2015, 360 kWh") == "construite entre 1948 et 1974, après 2015, 360 kWh"
