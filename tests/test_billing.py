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
