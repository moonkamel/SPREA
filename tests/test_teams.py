import asyncio
import re
import time

from api import accounts
from tests.test_accounts import ALICE, BOB, SUBSCRIBE, env, make_pro, webhook  # noqa: F401 (fixture)
from api.auth import User

CAROL = User(id="33333333-3333-3333-3333-333333333333", email="carol@example.com")


def activate(client, billing, org_id, quantity, user=ALICE, sub_id="sub_org"):
    billing.subscriptions[sub_id] = {"id": sub_id, "customer": "cus_1", "status": "active",
                                     "metadata": {"org_id": org_id, "user_id": user.id},
                                     "items": {"data": [{"quantity": quantity, "current_period_end": int(time.time()) + 86400}]}}
    webhook(client, {"type": "customer.subscription.updated", "data": {"object": {"id": sub_id}}})


def agency(client, store, billing, seats=3):
    res = client.post("/api/billing/subscribe", json={**SUBSCRIBE, "plan": "agence_monthly", "seats": seats, "agency_name": "Agence du Beffroi"})
    assert res.status_code == 200, res.text
    org_id = billing.checkouts[-1]["org_id"]
    activate(client, billing, org_id, seats)
    return org_id


def invite_and_join(client, state, email, user):
    state["user"] = ALICE
    res = client.post("/api/team/invitations", json={"email": email})
    assert res.status_code == 200, res.text
    token = re.search(r"token=([\w-]+)", res.json()["link"]).group(1)
    state["user"] = user
    return client.post("/api/team/join", json={"token": token})


def test_agency_subscription_gives_access_and_replaces_solo(env):
    client, store, billing, state = env
    make_pro(store)
    store.profiles[ALICE.id]["subscription_id"] = "sub_solo"
    assert client.post("/api/billing/subscribe", json={**SUBSCRIBE, "plan": "agence_monthly", "seats": 1, "agency_name": "X Y"}).status_code == 400
    assert client.post("/api/billing/subscribe", json={**SUBSCRIBE, "plan": "agence_monthly", "seats": 3}).status_code == 400
    org_id = agency(client, store, billing)
    assert billing.checkouts[-1] == {"plan": "agence_monthly", "quantity": 3, "org_id": org_id}
    assert store.orgs[org_id]["subscription_status"] == "active" and store.orgs[org_id]["seats"] == 3
    # The Solo plan is cancelled, access now comes from the agency
    assert billing.canceled == ["sub_solo"]
    me = client.get("/api/me").json()
    assert me["is_pro"] and me["team"]["name"] == "Agence du Beffroi" and me["team"]["role"] == "owner"
    assert client.post("/api/billing/subscribe", json={**SUBSCRIBE, "plan": "solo_monthly"}).status_code == 400


def test_invitations_join_and_seats(env):
    client, store, billing, state = env
    agency(client, store, billing, seats=2)
    state["user"] = BOB
    asyncio.run(store.ensure_profile(BOB.id, BOB.email))
    assert client.get("/api/me").json()["is_pro"] is False
    # Wrong account
    res = invite_and_join(client, state, BOB.email, CAROL)
    assert res.status_code == 403
    state["user"] = BOB
    token_res = client.post("/api/team/join", json={"token": "x" * 20})
    assert token_res.status_code == 404
    # Accepted with the invited email
    state["user"] = ALICE
    link = client.post("/api/team/invitations", json={"email": "Bob@Example.com"}).json()["link"]
    state["user"] = BOB
    assert client.post("/api/team/join", json={"token": link.split("token=")[1]}).json()["joined"] is True
    assert client.get("/api/me").json()["is_pro"] is True
    # The link works once
    assert client.post("/api/team/join", json={"token": link.split("token=")[1]}).status_code in (200, 404)
    # 2 seats, 2 members: no more invitations
    state["user"] = ALICE
    assert client.post("/api/team/invitations", json={"email": CAROL.email}).status_code == 409
    team = client.get("/api/team").json()
    assert [m["role"] for m in team["members"]] == ["owner", "agent"] and team["seats_used"] == 2
    # Agents do not manage the team
    state["user"] = BOB
    assert client.post("/api/team/invitations", json={"email": CAROL.email}).status_code == 403


def test_seats_change(env):
    client, store, billing, state = env
    agency(client, store, billing, seats=3)
    invite_and_join(client, state, BOB.email, BOB)
    state["user"] = ALICE
    client.post("/api/team/invitations", json={"email": CAROL.email})
    # Owner + Bob + Carol's pending invitation
    assert client.put("/api/team/seats", json={"seats": 2}).status_code == 400
    assert client.put("/api/team/seats", json={"seats": 5}).json() == {"seats": 5}
    assert billing.seat_updates == [("sub_org", 5)]
    state["user"] = BOB
    assert client.put("/api/team/seats", json={"seats": 6}).status_code == 403


def test_shared_contacts_and_departure(env):
    client, store, billing, state = env
    agency(client, store, billing)
    invite_and_join(client, state, BOB.email, BOB)
    store.links["BOBCODE2"] = {"code": "BOBCODE2", "user_id": BOB.id, "dpe_number": "2259E0123456X", "address": "1 rue A"}
    asyncio.run(store.create_lead({"code": "BOBCODE2", "user_id": BOB.id, "name": "Martine", "phone": "0600000000", "consent_text": "…"}))
    lead_id = store.leads[0]["id"]
    # The owner sees and handles Bob's requests
    state["user"] = ALICE
    leads = client.get("/api/leads").json()["leads"]
    assert [(l["name"], l["agent"], l["address"]) for l in leads] == [("Martine", BOB.email, "1 rue A")]
    assert client.patch(f"/api/leads/{lead_id}", json={"status": "contacted"}).status_code == 200
    # Bob sees his own
    state["user"] = BOB
    assert [l["name"] for l in client.get("/api/leads").json()["leads"]] == ["Martine"]
    # Bob leaves: his requests and links go to the owner, his access ends
    assert client.post("/api/team/leave").json() == {"left": True}
    assert client.get("/api/me").json()["is_pro"] is False
    assert store.leads[0]["user_id"] == ALICE.id and store.links["BOBCODE2"]["user_id"] == ALICE.id
    state["user"] = ALICE
    assert client.post("/api/team/leave").status_code == 400  # The owner cannot leave


def test_shared_alert_zones(env):
    client, store, billing, state = env
    agency(client, store, billing)
    invite_and_join(client, state, BOB.email, BOB)
    for u in (ALICE, BOB):
        asyncio.run(store.add_terms_acceptance(u.id, "prospection", accounts.TERMS_VERSION))
    asyncio.run(store.create_zone({"user_id": BOB.id, "name": "Vauban", "lat": 50.6, "lon": 3.0, "radius_m": 1000, "labels": "F,G", "kind": None}))
    state["user"] = ALICE
    zones = client.get("/api/alerts").json()["zones"]
    assert [(z["name"], z["mine"], z["owner"]) for z in zones] == [("Vauban", False, BOB.email)]


def test_removing_a_member_and_deleting_the_owner(env):
    client, store, billing, state = env
    agency(client, store, billing)
    invite_and_join(client, state, BOB.email, BOB)
    state["user"] = ALICE
    assert client.request("DELETE", "/api/me", json={"confirm": True}).status_code == 400
    assert client.delete(f"/api/team/members/{ALICE.id}").status_code == 404
    assert client.delete(f"/api/team/members/{BOB.id}").json() == {"removed": True}
    assert BOB.id not in store.memberships
    # Alone in the agency: the account and the agency subscription can go
    assert client.request("DELETE", "/api/me", json={"confirm": True}).json() == {"deleted": True}
    assert "sub_org" in billing.canceled and not store.orgs


def test_network_gives_access_and_console(env):
    client, store, billing, state = env
    network = asyncio.run(store.create_org({"name": "Réseau Nord", "kind": "reseau", "seats": 40, "subscription_status": "active"}))
    child = asyncio.run(store.create_org({"name": "Agence de Lille", "kind": "agence", "seats": 5, "parent_id": network["id"]}))
    asyncio.run(store.ensure_profile(ALICE.id, ALICE.email))
    asyncio.run(store.ensure_profile(BOB.id, BOB.email))
    asyncio.run(store.add_member(network["id"], ALICE.id, "owner"))
    asyncio.run(store.add_member(child["id"], BOB.id, "agent"))
    # The agency has no subscription of its own: the network's gives access
    state["user"] = BOB
    me = client.get("/api/me").json()
    assert me["is_pro"] and me["team"]["network"] == "Réseau Nord"
    assert client.get("/api/team/network").status_code == 403
    state["user"] = ALICE
    agencies = client.get("/api/team/network").json()["agencies"]
    assert agencies == [{"id": child["id"], "name": "Agence de Lille", "seats": 5, "members": 1, "leads": 0, "leads_open": 0}]
