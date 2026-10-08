import asyncio
import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from api import accounts, alerts, main
from tests.test_accounts import ALICE, BOB, FakeBilling, FakeStore  # noqa: F401
from tests.test_accounts import env  # noqa: F401  (fixture)

ROWS = [
    {"numero_dpe": "2659E0000001A", "etiquette_dpe": "G", "type_batiment": "maison", "surface_habitable_logement": 92.5,
     "adresse_ban": "3 Rue Doudin 59800 Lille", "date_etablissement_dpe": "2026-10-06", "date_reception_dpe": "2026-10-07",
     "periode_construction": "avant 1948"},
    {"numero_dpe": "2659E0000002B", "etiquette_dpe": "F", "type_batiment": "appartement", "surface_habitable_logement": 41,
     "adresse_ban": "12 Rue Doudin 59800 Lille", "date_etablissement_dpe": "2026-10-05", "date_reception_dpe": "2026-10-07",
     "numero_etage_appartement": 2},
]


def ademe(seen):
    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"total": 2, "results": ROWS})
    return httpx.MockTransport(handler)


def zone(**kw):
    return {"id": "z1", "user_id": ALICE.id, "name": "Vieux-Lille", "lat": 50.64, "lon": 3.06, "radius_m": 800,
            "labels": "F,G", "kind": None, "email": True, "active": True, "last_checked_on": None, **kw}


def test_check_zone_queries_new_dpe_and_ignores_duplicates():
    store, seen = FakeStore(), []
    store.zones["z1"] = zone()
    new = asyncio.run(alerts.check_zone(store, store.zones["z1"], date(2026, 10, 8), ademe(seen)))
    assert len(new) == 2 and new[1]["detail"] == "2e étage"
    assert seen[0]["geo_distance"] == "3.06,50.64,800"
    assert seen[0]["qs"] == "date_reception_dpe:[2026-09-24 TO *] AND etiquette_dpe:(F OR G)"  # 14-day window
    assert store.zones["z1"]["last_checked_on"] == "2026-10-08"
    # Next day: same DPE (published late or not), nothing new
    again = asyncio.run(alerts.check_zone(store, store.zones["z1"], date(2026, 10, 9), ademe(seen)))
    assert again == [] and seen[1]["qs"].startswith("date_reception_dpe:[2026-09-25 TO *]")


def test_run_alerts_emails_pro_users_only(monkeypatch):
    store, seen, sent = FakeStore(), [], []
    store.profiles[ALICE.id] = {"id": ALICE.id, "email": ALICE.email, "subscription_status": "active"}
    store.profiles[BOB.id] = {"id": BOB.id, "email": BOB.email, "subscription_status": "canceled"}
    store.zones["z1"] = zone()
    store.zones["z2"] = zone(id="z2", user_id=BOB.id)

    async def fake_send(to, subject, html, text):
        sent.append((to, subject, html))
        return True

    monkeypatch.setattr(alerts, "send_email", fake_send)
    res = asyncio.run(alerts.run_alerts(store, date(2026, 10, 8), ademe(seen)))
    assert res == {"zones_checked": 1, "users_notified": 1, "new_hits": 2, "errors": 0}
    assert sent[0][0] == ALICE.email and sent[0][1] == "2 nouveaux DPE dans vos secteurs"
    assert "3 Rue Doudin" in sent[0][2] and "<script" not in sent[0][2]
    # Already checked today: nothing more
    assert asyncio.run(alerts.run_alerts(store, date(2026, 10, 8), ademe(seen)))["zones_checked"] == 0


def test_email_content_escapes_external_text():
    hits = [{"zone_id": "z1", "label": "G", "address": "<b>1 rue</b>", "kind": "Maison", "surface": 50, "detail": None}]
    content = alerts.email_content({"z1": {"name": "Zone <x>"}}, hits)
    assert "<b>1 rue</b>" not in content["html"] and "&lt;b&gt;1 rue&lt;/b&gt;" in content["html"]
    assert "Zone &lt;x&gt;" in content["html"]


def test_zone_endpoints_and_cron_auth(env, monkeypatch):
    client, store, billing, state = env
    body = {"name": "Vieux-Lille", "lat": 50.64, "lon": 3.06, "radius_m": 800, "labels": ["f", "g", "Z"]}
    assert client.post("/api/alerts/zones", json=body).status_code == 402
    store.profiles[ALICE.id]["subscription_status"] = "active"
    assert client.post("/api/alerts/zones", json=body).status_code == 403
    client.post("/api/prospection/terms", json={"terms_version": accounts.TERMS_VERSION, "accept": True})

    async def fake_check(store_, zone_, today, transport=None):
        return [{"dpe_number": "x"}]
    monkeypatch.setattr(alerts, "check_zone", fake_check)
    res = client.post("/api/alerts/zones", json=body).json()
    assert res["new_hits"] == 1 and res["zone"]["labels"] == "F,G"
    assert client.post("/api/alerts/zones", json={**body, "radius_m": 5000}).status_code == 422
    zone_id = res["zone"]["id"]
    assert client.patch(f"/api/alerts/zones/{zone_id}", json={"email": False}).status_code == 200
    assert store.zones[zone_id]["email"] is False
    data = client.get("/api/alerts").json()
    assert [z["name"] for z in data["zones"]] == ["Vieux-Lille"] and data["email_enabled"] is False
    state["user"] = BOB
    assert client.delete(f"/api/alerts/zones/{zone_id}").status_code == 404
    state["user"] = ALICE
    assert client.delete(f"/api/alerts/zones/{zone_id}").status_code == 200

    anonymous = TestClient(main.app)
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert anonymous.get("/api/cron/alerts").status_code == 401
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert anonymous.get("/api/cron/alerts", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_resend_email_payload(monkeypatch):
    from api import emailer
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "e1"})

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert asyncio.run(emailer.send_email("a@b.fr", "s", "<p>h</p>", "t", httpx.MockTransport(handler))) is False
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("ALERTS_FROM", "SPREA <alertes@sprea.fr>")
    assert asyncio.run(emailer.send_email("a@b.fr", "s", "<p>h</p>", "t", httpx.MockTransport(handler))) is True
    assert seen["auth"] == "Bearer re_test" and seen["body"]["to"] == ["a@b.fr"]
