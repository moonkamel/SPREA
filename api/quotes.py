"""Quote requests for the Agence and Réseau offers, left on the pricing page.

Stored in Supabase (quote_requests); when QUOTES_TO is set and Resend is
configured, a notification is also emailed to that address.
"""
import html
import logging
import os
from typing import Literal, Optional

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
