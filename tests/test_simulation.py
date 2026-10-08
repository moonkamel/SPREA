import math

import pytest

from api.simulation import SimulationInput, rental_ban_date, simulate, suggest_works


def run(**kwargs):
    prop = {"surface": 80, "initial_cep": 380, "ges_value": 60, "building_type": "Maison", "postcode": "59000"}
    prop.update(kwargs.pop("property", {}))
    return simulate(SimulationInput(property=prop, **kwargs))


def test_no_works_keeps_label_and_costs_nothing():
    res = run()
    assert res["current_label"] == res["new_label"] == "F"
    assert res["cost"] == 0 and res["rest_to_pay"] == 0


def test_cost_formula():
    # ITI on an uninsulated 1960 house: (85 + 15 prep) * 8 * sqrt(80) * 131/120
    res = run(works=["iti"], property={"construction_year": 1960})
    wall = 8 * math.sqrt(80)
    assert res["cost"] == pytest.approx(100 * wall * 131 / 120)


def test_idf_costs_more_than_province():
    province = run(works=["iti", "roof"])
    idf = run(works=["iti", "roof"], property={"postcode": "75011"})
    assert idf["cost"] == pytest.approx(province["cost"] * 1.2)


def test_accessibility_and_parking():
    base = run(works=["vmc"])
    res = run(works=["vmc"], nb_etages=4, has_ascenseur=False, is_urban_dense=True, parking_cost=40)
    # +5%/floor without lift, +10% dense urban, parking for 1 day of works
    assert res["cost"] == pytest.approx(base["cost"] * 1.2 * 1.1 + 40)


def test_global_renovation_pathway():
    res = run(works=["iti", "roof", "heating", "ecs"], income_level="modeste")
    assert res["gain_classes"] >= 2
    assert res["aid_pathway"] == "accompagne"
    assert res["cee_est"] == 0


def test_income_from_rfr():
    res = run(works=["ecs"], rfr=20000, occupants=2)
    assert res["income_profile"] == "Très Modeste"


def test_savings_are_computed_on_final_energy_bill():
    # Gas: primary == final energy, 0.11 EUR/kWh
    res = run(works=["iti", "roof"], property={"heating_energy": "Gaz naturel"})
    ratio = res["new_cep"] / 380
    assert res["annual_bill_before"] == pytest.approx(380 * 80 * 0.11)
    assert res["annual_savings"] == pytest.approx(380 * 80 * 0.11 * (1 - ratio))


def test_electric_home_uses_final_consumption():
    # Without ADEME final consumption, primary is divided by the 1.9 coefficient
    res = run(property={"heating_energy": "Électricité"})
    assert res["initial_final_consumption"] == pytest.approx(380 / 1.9)
    res = run(property={"heating_energy": "Électricité", "final_consumption": 210})
    assert res["annual_bill_before"] == pytest.approx(210 * 80 * 0.20)


def test_heat_pump_replaces_gas_boiler():
    res = run(works=["pac_air_eau"], property={"heating_energy": "Gaz naturel"})
    heat = 380 * 0.7 * 0.85 / 2.9
    assert res["new_cep"] == pytest.approx(heat * 1.9 + 380 * 0.3)
    assert res["new_ges"] < 60
    assert res["annual_bill_after"] == pytest.approx((heat * 0.20 + 380 * 0.3 * 0.11) * 80)
    assert res["annual_savings"] > 0


def test_inertia_radiators_worsen_a_gas_heated_home():
    res = run(works=["heating"], property={"heating_energy": "Gaz naturel"})
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


def test_suggestions_skip_roof_for_apartments():
    res = suggest_works("Appartement", "E", 300, ["roof", "iti"], {"walls": 60, "windows": 5, "ventilation": 10})
    assert "roof" not in res["suggested"]
    assert res["preselected"] == ["iti"]


def test_suggestions_target_class_c():
    res = suggest_works("Maison", "F", 380, ["roof", "iti", "windows"], None, "Électricité")
    # Needs 230 kWh: roof (65) + iti (120) + windows (45)
    assert res["preselected"] == ["roof", "iti", "windows"]


def test_heat_pump_suggested_for_gas_heated_houses():
    res = suggest_works("maison", "F", 380, ["roof", "iti", "heating"], None, "Gaz naturel")
    assert "pac_air_eau" in res["suggested"]
    assert "heating" not in res["suggested"]
    assert res["preselected"] == ["roof", "iti", "pac_air_eau"]


def test_no_heat_pump_for_apartments_or_electric_homes():
    assert "pac_air_eau" not in suggest_works("appartement", "F", 380, [], None, "Gaz naturel")["suggested"]
    assert "pac_air_eau" not in suggest_works("maison", "F", 380, [], None, "Électricité")["suggested"]
