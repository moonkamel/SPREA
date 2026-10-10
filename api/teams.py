"""Teams: agencies (Agence offer, billed per agent) and networks (Réseau).

The owner subscribes for a number of agents (seats), then invites them by
email: the invitation link carries a random token, only its SHA-256 is stored.
Within an agency, alerts are shared with everyone and the owner and admins
see the callback requests received by all agents. When an agent leaves, their
letters' links and requests go to the owner (the agency is the controller).
A network sees its agencies and their figures, not their contacts.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

try:
    from api.accounts import (MAX_AGENCY_SEATS, MIN_AGENCY_SEATS, billing_dep, optional_billing_dep,
                              org_active, store_dep, team_summary)
    from api.auth import User, current_user
    from api.billing import PRO_ACTIVE_STATUSES, Billing
    from api.contacts import valid_email
    from api.emailer import send_email
    from api.store import SupabaseStore
except ImportError:
    from accounts import (MAX_AGENCY_SEATS, MIN_AGENCY_SEATS, billing_dep, optional_billing_dep,
                          org_active, store_dep, team_summary)
    from auth import User, current_user
    from billing import PRO_ACTIVE_STATUSES, Billing
    from contacts import valid_email
    from emailer import send_email
    from store import SupabaseStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/team")

INVITATION_DAYS = 7
MANAGERS = ("owner", "admin")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def join_url(token: str) -> str:
    base = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/") or "https://sprea.app"
    return f"{base}/rejoindre?token={token}"


async def team_scope(store: SupabaseStore, user: User) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """The user's profile and the members of their agency (just themselves
    without an agency)."""
    profile = await store.ensure_profile(user.id, user.email)
    org = profile.get("org")
    if not org:
        return profile, [{"user_id": user.id, "email": user.email, "role": None}]
    return profile, await store.list_members(org["id"])


def is_manager(profile: Dict[str, Any]) -> bool:
    return bool(profile.get("org")) and profile.get("org_role") in MANAGERS


async def require_team(store: SupabaseStore, user: User, manager: bool = False) -> Dict[str, Any]:
    profile = await store.ensure_profile(user.id, user.email)
    if not profile.get("org"):
        raise HTTPException(status_code=404, detail="Vous ne faites partie d'aucune agence.")
    if manager and not is_manager(profile):
        raise HTTPException(status_code=403, detail="Réservé au responsable de l'agence.")
    return profile


async def pending_invitations(store: SupabaseStore, org_id: str) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    return [i for i in await store.list_invitations(org_id) if i["expires_at"] > now]


# --- Team overview ---

@router.get("")
async def get_team(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    profile = await store.ensure_profile(user.id, user.email)
    team = team_summary(profile)
    if not team:
        return {"team": None}
    members = await store.list_members(team["id"])
    manager = is_manager(profile)
    invitations = await pending_invitations(store, team["id"]) if manager else []
    return {
        "team": team,
        "members": [{k: m.get(k) for k in ("user_id", "email", "role", "created_at")} for m in members],
        "invitations": invitations,
        "seats_used": len(members) + len(invitations),
        "can_manage": manager,
        "can_bill": profile.get("org_role") == "owner" and bool(profile["org"].get("stripe_subscription_id")),
    }


# --- Invitations ---

class InvitationRequest(BaseModel):
    email: str
    role: Literal["admin", "agent"] = "agent"

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        email = valid_email(v)
        if not email:
            raise ValueError("Email requis.")
        return email


@router.post("/invitations")
async def invite(data: InvitationRequest, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    profile = await require_team(store, user, manager=True)
    org = profile["org"]
    if not org_active(profile):
        raise HTTPException(status_code=402, detail="L'abonnement de l'agence n'est pas actif.")
    members = await store.list_members(org["id"])
    if any((m.get("email") or "").lower() == data.email for m in members):
        raise HTTPException(status_code=400, detail="Cette personne fait déjà partie de l'agence.")
    pending = [i for i in await pending_invitations(store, org["id"]) if i["email"] != data.email]
    if len(members) + len(pending) >= org["seats"]:
        raise HTTPException(status_code=409, detail="Toutes les places sont attribuées : ajoutez une place à l'abonnement.")
    token = secrets.token_urlsafe(24)
    invitation = await store.create_invitation({
        "org_id": org["id"], "email": data.email, "role": data.role, "token_hash": token_hash(token),
        "invited_by": user.id, "expires_at": (datetime.now(timezone.utc) + timedelta(days=INVITATION_DAYS)).isoformat(),
        "accepted_at": None,
    })
    link = join_url(token)
    sent = await send_email(
        data.email, f"Rejoignez {org['name']} sur SPREA",
        f"<p>{user.email} vous invite à rejoindre <b>{org['name']}</b> sur SPREA, l'outil DPE des professionnels de l'immobilier.</p>"
        f"<p><a href=\"{link}\">Accepter l'invitation</a> (valable {INVITATION_DAYS} jours)</p>",
        f"{user.email} vous invite à rejoindre {org['name']} sur SPREA.\nAccepter l'invitation : {link}\n"
        f"(valable {INVITATION_DAYS} jours)")
    logger.info("Invitation created")
    return {"invitation": {k: invitation.get(k) for k in ("id", "email", "role", "expires_at")}, "link": link, "email_sent": sent}


@router.delete("/invitations/{invitation_id}")
async def revoke_invitation(invitation_id: str, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    profile = await require_team(store, user, manager=True)
    if not await store.delete_invitation(profile["org"]["id"], invitation_id):
        raise HTTPException(status_code=404, detail="Invitation introuvable.")
    return {"deleted": True}


class JoinRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=100)


@router.post("/join")
async def join(data: JoinRequest, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep),
               billing: Optional[Billing] = Depends(optional_billing_dep)):
    invitation = await store.get_invitation(token_hash(data.token))
    now = datetime.now(timezone.utc).isoformat()
    if not invitation or invitation.get("accepted_at") or invitation["expires_at"] < now:
        raise HTTPException(status_code=404, detail="Invitation introuvable ou expirée : demandez-en une nouvelle.")
    if (user.email or "").lower() != invitation["email"].lower():
        raise HTTPException(status_code=403, detail=f"Cette invitation a été envoyée à {invitation['email']} : connectez-vous avec cette adresse.")
    profile = await store.ensure_profile(user.id, user.email)
    if profile.get("org"):
        if profile["org"]["id"] == invitation["org_id"]:
            return {"joined": True, "team": team_summary(profile)}
        raise HTTPException(status_code=409, detail="Vous faites déjà partie d'une autre agence : quittez-la d'abord.")
    org = await store.get_org(invitation["org_id"])
    members = await store.list_members(org["id"])
    if len(members) >= org["seats"]:
        raise HTTPException(status_code=409, detail="Toutes les places de l'agence sont prises : contactez votre responsable.")
    await store.add_member(org["id"], user.id, invitation["role"])
    await store.accept_invitation(invitation["id"])
    # A Solo plan of the new member is now useless: stopped, unused time credited
    if profile.get("subscription_status") in PRO_ACTIVE_STATUSES and profile.get("subscription_id") and billing:
        await billing.cancel_subscription(profile["subscription_id"], prorate=True)
        await store.update_profile(user.id, {"subscription_status": "canceled"})
    logger.info("Invitation accepted")
    return {"joined": True, "team": team_summary(await store.ensure_profile(user.id, user.email))}


# --- Members ---

class MemberUpdate(BaseModel):
    role: Literal["admin", "agent"]


@router.patch("/members/{member_id}")
async def update_member(member_id: str, data: MemberUpdate, user: User = Depends(current_user),
                        store: SupabaseStore = Depends(store_dep)):
    profile = await require_team(store, user, manager=True)
    if profile["org_role"] != "owner":
        raise HTTPException(status_code=403, detail="Seul le titulaire de l'abonnement peut changer les rôles.")
    member = next((m for m in await store.list_members(profile["org"]["id"]) if m["user_id"] == member_id), None)
    if not member or member["role"] == "owner":
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    await store.update_member(profile["org"]["id"], member_id, {"role": data.role})
    return {"updated": True}


async def owner_of(store: SupabaseStore, org_id: str) -> Optional[str]:
    return next((m["user_id"] for m in await store.list_members(org_id) if m["role"] == "owner"), None)


@router.delete("/members/{member_id}")
async def remove_member(member_id: str, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    profile = await require_team(store, user, manager=True)
    org_id = profile["org"]["id"]
    member = next((m for m in await store.list_members(org_id) if m["user_id"] == member_id), None)
    if not member or member["role"] == "owner" or member_id == user.id:
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    if member["role"] == "admin" and profile["org_role"] != "owner":
        raise HTTPException(status_code=403, detail="Seul le titulaire de l'abonnement peut retirer un responsable.")
    owner = await owner_of(store, org_id)
    if owner:
        await store.transfer_contacts(member_id, owner)
    await store.remove_member(org_id, member_id)
    logger.info("Member removed")
    return {"removed": True}


@router.post("/leave")
async def leave(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    profile = await require_team(store, user)
    if profile["org_role"] == "owner":
        raise HTTPException(status_code=400, detail="Le titulaire de l'abonnement ne peut pas quitter l'agence : résiliez l'abonnement.")
    org_id = profile["org"]["id"]
    owner = await owner_of(store, org_id)
    if owner:
        await store.transfer_contacts(user.id, owner)
    await store.remove_member(org_id, user.id)
    return {"left": True}


# --- Seats ---

class SeatsRequest(BaseModel):
    seats: int = Field(..., ge=MIN_AGENCY_SEATS, le=MAX_AGENCY_SEATS)


@router.put("/seats")
async def change_seats(data: SeatsRequest, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep),
                       billing: Billing = Depends(billing_dep)):
    profile = await require_team(store, user, manager=True)
    org = profile["org"]
    if profile["org_role"] != "owner" or not org.get("stripe_subscription_id"):
        raise HTTPException(status_code=403, detail="Seul le titulaire de l'abonnement peut changer le nombre de places.")
    used = len(await store.list_members(org["id"])) + len(await pending_invitations(store, org["id"]))
    if data.seats < used:
        raise HTTPException(status_code=400, detail=f"{used} places sont utilisées ou réservées par une invitation : retirez d'abord un membre.")
    await billing.update_seats(org["stripe_subscription_id"], data.seats)
    await store.update_org(org["id"], {"seats": data.seats})
    return {"seats": data.seats}


# --- Network console ---

@router.get("/network")
async def network(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    profile = await require_team(store, user, manager=True)
    org = profile["org"]
    if org["kind"] != "reseau":
        raise HTTPException(status_code=404, detail="Réservé aux réseaux.")
    agencies = []
    for child in await store.child_orgs(org["id"]):
        members = await store.list_members(child["id"])
        ids = [m["user_id"] for m in members]
        leads = await store.list_leads_for_users(ids) if ids else []
        agencies.append({"id": child["id"], "name": child["name"], "seats": child["seats"], "members": len(members),
                         "leads": len(leads), "leads_open": sum(1 for l in leads if l.get("status") == "new")})
    return {"network": team_summary(profile), "agencies": agencies}
