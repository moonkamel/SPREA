import pytest
from fastapi.testclient import TestClient

from api import main
from api.ademe_client import PropertySchema, SystemSchema, WallSchema, WindowSchema
from api.engine import DPECalculator, normalize_energy

client = TestClient(main.app)


def sample_property():
    return PropertySchema(
        address="1 rue de l'Église, Lille",
        shab=80,
        climate_zone="H1a",
        building_type="Maison",
        walls=[WallSchema(surface=120, u_value=2.5)],
        windows=[WindowSchema(surface=15, u_value=3.5)],
        systems=[SystemSchema(system_type="chauffage", energy_source="Gaz naturel")],
    )


def test_normalize_energy_french_labels():
    assert normalize_energy("Électricité") == "electricity"
    assert normalize_energy("Gaz naturel") == "gas"
    assert normalize_energy("Fioul domestique") == "oil"
    assert normalize_energy(None) == "gas"


SIM_INPUT = {
    "property": {"surface": 80, "initial_cep": 380, "ges_value": 60, "building_type": "Maison", "postcode": "59000"},
    "works": ["iti", "roof", "heating"],
    "income_level": "tres_modeste",
}


def test_works_catalog():
    res = client.get("/api/works")
    assert res.status_code == 200
    ids = [w["id"] for w in res.json()["works"]]
    assert "iti" in ids and "roof" in ids


def test_simulate_endpoint():
    res = client.post("/api/simulate", json=SIM_INPUT)
    assert res.status_code == 200
    body = res.json()
    assert body["current_label"] == "F"
    assert body["subsidies"] <= body["cost"]
    assert body["rest_to_pay"] == pytest.approx(max(0, body["cost"] - body["subsidies"] - body["cee_est"]))


def test_simulate_rejects_invalid_surface():
    res = client.post("/api/simulate", json={**SIM_INPUT, "property": {**SIM_INPUT["property"], "surface": 0}})
    assert res.status_code == 422


def test_engine_uses_electricity_factor():
    prop = sample_property()
    gas = DPECalculator().calculate(prop)["cep_m2"]
    prop.systems[0].energy_source = "Électricité"
    elec = DPECalculator().calculate(prop)["cep_m2"]
    assert elec > gas


def test_errors_do_not_leak_internals():
    res = client.post("/api/simulate", json={"property": {}, "works": [], "rfr": "abc"})
    assert res.status_code == 422
