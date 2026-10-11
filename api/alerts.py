"""DPE alerts: every morning, the new DPE received by the ADEME in the zones
watched by Pro agents. A new DPE often announces a sale or a rental (the DPE
is required before the listing). Results go to the /alertes page and, when
email is configured, to a morning email.
"""
import asyncio
import hashlib
import hmac
import logging
import os
import time
from datetime import date, timedelta
from html import escape
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

try:
    from api.accounts import is_pro, store_dep
    from api.auth import User, current_user
    from api.emailer import email_configured, send_email
    from api.prospection import dwelling_detail
    from api.ratelimit import search_limiter
    from api.store import SupabaseStore, get_store
except ImportError:
    from accounts import is_pro, store_dep
    from auth import User, current_user
    from emailer import email_configured, send_email
    from prospection import dwelling_detail
    from ratelimit import search_limiter
    from store import SupabaseStore, get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

ADEME_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
FIELDS = ["numero_dpe", "date_etablissement_dpe", "date_reception_dpe", "etiquette_dpe", "type_batiment",
          "surface_habitable_logement", "adresse_ban", "periode_construction", "complement_adresse_logement",
          "numero_etage_appartement"]
MAX_ZONES = 10
# The ADEME publishes DPE with a delay of a few days: each check looks back
# over this window and only DPE not already recorded for the zone are new.
LOOKBACK_DAYS = 14
LABELS = ["A", "B", "C", "D", "E", "F", "G"]
# The daily job stops starting new zones after this many seconds, to return
# before Vercel stops the function (300 s); the others are checked next run
TIME_BUDGET = 240


def app_url() -> str:
    return os.getenv("PUBLIC_APP_URL", "https://sprea.app").rstrip("/")


# --- One-click unsubscribe from the alert emails ---

def unsubscribe_secret() -> str:
    # The service role key is set wherever the alerts run
    return (os.getenv("ALERTS_UNSUBSCRIBE_SECRET") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()


def unsubscribe_token(user_id: str) -> str:
    sig = hmac.new(unsubscribe_secret().encode(), f"alerts-unsubscribe:{user_id}".encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{sig[:32]}"


def unsubscribe_user(token: str) -> Optional[str]:
    """User id of a valid token, None otherwise."""
    user_id, _, sig = token.partition(".")
    if not user_id or not sig or not unsubscribe_secret():
        return None
    return user_id if hmac.compare_digest(unsubscribe_token(user_id), token) else None


def unsubscribe_url(user_id: str) -> str:
    return f"{app_url()}/api/alerts/unsubscribe?token={unsubscribe_token(user_id)}"


async def fetch_new_dpe(zone: Dict[str, Any], since: date,
                        transport: Optional[httpx.AsyncBaseTransport] = None) -> List[Dict[str, Any]]:
    labels = [l for l in (zone.get("labels") or "").split(",") if l in LABELS] or ["E", "F", "G"]
    query = [f"date_reception_dpe:[{since.isoformat()} TO *]", f"etiquette_dpe:({' OR '.join(labels)})"]
    if zone.get("kind"):
        query.append(f"type_batiment:{zone['kind']}")
    params = {"geo_distance": f"{zone['lon']},{zone['lat']},{int(zone['radius_m'])}", "qs": " AND ".join(query),
              "size": "1000", "select": ",".join(FIELDS)}
    async with httpx.AsyncClient(timeout=20, transport=transport) as client:
        res = await client.get(ADEME_URL, params=params)
        res.raise_for_status()
        return res.json().get("results", [])


def to_hit(zone: Dict[str, Any], r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not r.get("numero_dpe"):
        return None
    try:
        surface = float(r["surface_habitable_logement"]) if r.get("surface_habitable_logement") not in (None, "") else None
    except (TypeError, ValueError):
        surface = None
    return {
        "zone_id": zone["id"], "user_id": zone["user_id"], "dpe_number": r["numero_dpe"],
        "address": r.get("adresse_ban"), "label": r.get("etiquette_dpe"),
        "kind": (r.get("type_batiment") or "").capitalize() or None, "surface": surface,
        "dpe_date": (r.get("date_etablissement_dpe") or "")[:10] or None,
        "received_on": (r.get("date_reception_dpe") or "")[:10] or None,
        "period": r.get("periode_construction"), "detail": dwelling_detail(r),
    }


async def check_zone(store: SupabaseStore, zone: Dict[str, Any], today: date,
                     transport: Optional[httpx.AsyncBaseTransport] = None) -> List[Dict[str, Any]]:
    """DPE received over the last LOOKBACK_DAYS not yet recorded for this zone."""
    rows = await fetch_new_dpe(zone, today - timedelta(days=LOOKBACK_DAYS), transport)
    hits = [h for h in (to_hit(zone, r) for r in rows) if h]
    new = await store.add_hits(hits)
    await store.update_zone(zone["id"], {"last_checked_on": today.isoformat()})
    return new


def email_content(zones: Dict[str, Dict[str, Any]], hits: List[Dict[str, Any]],
                  unsubscribe: Optional[str] = None) -> Dict[str, str]:
    by_zone: Dict[str, List[Dict[str, Any]]] = {}
    for h in hits:
        by_zone.setdefault(h["zone_id"], []).append(h)
    n = len(hits)
    subject = f"{n} nouveau{'x' if n > 1 else ''} DPE dans vos secteurs"
    html = [f"<p>Bonjour,</p><p><b>{n} nouveau{'x' if n > 1 else ''} DPE</b> reçu{'s' if n > 1 else ''} par l'ADEME dans vos secteurs :</p>"]
    text = [f"{subject} :", ""]
    for zone_id, zone_hits in by_zone.items():
        name = zones.get(zone_id, {}).get("name", "Secteur")
        html.append(f"<h3 style='margin:16px 0 4px'>{escape(name)} ({len(zone_hits)})</h3><ul>")
        text.append(f"{name} ({len(zone_hits)})")
        for h in sorted(zone_hits, key=lambda x: -LABELS.index(x["label"]) if x.get("label") in LABELS else 0)[:25]:
            line = " · ".join(str(x) for x in [h.get("label"), h.get("address"), h.get("kind"),
                                                f"{round(h['surface'])} m²" if h.get("surface") else None, h.get("detail")] if x)
            html.append(f"<li>{escape(line)}</li>")
            text.append(f"- {line}")
        if len(zone_hits) > 25:
            html.append(f"<li>… et {len(zone_hits) - 25} autres</li>")
        html.append("</ul>")
        text.append("")
    link = f"{app_url()}/alertes"
    stop = (f"<a href='{escape(unsubscribe)}'>Se désabonner de ces emails</a> ou gérer l'envoi par secteur sur <a href='{link}'>{link}</a>."
            if unsubscribe else f"Pour ne plus recevoir ces emails, désactivez l'envoi sur <a href='{link}'>{link}</a>.")
    html.append(f"<p><a href='{link}'>Voir les alertes, simuler et préparer les courriers</a></p>"
                "<p style='color:#777;font-size:12px'>Données publiques des DPE (ADEME). Utilisation soumise à l'article 14 des CGV de SPREA. "
                f"{stop}</p>")
    text.append(f"Voir les alertes : {link}")
    if unsubscribe:
        text.append(f"Se désabonner de ces emails : {unsubscribe}")
    return {"subject": subject, "html": "".join(html), "text": "\n".join(text)}


# --- Agent endpoints ---

class ZoneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    radius_m: int = Field(..., ge=200, le=3000)
    labels: List[str] = ["E", "F", "G"]
    kind: Optional[str] = Field(None, pattern="^(maison|appartement|immeuble)$")


class ZoneUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=60)
    active: Optional[bool] = None
    email: Optional[bool] = None


async def require_pro_map(store: SupabaseStore, user: User) -> None:
    profile = await store.ensure_profile(user.id, user.email)
    if not is_pro(profile):
        raise HTTPException(status_code=402, detail="Réservé aux abonnés Pro.")


@router.get("/alerts")
async def list_alerts(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    await require_pro_map(store, user)
    # Within an agency, every member sees the zones and DPE of the others
    profile = await store.ensure_profile(user.id, user.email)
    if profile.get("org"):
        members = {m["user_id"]: m.get("email") for m in await store.list_members(profile["org"]["id"])}
        zones = [{**z, "mine": z["user_id"] == user.id, "owner": members.get(z["user_id"])}
                 for z in await store.list_zones_for_users(list(members))]
        hits = await store.list_hits_for_users(list(members))
    else:
        zones = [{**z, "mine": True, "owner": None} for z in await store.list_zones(user.id)]
        hits = await store.list_hits(user.id)
    return {"zones": zones, "hits": hits, "email_enabled": email_configured()}


@router.post("/alerts/zones", dependencies=[Depends(search_limiter.per_user)])
async def create_zone(data: ZoneCreate, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    await require_pro_map(store, user)
    if len(await store.list_zones(user.id)) >= MAX_ZONES:
        raise HTTPException(status_code=400, detail=f"{MAX_ZONES} zones au maximum : supprimez-en une.")
    labels = [l for l in (x.upper() for x in data.labels) if l in LABELS] or ["E", "F", "G"]
    zone = await store.create_zone({"user_id": user.id, "name": data.name.strip(), "lat": data.lat, "lon": data.lon,
                                    "radius_m": data.radius_m, "labels": ",".join(sorted(set(labels))), "kind": data.kind})
    # First results right away: the DPE of the last days
    try:
        new = await check_zone(store, zone, date.today())
    except httpx.HTTPError:
        new = []
    return {"zone": zone, "new_hits": len(new)}


@router.patch("/alerts/zones/{zone_id}")
async def update_zone(zone_id: str, data: ZoneUpdate, user: User = Depends(current_user),
                      store: SupabaseStore = Depends(store_dep)):
    fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not fields or not await store.update_zone(zone_id, fields, user_id=user.id):
        raise HTTPException(status_code=404, detail="Zone introuvable.")
    return {"updated": True}


@router.delete("/alerts/zones/{zone_id}")
async def delete_zone(zone_id: str, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    if not await store.delete_zone(user.id, zone_id):
        raise HTTPException(status_code=404, detail="Zone introuvable.")
    return {"deleted": True}


def unsubscribe_page(message: str, status_code: int = 200, form: str = "") -> HTMLResponse:
    return HTMLResponse(status_code=status_code, content=(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        "<title>Alertes DPE · SPREA</title></head><body style='font-family:system-ui,sans-serif;max-width:480px;margin:48px auto;padding:0 16px'>"
        f"<h1 style='font-size:20px'>Alertes DPE</h1><p>{message}</p>{form}"
        f"<p><a href='{app_url()}/alertes'>Gérer mes alertes</a></p></body></html>"))


@router.get("/alerts/unsubscribe")
async def unsubscribe_confirm(token: str = ""):
    """Link in the email: asks for a click first, as mail scanners open links."""
    if not unsubscribe_user(token):
        return unsubscribe_page("Ce lien de désabonnement n'est pas valide.", 400)
    return unsubscribe_page(
        "Ne plus recevoir les emails d'alertes DPE ? Les alertes restent visibles dans SPREA.",
        form=f"<form method='post' action='?token={escape(token)}'><button type='submit'>Me désabonner</button></form>")


@router.post("/alerts/unsubscribe")
async def unsubscribe(token: str = "", store: SupabaseStore = Depends(store_dep)):
    """One click (List-Unsubscribe-Post, RFC 8058) or the button of the page:
    emails off for every zone of the user."""
    user_id = unsubscribe_user(token)
    if not user_id:
        return unsubscribe_page("Ce lien de désabonnement n'est pas valide.", 400)
    await store.disable_zone_emails(user_id)
    logger.info("Alert emails unsubscribed")
    return unsubscribe_page("C'est fait : vous ne recevrez plus les emails d'alertes DPE. "
                            "Vous pouvez les réactiver secteur par secteur dans SPREA.")


# --- Daily job (Vercel Cron) ---

async def run_alerts(store: SupabaseStore, today: date, transport: Optional[httpx.AsyncBaseTransport] = None,
                     budget: float = TIME_BUDGET) -> Dict[str, int]:
    zones = await store.active_zones()
    # Zones of users whose Pro subscription ended are kept but not checked
    profiles = {uid: await store.get_profile(uid) for uid in {z["user_id"] for z in zones}}
    todo = [z for z in zones if is_pro(profiles.get(z["user_id"])) and z.get("last_checked_on") != today.isoformat()]
    semaphore = asyncio.Semaphore(5)
    new_by_user: Dict[str, List[Dict[str, Any]]] = {}
    errors = skipped = 0
    started = time.monotonic()

    async def process(zone: Dict[str, Any]) -> None:
        nonlocal errors, skipped
        async with semaphore:
            if time.monotonic() - started > budget:
                skipped += 1
                return
            try:
                new = await check_zone(store, zone, today, transport)
            except Exception as e:  # One zone never stops the others
                errors += 1
                logger.error(f"Alert zone check failed: {type(e).__name__}")
                return
        if new and zone.get("email"):
            new_by_user.setdefault(zone["user_id"], []).extend(new)

    await asyncio.gather(*(process(z) for z in todo))

    sent = 0
    zone_index = {z["id"]: z for z in zones}
    for uid, hits in new_by_user.items():
        email = (profiles.get(uid) or {}).get("email")
        if email:
            url = unsubscribe_url(uid)
            content = email_content(zone_index, hits, url)
            sent += await send_email(email, content["subject"], content["html"], content["text"],
                                     headers={"List-Unsubscribe": f"<{url}>",
                                              "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
    return {"zones_checked": len(todo) - skipped, "users_notified": sent,
            "new_hits": sum(len(h) for h in new_by_user.values()), "errors": errors, "skipped": skipped}


@router.get("/cron/alerts")
async def cron_alerts(authorization: Optional[str] = Header(None)):
    secret = os.getenv("CRON_SECRET", "").strip()
    if not secret or not hmac.compare_digest((authorization or "").encode(), f"Bearer {secret}".encode()):
        raise HTTPException(status_code=401, detail="Non autorisé.")
    result = await run_alerts(get_store(), date.today())
    logger.info(f"Alerts: {result}")
    return result
