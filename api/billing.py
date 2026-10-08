"""Stripe integration: Checkout for single reports and the Pro subscription,
Customer Portal, webhook signature verification.

Prices are created in the Stripe dashboard; their ids are given through
STRIPE_PRICE_REPORT (one-time) and STRIPE_PRICE_PRO (recurring).
"""
import logging
import os
from typing import Any, Dict, Optional

import stripe

logger = logging.getLogger(__name__)

PRO_ACTIVE_STATUSES = {"active", "trialing"}

# Reminder shown next to the pay button (acceptance itself is recorded before Checkout)
REPORT_CHECKOUT_MESSAGE = (
    "En payant, vous confirmez avoir accepté les CGV et demandé l'accès immédiat à votre rapport : "
    "vous renoncez à votre droit de rétractation dès sa mise à disposition."
)
PRO_CHECKOUT_MESSAGE = (
    "En payant, vous confirmez avoir accepté les CGV. Abonnement mensuel sans engagement, "
    "résiliable à tout moment depuis votre compte."
)


def format_price(unit_amount: int, currency: str, interval: Optional[str] = None) -> str:
    amount = f"{unit_amount // 100}" if unit_amount % 100 == 0 else f"{unit_amount / 100:.2f}".replace(".", ",")
    symbol = "€" if currency.lower() == "eur" else currency.upper()
    suffix = {"month": " / mois", "year": " / an"}.get(interval or "", "")
    return f"{amount} {symbol}{suffix}"


def subscription_period_end(subscription: Dict[str, Any]) -> Optional[int]:
    """current_period_end moved from the subscription to its items in recent API versions."""
    if subscription.get("current_period_end"):
        return subscription["current_period_end"]
    items = (subscription.get("items") or {}).get("data") or []
    return items[0].get("current_period_end") if items else None


class Billing:
    def __init__(self, secret_key: str, webhook_secret: str, price_report: str, price_pro: str, app_url: str):
        self.client = stripe.StripeClient(secret_key, http_client=stripe.HTTPXClient())
        self.webhook_secret = webhook_secret
        self.price_report = price_report
        self.price_pro = price_pro
        self.app_url = app_url.rstrip("/")
        self._price_labels: Dict[str, str] = {}

    async def price_label(self, price_id: str) -> Optional[str]:
        if price_id not in self._price_labels:
            try:
                price = await self.client.v1.prices.retrieve_async(price_id)
                recurring = price.get("recurring") or {}
                self._price_labels[price_id] = format_price(price["unit_amount"], price["currency"], recurring.get("interval"))
            except stripe.StripeError as e:
                logger.error(f"Cannot load Stripe price {price_id}: {e}")
                return None
        return self._price_labels[price_id]

    async def create_customer(self, user_id: str, email: Optional[str]) -> str:
        customer = await self.client.v1.customers.create_async(params={
            "email": email,
            "metadata": {"user_id": user_id},
        })
        return customer["id"]

    async def report_checkout(self, report_id: str, user_id: str, customer_id: str) -> Dict[str, str]:
        session = await self.client.v1.checkout.sessions.create_async(params={
            "mode": "payment",
            "customer": customer_id,
            "client_reference_id": user_id,
            "line_items": [{"price": self.price_report, "quantity": 1}],
            "metadata": {"kind": "report", "report_id": report_id, "user_id": user_id},
            # Invoice available to professionals buying a single report
            "invoice_creation": {"enabled": True},
            "allow_promotion_codes": True,
            "custom_text": {"submit": {"message": REPORT_CHECKOUT_MESSAGE}},
            "success_url": f"{self.app_url}/?report={report_id}&checkout=success",
            "cancel_url": f"{self.app_url}/?report={report_id}&checkout=cancel",
        })
        return {"id": session["id"], "url": session["url"]}

    async def subscription_checkout(self, user_id: str, customer_id: str) -> str:
        session = await self.client.v1.checkout.sessions.create_async(params={
            "mode": "subscription",
            "customer": customer_id,
            "client_reference_id": user_id,
            "line_items": [{"price": self.price_pro, "quantity": 1}],
            "metadata": {"kind": "subscription", "user_id": user_id},
            "subscription_data": {"metadata": {"user_id": user_id}},
            "allow_promotion_codes": True,
            "custom_text": {"submit": {"message": PRO_CHECKOUT_MESSAGE}},
            "success_url": f"{self.app_url}/?checkout=pro_success",
            "cancel_url": f"{self.app_url}/?checkout=pro_cancel",
        })
        return session["url"]

    async def portal_url(self, customer_id: str) -> str:
        session = await self.client.v1.billing_portal.sessions.create_async(params={
            "customer": customer_id,
            "return_url": self.app_url,
        })
        return session["url"]

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        return await self.client.v1.checkout.sessions.retrieve_async(session_id)

    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        return await self.client.v1.subscriptions.retrieve_async(subscription_id)

    def parse_event(self, payload: bytes, signature: Optional[str]) -> Dict[str, Any]:
        """Raises ValueError / stripe.SignatureVerificationError on invalid input."""
        return self.client.construct_event(payload, signature, self.webhook_secret)


_billing: Optional[Billing] = None

REQUIRED_ENV = ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_REPORT", "STRIPE_PRICE_PRO", "PUBLIC_APP_URL"]


def billing_configured() -> bool:
    return all(os.getenv(k) for k in REQUIRED_ENV)


def get_billing() -> Billing:
    """FastAPI dependency (overridden in tests)."""
    global _billing
    if _billing is None:
        if not billing_configured():
            raise RuntimeError(f"Stripe is not configured: {', '.join(REQUIRED_ENV)} must be set")
        _billing = Billing(
            os.environ["STRIPE_SECRET_KEY"],
            os.environ["STRIPE_WEBHOOK_SECRET"],
            os.environ["STRIPE_PRICE_REPORT"],
            os.environ["STRIPE_PRICE_PRO"],
            os.environ["PUBLIC_APP_URL"],
        )
    return _billing
