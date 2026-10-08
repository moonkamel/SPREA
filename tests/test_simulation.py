import pytest

from api.envelope import Envelope
from api.simulation import SimulationInput, SimulationProperty, rental_ban_date, simulate, suggest_works

HOUSE_1960 = {"surface": 80, "initial_cep": 380, "ges_value": 60, "building_type": "Maison", "postcode": "59000",
              "construction_year": 1960, "heating_energy": "Gaz naturel"}


def run(**kwargs):
    prop = dict(HOUSE_1960)
    prop.update(kwargs.pop("property", {}))
    return simulate(SimulationInput(property=prop, **kwargs))


def test_no_works_keeps_label_and_costs_nothing():
    res = run()
    assert res["current_label"] == res["new_label"] == "F"
    assert res["new_cep"] == pytest.approx(380)
    assert res["cost"] == 0 and res["rest_to_pay"] == 0


def test_cost_uses_envelope_geometry():
    # ITI on uninsulated 1960 walls: (85 + 15 preparation) EUR/m2 * wall area * 131/120
    res = run(works=["iti"])
    walls = Envelope(80, "Maison", 1960).wall_area
    assert res["cost"] == pytest.approx(100 * walls * 131 / 120)
    # Insulated walls (1995): no preparation
    res = run(works=["iti"], property={"construction_year": 1995})
    assert res["cost"] == pytest.approx(85 * walls * 131 / 120)


def test_idf_costs_more_than_province():
    province = run(works=["iti", "roof"])
    idf = run(works=["iti", "roof"], property={"postcode": "75011"})
    assert idf["cost"] == pytest.approx(province["cost"] * 1.2)


def test_accessibility_and_parking():
    base = run(works=["vmc"])
    res = run(works=["vmc"], nb_etages=4, has_ascenseur=False, is_urban_dense=True, parking_cost=40)
    # +5%/floor without lift, +10% dense urban, parking for 1 day of works
    assert res["cost"] == pytest.approx(base["cost"] * 1.2 * 1.1 + 40)


def test_same_work_gains_more_on_an_uninsulated_house():
    old = run(works=["roof"])
    recent = run(works=["roof"], property={"construction_year": 1995, "initial_cep": 230})
    assert old["heating_need_reduction"] > 2 * recent["heating_need_reduction"]
    assert 380 - old["new_cep"] > 230 - recent["new_cep"]


def test_already_good_walls_gain_little():
    poor = run(works=["iti"], property={"construction_year": 1930})
    good = run(works=["iti"], property={"construction_year": 1930, "insulation_quality": {"walls": "bonne"}})
    assert good["heating_need_reduction"] < 0.05 < poor["heating_need_reduction"]


def test_insulation_never_increases_consumption():
    res = run(works=["iti", "roof", "floor_ceiling", "windows", "vmc"], property={"construction_year": 2018, "initial_cep": 90})
    assert res["new_cep"] <= 90


def test_dpe_losses_are_used_as_weights():
    # This DPE says almost all losses go through the roof
    dpe_losses = {"walls": 10, "roof": 300, "floor": 10, "windows": 10, "air": 10, "bridges": 10}
    roof = run(works=["roof"], property={"dpe_losses": dpe_losses})
    walls = run(works=["iti"], property={"dpe_losses": dpe_losses})
    assert roof["heating_need_reduction"] > 0.8
    assert walls["heating_need_reduction"] < 0.05
    assert roof["loss_shares"]["roof"] == pytest.approx(300 / 350)


def test_global_renovation_pathway():
    res = run(works=["iti", "roof", "pac_air_eau"], income_level="modeste")
    assert res["gain_classes"] >= 2
    assert res["aid_pathway"] == "accompagne"
    assert res["cee_est"] == 0


def test_income_from_rfr():
    res = run(works=["ecs"], rfr=20000, occupants=2)
    assert res["income_profile"] == "Très Modeste"


def test_bill_is_split_by_usage_and_energy():
    res = run()
    assert res["annual_bill_before"] == pytest.approx(380 * 80 * 0.11)
    # Heat pump: heating moves to electricity
    hp = run(works=["pac_air_eau"])
    heating = 380 * 0.75
    expected = (heating * 0.85 / 2.9 * 0.20 + (380 - heating) * 0.11) * 80
    assert hp["annual_bill_after"] == pytest.approx(expected)
    assert hp["new_ges"] < 60


def test_electric_home_uses_final_consumption():
    # Without ADEME final consumption, primary is divided by the 1.9 coefficient
    res = run(property={"heating_energy": "Électricité"})
    assert res["initial_final_consumption"] == pytest.approx(380 / 1.9)
    res = run(property={"heating_energy": "Électricité", "final_consumption": 210})
    assert res["annual_bill_before"] == pytest.approx(210 * 80 * 0.20)


def test_thermodynamic_water_heater_acts_on_hot_water_only():
    res = run(works=["ecs"], property={"heating_energy": "Électricité"})
    hot_water = 380 / 1.9 * 0.15
    saved = hot_water - hot_water * 0.9 / 2.5
    assert res["annual_savings"] == pytest.approx(saved * 80 * 0.20)


def test_inertia_radiators_worsen_a_gas_heated_home():
    res = run(works=["heating"])
    assert res["new_cep"] > 380
    assert res["annual_savings"] == 0
    assert res["roi_years"] is None


def test_heat_pump_gets_maprimerenov_forfait():
    res = run(works=["pac_air_eau"], property={"heating_energy": "Fioul domestique"}, income_level="modeste")
    assert res["subsidies"] == 4000


def test_rental_ban_dates():
    assert rental_ban_date("G", 400, "59000").year == 2025
    # 450 kWh final energy rule
    assert rental_ban_date("F", 460, "59000").year == 2023
    assert rental_ban_date("F", 400, "97400").year == 2031
    assert rental_ban_date("C", 150, "59000") is None


def suggest(label="F", **prop):
    return suggest_works(SimulationProperty(**{**HOUSE_1960, **prop}), label)


def test_suggestions_for_an_uninsulated_gas_house():
    res = suggest()
    assert {"roof", "iti", "windows", "pac_air_eau"} <= set(res["suggested"])
    assert "heating" not in res["suggested"]
    assert res["preselected"][0] == "roof"


def test_preselection_reaches_the_target_class():
    res = suggest()
    sim = run(works=res["preselected"])
    assert sim["new_cep"] <= 150


def test_no_roof_or_heat_pump_for_apartments():
    res = suggest(building_type="Appartement", surface=50)
    assert "roof" not in res["suggested"] and "pac_air_eau" not in res["suggested"]


def test_electric_homes_get_radiators_and_water_heater():
    res = suggest(heating_energy="Électricité")
    assert {"heating", "ecs"} <= set(res["suggested"])
    assert "pac_air_eau" not in res["suggested"]


def test_insulated_house_gets_fewer_insulation_suggestions():
    res = suggest(label="D", construction_year=2015, initial_cep=200)
    assert not {"iti", "roof", "floor_ceiling", "windows"} & set(res["suggested"])


def test_rental_ban_after_works():
    res = run(works=["roof", "iti", "pac_air_eau"])
    assert res["ban_date"] == "2028-01-01"  # F today
    assert res["new_ban_date"] is None  # C after works
