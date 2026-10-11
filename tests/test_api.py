from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import main
from api.simulation import normalize_energy

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def subscriber():
    """These tests exercise the tools themselves, as a subscriber."""
    main.app.dependency_overrides[main.subscriber_access] = lambda: None
    yield
    main.app.dependency_overrides.pop(main.subscriber_access, None)


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


def test_errors_do_not_leak_internals():
    res = client.post("/api/simulate", json={"property": {}, "works": [], "rfr": "abc"})
    assert res.status_code == 422


def test_market_price_endpoint():
    main.search_limiter.calls.clear()
    assert client.get("/api/market-price?insee=../x").status_code in (400, 422)

    async def fake(insee, building_type, lat, lon, surface):
        return {"price_per_m2": 3100, "source": "prix médian DVF"} if insee == "59350" else None

    with patch.object(main, "market_price", fake):
        assert client.get("/api/market-price?insee=59350&building_type=Maison").json()["price_per_m2"] == 3100
        assert client.get("/api/market-price?insee=2A004").json() == {"price_per_m2": None}
    main.search_limiter.calls.clear()
