import asyncio
import json
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from api import accounts, main
from api.auth import User, current_user, verify_token

SIM_INPUT = {
    "property": {"surface": 80, "initial_cep": 380, "ges_value": 60, "building_type": "Maison",
                 "postcode": "59000", "heating_energy": "Gaz naturel"},
    "works": ["iti", "roof", "pac_air_eau"],
    "income_level": "modeste",
}
REPORT_REQUEST = {"meta": {"address": "1 rue de l'Église, Lille", "year": 1960}, "simulation": SIM_INPUT,
                  "accept_terms": True}
SUBSCRIBE = {"accept_terms": True}


class FakeStore:
    def __init__(self):
        self.profiles = {}
        self.reports = {}
        self.archive = []
        self.deleted_users = []
        self.acceptances = []
        self.agent_pages = {}
        self.links = {}
        self.leads = []
        self.zones = {}
        self.hits = []
        self.orgs = {}
        self.memberships = {}
        self.invitations = {}

    def _with_org(self, profile):
        m = self.memberships.get(profile["id"])
        if m:
            org = self.orgs.get(m["org_id"])
            profile["org"] = dict(org) if org else None
            profile["org_role"] = m["role"]
            parent = self.orgs.get(org.get("parent_id")) if org else None
            profile["org_parent"] = dict(parent) if parent else None
        return profile

    async def ensure_profile(self, user_id, email):
        profile = self.profiles.setdefault(user_id, {"id": user_id})
        profile["email"] = email
        return self._with_org(dict(profile))

    async def get_profile(self, user_id):
        p = self.profiles.get(user_id)
        return self._with_org(dict(p)) if p else None

    # --- Teams ---

    async def create_org(self, row):
        org = {"id": str(uuid.uuid4()), "parent_id": None, "stripe_subscription_id": None, "subscription_status": None, **row}
        self.orgs[org["id"]] = org
        return dict(org)

    async def get_org(self, org_id):
        o = self.orgs.get(org_id)
        return dict(o) if o else None

    async def update_org(self, org_id, fields):
        self.orgs[org_id].update(fields)

    async def delete_org(self, org_id):
        self.orgs.pop(org_id, None)
        self.memberships = {u: m for u, m in self.memberships.items() if m["org_id"] != org_id}

    async def child_orgs(self, parent_id):
        return [dict(o) for o in self.orgs.values() if o.get("parent_id") == parent_id]

    async def get_membership(self, user_id):
        m = self.memberships.get(user_id)
        return dict(m) if m else None

    async def add_member(self, org_id, user_id, role):
        assert user_id not in self.memberships
        self.memberships[user_id] = {"user_id": user_id, "org_id": org_id, "role": role, "created_at": f"2026-10-08T10:{len(self.memberships):02d}:00Z"}

    async def update_member(self, org_id, user_id, fields):
        self.memberships[user_id].update(fields)

    async def remove_member(self, org_id, user_id):
        self.memberships.pop(user_id, None)

    async def list_members(self, org_id):
        ms = sorted((m for m in self.memberships.values() if m["org_id"] == org_id), key=lambda m: m["created_at"])
        return [{**m, "email": (self.profiles.get(m["user_id"]) or {}).get("email")} for m in ms]

    async def create_invitation(self, row):
        for k, i in list(self.invitations.items()):
            if i["org_id"] == row["org_id"] and i["email"] == row["email"]:
                del self.invitations[k]
        inv = {"id": str(uuid.uuid4()), "created_at": "2026-10-08T10:00:00Z", **row}
        self.invitations[inv["id"]] = inv
        return dict(inv)

    async def get_invitation(self, token_hash):
        return next((dict(i) for i in self.invitations.values() if i["token_hash"] == token_hash), None)

    async def list_invitations(self, org_id):
        return [dict(i) for i in self.invitations.values() if i["org_id"] == org_id and not i.get("accepted_at")]

    async def accept_invitation(self, invitation_id):
        self.invitations[invitation_id]["accepted_at"] = "2026-10-08T11:00:00Z"

    async def delete_invitation(self, org_id, invitation_id):
        i = self.invitations.get(invitation_id)
        if not i or i["org_id"] != org_id:
            return []
        return [self.invitations.pop(invitation_id)]

    async def list_links_for_users(self, user_ids):
        return [dict(l) for l in self.links.values() if l["user_id"] in user_ids]

    async def list_leads_for_users(self, user_ids):
        return [dict(l) for l in self.leads if l["user_id"] in user_ids]

    async def list_zones_for_users(self, user_ids):
        return [dict(z) for z in self.zones.values() if z["user_id"] in user_ids]

    async def list_hits_for_users(self, user_ids, limit=500):
        return [dict(h) for h in self.hits if h["user_id"] in user_ids][:limit]

    async def transfer_contacts(self, from_user, to_user):
        for l in self.links.values():
            if l["user_id"] == from_user:
                l["user_id"] = to_user
        for lead in self.leads:
            if lead["user_id"] == from_user:
                lead["user_id"] = to_user

    async def get_profile_by_customer(self, customer_id):
        return next((dict(p) for p in self.profiles.values() if p.get("stripe_customer_id") == customer_id), None)

    async def update_profile(self, user_id, fields):
        self.profiles[user_id].update(fields)

    async def create_report(self, row):
        report = {"id": str(uuid.uuid4()), "created_at": "2026-10-08T10:00:00Z", "narrative": None,
                  "stripe_session_id": None, **row}
        self.reports[report["id"]] = report
        return dict(report)

    async def get_report(self, report_id):
        r = self.reports.get(report_id)
        return dict(r) if r else None

    async def update_report(self, report_id, fields):
        self.reports[report_id].update(fields)

    async def paid_reports(self, user_id):
        return [r for r in self.reports.values() if r["user_id"] == user_id and r["status"] == "paid"]

    async def archive_purchases(self, rows):
        self.archive.extend(rows)

    async def add_terms_acceptance(self, user_id, scope, version):
        row = {"user_id": user_id, "scope": scope, "terms_version": version, "accepted_at": f"2026-10-08T12:{len(self.acceptances):02d}:00Z"}
        self.acceptances.append(row)
        return dict(row)

    async def latest_terms_acceptance(self, user_id, scope):
        rows = [a for a in self.acceptances if a["user_id"] == user_id and a["scope"] == scope]
        return dict(rows[-1]) if rows else None

    async def terms_acceptances(self, user_id):
        return [dict(a) for a in self.acceptances if a["user_id"] == user_id]

    async def get_agent_page(self, user_id):
        return dict(self.agent_pages[user_id]) if user_id in self.agent_pages else None

    async def upsert_agent_page(self, user_id, fields):
        self.agent_pages[user_id] = {**self.agent_pages.get(user_id, {}), **fields, "user_id": user_id}
        return dict(self.agent_pages[user_id])

    async def get_link(self, code):
        return dict(self.links[code]) if code in self.links else None

    async def get_link_for_dpe(self, user_id, dpe_number):
        return next((dict(l) for l in self.links.values() if l["user_id"] == user_id and l["dpe_number"] == dpe_number), None)

    async def create_link(self, row):
        self.links[row["code"]] = {"visits": 0, **row}
        return dict(self.links[row["code"]])

    async def update_link(self, code, fields):
        self.links[code].update(fields)

    async def list_links(self, user_id):
        return [dict(l) for l in self.links.values() if l["user_id"] == user_id]

    async def create_lead(self, row):
        lead = {"id": str(uuid.uuid4()), "status": "new", "created_at": "2026-10-08T14:00:00Z", **row}
        self.leads.append(lead)
        return dict(lead)

    async def list_leads(self, user_id):
        return [dict(l) for l in self.leads if l["user_id"] == user_id]

    async def update_lead(self, user_id, lead_id, fields):
        hits = [l for l in self.leads if l["id"] == lead_id and l["user_id"] == user_id]
        for l in hits:
            l.update(fields)
        return hits

    async def delete_lead(self, user_id, lead_id):
        hits = [l for l in self.leads if l["id"] == lead_id and l["user_id"] == user_id]
        self.leads = [l for l in self.leads if l not in hits]
        return hits

    async def list_zones(self, user_id):
        return [dict(z) for z in self.zones.values() if z["user_id"] == user_id]

    async def active_zones(self):
        return [dict(z) for z in self.zones.values() if z.get("active", True)]

    async def create_zone(self, row):
        zone = {"id": str(uuid.uuid4()), "active": True, "email": True, "last_checked_on": None, **row}
        self.zones[zone["id"]] = zone
        return dict(zone)

    async def update_zone(self, zone_id, fields, user_id=None):
        z = self.zones.get(zone_id)
        if not z or (user_id and z["user_id"] != user_id):
            return []
        z.update(fields)
        return [dict(z)]

    async def delete_zone(self, user_id, zone_id):
        z = self.zones.get(zone_id)
        if not z or z["user_id"] != user_id:
            return []
        del self.zones[zone_id]
        return [z]

    async def add_hits(self, rows):
        known = {(h["zone_id"], h["dpe_number"]) for h in self.hits}
        new = [dict(r, id=str(uuid.uuid4())) for r in rows if (r["zone_id"], r["dpe_number"]) not in known]
        self.hits.extend(new)
        return new

    async def list_hits(self, user_id, limit=300):
        return [dict(h) for h in self.hits if h["user_id"] == user_id][:limit]

    async def delete_user(self, user_id):
        # Cascade of the real schema
        self.deleted_users.append(user_id)
        self.acceptances = [a for a in self.acceptances if a["user_id"] != user_id]
        self.profiles.pop(user_id, None)
        self.reports = {k: r for k, r in self.reports.items() if r["user_id"] != user_id}

    async def list_reports(self, user_id):
        return [r for r in self.reports.values() if r["user_id"] == user_id and r["status"] in ("paid", "included")]


class FakeBilling:
    def __init__(self):
        self.sessions = {}
        self.subscriptions = {}
        self.customers = []
        self.canceled = []
        self.plans = []
        self.checkouts = []
        self.seat_updates = []

    async def create_customer(self, user_id, email):
        self.customers.append(user_id)
        return f"cus_{len(self.customers)}"

    async def report_checkout(self, report_id, user_id, customer_id):
        session_id = f"cs_{len(self.sessions) + 1}"
        self.sessions[session_id] = {"id": session_id, "payment_status": "unpaid", "amount_total": 3900,
                                     "currency": "eur", "metadata": {"kind": "report", "report_id": report_id}}
        return {"id": session_id, "url": f"https://checkout.stripe.test/{session_id}"}

    async def subscription_checkout(self, user_id, customer_id, plan="solo_monthly", quantity=1, org_id=None):
        self.plans.append(plan)
        self.checkouts.append({"plan": plan, "quantity": quantity, "org_id": org_id})
        return "https://checkout.stripe.test/sub"

    async def portal_url(self, customer_id):
        return "https://billing.stripe.test/portal"

    async def cancel_subscription(self, subscription_id, prorate=False):
        self.canceled.append(subscription_id)

    async def update_seats(self, subscription_id, seats):
        self.seat_updates.append((subscription_id, seats))

    async def get_session(self, session_id):
        return self.sessions[session_id]

    async def get_subscription(self, subscription_id):
        return self.subscriptions[subscription_id]

    def parse_event(self, payload, signature):
        if signature != "valid":
            raise ValueError("bad signature")
        return json.loads(payload)


ALICE = User(id="11111111-1111-1111-1111-111111111111", email="alice@example.com")
BOB = User(id="22222222-2222-2222-2222-222222222222", email="bob@example.com")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store, billing = FakeStore(), FakeBilling()
    state = {"user": ALICE}
    main.app.dependency_overrides[accounts.store_dep] = lambda: store
    main.app.dependency_overrides[accounts.billing_dep] = lambda: billing
    main.app.dependency_overrides[accounts.optional_billing_dep] = lambda: billing
    main.app.dependency_overrides[current_user] = lambda: state["user"]
    main.ai_limiter.calls.clear()
    yield TestClient(main.app), store, billing, state
    main.app.dependency_overrides.clear()
    main.ai_limiter.calls.clear()


def make_pro(store, user=ALICE):
    asyncio.run(store.ensure_profile(user.id, user.email))
    store.profiles[user.id]["subscription_status"] = "active"


def legacy_report(store, billing, user=ALICE):
    """Report bought alone, before the subscription-only offer."""
    report = asyncio.run(store.create_report({"user_id": user.id, "address": REPORT_REQUEST["meta"]["address"],
                                              "meta": REPORT_REQUEST["meta"], "simulation": SIM_INPUT, "status": "pending",
                                              "terms_version": accounts.TERMS_VERSION}))
    session = asyncio.run(billing.report_checkout(report["id"], user.id, "cus_1"))
    asyncio.run(store.update_report(report["id"], {"stripe_session_id": session["id"]}))
    return report["id"], billing.sessions[session["id"]]


def test_reports_are_for_subscribers_only(env):
    client, store, billing, _ = env
    res = client.post("/api/reports", json=REPORT_REQUEST)
    assert res.status_code == 402 and not store.reports
    assert client.post("/api/billing/subscribe", json={"accept_terms": False}).status_code == 400
    make_pro(store)
    res = client.post("/api/reports", json=REPORT_REQUEST).json()
    assert res["status"] == "included"
    assert client.get(f"/api/reports/{res['id']}/pdf").content.startswith(b"%PDF")


def test_legacy_report_unlocked_by_webhook(env):
    client, store, billing, _ = env
    report_id, session = legacy_report(store, billing)
    assert client.get(f"/api/reports/{report_id}/pdf").status_code == 402
    # Forged signature: ignored
    paid = dict(session, payment_status="paid")
    assert webhook(client, {"type": "checkout.session.completed", "data": {"object": paid}}, signature="forged").status_code == 400
    assert store.reports[report_id]["status"] == "pending"
    assert webhook(client, {"type": "checkout.session.completed", "data": {"object": paid}}).status_code == 200
    assert store.reports[report_id]["status"] == "paid" and store.reports[report_id]["amount_paid"] == 3900
    assert client.get(f"/api/reports/{report_id}/pdf").content.startswith(b"%PDF")


def test_subscription_records_terms_and_plan(env):
    client, store, billing, _ = env
    client.post("/api/billing/subscribe", json={**SUBSCRIBE, "plan": "solo_yearly"})
    assert store.profiles[ALICE.id]["terms_version"] == accounts.TERMS_VERSION
    assert billing.plans == ["solo_yearly"]
    assert client.post("/api/billing/subscribe", json={**SUBSCRIBE, "plan": "gratuit"}).status_code == 422


def test_tools_are_for_subscribers(env):
    client, store, billing, _ = env
    sim = {"property": SIM_INPUT["property"], "works": []}
    assert client.post("/api/simulate", json=sim).status_code == 402
    make_pro(store)
    assert client.post("/api/simulate", json=sim).status_code == 200


def test_owner_link_opens_the_tools(env):
    client, store, billing, state = env
    sim = {"property": SIM_INPUT["property"], "works": []}
    state["user"] = None
    main.app.dependency_overrides.pop(current_user)
    asyncio.run(store.create_link({"code": "Ab3dEf7h", "user_id": ALICE.id, "dpe_number": "2259E0123456X"}))
    assert client.post("/api/simulate", json=sim).status_code == 401
    assert client.post("/api/simulate", json=sim, headers={"X-Link-Code": "Zz9zZz9z"}).status_code == 401
    assert client.post("/api/simulate", json=sim, headers={"X-Link-Code": "Ab3dEf7h"}).status_code == 200


def webhook(client, event, signature="valid"):
    return client.post("/api/stripe/webhook", content=json.dumps(event), headers={"stripe-signature": signature})


def test_report_requires_login():
    client = TestClient(main.app)
    assert client.post("/api/reports", json=REPORT_REQUEST).status_code == 401
    assert client.get("/api/me").status_code == 401


def test_dpe_pdf_analysis_requires_login():
    client = TestClient(main.app)
    res = client.post("/api/analyze-dpe", files={"file": ("dpe.pdf", b"%PDF-1.4", "application/pdf")})
    assert res.status_code == 401


def test_reports_are_private(env):
    client, store, billing, state = env
    make_pro(store)
    report_id = client.post("/api/reports", json=REPORT_REQUEST).json()["id"]
    state["user"] = BOB
    assert client.get(f"/api/reports/{report_id}").status_code == 404
    assert client.get(f"/api/reports/{report_id}/pdf").status_code == 404


def test_pro_subscription_flow(env):
    client, store, billing, _ = env
    assert client.post("/api/billing/subscribe", json=SUBSCRIBE).json()["checkout_url"] == "https://checkout.stripe.test/sub"
    customer = store.profiles[ALICE.id]["stripe_customer_id"]

    billing.subscriptions["sub_1"] = {"id": "sub_1", "customer": customer, "status": "active", "metadata": {},
                                      "items": {"data": [{"current_period_end": int(time.time()) + 30 * 86400}]}}
    webhook(client, {"type": "checkout.session.completed", "data": {"object": {
        "mode": "subscription", "subscription": "sub_1", "client_reference_id": ALICE.id, "metadata": {}}}})
    me = client.get("/api/me").json()
    assert me["is_pro"] is True
    assert me["subscription_current_period_end"]

    # Pro: reports are included, no checkout
    res = client.post("/api/reports", json=REPORT_REQUEST).json()
    assert res["status"] == "included" and "checkout_url" not in res
    assert client.get(f"/api/reports/{res['id']}/pdf").status_code == 200
    assert client.post("/api/billing/subscribe", json=SUBSCRIBE).status_code == 400
    assert client.post("/api/billing/portal").json()["url"].startswith("https://billing.stripe.test")

    # Cancellation
    billing.subscriptions["sub_1"]["status"] = "canceled"
    webhook(client, {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_1"}}})
    assert client.get("/api/me").json()["is_pro"] is False
    assert client.post("/api/reports", json=REPORT_REQUEST).status_code == 402


def test_old_subscription_event_does_not_override_new_one(env):
    client, store, billing, _ = env
    store.profiles[ALICE.id] = {"id": ALICE.id, "stripe_customer_id": "cus_9", "subscription_id": "sub_new",
                                "subscription_status": "active"}
    billing.subscriptions["sub_old"] = {"id": "sub_old", "customer": "cus_9", "status": "canceled", "metadata": {}}
    webhook(client, {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_old"}}})
    assert store.profiles[ALICE.id]["subscription_status"] == "active"


def test_pdf_download_is_rate_limited(env):
    client, store, billing, state = env
    store.profiles[ALICE.id] = {"id": ALICE.id, "subscription_status": "active"}
    report_id = client.post("/api/reports", json=REPORT_REQUEST).json()["id"]
    statuses = [client.get(f"/api/reports/{report_id}/pdf").status_code for _ in range(main.ai_limiter.max_calls + 1)]
    assert statuses[-1] == 429
    assert all(s == 200 for s in statuses[:-1])


def test_invalid_simulation_is_rejected_before_payment(env):
    client, store, billing, _ = env
    bad = {**REPORT_REQUEST, "simulation": {**SIM_INPUT, "property": {"surface": -1, "initial_cep": 300}}}
    assert client.post("/api/reports", json=bad).status_code == 422
    assert not billing.sessions


def test_supabase_token_verification(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-with-at-least-32-bytes!!")
    claims = {"sub": ALICE.id, "email": ALICE.email, "aud": "authenticated", "exp": int(time.time()) + 60}
    token = jwt.encode(claims, "test-secret-with-at-least-32-bytes!!", algorithm="HS256")
    assert verify_token(token) == ALICE

    client = TestClient(main.app)
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}x"}).status_code == 401
    expired = jwt.encode({**claims, "exp": int(time.time()) - 10}, "test-secret-with-at-least-32-bytes!!", algorithm="HS256")
    assert client.get("/api/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    wrong_aud = jwt.encode({**claims, "aud": "anon"}, "test-secret-with-at-least-32-bytes!!", algorithm="HS256")
    with pytest.raises(jwt.InvalidAudienceError):
        verify_token(wrong_aud)


def test_public_config_without_setup(monkeypatch):
    for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "STRIPE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    body = TestClient(main.app).get("/api/config").json()
    assert body["auth_enabled"] is False and body["billing_enabled"] is False


def test_real_stripe_signature_verification():
    import hashlib
    import hmac

    from api.billing import Billing

    billing = Billing("sk_test_x", "whsec_test", "price_r", "price_p", "https://app.test")
    payload = json.dumps({"id": "evt_1", "object": "event", "type": "checkout.session.completed",
                          "data": {"object": {"id": "cs_1"}}}).encode()
    ts = int(time.time())
    sig = hmac.new(b"whsec_test", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    event = billing.parse_event(payload, f"t={ts},v1={sig}")
    assert event["type"] == "checkout.session.completed"
    with pytest.raises(Exception):
        billing.parse_event(payload, f"t={ts},v1={'0' * 64}")


def test_price_labels():
    from api.billing import format_price, subscription_period_end

    assert format_price(3900, "eur") == "39 €"
    assert format_price(4990, "eur", "month") == "49,90 € / mois"
    assert subscription_period_end({"items": {"data": [{"current_period_end": 42}]}}) == 42
    assert subscription_period_end({"current_period_end": 7}) == 7


def test_pro_reports_do_not_need_a_new_acceptance(env):
    client, store, billing, _ = env
    store.profiles[ALICE.id] = {"id": ALICE.id, "subscription_status": "active"}
    res = client.post("/api/reports", json={**REPORT_REQUEST, "accept_terms": False})
    assert res.json()["status"] == "included"


def delete_account(client, confirm=True):
    return client.request("DELETE", "/api/me", json={"confirm": confirm})


def test_account_deletion_requires_confirmation(env):
    client, store, billing, _ = env
    client.get("/api/me")
    assert delete_account(client, confirm=False).status_code == 400
    assert not store.deleted_users


def test_account_deletion_removes_data_and_keeps_minimal_proof(env):
    client, store, billing, state = env
    report_id, session = legacy_report(store, billing)
    session["payment_status"] = "paid"
    webhook(client, {"type": "checkout.session.completed", "data": {"object": session}})
    state["user"] = BOB
    make_pro(store, BOB)
    client.post("/api/reports", json=REPORT_REQUEST)  # Someone else's report
    state["user"] = ALICE

    assert delete_account(client).json() == {"deleted": True}
    assert store.deleted_users == [ALICE.id]
    assert ALICE.id not in store.profiles
    assert all(r["user_id"] == BOB.id for r in store.reports.values())
    # Proof of purchase: references only, no email, address or simulation
    [record] = store.archive
    assert record["kind"] == "report"
    assert record["stripe_session_id"] == session["id"]
    assert record["terms_version"] == accounts.TERMS_VERSION
    assert record["amount_paid"] == 3900
    assert not {"email", "address", "meta", "simulation"} & set(record)


def test_account_deletion_cancels_running_subscription(env):
    client, store, billing, _ = env
    store.profiles[ALICE.id] = {"id": ALICE.id, "stripe_customer_id": "cus_1", "subscription_id": "sub_1",
                                "subscription_status": "active", "terms_version": accounts.TERMS_VERSION}
    assert delete_account(client).status_code == 200
    assert billing.canceled == ["sub_1"]
    assert store.archive[0]["kind"] == "subscription"


def test_account_deletion_does_not_touch_ended_subscription(env):
    client, store, billing, _ = env
    store.profiles[ALICE.id] = {"id": ALICE.id, "subscription_id": "sub_1", "subscription_status": "canceled"}
    assert delete_account(client).status_code == 200
    assert billing.canceled == []


def test_account_deletion_aborts_if_subscription_cannot_be_canceled(env):
    client, store, billing, _ = env
    store.profiles[ALICE.id] = {"id": ALICE.id, "subscription_id": "sub_1", "subscription_status": "active"}
    main.app.dependency_overrides[accounts.optional_billing_dep] = lambda: None
    assert delete_account(client).status_code == 503
    assert not store.deleted_users


def test_account_deletion_requires_login():
    assert TestClient(main.app).request("DELETE", "/api/me", json={"confirm": True}).status_code == 401


@pytest.mark.parametrize("automatic_tax", [False, True])
def test_checkout_tax_parameters(automatic_tax):
    import asyncio

    from api.billing import Billing

    billing = Billing("sk_test_x", "whsec", "price_r", "price_p", "https://sprea.vercel.app", automatic_tax=automatic_tax)
    sent = []

    async def fake_create(params):
        sent.append(params)
        return {"id": "cs_1", "url": "https://checkout.stripe.test/cs_1"}

    billing.client.v1.checkout.sessions.create_async = fake_create
    asyncio.run(billing.report_checkout("r1", "u1", "cus_1"))
    asyncio.run(billing.subscription_checkout("u1", "cus_1"))
    for params in sent:
        assert params["success_url"].startswith("https://sprea.vercel.app/?")
        assert ("automatic_tax" in params) is automatic_tax
        if automatic_tax:
            assert params["automatic_tax"] == {"enabled": True}
            assert params["tax_id_collection"] == {"enabled": True}
            assert params["customer_update"] == {"address": "auto", "name": "auto"}


def test_claude_analysis_is_generated_once_and_stored(env, monkeypatch):
    import httpx
    from api.ai_service import ai_service

    client, store, billing, state = env
    store.profiles[ALICE.id] = {"id": ALICE.id, "email": ALICE.email, "subscription_status": "active"}
    calls = []
    sections = {k: f"Texte {k} pour ce logement de 85 m²." for k in ("verdict", "diagnostic", "strategie", "financement", "profil")}

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "rediger_analyse",
                                                      "input": {**sections, "vigilance": ["Premier point à vérifier.", "Second point à vérifier."]}}]})

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(ai_service, "transport", httpx.MockTransport(handler))
    report_id = client.post("/api/reports", json=REPORT_REQUEST).json()["id"]
    assert client.get(f"/api/reports/{report_id}/pdf").status_code == 200
    assert json.loads(store.reports[report_id]["narrative"])["source"] == "claude"
    # Second download reuses the stored analysis
    assert client.get(f"/api/reports/{report_id}/pdf").status_code == 200
    assert len(calls) == 1
    # The street address is never sent
    prompt = json.loads(calls[0].content)["messages"][0]["content"]
    assert "rue de l" not in prompt and "Église" not in prompt
    assert "surface_m2" in prompt


def test_report_uses_local_dvf_price_for_green_value(env, monkeypatch):
    client, store, billing, state = env
    store.profiles[ALICE.id] = {"id": ALICE.id, "email": ALICE.email, "subscription_status": "active"}
    seen = {}

    async def fake_price(insee, building_type, lat=None, lon=None, surface=None):
        seen.update(insee=insee, lat=lat)
        return {"price_per_m2": 3100, "source": "prix médian DVF de 42 ventes de maisons à Lille (2024-2025)"}

    monkeypatch.setattr(accounts, "market_price", fake_price)
    built = {}
    real_build = accounts.build_report
    monkeypatch.setattr(accounts, "build_report", lambda meta, sim: built.setdefault("r", real_build(meta, sim)))
    request = {**REPORT_REQUEST, "meta": {**REPORT_REQUEST["meta"], "insee_code": "59350", "latitude": 50.63, "longitude": 3.06}}
    report_id = client.post("/api/reports", json=request).json()["id"]
    assert client.get(f"/api/reports/{report_id}/pdf").status_code == 200
    assert seen == {"insee": "59350", "lat": 50.63}
    assert built["r"]["price_per_m2"] == 3100 and not built["r"]["price_is_default"]


def test_prospection_is_detailed_for_pro_only(env, monkeypatch):
    client, store, billing, state = env

    async def fake_search(bbox, labels, kind=None, since=None):
        return {"addresses": [{"address": "1 Rue des Brigittines 59800 Lille", "lat": 50.633285, "lon": 3.069252,
                               "insee": "59350", "worst": "G", "dpe": [{"number": "2659E0077758E", "label": "G"}]}],
                "dwellings": 1, "total": 1, "truncated": False}

    monkeypatch.setattr(accounts.prospection, "search", fake_search)
    res = client.get("/api/prospection?bbox=3.05,50.63,3.07,50.64").json()
    assert res["locked"] is True
    assert res["addresses"] == [{"lat": 50.633, "lon": 3.069, "worst": "G", "count": 1}]

    store.profiles[ALICE.id]["subscription_status"] = "active"
    # Pro, but the map terms are not accepted yet: still no address
    res = client.get("/api/prospection?bbox=3.05,50.63,3.07,50.64").json()
    assert res["terms_required"] is True and "address" not in res["addresses"][0]

    assert client.post("/api/prospection/terms", json={"terms_version": "old", "accept": True}).status_code == 409
    assert client.post("/api/prospection/terms", json={"terms_version": accounts.TERMS_VERSION}).status_code == 400
    ok = client.post("/api/prospection/terms", json={"terms_version": accounts.TERMS_VERSION, "accept": True}).json()
    assert ok["accepted"] and store.acceptances[-1]["terms_version"] == accounts.TERMS_VERSION

    res = client.get("/api/prospection?bbox=3.05,50.63,3.07,50.64").json()
    assert res["locked"] is False and res["addresses"][0]["address"].startswith("1 Rue")

    # New version of the terms: acceptance asked again
    monkeypatch.setattr(accounts, "TERMS_VERSION", "2099-01-01")
    assert client.get("/api/prospection?bbox=3.05,50.63,3.07,50.64").json()["terms_required"] is True
    monkeypatch.undo()
    monkeypatch.setattr(accounts.prospection, "search", fake_search)

    # The acceptance survives account deletion in the archive
    assert client.request("DELETE", "/api/me", json={"confirm": True}).status_code == 200
    archived = [a for a in store.archive if a["kind"] == "prospection_terms"]
    assert archived and archived[0]["terms_accepted_at"]
    store.profiles[ALICE.id] = {"id": ALICE.id, "email": ALICE.email, "subscription_status": "active"}

    async def too_large(*a, **k):
        raise accounts.prospection.AreaTooLarge("Zone trop grande : zoomez sur un quartier.")
    monkeypatch.setattr(accounts.prospection, "search", too_large)
    assert client.get("/api/prospection?bbox=1,2,3,4").status_code == 400
    main.search_limiter.calls.clear()


def test_prospection_requires_login():
    assert TestClient(main.app).get("/api/prospection?bbox=3.05,50.63,3.07,50.64").status_code == 401



def test_owner_contact_page_flow(env):
    client, store, billing, state = env
    from api.ratelimit import lead_limiter
    lead_limiter.calls.clear()
    link_req = {"dpe_number": "2659E0077758E", "address": "1 Rue des Brigittines 59800 Lille", "label": "F"}

    # Pro + accepted terms + agency name required
    assert client.post("/api/prospection/links", json=link_req).status_code == 402
    store.profiles[ALICE.id]["subscription_status"] = "active"
    assert client.post("/api/prospection/links", json=link_req).status_code == 403
    client.post("/api/prospection/terms", json={"terms_version": accounts.TERMS_VERSION, "accept": True})
    assert client.post("/api/prospection/links", json=link_req).status_code == 409
    assert client.put("/api/agent-page", json={"agency_name": "Agence du Vieux-Lille", "phone": "abc"}).status_code == 422
    assert client.put("/api/agent-page", json={"agency_name": "Agence du Vieux-Lille", "agent_name": "Tarik",
                                               "phone": "03 20 00 00 00", "email": "Contact@Agence.fr"}).status_code == 200
    code = client.post("/api/prospection/links", json=link_req).json()["code"]
    assert len(code) == 8
    # Same dwelling: same link
    assert client.post("/api/prospection/links", json=link_req).json()["code"] == code

    # Public page, no login
    anonymous = TestClient(main.app)
    page = anonymous.get(f"/api/l/{code.lower()}").json()
    assert page["agency"]["agency_name"] == "Agence du Vieux-Lille" and page["dpe_number"] == "2659E0077758E"
    assert "Agence du Vieux-Lille" in page["consent_text"]
    assert store.links[code]["visits"] == 1
    assert anonymous.get("/api/l/AAAAAAAA").status_code == 404
    assert anonymous.get("/api/l/../x").status_code == 404

    # Callback request: consent and a phone or email required
    lead = {"name": "Marie Martin", "phone": "06 12 34 56 78", "message": "Rappel le soir"}
    assert anonymous.post(f"/api/l/{code}/lead", json=lead).status_code == 400
    assert anonymous.post(f"/api/l/{code}/lead", json={"name": "Marie", "consent": True}).status_code == 400
    assert anonymous.post(f"/api/l/{code}/lead", json={**lead, "consent": True, "website": "spam"}).json()["received"]
    assert store.leads == []  # Honeypot
    assert anonymous.post(f"/api/l/{code}/lead", json={**lead, "consent": True}).status_code == 200
    assert store.leads[0]["consent_text"].startswith("J'accepte que Agence du Vieux-Lille")

    # The agent sees it, with the address; another user does not
    leads = client.get("/api/leads").json()["leads"]
    assert leads[0]["name"] == "Marie Martin" and leads[0]["address"].startswith("1 Rue")
    lead_id = leads[0]["id"]
    assert client.patch(f"/api/leads/{lead_id}", json={"status": "contacted"}).status_code == 200
    state["user"] = BOB
    assert client.get("/api/leads").json()["leads"] == []
    assert client.delete(f"/api/leads/{lead_id}").status_code == 404
    state["user"] = ALICE
    assert client.delete(f"/api/leads/{lead_id}").status_code == 200
    lead_limiter.calls.clear()
    main.search_limiter.calls.clear()


def test_quote_request_is_stored(env, monkeypatch):
    client, store, billing, _ = env
    store.quotes = []

    async def create_quote_request(row):
        store.quotes.append(row)

    store.create_quote_request = create_quote_request
    main.lead_limiter.calls.clear() if hasattr(main, "lead_limiter") else None
    body = {"offer": "agence", "name": "Jeanne Martin", "company": "Agence du Centre", "email": "Jeanne@Agence.fr",
            "agents": 4, "message": "Démo pour l'équipe"}
    assert client.post("/api/quote", json=body).status_code == 200
    assert store.quotes[0]["email"] == "jeanne@agence.fr" and store.quotes[0]["agents"] == 4
    assert client.post("/api/quote", json={**body, "email": "pas-un-email"}).status_code == 422
    assert client.post("/api/quote", json={**body, "offer": "solo"}).status_code == 422
    assert client.post("/api/quote", json={**body, "website": "spam"}).json() == {"received": True}
    assert len(store.quotes) == 1


def test_shared_test_account_cannot_be_deleted(env):
    client, store, _, state = env
    state["user"] = User(id="33333333-3333-3333-3333-333333333333", email="test@sprea.invalid")
    make_pro(store, state["user"])
    res = delete_account(client)
    assert res.status_code == 403
    assert state["user"].id in store.profiles


def test_approximate_location_from_vercel_headers(env):
    client = env[0]
    h = {"x-vercel-ip-latitude": "50.6292", "x-vercel-ip-longitude": "3.0573", "x-vercel-ip-country": "FR",
         "x-vercel-ip-city": "Villeneuve-d%27Ascq"}
    assert client.get("/api/geo", headers=h).json() == {"lat": 50.6292, "lon": 3.0573, "city": "Villeneuve-d'Ascq"}
    # Abroad (no DPE) or no header: the map opens on its default place
    assert client.get("/api/geo", headers={**h, "x-vercel-ip-country": "BE"}).json()["lat"] is None
    assert client.get("/api/geo").json() == {"lat": None, "lon": None, "city": None}
