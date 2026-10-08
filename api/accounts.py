"""Accounts, paid reports and Pro subscription.

Flow:
- The simulation is free and anonymous.
- A PDF report requires an account. A Pro subscriber gets it immediately
  ("included"); anyone else pays it once through Stripe Checkout ("paid").
- Payment is confirmed by the Stripe webhook, and also checked directly
  against Stripe when the user comes back from Checkout (webhooks can lag).
- Paid reports can be downloaded again at any time. The AI narrative is
  generated once and stored.
"""
import logging
import os
import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

try:
    from api.ai_service import ai_service
    from api.auth import User, current_user
    from api.billing import PRO_ACTIVE_STATUSES, Billing, billing_configured, get_billing, subscription_period_end
    from api.pdf_service import pdf_service
    from api.ratelimit import ai_limiter
    from api.simulation import SimulationInput, simulate as run_simulation
    from api.store import SupabaseStore, get_store
except ImportError:
    from ai_service import ai_service
    from auth import User, current_user
    from billing import PRO_ACTIVE_STATUSES, Billing, billing_configured, get_billing, subscription_period_end
    from pdf_service import pdf_service
    from ratelimit import ai_limiter
    from simulation import SimulationInput, simulate as run_simulation
    from store import SupabaseStore, get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# --- Dependencies ---

def store_dep() -> SupabaseStore:
    try:
        return get_store()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Les comptes ne sont pas encore configurés.")


def billing_dep() -> Billing:
    try:
        return get_billing()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Le paiement n'est pas encore configuré.")


def optional_billing_dep() -> Optional[Billing]:
    return get_billing() if billing_configured() else None


# --- Helpers ---

def is_pro(profile: Optional[Dict[str, Any]]) -> bool:
    return bool(profile) and profile.get("subscription_status") in PRO_ACTIVE_STATUSES


def safe_filename(text: str) -> str:
    """ASCII-only filename, safe to put in a Content-Disposition header."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_")[:80] or "bien"


def iso_from_timestamp(ts: Optional[int]) -> Optional[str]:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


async def ensure_customer(store: SupabaseStore, billing: Billing, user: User, profile: Dict[str, Any]) -> str:
    if profile.get("stripe_customer_id"):
        return profile["stripe_customer_id"]
    customer_id = await billing.create_customer(user.id, user.email)
    await store.update_profile(user.id, {"stripe_customer_id": customer_id})
    return customer_id


async def owned_report(store: SupabaseStore, report_id: UUID, user: User) -> Dict[str, Any]:
    report = await store.get_report(str(report_id))
    if not report or report["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Rapport introuvable.")
    return report


async def mark_report_paid(store: SupabaseStore, report: Dict[str, Any], session: Dict[str, Any]) -> bool:
    """Idempotent: only a pending report whose Checkout session matches is updated."""
    if report["status"] != "pending" or report.get("stripe_session_id") != session["id"]:
        return False
    if session.get("payment_status") != "paid":
        return False
    await store.update_report(report["id"], {
        "status": "paid",
        "paid_at": datetime.now(timezone.utc).isoformat(),
        "amount_paid": session.get("amount_total"),
        "currency": session.get("currency"),
    })
    return True


async def sync_subscription(store: SupabaseStore, billing: Billing, subscription_id: str,
                            user_id: Optional[str] = None) -> None:
    """Copies the current state of a subscription (fetched from Stripe, so event
    ordering does not matter) to the owner's profile."""
    sub = await billing.get_subscription(subscription_id)
    profile = await store.get_profile(user_id) if user_id else None
    if not profile:
        profile = await store.get_profile_by_customer(sub["customer"])
    if not profile and (sub.get("metadata") or {}).get("user_id"):
        profile = await store.get_profile(sub["metadata"]["user_id"])
    if not profile:
        logger.error(f"No profile for subscription {subscription_id}")
        return
    # An event about an old, ended subscription must not override a newer one
    if profile.get("subscription_id") not in (None, subscription_id) and sub["status"] not in PRO_ACTIVE_STATUSES:
        return
    await store.update_profile(profile["id"], {
        "stripe_customer_id": sub["customer"],
        "subscription_id": subscription_id,
        "subscription_status": sub["status"],
        "subscription_current_period_end": iso_from_timestamp(subscription_period_end(sub)),
    })


def build_report_data(meta: Dict[str, Any], simulation: SimulationInput) -> Dict[str, Any]:
    """Every figure of the report comes from the simulation engine."""
    sim = run_simulation(simulation)
    prop = simulation.property
    return {
        "address": meta.get("address") or "Adresse inconnue",
        "year": meta.get("year") or "N/A",
        "construction_period": meta.get("construction_period") or "N/A",
        "building_type": meta.get("building_type") or "Logement",
        "ademe_dpe_number": meta.get("ademe_dpe_number") or "N/A",
        "surface": prop.surface,
        "current_label": sim["current_label"],
        "new_label": sim["new_label"],
        "initial_cep": sim["initial_cep"],
        "new_cep": sim["new_cep"],
        "ges_value": sim["initial_ges"],
        "new_ges": sim["new_ges"],
        "total_cost": sim["cost"],
        "subsidies": sim["subsidies"],
        "cee_est": sim["cee_est"],
        "rest_to_pay": sim["rest_to_pay"],
        "latent_gain": sim["latent_gain"],
        "annual_savings": sim["annual_savings"],
        "roi_years": round(sim["roi_years"]) if sim["roi_years"] is not None else None,
        "detailed_costs": sim["detailed_costs"],
        "yield_brut": sim["yield_brut"],
        "cashflow": sim["cashflow"],
        "purchase_price": simulation.purchase_price,
        "ban_date": date.fromisoformat(sim["ban_date"]).strftime("%d/%m/%Y") if sim["ban_date"] else None,
        "eco_ptz_amount": sim["eco_ptz_amount"],
        "tax_benefit": sim["tax_benefit"],
        "has_iti": sim["has_iti"],
        "user_profile": "investisseur" if simulation.is_investor else "propriétaire",
    }


def report_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {k: report.get(k) for k in ("id", "address", "status", "created_at")}


# --- Schemas ---

class ReportMeta(BaseModel):
    address: str = Field(..., min_length=1, max_length=300)
    year: Optional[int] = None
    ademe_dpe_number: Optional[str] = Field(None, max_length=20)
    building_type: Optional[str] = Field(None, max_length=100)
    construction_period: Optional[str] = Field(None, max_length=100)


class ReportCreate(BaseModel):
    meta: ReportMeta
    simulation: SimulationInput


# --- Endpoints ---

@router.get("/config")
async def public_config():
    """Public settings for the frontend (the Supabase anon key is meant to be public)."""
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    billing_enabled = billing_configured()
    report_price = pro_price = None
    if billing_enabled:
        billing = get_billing()
        report_price = await billing.price_label(billing.price_report)
        pro_price = await billing.price_label(billing.price_pro)
    return {
        "auth_enabled": bool(supabase_url and anon_key),
        "supabase_url": supabase_url,
        "supabase_anon_key": anon_key,
        "billing_enabled": billing_enabled,
        "report_price": report_price,
        "pro_price": pro_price,
    }


@router.get("/me")
async def me(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    profile = await store.ensure_profile(user.id, user.email)
    reports = await store.list_reports(user.id)
    return {
        "email": user.email,
        "is_pro": is_pro(profile),
        "subscription_status": profile.get("subscription_status"),
        "subscription_current_period_end": profile.get("subscription_current_period_end"),
        "has_billing_account": bool(profile.get("stripe_customer_id")),
        "reports": [report_summary(r) for r in reports],
    }


@router.post("/reports")
async def create_report(data: ReportCreate, user: User = Depends(current_user),
                        store: SupabaseStore = Depends(store_dep),
                        billing: Optional[Billing] = Depends(optional_billing_dep)):
    """Creates a report. Pro: available immediately. Otherwise: returns a Checkout URL."""
    # Validates the simulation before anyone pays for it
    run_simulation(data.simulation)
    profile = await store.ensure_profile(user.id, user.email)
    row = {
        "user_id": user.id,
        "address": data.meta.address,
        "meta": data.meta.model_dump(mode="json"),
        "simulation": data.simulation.model_dump(mode="json"),
    }
    if is_pro(profile):
        report = await store.create_report({**row, "status": "included"})
        return {"id": report["id"], "status": "included"}

    if billing is None:
        raise HTTPException(status_code=503, detail="Le paiement n'est pas encore configuré.")
    customer_id = await ensure_customer(store, billing, user, profile)
    report = await store.create_report({**row, "status": "pending"})
    session = await billing.report_checkout(report["id"], user.id, customer_id)
    await store.update_report(report["id"], {"stripe_session_id": session["id"]})
    return {"id": report["id"], "status": "pending", "checkout_url": session["url"]}


@router.get("/reports/{report_id}")
async def get_report(report_id: UUID, user: User = Depends(current_user),
                     store: SupabaseStore = Depends(store_dep),
                     billing: Optional[Billing] = Depends(optional_billing_dep)):
    report = await owned_report(store, report_id, user)
    if report["status"] == "pending" and report.get("stripe_session_id") and billing:
        # Back from Checkout before the webhook: ask Stripe directly
        session = await billing.get_session(report["stripe_session_id"])
        if await mark_report_paid(store, report, session):
            report["status"] = "paid"
    return report_summary(report)


@router.get("/reports/{report_id}/pdf", dependencies=[Depends(ai_limiter)])
async def download_report(report_id: UUID, user: User = Depends(current_user),
                          store: SupabaseStore = Depends(store_dep)):
    report = await owned_report(store, report_id, user)
    if report["status"] not in ("paid", "included"):
        raise HTTPException(status_code=402, detail="Ce rapport n'a pas encore été payé.")

    report_data = build_report_data(report["meta"], SimulationInput.model_validate(report["simulation"]))
    narrative = report.get("narrative")
    if not narrative:
        narrative = await ai_service.generate_narrative(report_data, report_data["user_profile"])
        await store.update_report(report["id"], {"narrative": narrative})
    report_data["ai_narrative"] = narrative

    pdf_bytes = pdf_service.generate(report_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Rapport_SPREA_{safe_filename(report['address'])}.pdf"},
    )


@router.post("/billing/subscribe")
async def subscribe(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep),
                    billing: Billing = Depends(billing_dep)):
    profile = await store.ensure_profile(user.id, user.email)
    if is_pro(profile):
        raise HTTPException(status_code=400, detail="Votre abonnement Pro est déjà actif.")
    customer_id = await ensure_customer(store, billing, user, profile)
    return {"checkout_url": await billing.subscription_checkout(user.id, customer_id)}


@router.post("/billing/portal")
async def billing_portal(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep),
                         billing: Billing = Depends(billing_dep)):
    profile = await store.ensure_profile(user.id, user.email)
    if not profile.get("stripe_customer_id"):
        raise HTTPException(status_code=400, detail="Aucun compte de facturation.")
    return {"url": await billing.portal_url(profile["stripe_customer_id"])}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, store: SupabaseStore = Depends(store_dep),
                         billing: Billing = Depends(billing_dep)):
    payload = await request.body()
    try:
        event = billing.parse_event(payload, request.headers.get("stripe-signature"))
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    obj = event["data"]["object"]
    logger.info(f"Stripe event {event_type}")

    if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        metadata = obj.get("metadata") or {}
        if metadata.get("kind") == "report" and metadata.get("report_id"):
            report = await store.get_report(metadata["report_id"])
            if report:
                await mark_report_paid(store, report, obj)
        elif obj.get("mode") == "subscription" and obj.get("subscription"):
            await sync_subscription(store, billing, obj["subscription"], user_id=obj.get("client_reference_id"))
    elif event_type in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"):
        await sync_subscription(store, billing, obj["id"])

    return {"received": True}
