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


def test_simulate_returns_capped_aids():
    payload = {
        "property_data": sample_property().model_dump(mode="json"),
        "selected_works": ["ite_pse", "windows_pvc", "pac_air_eau"],
        "rfr": 20000,
        "postcode": "59000",
        "occupants": 2,
    }
    res = client.post("/api/simulate", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["profile"] == "Très Modeste"
    assert body["subsidies"] <= body["total_cost"]
    assert body["rest_to_pay"] == round(max(0, body["total_cost"] - body["subsidies"] - body["cee_est"]))


def test_engine_uses_electricity_factor():
    prop = sample_property()
    gas = DPECalculator().calculate(prop)["cep_m2"]
    prop.systems[0].energy_source = "Électricité"
    elec = DPECalculator().calculate(prop)["cep_m2"]
    assert elec > gas


def test_generate_report_without_ai_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    main.ai_limiter.calls.clear()
    res = client.post("/api/generate-report", json={"address": "1 rue de l'Église, Lille", "surface": 80})
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")
    assert "Rapport_SPREA_1_rue_de_l_Eglise_Lille.pdf" in res.headers["content-disposition"]


def test_ai_endpoints_are_rate_limited(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    main.ai_limiter.calls.clear()
    statuses = [
        client.post("/api/generate-report", json={"address": "x", "surface": 50}).status_code
        for _ in range(main.ai_limiter.max_calls + 1)
    ]
    assert statuses[-1] == 429
    assert all(s == 200 for s in statuses[:-1])
    main.ai_limiter.calls.clear()


def test_errors_do_not_leak_internals():
    res = client.post("/api/simulate", json={"property_data": {}, "selected_works": [], "rfr": "abc"})
    assert res.status_code == 422
