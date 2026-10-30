"""SPREA's admin dashboard (/admin): every request left on the public
estimator, newest first, with the advisor it was routed to, and its status.
Only for the profiles flagged is_admin in the database."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

try:
    from api.accounts import store_dep
    from api.auth import User, current_user
    from api.store import SupabaseStore
except ImportError:
    from accounts import store_dep
    from auth import User, current_user
    from store import SupabaseStore

router = APIRouter(prefix="/api/admin")


async def admin_user(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)) -> User:
    profile = await store.get_profile(user.id)
    if not (profile or {}).get("is_admin"):
        raise HTTPException(status_code=403, detail="Réservé à l'équipe SPREA.")
    return user


class LeadUpdate(BaseModel):
    status: str = Field(..., pattern="^(new|contacted|closed)$")


@router.get("/estimate-leads")
async def estimate_leads(_: User = Depends(admin_user), store: SupabaseStore = Depends(store_dep)):
    leads: List[Dict[str, Any]] = await store.all_estimate_leads()
    emails: Dict[str, Optional[str]] = await store.profile_emails(
        sorted({l["assigned_user_id"] for l in leads if l.get("assigned_user_id")}))
    for l in leads:
        l["advisor"] = emails.get(l["assigned_user_id"]) if l.get("assigned_user_id") else None
    return {"leads": leads}


@router.patch("/estimate-leads/{lead_id}")
async def update_lead(lead_id: str, data: LeadUpdate, _: User = Depends(admin_user),
                      store: SupabaseStore = Depends(store_dep)):
    if not await store.admin_update_estimate_lead(lead_id, {"status": data.status}):
        raise HTTPException(status_code=404, detail="Demande introuvable.")
    return {"updated": True}
