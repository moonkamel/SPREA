"""Billing against real stripe-python objects (not dicts since stripe 15)."""
import asyncio
import json
import time

import stripe

from api.billing import Billing


def make_billing():
    return Billing("sk_test_x", "whsec_test", "price_report", "price_pro", "https://sprea.vercel.app")


def stripe_obj(data):
    return stripe.StripeObject.construct_from(data, "sk_test_x")


def test_price_label_from_stripe_object():
    billing = make_billing()

    async def retrieve(price_id):
        return stripe_obj({"id": price_id, "unit_amount": 4900, "currency": "eur", "recurring": {"interval": "month"}})

    billing.client.v1.prices.retrieve_async = retrieve
    assert asyncio.run(billing.price_label("price_pro")) == "49 € / mois"


def test_price_label_never_raises():
    billing = make_billing()

    async def retrieve(price_id):
        raise AttributeError("unexpected")

    billing.client.v1.prices.retrieve_async = retrieve
    assert asyncio.run(billing.price_label("price_report")) is None


def test_session_and_subscription_are_dicts():
    billing = make_billing()

    async def get_session(session_id):
        return stripe_obj({"id": session_id, "payment_status": "paid", "metadata": {"report_id": "r1"}})

    async def get_sub(sub_id):
        return stripe_obj({"id": sub_id, "status": "active", "items": {"data": [{"current_period_end": 123}]}})

    billing.client.v1.checkout.sessions.retrieve_async = get_session
    billing.client.v1.subscriptions.retrieve_async = get_sub
    session = asyncio.run(billing.get_session("cs_1"))
    assert session.get("payment_status") == "paid" and session["metadata"].get("report_id") == "r1"
    sub = asyncio.run(billing.get_subscription("sub_1"))
    assert sub.get("status") == "active"


def test_parse_event_returns_dict():
    billing = make_billing()
    payload = json.dumps({
        "id": "evt_1", "object": "event", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_1", "object": "checkout.session", "metadata": {"kind": "report"}}},
    })
    ts = int(time.time())
    sig = stripe.WebhookSignature._compute_signature(f"{ts}.{payload}", "whsec_test")
    event = billing.parse_event(payload.encode(), f"t={ts},v1={sig}")
    assert event["data"]["object"].get("metadata").get("kind") == "report"


def test_plan_checkout_adds_vat_when_stripe_tax_is_off():
    billing = make_billing()
    sent, created = [], []

    async def list_prices(params):
        assert params["lookup_keys"] == ["solo_yearly"]
        return stripe_obj({"data": [{"id": "price_solo_y"}]})

    async def list_rates(params):
        return stripe_obj({"data": [{"id": "txr_other", "metadata": {}}]})

    async def create_rate(params):
        created.append(params)
        return stripe_obj({"id": "txr_vat"})

    async def create_session(params):
        sent.append(params)
        return {"id": "cs_1", "url": "https://checkout.stripe.test/cs_1"}

    billing.client.v1.prices.list_async = list_prices
    billing.client.v1.tax_rates.list_async = list_rates
    billing.client.v1.tax_rates.create_async = create_rate
    billing.client.v1.checkout.sessions.create_async = create_session
    asyncio.run(billing.subscription_checkout("u1", "cus_1", "solo_yearly"))
    asyncio.run(billing.subscription_checkout("u1", "cus_1", "solo_yearly"))
    assert sent[0]["line_items"] == [{"price": "price_solo_y", "quantity": 1, "tax_rates": ["txr_vat"]}]
    assert sent[0]["tax_id_collection"] == {"enabled": True}
    assert len(created) == 1 and created[0]["percentage"] == 20 and created[0]["inclusive"] is False


def test_unknown_plan_falls_back_to_pro_price():
    billing = make_billing()

    async def list_prices(params):
        return stripe_obj({"data": []})

    billing.client.v1.prices.list_async = list_prices
    assert asyncio.run(billing.plan_price("solo_monthly")) == "price_pro"
