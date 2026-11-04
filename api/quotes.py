"""Quote requests for the Agence and Réseau offers, left on the pricing page.

Stored in Supabase (quote_requests); when QUOTES_TO is set and Resend is
configured, a notification is also emailed to that address.
"""
import html
import logging
import os
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

try:
    from api.accounts import store_dep
    from api.contacts import clean, valid_email
    from api.emailer import send_email
    from api.ratelimit import lead_limiter
    from api.store import SupabaseStore
except ImportError:
    from accounts import store_dep
    from contacts import clean, valid_email
    from emailer import send_email
    from ratelimit import lead_limiter
    from store import SupabaseStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class QuoteRequest(BaseModel):
    offer: Literal["agence", "reseau"]
    name: str = Field(..., min_length=2, max_length=80)
    company: str = Field(..., min_length=2, max_length=120)
    email: str
    phone: Optional[str] = Field(None, max_length=25)
    agents: int = Field(..., ge=1, le=5000)
    message: Optional[str] = Field(None, max_length=2000)
    website: Optional[str] = None  # Honeypot

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        email = valid_email(v)
        if not email:
            raise ValueError("Email requis.")
        return email


@router.post("/quote", dependencies=[Depends(lead_limiter)])
async def request_quote(data: QuoteRequest, store: SupabaseStore = Depends(store_dep)):
    if data.website:
        return {"received": True}  # Bot: silently ignored
    row = {"offer": data.offer, "name": clean(data.name, 80), "company": clean(data.company, 120), "email": data.email,
           "phone": clean(data.phone, 25), "agents": data.agents, "message": clean(data.message, 2000)}
    await store.create_quote_request(row)
    logger.info(f"Quote request received ({data.offer}, {data.agents} agents)")
    to = os.getenv("QUOTES_TO", "").strip()
    if to:
        lines = [f"{k} : {v}" for k, v in row.items() if v]
        await send_email(to, f"Demande de devis {data.offer} : {row['company']} ({data.agents} agents)",
                         "<br>".join(html.escape(str(line)) for line in lines), "\n".join(map(str, lines)))
    return {"received": True}


# --- Worksite dossiers for building firms (/trouver-des-chantiers) ---

CHANTIER_OFFERS = {"essai": "Dossier d'essai gratuit", "pack": "Pack Découverte (99 € HT)",
                   "zone": "Zone exclusive (349 € HT / mois)"}


class ChantierRequest(BaseModel):
    offer: Literal["essai", "pack", "zone"]
    trades: List[str] = Field(..., min_length=1, max_length=10)
    city: str = Field(..., min_length=2, max_length=80)
    insee: Optional[str] = Field(None, max_length=5)
    radius: int = Field(20, ge=5, le=100)
    first_name: str = Field(..., min_length=1, max_length=40)
    last_name: str = Field(..., min_length=1, max_length=40)
    company: str = Field(..., min_length=2, max_length=120)
    siret: Optional[str] = Field(None, max_length=20)
    email: str
    phone: str = Field(..., min_length=10, max_length=25)
    website: Optional[str] = None  # Honeypot

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        email = valid_email(v)
        if not email:
            raise ValueError("Email requis.")
        return email

    @field_validator("trades")
    @classmethod
    def _trades(cls, v: List[str]) -> List[str]:
        return [t for t in (clean(x, 40) for x in v) if t]


@router.post("/chantiers/demande", dependencies=[Depends(lead_limiter)])
async def request_chantier(data: ChantierRequest, store: SupabaseStore = Depends(store_dep)):
    if data.website:
        return {"received": True}  # Bot: silently ignored
    name = clean(f"{data.first_name} {data.last_name}", 80)
    details = [f"Offre : {CHANTIER_OFFERS[data.offer]}", f"Métiers : {', '.join(data.trades)}",
               f"Zone : {clean(data.city, 80)}{f' ({data.insee})' if data.insee else ''}, {data.radius} km",
               f"SIRET : {clean(data.siret, 20)}" if data.siret else None]
    row = {"offer": f"chantier_{data.offer}", "name": name, "company": clean(data.company, 120), "email": data.email,
           "phone": clean(data.phone, 25), "agents": 1, "message": "\n".join(x for x in details if x)}
    await store.create_quote_request(row)
    logger.info(f"Worksite dossier request received ({data.offer})")
    to = os.getenv("QUOTES_TO", "").strip()
    if to:
        lines = [f"{name} · {row['company']}", f"{data.email} · {row['phone']}", *row["message"].split("\n")]
        await send_email(to, f"{CHANTIER_OFFERS[data.offer]} : {row['company']} ({clean(data.city, 80)})",
                         "<br>".join(html.escape(line) for line in lines), "\n".join(lines))
    return {"received": True}
