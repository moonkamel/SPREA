"""Owner contact pages.

An agent (Pro) prepares a letter for a dwelling found on the prospection map:
the letter carries a QR code to /l/<code>, a public page in the agency's name
showing the simulation of that dwelling. The owner may leave their contact
details to be called back, with explicit consent. The agent is the controller
of these requests; SPREA stores them on its behalf.
"""
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

try:
    from api.accounts import TERMS_VERSION, is_pro, prospection_terms_accepted, store_dep
    from api.auth import User, current_user
    from api.ratelimit import lead_limiter, search_limiter
    from api.store import SupabaseStore
except ImportError:
    from accounts import TERMS_VERSION, is_pro, prospection_terms_accepted, store_dep
    from auth import User, current_user
    from ratelimit import lead_limiter, search_limiter
    from store import SupabaseStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Unambiguous characters (no 0/O, 1/I/L) for codes typed from a letter
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 8
CODE_RE = re.compile(f"^[{CODE_ALPHABET}]{{{CODE_LENGTH}}}$")
DPE_RE = re.compile(r"^[0-9A-Z]{13}$")
PHONE_RE = re.compile(r"^[0-9+ .()-]{6,25}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip()
    if not v:
        return None
    if not EMAIL_RE.match(v):
        raise ValueError("Adresse email invalide.")
    return v.lower()


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def consent_text(agency: str) -> str:
    return (f"J'accepte que {agency} me recontacte au sujet de ce logement, par téléphone ou par email. "
            "Mes coordonnées sont transmises uniquement à cette agence, via SPREA, et ne servent à rien d'autre.")


def clean(value: Optional[str], limit: int) -> Optional[str]:
    value = re.sub(r"\s+", " ", (value or "")).strip()
    return value[:limit] or None


# --- Agent page ---

class AgentPage(BaseModel):
    agency_name: str = Field(..., min_length=2, max_length=80)
    agent_name: Optional[str] = Field(None, max_length=80)
    phone: Optional[str] = Field(None, max_length=25)
    email: Optional[str] = Field(None, max_length=120)

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v):
        if v and not PHONE_RE.match(v):
            raise ValueError("Numéro de téléphone invalide.")
        return v

    _email = field_validator("email")(lambda cls, v: valid_email(v))


@router.get("/agent-page")
async def get_agent_page(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    return await store.get_agent_page(user.id) or {}


@router.put("/agent-page")
async def put_agent_page(data: AgentPage, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    fields = {"agency_name": clean(data.agency_name, 80), "agent_name": clean(data.agent_name, 80),
              "phone": clean(data.phone, 25), "email": data.email}
    return await store.upsert_agent_page(user.id, fields)


# --- Links (one per dwelling and agent) ---

class LinkRequest(BaseModel):
    dpe_number: str = Field(..., min_length=13, max_length=13)
    address: str = Field(..., min_length=3, max_length=200)
    label: Optional[str] = Field(None, pattern=r"^[A-G]$")


@router.post("/prospection/links")
async def create_link(data: LinkRequest, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    profile = await store.ensure_profile(user.id, user.email)
    if not is_pro(profile):
        raise HTTPException(status_code=402, detail="Réservé aux abonnés Pro.")
    if not await prospection_terms_accepted(store, user.id):
        raise HTTPException(status_code=403, detail="Acceptez d'abord les conditions d'utilisation de la carte.")
    if not await store.get_agent_page(user.id):
        raise HTTPException(status_code=409, detail="Renseignez d'abord le nom de votre agence.")
    dpe = data.dpe_number.upper()
    if not DPE_RE.match(dpe):
        raise HTTPException(status_code=400, detail="Numéro de DPE invalide.")
    link = await store.get_link_for_dpe(user.id, dpe)
    if not link:
        link = await store.create_link({"code": new_code(), "user_id": user.id, "dpe_number": dpe,
                                        "address": clean(data.address, 200), "label": data.label})
    return {"code": link["code"], "visits": link.get("visits", 0)}


# --- Public owner page ---

async def public_link(store: SupabaseStore, code: str) -> Dict[str, Any]:
    code = code.upper()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=404, detail="Page introuvable.")
    link = await store.get_link(code)
    page = await store.get_agent_page(link["user_id"]) if link else None
    if not link or not page:
        raise HTTPException(status_code=404, detail="Page introuvable.")
    return {"link": link, "page": page}


@router.get("/l/{code}", dependencies=[Depends(search_limiter)])
async def owner_page(code: str, store: SupabaseStore = Depends(store_dep)):
    found = await public_link(store, code)
    link, page = found["link"], found["page"]
    try:
        await store.update_link(link["code"], {"visits": (link.get("visits") or 0) + 1,
                                               "last_visit_at": datetime.now(timezone.utc).isoformat()})
    except Exception as e:  # A visit counter must never break the page
        logger.warning(f"Visit not counted: {type(e).__name__}")
    return {
        "code": link["code"],
        "dpe_number": link["dpe_number"],
        "address": link["address"],
        "label": link.get("label"),
        "agency": {k: page.get(k) for k in ("agency_name", "agent_name", "phone", "email")},
        "consent_text": consent_text(page["agency_name"]),
    }


class LeadRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    phone: Optional[str] = Field(None, max_length=25)
    email: Optional[str] = Field(None, max_length=120)
    message: Optional[str] = Field(None, max_length=1000)
    consent: bool = False
    # Honeypot: hidden on the page, filled only by bots
    website: Optional[str] = Field(None, max_length=200)

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v):
        if v and not PHONE_RE.match(v):
            raise ValueError("Numéro de téléphone invalide.")
        return v

    _email = field_validator("email")(lambda cls, v: valid_email(v))


@router.post("/l/{code}/lead", dependencies=[Depends(lead_limiter)])
async def leave_contact(code: str, data: LeadRequest, store: SupabaseStore = Depends(store_dep)):
    found = await public_link(store, code)
    if data.website:
        return {"received": True}  # Bot: silently ignored
    if not data.consent:
        raise HTTPException(status_code=400, detail="Cochez la case pour accepter d'être recontacté.")
    if not data.phone and not data.email:
        raise HTTPException(status_code=400, detail="Indiquez un téléphone ou un email.")
    link, page = found["link"], found["page"]
    await store.create_lead({
        "code": link["code"], "user_id": link["user_id"], "name": clean(data.name, 80),
        "phone": clean(data.phone, 25), "email": data.email, "message": clean(data.message, 1000),
        "consent_text": consent_text(page["agency_name"]),
    })
    logger.info("Lead received")
    return {"received": True}


# --- Agent: requests received ---

async def visible_owners(store: SupabaseStore, user: User) -> Dict[str, Optional[str]]:
    """Users whose requests this user sees, with their email: the whole agency
    for its owner and admins, otherwise only themselves."""
    profile = await store.ensure_profile(user.id, user.email)
    if profile.get("org") and profile.get("org_role") in ("owner", "admin"):
        return {m["user_id"]: m.get("email") for m in await store.list_members(profile["org"]["id"])}
    return {user.id: user.email}


@router.get("/leads")
async def list_leads(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    owners = await visible_owners(store, user)
    ids = list(owners)
    links = {l["code"]: l for l in await store.list_links_for_users(ids)}
    leads = [{**lead, "address": links.get(lead["code"], {}).get("address"),
              "dpe_number": links.get(lead["code"], {}).get("dpe_number"),
              # Who received it, when the agency's requests are shown together
              "agent": owners.get(lead["user_id"]) if len(ids) > 1 else None}
             for lead in await store.list_leads_for_users(ids)]
    own_links = [l for l in links.values() if l.get("user_id") == user.id]
    return {"leads": leads, "links": own_links}


class LeadUpdate(BaseModel):
    status: str = Field(..., pattern="^(new|contacted|closed)$")


async def lead_owner(store: SupabaseStore, user: User, lead_id: str) -> str:
    owners = await visible_owners(store, user)
    if len(owners) == 1:
        return user.id
    lead = next((l for l in await store.list_leads_for_users(list(owners)) if l["id"] == lead_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    return lead["user_id"]


@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, data: LeadUpdate, user: User = Depends(current_user),
                      store: SupabaseStore = Depends(store_dep)):
    if not await store.update_lead(await lead_owner(store, user, lead_id), lead_id, {"status": data.status}):
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    return {"updated": True}


@router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    if not await store.delete_lead(await lead_owner(store, user, lead_id), lead_id):
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    return {"deleted": True}
