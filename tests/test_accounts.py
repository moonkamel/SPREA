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

    async def ensure_profile(self, user_id, email):
        profile = self.profiles.setdefault(user_id, {"id": user_id})
        profile["email"] = email
        return dict(profile)

    async def get_profile(self, user_id):
        p = self.profiles.get(user_id)
        return dict(p) if p else None

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

    async def delete_user(self, user_id):
        # Cascade of the real schema
        self.deleted_users.append(user_id)
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

    async def create_customer(self, user_id, email):
        self.customers.append(user_id)
        return f"cus_{len(self.customers)}"

    async def report_checkout(self, report_id, user_id, customer_id):
        session_id = f"cs_{len(self.sessions) + 1}"
        self.sessions[session_id] = {"id": session_id, "payment_status": "unpaid", "amount_total": 3900,
                                     "currency": "eur", "metadata": {"kind": "report", "report_id": report_id}}
        return {"id": session_id, "url": f"https://checkout.stripe.test/{session_id}"}

    async def subscription_checkout(self, user_id, customer_id):
        return "https://checkout.stripe.test/sub"

    async def portal_url(self, customer_id):
        return "https://billing.stripe.test/portal"

    async def cancel_subscription(self, subscription_id):
        self.canceled.append(subscription_id)

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


def test_report_purchase_flow_with_webhook(env):
    client, store, billing, _ = env
    res = client.post("/api/reports", json=REPORT_REQUEST)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "pending"
    assert body["checkout_url"].startswith("https://checkout.stripe.test/")
    report_id = body["id"]
    assert store.profiles[ALICE.id]["stripe_customer_id"] == "cus_1"

    # Not paid yet
    assert client.get(f"/api/reports/{report_id}/pdf").status_code == 402

    session = billing.sessions[store.reports[report_id]["stripe_session_id"]]
    session["payment_status"] = "paid"
    assert webhook(client, {"type": "checkout.session.completed", "data": {"object": session}}).status_code == 200
    assert store.reports[report_id]["status"] == "paid"
    assert store.reports[report_id]["amount_paid"] == 3900

    res = client.get(f"/api/reports/{report_id}/pdf")
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")
    assert "Rapport_SPREA_1_rue_de_l_Eglise_Lille.pdf" in res.headers["content-disposition"]
    # Without an API key the rule-based analysis is used and not stored,
    # so the report gets Claude's analysis once a key is configured
    assert store.reports[report_id]["narrative"] is None

    reports = client.get("/api/me").json()["reports"]
    assert [r["id"] for r in reports] == [report_id]


def test_payment_confirmed_without_webhook(env):
    client, store, billing, _ = env
    report_id = client.post("/api/reports", json=REPORT_REQUEST).json()["id"]
    assert client.get(f"/api/reports/{report_id}").json()["status"] == "pending"
    billing.sessions[store.reports[report_id]["stripe_session_id"]]["payment_status"] = "paid"
    assert client.get(f"/api/reports/{report_id}").json()["status"] == "paid"


def test_webhook_rejects_bad_signature(env):
    client, store, billing, _ = env
    report_id = client.post("/api/reports", json=REPORT_REQUEST).json()["id"]
    session = dict(billing.sessions[store.reports[report_id]["stripe_session_id"]], payment_status="paid")
    res = webhook(client, {"type": "checkout.session.completed", "data": {"object": session}}, signature="forged")
    assert res.status_code == 400
    assert store.reports[report_id]["status"] == "pending"


def test_session_must_match_report(env):
    client, store, billing, _ = env
    first = client.post("/api/reports", json=REPORT_REQUEST).json()["id"]
    second = client.post("/api/reports", json=REPORT_REQUEST).json()["id"]
    # A paid session for the first report cannot unlock the second one
    session = dict(billing.sessions[store.reports[first]["stripe_session_id"]], payment_status="paid")
    session["metadata"] = {"kind": "report", "report_id": second}
    webhook(client, {"type": "checkout.session.completed", "data": {"object": session}})
    assert store.reports[second]["status"] == "pending"


def test_reports_are_private(env):
    client, store, billing, state = env
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
    assert client.post("/api/reports", json=REPORT_REQUEST).json()["status"] == "pending"


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


def test_purchase_requires_terms_acceptance(env):
    client, store, billing, _ = env
    res = client.post("/api/reports", json={**REPORT_REQUEST, "accept_terms": False})
    assert res.status_code == 400
    assert not billing.sessions and not store.reports
    assert client.post("/api/billing/subscribe", json={"accept_terms": False}).status_code == 400


def test_terms_acceptance_is_recorded(env):
    client, store, billing, _ = env
    report_id = client.post("/api/reports", json=REPORT_REQUEST).json()["id"]
    assert store.reports[report_id]["terms_version"] == accounts.TERMS_VERSION
    assert store.reports[report_id]["terms_accepted_at"]
    client.post("/api/billing/subscribe", json=SUBSCRIBE)
    assert store.profiles[ALICE.id]["terms_version"] == accounts.TERMS_VERSION


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
    report_id = client.post("/api/reports", json=REPORT_REQUEST).json()["id"]
    session = billing.sessions[store.reports[report_id]["stripe_session_id"]]
    session["payment_status"] = "paid"
    webhook(client, {"type": "checkout.session.completed", "data": {"object": session}})
    state["user"] = BOB
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
