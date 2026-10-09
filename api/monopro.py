"""Whole buildings held by a single owner (monopropriétés), for the
prospection map: the buildings an investor may buy in one piece, split and
sell flat by flat.

Sources, all public:
- BDNB (CSTB, Licence Ouverte 2.0), loaded into Supabase by
  scripts/monopro/import_bdnb.py: dwellings, copropriété registration,
  owning company (personnes morales of the land registry), DPE, last sale;
- Annuaire des entreprises (recherche-entreprises.api.gouv.fr, data from
  INSEE Sirene and the RNE): registered office and officers of the owning
  company, read at request time and not stored.

The identity of private owners is not public: such buildings are shown with
an unknown owner. Officers' names come from the public company registers; the
subscriber uses them under article 14 of the CGV (origin of the data stated,
objections honoured, no phone or email canvassing).
"""
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response

try:
    from api import monopro_pdf
    from api.accounts import is_pro, safe_filename, store_dep
    from api.auth import User, current_user
    from api.dvf import market_price
    from api.immeuble import ademe_rows
    from api.monopro_report import DEFAULT_UNIT_M2, build_dossier
    from api.prospection import parse_bbox
    from api.ratelimit import ai_limiter, search_limiter
    from api.store import SupabaseStore
except ImportError:
    import monopro_pdf
    from accounts import is_pro, safe_filename, store_dep
    from auth import User, current_user
    from dvf import market_price
    from immeuble import ademe_rows
    from monopro_report import DEFAULT_UNIT_M2, build_dossier
    from prospection import parse_bbox
    from ratelimit import ai_limiter, search_limiter
    from store import SupabaseStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

COMPANY_URL = "https://recherche-entreprises.api.gouv.fr/search"
MAX_BUILDINGS = 1500
PORTFOLIO_LIMIT = 50
CACHE_TTL = 24 * 3600
_company_cache: Dict[str, Tuple[float, Optional[Dict]]] = {}


async def require_pro(store: SupabaseStore, user: User) -> None:
    profile = await store.ensure_profile(user.id, user.email)
    if not is_pro(profile):
        raise HTTPException(status_code=402, detail="Réservé aux abonnés Pro.")


def owner_summary(owner: Optional[Dict]) -> Optional[Dict]:
    if not owner:
        return None
    return {"siren": owner["siren"], "name": owner.get("name"), "legal_form": owner.get("legal_form"),
            "city": " ".join(x for x in (owner.get("postcode"), owner.get("city")) if x) or None}


def building_summary(b: Dict, owners: Dict[str, Dict]) -> Dict:
    return {
        "id": b["id"], "address": b.get("address"), "lat": b["lat"], "lon": b["lon"],
        "nb_log": b["nb_log"], "levels": b.get("levels"), "year_built": b.get("year_built"),
        "owner": owner_summary(owners.get(b.get("owner_siren") or "")),
        "owner_share": b.get("owner_share"),
        "dpe_label": b.get("dpe_label"), "dpe_date": b.get("dpe_date"),
        "dpe_count": b.get("dpe_count"), "dpe_fg": b.get("dpe_fg"),
        "last_sale_date": b.get("last_sale_date"), "last_sale_price": b.get("last_sale_price"),
        "last_sale_units": b.get("last_sale_units"),
    }


def company_details(result: Dict) -> Dict:
    """Registered office and officers, as published by the Annuaire des entreprises."""
    siege = result.get("siege") or {}
    officers = []
    for d in result.get("dirigeants") or []:
        if d.get("type_dirigeant") == "personne physique":
            name = " ".join(x for x in ((d.get("prenoms") or "").split(" ")[0].title(), (d.get("nom") or "").upper()) if x)
        else:
            name = d.get("denomination") or d.get("nom")
        if name:
            officers.append({"name": name, "role": d.get("qualite"), "company": d.get("type_dirigeant") != "personne physique"})
    return {
        "name": result.get("nom_raison_sociale") or result.get("nom_complet"),
        "address": siege.get("adresse"),
        "active": result.get("etat_administratif") == "A",
        "created": result.get("date_creation"),
        "officers": officers[:6],
        "url": f"https://annuaire-entreprises.data.gouv.fr/entreprise/{result.get('siren')}",
    }


async def fetch_company(siren: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> Optional[Dict]:
    cached = _company_cache.get(siren)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            res = await client.get(COMPANY_URL, params={"q": siren, "per_page": 1})
            res.raise_for_status()
            results = [r for r in res.json().get("results") or [] if r.get("siren") == siren]
    except httpx.HTTPError as e:
        logger.warning(f"Company lookup failed: {type(e).__name__}")
        return None  # Not cached: retried next time
    details = company_details(results[0]) if results else None
    _company_cache[siren] = (time.time(), details)
    return details


# Building found from the position of a DPE: within about 40 m
NEAR_DEG = 0.0004
NEAR_M = 40


def metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat1 - lat2) * 111_320
    dx = (lon1 - lon2) * 111_320 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


@router.get("/monopro/near", dependencies=[Depends(search_limiter)])
async def monopro_near(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
                       user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    """The whole building at the position of a building DPE, if a private company holds it."""
    await require_pro(store, user)
    around = await store.monopro_in_bbox(lon - NEAR_DEG, lat - NEAR_DEG, lon + NEAR_DEG, lat + NEAR_DEG, False, 3, 20)
    close = sorted((metres(lat, lon, b["lat"], b["lon"]), b["id"]) for b in around)
    if not close or close[0][0] > NEAR_M:
        raise HTTPException(status_code=404, detail="Aucun immeuble détenu par une société à cette adresse.")
    return {"id": close[0][1]}


@router.get("/monopro", dependencies=[Depends(search_limiter)])
async def monopro_map(bbox: str, owner: str = Query("all", pattern="^(all|company)$"),
                      min_log: int = Query(3, ge=3, le=200), dpe: str = Query("all", pattern="^(all|fg)$"),
                      user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    await require_pro(store, user)
    try:
        west, south, east, north = parse_bbox(bbox)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        buildings = await store.monopro_in_bbox(west, south, east, north, owner == "company", min_log, MAX_BUILDINGS + 1,
                                                poor_dpe=dpe == "fg")
        sirens = sorted({b["owner_siren"] for b in buildings if b.get("owner_siren")})
        owners = {o["siren"]: o for o in await store.monopro_owners(sirens)} if sirens else {}
    except httpx.HTTPError as e:
        logger.error(f"Monopro lookup failed: {type(e).__name__}")
        raise HTTPException(status_code=502, detail="La recherche a échoué, réessayez dans un instant.")
    return {
        "buildings": [building_summary(b, owners) for b in buildings[:MAX_BUILDINGS]],
        "truncated": len(buildings) > MAX_BUILDINGS,
    }


@router.get("/monopro/{building_id}/dossier", dependencies=[Depends(ai_limiter)])
async def monopro_dossier(building_id: str, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    """Sale dossier of the building (PDF), in the agency's name."""
    await require_pro(store, user)
    building = await store.get_monopro(building_id) if building_id.startswith("bdnb-") and len(building_id) <= 40 else None
    if not building:
        raise HTTPException(status_code=404, detail="Immeuble introuvable.")
    agency = await store.get_agent_page(user.id) or {}
    if not agency.get("agency_name"):
        raise HTTPException(status_code=409, detail="Renseignez d'abord le nom de votre agence : il figure sur le dossier.")
    siren = building.get("owner_siren")
    owner = (await store.monopro_owners([siren]) or [None])[0] if siren else None
    portfolio = len(await store.monopro_by_owner(siren, PORTFOLIO_LIMIT + 1)) - 1 if siren else 0
    company = await fetch_company(siren) if siren else None
    rows: List[Dict] = []
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            rows = await ademe_rows(client, {"geo_distance": f"{building['lon']},{building['lat']},30", "size": "300"})
    except httpx.HTTPError as e:
        logger.warning(f"ADEME lookup failed for the dossier: {type(e).__name__}")
    market = None
    try:
        market = await market_price(building.get("insee") or "", "Appartement", building["lat"], building["lon"], DEFAULT_UNIT_M2)
    except Exception as e:  # The dossier is still useful without prices
        logger.warning(f"DVF lookup failed for the dossier: {type(e).__name__}")
    dossier = build_dossier(building, owner, company, max(portfolio, 0), rows, market, agency)
    filename = safe_filename(building.get("address") or "immeuble")[:60]
    return Response(content=monopro_pdf.generate(dossier), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=Dossier_immeuble_{filename}.pdf"})


@router.get("/monopro/{building_id}", dependencies=[Depends(search_limiter)])
async def monopro_sheet(building_id: str, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    await require_pro(store, user)
    if not building_id.startswith("bdnb-") or len(building_id) > 40:
        raise HTTPException(status_code=404, detail="Immeuble introuvable.")
    building = await store.get_monopro(building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Immeuble introuvable.")
    siren = building.get("owner_siren")
    owners: Dict[str, Dict] = {}
    portfolio: List[Dict[str, Any]] = []
    company = None
    if siren:
        owners = {o["siren"]: o for o in await store.monopro_owners([siren])}
        others = await store.monopro_by_owner(siren, PORTFOLIO_LIMIT + 1)
        portfolio = [{"id": b["id"], "address": b.get("address"), "nb_log": b["nb_log"], "dpe_label": b.get("dpe_label"),
                      "lat": b["lat"], "lon": b["lon"]} for b in others if b["id"] != building_id][:PORTFOLIO_LIMIT]
        company = await fetch_company(siren)
    return {**building_summary(building, owners), "company": company, "portfolio": portfolio}
