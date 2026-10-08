from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import main
from api.simulation import normalize_energy

client = TestClient(main.app)


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


class TestDpePdfAnalysis:
    """POST /api/analyze-dpe (signed-in users only, see test_accounts)."""

    @pytest.fixture(autouse=True)
    def signed_in(self):
        from api.auth import User, current_user
        main.app.dependency_overrides[current_user] = lambda: User(id="u1", email="u1@example.com")
        main.ai_limiter.calls.clear()
        yield
        main.app.dependency_overrides.clear()
        main.ai_limiter.calls.clear()

    def post(self, name, content, content_type="application/pdf"):
        return client.post("/api/analyze-dpe", files={"file": (name, content, content_type)})

    def test_rejects_non_pdf(self):
        res = self.post("test.txt", b"dummy", "text/plain")
        assert res.status_code == 400
        assert "Only PDFs are allowed" in res.json()["detail"]

    def test_rejects_large_file(self):
        res = self.post("large.pdf", b"0" * (11 * 1024 * 1024))
        assert res.status_code == 400
        assert "File too large" in res.json()["detail"]

    def test_successful_analysis(self):
        extracted = {"numero_dpe": "2134E1234567A", "etiquette_actuelle": "D"}
        with patch.object(main, "extract_text_from_pdf", return_value="Numéro DPE: 2134E1234567A"), \
                patch.object(main, "analyze_text_with_llm", return_value=extracted):
            res = self.post("sample.pdf", b"%PDF-1.4")
        assert res.status_code == 200
        assert res.json()["data"] == extracted
        assert res.json()["raw_text_length"] > 0

    def test_empty_pdf(self):
        with patch.object(main, "extract_text_from_pdf", return_value=""):
            res = self.post("empty.pdf", b"%PDF-1.4")
        assert res.status_code == 422
        assert "PDF seems empty" in res.json()["detail"]


def test_market_price_endpoint():
    main.search_limiter.calls.clear()
    assert client.get("/api/market-price?insee=../x").status_code in (400, 422)

    async def fake(insee, building_type, lat, lon, surface):
        return {"price_per_m2": 3100, "source": "prix médian DVF"} if insee == "59350" else None

    with patch.object(main, "market_price", fake):
        assert client.get("/api/market-price?insee=59350&building_type=Maison").json()["price_per_m2"] == 3100
        assert client.get("/api/market-price?insee=2A004").json() == {"price_per_m2": None}
    main.search_limiter.calls.clear()
