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


def test_savings_use_floored_consumption():
    res = run(works=["iti", "roof", "floor_ceiling", "heating", "ecs"], property={"initial_cep": 200})
    assert res["new_cep"] == 35
    assert res["annual_savings"] == pytest.approx((200 - 35) * 80 * 0.228)


def test_rental_ban_dates():
    assert rental_ban_date("G", 400, "59000").year == 2025
    assert rental_ban_date("F", 400, "97400").year == 2031
    assert rental_ban_date("C", 150, "59000") is None


def test_suggestions_skip_roof_for_apartments():
    res = suggest_works("Appartement", "E", 300, ["roof", "iti"], {"walls": 60, "windows": 5, "ventilation": 10})
    assert "roof" not in res["suggested"]
    assert res["preselected"] == ["iti"]


def test_suggestions_target_class_c():
    res = suggest_works("Maison", "F", 380, ["roof", "iti", "windows"], None)
    # Needs 230 kWh: roof (65) + iti (120) + windows (45)
    assert res["preselected"] == ["roof", "iti", "windows"]
