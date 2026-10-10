import io

import pdfplumber
import pytest

from api import valuation
from tests.test_accounts import ALICE  # noqa: F401
from tests.test_accounts import env  # noqa: F401  (fixture)

PROP = {"surface": 95, "initial_cep": 420, "ges_value": 70, "building_type": "Maison", "postcode": "59000",
        "insee_code": "59350", "construction_period": "1948-1974", "heating_energy": "Gaz naturel"}
MARKET = {"price_per_m2": 2900, "q25": 2450, "q75": 3350, "sales": 64, "scope": "à moins de 1 km", "period": "2024-2025",
          "source": "prix médian DVF de 64 ventes", "comparables": [
              {"date": "2025-11-14", "street": "Rue Des Postes", "surface": 92, "rooms": "4", "price": 265000,
               "price_m2": 2880, "adjusted_m2": 2900, "distance": 180}],
          "surface_matched": False, "adjusted": True}
REQUEST = {"meta": {"address": "12 RUE DES POSTES", "city": "Lille", "postcode": "59000", "insee_code": "59350",
                    "latitude": 50.63, "longitude": 3.05},
           "simulation": {"property": PROP, "works": ["roof", "iti", "pac_air_eau", "windows"]},
           "adjustment_pct": -5, "adjustment_note": "cuisine à refaire", "client_name": "M. Martin"}


def test_class_factor_and_values():
    from api.simulation import SimulationInput, simulate
    sim = simulate(SimulationInput(property=PROP, works=["roof", "iti", "pac_air_eau", "windows"]))
    r = valuation.compute(sim, MARKET, 95, "Maison", "59", 0)
    assert r["value_now"]["low"] < r["value_now"]["value"] < r["value_now"]["high"]
    assert r["value_after"]["value"] > r["value_now"]["value"]
    # A poor class is worth less than the local median, mixing all classes
    assert r["price_m2_now"] < MARKET["price_per_m2"]
    adjusted = valuation.compute(sim, MARKET, 95, "Maison", "59", 10)
    assert adjusted["value_now"]["value"] == pytest.approx(r["value_now"]["value"] * 1.1, rel=0.01)
    no_works = valuation.compute(simulate(SimulationInput(property=PROP)), MARKET, 95, "Maison", "59", 0)
    assert no_works["value_after"] is None and no_works["net_gain"] is None


def test_valuation_endpoints(env, monkeypatch):
    client, store, billing, state = env

    async def fake_market(insee, building_type, lat=None, lon=None, surface=None):
        return dict(MARKET)

    monkeypatch.setattr(valuation, "market_price", fake_market)
    assert client.post("/api/valuation", json=REQUEST).status_code == 402
    store.profiles[ALICE.id]["subscription_status"] = "active"
    res = client.post("/api/valuation", json=REQUEST).json()
    assert res["value_now"]["value"] > 0 and res["market"]["sales"] == 64 and res["detailed_costs"]
    assert client.post("/api/valuation", json={**REQUEST, "adjustment_pct": 50}).status_code == 422
    # PDF needs the agency
    assert client.post("/api/valuation/pdf", json=REQUEST).status_code == 409
    client.put("/api/agent-page", json={"agency_name": "Agence du Vieux-Lille", "phone": "03 20 00 00 00"})
    pdf = client.post("/api/valuation/pdf", json=REQUEST)
    assert pdf.status_code == 200 and "Avis_de_valeur_12_RUE_DES_POSTES" in pdf.headers["content-disposition"]
    with pdfplumber.open(io.BytesIO(pdf.content)) as doc:
        text = "\n".join(p.extract_text() or "" for p in doc.pages)
    for part in ("Agence du Vieux-Lille", "Avis de valeur", "12 Rue des Postes", "59000 Lille", "Établi pour M. Martin",
                 "Valeur actuelle", "Après rénovation", "Ventes comparables", "Rue Des Postes", "Ajustement du conseiller : -5",
                 "ne constitue pas une expertise", "actualisé"):
        assert part in text, part
    # Sales of any surface: not claimed comparable
    assert "surface comparable" not in text

    async def no_market(*a, **k):
        return None
    monkeypatch.setattr(valuation, "market_price", no_market)
    assert client.post("/api/valuation", json=REQUEST).status_code == 422
