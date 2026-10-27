import pytest
from fastapi.testclient import TestClient

from api import accounts, estimate, main
from api.auth import User, current_user

MARKET = {"price_per_m2": 3000, "q25": 2600, "q75": 3500, "sales": 64, "scope": "à moins de 500 m",
          "period": "2024-2025", "source": "prix médian DVF", "comparables": [{"street": "Rue A"}] * 9,
          "surface_matched": True, "wide": False}

BASE = {"address": "12 rue de la Paix 59000 Lille", "insee": "59350", "postcode": "59000", "city": "Lille",
        "lat": 50.63, "lon": 3.06, "kind": "appartement", "surface": 60}


def req(**kw):
    return estimate.EstimateRequest(**{**BASE, **kw})


class Store:
    def __init__(self):
        self.leads, self.zones, self.profiles = [], [], {}

    async def create_estimate_lead(self, row):
        lead = {"id": f"l{len(self.leads)}", "status": "new", **row}
        self.leads.append(lead)
        return lead

    async def list_estimate_leads(self, user_id):
        return [l for l in self.leads if l["assigned_user_id"] == user_id]

    async def update_estimate_lead(self, user_id, lead_id, fields):
        hits = [l for l in self.leads if l["id"] == lead_id and l["assigned_user_id"] == user_id]
        for l in hits:
            l.update(fields)
        return hits

    async def active_zones(self):
        return self.zones

    async def get_profile(self, uid):
        return self.profiles.get(uid)


@pytest.fixture
def client(monkeypatch):
    store = Store()
    main.app.dependency_overrides[accounts.store_dep] = lambda: store
    sent = []

    async def fake_send(to, subject, html, text, **kw):
        sent.append({"to": to, "subject": subject, "text": text})
        return True

    async def fake_market(insee, building_type, lat=None, lon=None, surface=None, **kw):
        return dict(MARKET) if insee != "99999" else None

    monkeypatch.setattr(estimate, "send_email", fake_send)
    monkeypatch.setattr(estimate, "market_price", fake_market)
    for lim in (estimate.estimate_limiter, estimate.estimate_ai_limiter, estimate.lead_limiter):
        lim.calls.clear()
    c = TestClient(main.app)
    c.store, c.sent = store, sent
    yield c
    main.app.dependency_overrides.clear()


def test_value_is_surface_times_comparable_price_without_extras():
    r = estimate.compute(req(), MARKET)
    assert r["price_m2"] == 3000 and r["value"] == 180000
    assert r["low"] < r["value"] < r["high"]
    assert r["adjustments"] == [] and r["dpe_effect"] is None


def test_range_follows_the_spread_of_sales_within_bounds():
    tight = estimate.compute(req(), {**MARKET, "q25": 2950, "q75": 3050})
    wide = estimate.compute(req(), {**MARKET, "q25": 1000, "q75": 6000})
    assert tight["high"] / tight["value"] == pytest.approx(1.05, abs=0.01)
    assert wide["high"] / wide["value"] == pytest.approx(1.15, abs=0.01)


def test_usual_adjustments_and_cap():
    adj = estimate.adjustments(req(condition="a_renover", floor=5, elevator=False, outdoor=["balcon", "terrasse"], parking=True))
    labels = {a["label"]: a["pct"] for a in adj}
    assert labels["À rénover"] == -12 and labels["5e étage sans ascenseur"] == -9
    # Only the best outdoor space counts
    assert "Balcon" not in labels and labels["Terrasse"] == 4 and labels["Stationnement"] == 3
    r = estimate.compute(req(condition="a_renover", floor=0, outdoor=[]), MARKET)
    assert r["adjustment_total"] == -18 and r["value"] == round(180000 * 0.82 / 1000) * 1000
    worst = estimate.compute(req(condition="a_renover", floor=6, elevator=False), {**MARKET})
    assert worst["adjustment_total"] >= -25


def test_house_garden_is_not_an_extra_but_a_pool_is():
    adj = estimate.adjustments(req(kind="maison", outdoor=["jardin"], pool=True))
    assert [a["label"] for a in adj] == ["Piscine"]


def test_dpe_class_moves_the_value_and_shows_renovation_potential():
    g = estimate.compute(req(dpe="G"), MARKET)
    b = estimate.compute(req(dpe="B"), MARKET)
    assert g["value"] < b["value"] and g["dpe_effect"] < 0 < b["dpe_effect"]
    assert g["renovation"] and g["renovation"]["target"] == "C" and g["renovation"]["gain"] > 0
    assert b["renovation"] is None


def test_reliability_needs_many_close_sales_and_the_dpe():
    best = estimate.reliability(MARKET, 0.08, True)
    no_dpe = estimate.reliability(MARKET, 0.08, False)
    thin = estimate.reliability({**MARKET, "sales": 12, "scope": "à Lille", "surface_matched": False}, 0.15, True)
    assert best["score"] == 5 and no_dpe["score"] == 4 and thin["score"] == 1


def test_trend_compares_the_last_four_quarters():
    t = estimate.trend("appartement", "59")
    assert t and t["to"] > t["from"] and -30 < t["pct"] < 30


def test_parse_rules_read_the_obvious():
    f = estimate.parse_rules("Bel appartement T3 de 68 m² au 4e étage avec ascenseur, balcon, parking, refait à neuf, DPE C")
    assert f["kind"] == "appartement" and f["surface"] == 68 and f["rooms"] == 3 and f["floor"] == 4
    assert f["elevator"] is True and f["outdoor"] == ["balcon"] and f["parking"] and f["condition"] == "refait"
    assert f["dpe"] == "C"
    h = estimate.parse_rules("Maison 120 m2 avec 800 m² de terrain, piscine, travaux à prévoir")
    assert h["kind"] == "maison" and h["surface"] == 120 and h["land"] == 800 and h["pool"] and h["condition"] == "rafraichir"


def test_estimate_endpoint(client):
    r = client.post("/api/estimate", json={**BASE, "dpe": "D", "condition": "refait"})
    assert r.status_code == 200
    body = r.json()
    assert body["value"] > 180000 and len(body["comparables"]) == 6 and body["reliability"]["score"] >= 4
    assert client.post("/api/estimate", json={**BASE, "insee": "99999"}).status_code == 422
    assert client.post("/api/estimate", json={**BASE, "surface": 3}).status_code == 422


def test_parse_and_explain_fall_back_without_claude(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = client.post("/api/estimate/parse", json={"text": "Maison de 95 m2, 4 pièces, jardin"}).json()
    assert p["source"] == "regles" and p["fields"]["surface"] == 95 and p["fields"]["rooms"] == 4
    e = client.post("/api/estimate/explain", json={
        "city": "Lille", "kind": "appartement", "surface": 60, "value": 180000, "low": 170000, "high": 190000,
        "price_m2": 3000, "market_m2": 3000, "sales": 64, "scope": "à moins de 500 m", "dpe": "F", "dpe_effect": -8,
        "adjustments": [{"label": "Balcon", "pct": 2}]}).json()
    assert e["source"] == "regles" and "3 000 €" in e["text"].replace(" ", " ") and "F" in e["text"]


def lead(**kw):
    return {"estimate": BASE, "value": 180000, "low": 170000, "high": 190000, "name": "Marie Martin",
            "phone": "06 12 34 56 78", "project": "vendre_3m", "consent": True, **kw}


def test_lead_needs_consent_and_a_way_to_reach(client):
    assert client.post("/api/estimate/lead", json=lead(consent=False)).status_code == 400
    assert client.post("/api/estimate/lead", json=lead(phone=None)).status_code == 400
    assert client.post("/api/estimate/lead", json=lead(website="bot")).json() == {"received": True}
    assert client.store.leads == []


def test_lead_goes_to_the_subscriber_whose_zone_covers_the_address(client):
    s = client.store
    s.profiles = {"pro": {"id": "pro", "email": "pro@x.fr", "subscription_status": "active"},
                  "far": {"id": "far", "email": "far@x.fr", "subscription_status": "active"},
                  "ex": {"id": "ex", "email": "ex@x.fr", "subscription_status": "canceled"}}
    s.zones = [{"user_id": "ex", "lat": 50.63, "lon": 3.06, "radius_m": 1000},
               {"user_id": "far", "lat": 50.70, "lon": 3.20, "radius_m": 2000},
               {"user_id": "pro", "lat": 50.632, "lon": 3.062, "radius_m": 1500}]
    r = client.post("/api/estimate/lead", json=lead())
    assert r.json() == {"received": True, "assigned": True}
    row = s.leads[0]
    assert row["assigned_user_id"] == "pro" and "partenaire de SPREA" in row["consent_text"]
    assert client.sent and client.sent[0]["to"] == "pro@x.fr" and "06 12 34 56 78" in client.sent[0]["text"]

    main.app.dependency_overrides[current_user] = lambda: User(id="pro", email="pro@x.fr")
    listed = client.get("/api/estimate-leads").json()["leads"]
    assert [l["id"] for l in listed] == [row["id"]]
    assert client.patch(f"/api/estimate-leads/{row['id']}", json={"status": "contacted"}).status_code == 200
    main.app.dependency_overrides[current_user] = lambda: User(id="far", email="far@x.fr")
    assert client.get("/api/estimate-leads").json()["leads"] == []
    assert client.patch(f"/api/estimate-leads/{row['id']}", json={"status": "closed"}).status_code == 404


def test_lead_without_covering_zone_is_kept_unassigned(client):
    r = client.post("/api/estimate/lead", json=lead(email="marie@exemple.fr", phone=None))
    assert r.json() == {"received": True, "assigned": False}
    assert client.store.leads[0]["assigned_user_id"] is None and client.sent == []
