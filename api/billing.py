"""Stripe integration: Checkout for single reports and the Pro subscription,
Customer Portal, webhook signature verification.

Prices are created in the Stripe dashboard. The subscription plans are found
by their lookup key (solo_monthly, solo_yearly), prices excluding VAT; the
former STRIPE_PRICE_PRO is the fallback. STRIPE_PRICE_REPORT (one-time) is
kept for the reports bought before the subscription-only offer.
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
    "En payant, vous confirmez avoir accepté les CGV. Abonnement sans engagement, résiliable à tout moment "
    "depuis votre compte. Satisfait ou remboursé pendant 14 jours."
)

# Subscription plans: Stripe lookup keys
PLANS = ("solo_monthly", "solo_yearly")
VAT_RATE_KEY = "tva20"


def format_price(unit_amount: int, currency: str, interval: Optional[str] = None) -> str:
    amount = f"{unit_amount // 100}" if unit_amount % 100 == 0 else f"{unit_amount / 100:.2f}".replace(".", ",")
    symbol = "€" if currency.lower() == "eur" else currency.upper()
    suffix = {"month": " / mois", "year": " / an"}.get(interval or "", "")
    return f"{amount} {symbol}{suffix}"


def as_dict(obj: Any) -> Dict[str, Any]:
    """Stripe objects are not dicts since stripe-python 15 (obj.get() raises):
    everything leaving this module is converted to plain dicts."""
    return obj.to_dict() if isinstance(obj, stripe.StripeObject) else obj


def subscription_period_end(subscription: Dict[str, Any]) -> Optional[int]:
    """current_period_end moved from the subscription to its items in recent API versions."""
    if subscription.get("current_period_end"):
        return subscription["current_period_end"]
    items = (subscription.get("items") or {}).get("data") or []
    return items[0].get("current_period_end") if items else None


class Billing:
    def __init__(self, secret_key: str, webhook_secret: str, price_report: str, price_pro: str, app_url: str,
                 automatic_tax: bool = False):
        self.client = stripe.StripeClient(secret_key, http_client=stripe.HTTPXClient())
        self.automatic_tax = automatic_tax
        self.webhook_secret = webhook_secret
        self.price_report = price_report
        self.price_pro = price_pro
        self.app_url = app_url.rstrip("/")
        self._price_labels: Dict[str, str] = {}
        self._plan_prices: Dict[str, str] = {}
        self._vat_rate: Optional[str] = None

    async def price_label(self, price_id: str) -> Optional[str]:
        if price_id not in self._price_labels:
            try:
                price = as_dict(await self.client.v1.prices.retrieve_async(price_id))
                recurring = price.get("recurring") or {}
                self._price_labels[price_id] = format_price(price["unit_amount"], price["currency"], recurring.get("interval"))
            except Exception as e:  # Never break /api/config over a price label
                logger.error(f"Cannot load Stripe price {price_id}: {e}")
                return None
        return self._price_labels[price_id]

    async def plan_price(self, plan: str) -> str:
        """Price id of a plan, from its lookup key (falls back to STRIPE_PRICE_PRO)."""
        if plan not in self._plan_prices:
            try:
                prices = as_dict(await self.client.v1.prices.list_async(params={"lookup_keys": [plan], "active": True}))
                found = prices.get("data") or []
                if not found:
                    return self.price_pro
                self._plan_prices[plan] = found[0]["id"]
            except Exception as e:
                logger.error(f"Cannot load Stripe plan {plan}: {e}")
                return self.price_pro
        return self._plan_prices[plan]

    async def plan_labels(self) -> Dict[str, Optional[str]]:
        return {plan: await self.price_label(await self.plan_price(plan)) for plan in PLANS}

    async def vat_rate(self) -> Optional[str]:
        """20 % VAT tax rate added to prices excluding VAT when Stripe Tax is off
        (found or created once, tagged with metadata sprea=tva20)."""
        if self._vat_rate is None:
            try:
                rates = as_dict(await self.client.v1.tax_rates.list_async(params={"active": True, "limit": 100}))
                rate = next((r for r in rates.get("data") or [] if (r.get("metadata") or {}).get("sprea") == VAT_RATE_KEY), None)
                if rate is None:
                    rate = as_dict(await self.client.v1.tax_rates.create_async(params={
                        "display_name": "TVA", "percentage": 20, "inclusive": False, "country": "FR",
                        "jurisdiction": "FR", "tax_type": "vat", "description": "TVA 20 % (France)",
                        "metadata": {"sprea": VAT_RATE_KEY},
                    }))
                self._vat_rate = rate["id"]
            except Exception as e:
                logger.error(f"Cannot load the VAT rate: {e}")
                return None
        return self._vat_rate

    def _tax_params(self) -> Dict[str, Any]:
        """Stripe Tax: VAT computed from the customer's address, VAT number
        collected for professionals (shown on the invoice). Prices must be set
        to "tax inclusive" in Stripe since the site displays prices TTC."""
        if not self.automatic_tax:
            return {}
        return {
            "automatic_tax": {"enabled": True},
            "tax_id_collection": {"enabled": True},
            "billing_address_collection": "required",
            # Saves the address / company name entered in Checkout on the customer
            "customer_update": {"address": "auto", "name": "auto"},
        }

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
            **self._tax_params(),
            "success_url": f"{self.app_url}/?report={report_id}&checkout=success",
            "cancel_url": f"{self.app_url}/?report={report_id}&checkout=cancel",
        })
        return {"id": session["id"], "url": session["url"]}

    async def subscription_checkout(self, user_id: str, customer_id: str, plan: str = "solo_monthly") -> str:
        line = {"price": await self.plan_price(plan), "quantity": 1}
        if not self.automatic_tax:
            # Prices excluding VAT: add the VAT rate ourselves
            rate = await self.vat_rate()
            if rate:
                line["tax_rates"] = [rate]
        session = await self.client.v1.checkout.sessions.create_async(params={
            "mode": "subscription",
            "customer": customer_id,
            "client_reference_id": user_id,
            "line_items": [line],
            "metadata": {"kind": "subscription", "user_id": user_id, "plan": plan},
            "subscription_data": {"metadata": {"user_id": user_id, "plan": plan}},
            "allow_promotion_codes": True,
            # Professionals: company name and VAT number on the invoice
            "tax_id_collection": {"enabled": True},
            "billing_address_collection": "required",
            "customer_update": {"address": "auto", "name": "auto"},
            "custom_text": {"submit": {"message": PRO_CHECKOUT_MESSAGE}},
            **self._tax_params(),
            "success_url": f"{self.app_url}/?checkout=pro_success",
            "cancel_url": f"{self.app_url}/tarifs?checkout=pro_cancel",
        })
        return session["url"]

    async def portal_url(self, customer_id: str) -> str:
        session = await self.client.v1.billing_portal.sessions.create_async(params={
            "customer": customer_id,
            "return_url": self.app_url,
        })
        return session["url"]

    async def cancel_subscription(self, subscription_id: str) -> None:
        """Immediate cancellation (account deletion). Already canceled: nothing to do."""
        try:
            await self.client.v1.subscriptions.cancel_async(subscription_id)
        except stripe.InvalidRequestError as e:
            logger.info(f"Subscription {subscription_id} not cancelable: {e.user_message or e.code}")

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        return as_dict(await self.client.v1.checkout.sessions.retrieve_async(session_id))

    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        return as_dict(await self.client.v1.subscriptions.retrieve_async(subscription_id))

    def parse_event(self, payload: bytes, signature: Optional[str]) -> Dict[str, Any]:
        """Raises ValueError / stripe.SignatureVerificationError on invalid input."""
        return as_dict(self.client.construct_event(payload, signature, self.webhook_secret))


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
        # strip(): a space or newline pasted with a key breaks it silently
        env = {k: os.environ[k].strip() for k in REQUIRED_ENV}
        _billing = Billing(
            env["STRIPE_SECRET_KEY"],
            env["STRIPE_WEBHOOK_SECRET"],
            env["STRIPE_PRICE_REPORT"],
            env["STRIPE_PRICE_PRO"],
            env["PUBLIC_APP_URL"],
            automatic_tax=os.getenv("STRIPE_AUTOMATIC_TAX", "").lower() in ("1", "true", "yes"),
        )
    return _billing
