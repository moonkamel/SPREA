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
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from urllib.parse import unquote
from uuid import UUID

import httpx
import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

try:
    from api.ai_service import ai_service, parse_stored
    from api.auth import User, current_user
    from api.dvf import market_price
    from api.billing import AGENCY_PLANS, PRO_ACTIVE_STATUSES, Billing, billing_configured, get_billing, subscription_period_end
    from api.pdf_service import pdf_service
    from api.report_content import build_report, facts_for_writer
    from api.ratelimit import ai_limiter, search_limiter
    from api import prospection
    from api.simulation import SimulationInput, simulate as run_simulation
    from api.store import SupabaseStore, get_store
except ImportError:
    from ai_service import ai_service, parse_stored
    from auth import User, current_user
    from dvf import market_price
    from billing import AGENCY_PLANS, PRO_ACTIVE_STATUSES, Billing, billing_configured, get_billing, subscription_period_end
    from pdf_service import pdf_service
    from report_content import build_report, facts_for_writer
    from ratelimit import ai_limiter, search_limiter
    import prospection
    from simulation import SimulationInput, simulate as run_simulation
    from store import SupabaseStore, get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Version of the CGV shown to the user (src/legal.ts, CGV_VERSION): stored with
# each acceptance so we know which terms a customer agreed to.
TERMS_VERSION = "2026-10-09.1"
TERMS_REQUIRED = "Vous devez accepter les conditions générales de vente."


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

def org_active(profile: Optional[Dict[str, Any]]) -> bool:
    """Access through the user's agency, or the network the agency belongs to
    (the store adds org / org_parent to the profile)."""
    if not profile:
        return False
    return any((o or {}).get("subscription_status") in PRO_ACTIVE_STATUSES
               for o in (profile.get("org"), profile.get("org_parent")))


# Shared test accounts ("test" on the login form), created by hand in Supabase
# under a reserved domain that cannot receive emails (src/account.tsx)
SHARED_ACCOUNT_DOMAIN = "@sprea.invalid"


def is_shared_account(email: Optional[str]) -> bool:
    return bool(email) and email.lower().endswith(SHARED_ACCOUNT_DOMAIN)


def is_pro(profile: Optional[Dict[str, Any]]) -> bool:
    return bool(profile) and (profile.get("subscription_status") in PRO_ACTIVE_STATUSES or org_active(profile))


def team_summary(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    org = profile.get("org")
    if not org:
        return None
    parent = profile.get("org_parent")
    return {"id": org["id"], "name": org["name"], "kind": org["kind"], "role": profile.get("org_role"),
            "seats": org.get("seats"), "active": org_active(profile),
            "subscription_status": org.get("subscription_status"),
            "network": parent["name"] if parent else None}


SUBSCRIBERS_ONLY = "Réservé aux abonnés SPREA."


async def subscriber_access(request: Request, authorization: Optional[str] = Header(None),
                            x_link_code: Optional[str] = Header(None)) -> None:
    """The tools are for subscribers. Exception: the owner page reached from a
    letter's QR code (its link code is sent in X-Link-Code)."""
    # Dependencies resolved by hand, so that this check runs only when needed
    # (and still honours the overrides used in tests)
    overrides = request.app.dependency_overrides

    async def user() -> User:
        override = overrides.get(current_user)
        return override() if override else await current_user(authorization)

    if x_link_code:
        store = overrides.get(store_dep, store_dep)()
        if re.fullmatch(r"[A-Za-z0-9]{8}", x_link_code) and await store.get_link(x_link_code):
            return
        u = await user()
    else:
        u = await user()  # 401 before touching the database
        store = overrides.get(store_dep, store_dep)()
    if not is_pro(await store.ensure_profile(u.id, u.email)):
        raise HTTPException(status_code=402, detail=SUBSCRIBERS_ONLY)


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
    ordering does not matter) to the owner's profile, or to the organization
    for an agency subscription (metadata org_id)."""
    sub = await billing.get_subscription(subscription_id)
    metadata = sub.get("metadata") or {}
    if metadata.get("org_id"):
        await sync_org_subscription(store, billing, sub)
        return
    profile = await store.get_profile(user_id) if user_id else None
    if not profile:
        profile = await store.get_profile_by_customer(sub["customer"])
    if not profile and metadata.get("user_id"):
        profile = await store.get_profile(metadata["user_id"])
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


async def sync_org_subscription(store: SupabaseStore, billing: Billing, sub: Dict[str, Any]) -> None:
    metadata = sub.get("metadata") or {}
    org = await store.get_org(metadata["org_id"])
    if not org:
        logger.error(f"No organization for subscription {sub['id']}")
        return
    if org.get("stripe_subscription_id") not in (None, sub["id"]) and sub["status"] not in PRO_ACTIVE_STATUSES:
        return
    items = (sub.get("items") or {}).get("data") or []
    fields = {
        "stripe_subscription_id": sub["id"],
        "subscription_status": sub["status"],
        "subscription_current_period_end": iso_from_timestamp(subscription_period_end(sub)),
    }
    if items and items[0].get("quantity"):
        fields["seats"] = items[0]["quantity"]
    await store.update_org(org["id"], fields)
    # The owner's Solo plan is replaced by the agency one: unused time credited
    owner_id = metadata.get("user_id")
    if sub["status"] in PRO_ACTIVE_STATUSES and owner_id:
        owner = await store.get_profile(owner_id)
        solo = (owner or {}).get("subscription_id")
        if solo and solo != sub["id"] and owner.get("subscription_status") in PRO_ACTIVE_STATUSES:
            await billing.cancel_subscription(solo, prorate=True)
            await store.update_profile(owner_id, {"subscription_status": "canceled"})
            logger.info("Solo plan replaced by an agency subscription")


def report_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {k: report.get(k) for k in ("id", "address", "status", "created_at")}


# --- Schemas ---

class ReportMeta(BaseModel):
    address: str = Field(..., min_length=1, max_length=300)
    year: Optional[int] = None
    ademe_dpe_number: Optional[str] = Field(None, max_length=20)
    building_type: Optional[str] = Field(None, max_length=100)
    construction_period: Optional[str] = Field(None, max_length=100)
    dpe_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}", max_length=30)
    city: Optional[str] = Field(None, max_length=100)
    postcode: Optional[str] = Field(None, max_length=10)
    insee_code: Optional[str] = Field(None, max_length=5)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    # Equipment labels from the DPE (heating, hot water, ventilation...)
    details: Optional[Dict[str, Optional[str]]] = Field(None, max_length=10)

    @field_validator("details")
    @classmethod
    def short_details(cls, v):
        if v is None:
            return v
        return {str(k)[:40]: (str(val)[:120] if val is not None else None) for k, val in v.items()}


class ReportCreate(BaseModel):
    meta: ReportMeta
    simulation: SimulationInput
    # CGV accepted, immediate access requested and loss of the withdrawal
    # right acknowledged (art. L221-28 13° Code de la consommation).
    # Not needed for Pro subscribers, who accepted the terms when subscribing.
    accept_terms: bool = False


class DeleteAccountRequest(BaseModel):
    confirm: bool = False


MIN_AGENCY_SEATS, MAX_AGENCY_SEATS = 2, 50


class SubscribeRequest(BaseModel):
    # CGV accepted and immediate start of the subscription requested
    accept_terms: bool = False
    plan: Literal["solo_monthly", "solo_yearly", "agence_monthly", "agence_yearly"] = "solo_monthly"
    # Agence: number of agents and name of the agency
    seats: int = Field(1, ge=1, le=MAX_AGENCY_SEATS)
    agency_name: Optional[str] = Field(None, max_length=120)


def terms_acceptance() -> Dict[str, str]:
    return {"terms_accepted_at": datetime.now(timezone.utc).isoformat(), "terms_version": TERMS_VERSION}


# --- Endpoints ---

# Countries and overseas departments covered by the DPE database
DPE_COUNTRIES = {"FR", "GP", "MQ", "GF", "RE", "YT"}


@router.get("/geo")
async def approximate_location(request: Request):
    """Approximate position of the visitor, from the IP geolocation headers
    added by Vercel (city level): where the prospection map opens. Nothing is
    stored, and no browser permission is asked."""
    h = request.headers
    try:
        lat, lon = float(h.get("x-vercel-ip-latitude", "")), float(h.get("x-vercel-ip-longitude", ""))
    except ValueError:
        return {"lat": None, "lon": None, "city": None}
    if (h.get("x-vercel-ip-country") or "").upper() not in DPE_COUNTRIES:
        return {"lat": None, "lon": None, "city": None}
    return {"lat": round(lat, 4), "lon": round(lon, 4), "city": unquote(h.get("x-vercel-ip-city") or "") or None}


@router.get("/config")
async def public_config():
    """Public settings for the frontend (the Supabase anon key is meant to be public)."""
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    billing_enabled = billing_configured()
    report_price = pro_price = None
    plans: Dict[str, Optional[str]] = {}
    if billing_enabled:
        billing = get_billing()
        plans = await billing.plan_labels()
        pro_price = plans.get("solo_monthly")
    return {
        "auth_enabled": bool(supabase_url and anon_key),
        "supabase_url": supabase_url,
        "supabase_anon_key": anon_key,
        "billing_enabled": billing_enabled,
        "report_price": report_price,
        "pro_price": pro_price,
        # Prices excluding VAT
        "plans": plans,
        "terms_version": TERMS_VERSION,
    }


@router.get("/me")
async def me(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    profile = await store.ensure_profile(user.id, user.email)
    reports = await store.list_reports(user.id)
    return {
        "email": user.email,
        "is_pro": is_pro(profile),
        "team": team_summary(profile),
        "subscription_status": profile.get("subscription_status"),
        "subscription_current_period_end": profile.get("subscription_current_period_end"),
        "has_billing_account": bool(profile.get("stripe_customer_id")),
        "reports": [report_summary(r) for r in reports],
    }


# Subscription states that still bill or may bill the customer
ENDED_SUBSCRIPTION_STATUSES = {"canceled", "incomplete_expired"}


@router.delete("/me")
async def delete_account(data: DeleteAccountRequest, user: User = Depends(current_user),
                         store: SupabaseStore = Depends(store_dep),
                         billing: Optional[Billing] = Depends(optional_billing_dep)):
    """Deletes the account, its reports and any running subscription.

    Kept afterwards (legal obligations): invoices at Stripe, and a minimal
    record of each purchase (CGV version and date, payment references).
    """
    if not data.confirm:
        raise HTTPException(status_code=400, detail="Confirmez la suppression du compte.")
    if is_shared_account(user.email):
        raise HTTPException(status_code=403, detail="Le compte de test partagé ne peut pas être supprimé.")
    profile = await store.get_profile(user.id) or {}
    org = profile.get("org")
    org_subscription = None
    if org:
        members = await store.list_members(org["id"])
        if profile.get("org_role") == "owner":
            if len(members) > 1:
                raise HTTPException(status_code=400, detail="Retirez d'abord les membres de votre agence (page Équipe) : leur accès dépend de votre abonnement.")
            if org.get("stripe_subscription_id") and org.get("subscription_status") not in ENDED_SUBSCRIPTION_STATUSES:
                org_subscription = org["stripe_subscription_id"]
        else:
            # The requests received stay with the agency
            owner = next((m["user_id"] for m in members if m["role"] == "owner"), None)
            if owner:
                await store.transfer_contacts(user.id, owner)

    # 1. Stop billing first: abort if Stripe cannot be reached
    subscription_id = profile.get("subscription_id")
    running = [sid for sid in (subscription_id if profile.get("subscription_status") not in ENDED_SUBSCRIPTION_STATUSES else None,
                               org_subscription) if sid]
    if running and billing is None:
        raise HTTPException(status_code=503, detail="Suppression impossible pour le moment, réessayez plus tard.")
    for sid in running:
        await billing.cancel_subscription(sid)

    # 2. Keep the proof of purchases, without personal data
    deleted_at = datetime.now(timezone.utc).isoformat()
    customer_id = profile.get("stripe_customer_id")
    archive = [{
        "kind": "report",
        "stripe_customer_id": customer_id,
        "stripe_session_id": r.get("stripe_session_id"),
        "terms_version": r.get("terms_version"),
        "terms_accepted_at": r.get("terms_accepted_at"),
        "amount_paid": r.get("amount_paid"),
        "currency": r.get("currency"),
        "paid_at": r.get("paid_at"),
        "account_deleted_at": deleted_at,
    } for r in await store.paid_reports(user.id)]
    if org_subscription:
        archive.append({
            "kind": "subscription",
            "stripe_customer_id": customer_id,
            "subscription_id": org_subscription,
            "terms_version": profile.get("terms_version"),
            "terms_accepted_at": profile.get("terms_accepted_at"),
            "account_deleted_at": deleted_at,
        })
    if subscription_id:
        archive.append({
            "kind": "subscription",
            "stripe_customer_id": customer_id,
            "subscription_id": subscription_id,
            "terms_version": profile.get("terms_version"),
            "terms_accepted_at": profile.get("terms_accepted_at"),
            "account_deleted_at": deleted_at,
        })
    # Acceptances of the prospection map terms (CGV article 14)
    archive += [{
        "kind": "prospection_terms",
        "stripe_customer_id": customer_id,
        "terms_version": a.get("terms_version"),
        "terms_accepted_at": a.get("accepted_at"),
        "account_deleted_at": deleted_at,
    } for a in await store.terms_acceptances(user.id)]
    if archive:
        await store.archive_purchases(archive)

    # 3. Delete the user: profile and reports are removed by cascade (and the
    # agency of an owner without members)
    if org and profile.get("org_role") == "owner":
        await store.delete_org(org["id"])
    await store.delete_user(user.id)
    logger.info("Account deleted")
    return {"deleted": True}


@router.post("/reports")
async def create_report(data: ReportCreate, user: User = Depends(current_user),
                        store: SupabaseStore = Depends(store_dep),
                        billing: Optional[Billing] = Depends(optional_billing_dep)):
    """Creates a report, included in the subscription."""
    # Validates the simulation first
    run_simulation(data.simulation)
    profile = await store.ensure_profile(user.id, user.email)
    if not is_pro(profile):
        raise HTTPException(status_code=402, detail=SUBSCRIBERS_ONLY)
    report = await store.create_report({
        "user_id": user.id,
        "address": data.meta.address,
        "meta": data.meta.model_dump(mode="json"),
        "simulation": data.simulation.model_dump(mode="json"),
        "status": "included",
    })
    return {"id": report["id"], "status": "included"}


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

    meta = report["meta"]
    simulation = SimulationInput.model_validate(report["simulation"])
    if not simulation.property.price_per_m2 and meta.get("insee_code"):
        # Local DVF price for the green value, when the page did not provide it
        market = await market_price(meta["insee_code"], simulation.property.building_type,
                                    meta.get("latitude"), meta.get("longitude"), simulation.property.surface)
        if market:
            simulation.property.price_per_m2 = market["price_per_m2"]
            simulation.property.price_source = market["source"]
    if not simulation.property.insee_code and meta.get("insee_code"):
        simulation.property.insee_code = meta["insee_code"]
    content = build_report(meta, simulation)
    # Qualified companies near the dwelling for the works retained (ADEME open data)
    try:
        from api.rge import nearby_or_empty
    except ImportError:
        from rge import nearby_or_empty
    content["rge"] = await nearby_or_empty(meta.get("latitude"), meta.get("longitude"), list(simulation.works),
                                           simulation.property.building_type)
    # Building sheet of an apartment: copropriété registry, collective DPE, works to come
    try:
        from api.immeuble import sheet_or_none
    except ImportError:
        from immeuble import sheet_or_none
    content["immeuble"] = await sheet_or_none(meta.get("ademe_dpe_number"), simulation.property.building_type, store)
    analysis = parse_stored(report.get("narrative"))
    if not analysis:
        analysis = await ai_service.write_analysis(facts_for_writer(content))
        # Only Claude's text is kept: a rule-based fallback is regenerated next time
        if analysis["source"] == "claude":
            await store.update_report(report["id"], {"narrative": json.dumps(analysis, ensure_ascii=False)})

    pdf_bytes = pdf_service.generate(content, analysis["sections"])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Rapport_SPREA_{safe_filename(report['address'])}.pdf"},
    )


@router.post("/billing/subscribe")
async def subscribe(data: SubscribeRequest, user: User = Depends(current_user),
                    store: SupabaseStore = Depends(store_dep), billing: Billing = Depends(billing_dep)):
    profile = await store.ensure_profile(user.id, user.email)
    if not data.accept_terms:
        raise HTTPException(status_code=400, detail=TERMS_REQUIRED)
    agency = data.plan in AGENCY_PLANS
    org = profile.get("org")
    if org_active(profile):
        raise HTTPException(status_code=400, detail="Votre accès est déjà fourni par votre agence.")
    org_id = None
    if agency:
        name = (data.agency_name or "").strip()
        if len(name) < 2:
            raise HTTPException(status_code=400, detail="Indiquez le nom de votre agence.")
        if data.seats < MIN_AGENCY_SEATS:
            raise HTTPException(status_code=400, detail=f"La formule Agence commence à {MIN_AGENCY_SEATS} agents.")
        if org and profile.get("org_role") != "owner":
            raise HTTPException(status_code=400, detail="Vous faites déjà partie d'une agence.")
        if org:
            # Checkout started earlier but not paid: same agency
            await store.update_org(org["id"], {"name": name, "seats": data.seats})
            org_id = org["id"]
        else:
            org_id = (await store.create_org({"name": name, "kind": "agence", "seats": data.seats}))["id"]
            await store.add_member(org_id, user.id, "owner")
    elif profile.get("subscription_status") in PRO_ACTIVE_STATUSES:
        raise HTTPException(status_code=400, detail="Votre abonnement est déjà actif.")
    await store.update_profile(user.id, terms_acceptance())
    customer_id = await ensure_customer(store, billing, user, profile)
    url = await billing.subscription_checkout(user.id, customer_id, data.plan,
                                              quantity=data.seats if agency else 1, org_id=org_id)
    return {"checkout_url": url}


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
    except (ValueError, stripe.SignatureVerificationError) as e:
        # Usually a STRIPE_WEBHOOK_SECRET that does not match the endpoint's signing secret
        logger.warning(f"Rejected Stripe webhook: {type(e).__name__}")
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


# --- Prospection map (Pro) ---

@router.get("/prospection", dependencies=[Depends(search_limiter)])
async def prospection_map(bbox: str, labels: str = "F,G", kind: Optional[str] = None,
                          since: Optional[str] = Query(None, pattern=r"^\d{4}(-\d{2}-\d{2})?$"),
                          user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    """Poor DPE in the visible area, established since a year or a date. Full
    list for Pro subscribers, whose use of the addresses is governed by the
    CGV accepted at subscription (article 14); others get counts on an
    approximate location, without addresses."""
    profile = await store.ensure_profile(user.id, user.email)
    pro = is_pro(profile)
    try:
        result = await prospection.search(bbox, labels.upper().split(","), kind, since)
    except prospection.AreaTooLarge as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Les données de l'ADEME ne répondent pas, réessayez dans un instant.")
    if pro:
        return {**result, "locked": False}
    return {
        "locked": True,
        "dwellings": result["dwellings"],
        "total": result["total"],
        "truncated": result["truncated"],
        # About 100 m precision, no address
        "addresses": [{"lat": round(a["lat"], 3), "lon": round(a["lon"], 3), "worst": a["worst"], "count": len(a["dpe"])}
                      for a in result["addresses"]],
    }
