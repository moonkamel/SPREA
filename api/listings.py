"""Listings that do not sell: properties for sale in the visible map, online
for a long time or whose price went down, from the Stream Estate API (Melo's
listings feed, many portals and agencies merged into one property). Key in
STREAM_ESTATE_API_KEY.

What the agent sees: where it is, what it is, since when it is online, the
price drops, whether it is sold by a private owner, and the link to the
listing. Not the contact details of the seller: the agent goes through the
listing. Listings saying « agences s'abstenir » are left out by default.
"""
import logging
import math
import os
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

try:
    from api import prospection
    from api.accounts import store_dep
    from api.auth import User, current_user
    from api.opportunities import require_pro
    from api.ratelimit import search_limiter
    from api.store import SupabaseStore
except ImportError:
    import prospection
    from accounts import store_dep
    from auth import User, current_user
    from opportunities import require_pro
    from ratelimit import search_limiter
    from store import SupabaseStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

API_URL = "https://api.stream.estate/documents/properties"
PAGES = 3          # 30 properties a page
CACHE_TTL = 3600
_cache: Dict[Tuple, Tuple[float, Dict[str, Any]]] = {}
NO_AGENCY = re.compile(r"(agences?\s+s.?abstenir|pas\s+d.?agences?|sans\s+agences?|agences?\s+non\s+merci|ni\s+agences?)", re.I)
KINDS = {0: "Appartement", 1: "Maison"}


def api_key() -> str:
    return os.getenv("STREAM_ESTATE_API_KEY", "").strip()


def configured() -> bool:
    return bool(api_key())


def area(bbox: str) -> Tuple[float, float, float]:
    """Centre and radius (km) of the circle around the visible map."""
    west, south, east, north = prospection.parse_bbox(bbox)
    lat, lon = (south + north) / 2, (west + east) / 2
    half_w = (east - west) / 2 * 111.32 * math.cos(math.radians(lat))
    half_h = (north - south) / 2 * 110.57
    return lat, lon, round(max(0.3, math.hypot(half_w, half_h)), 2)


def parse_date(value: Optional[str]) -> Optional[date]:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00")).date() if value else None
    except ValueError:
        return None


def summarize(p: Dict[str, Any], today: date, bbox: Tuple[float, float, float, float]) -> Optional[Dict[str, Any]]:
    loc = p.get("locations") or (p.get("city") or {}).get("location") or {}
    lat, lon = loc.get("lat"), loc.get("lon")
    west, south, east, north = bbox
    if lat is None or lon is None or not (south <= lat <= north and west <= lon <= east):
        return None
    adverts = p.get("adverts") or []
    live = [a for a in adverts if not a.get("expired")] or adverts
    first_seen = min((d for d in (parse_date(a.get("createdAt")) for a in adverts) if d), default=parse_date(p.get("createdAt")))
    drops = [e for a in adverts for e in (a.get("events") or [])
             if e.get("fieldName") == "price" and (e.get("percentVariation") or 0) < 0]
    first_price = None
    for e in sorted(drops, key=lambda e: e.get("createdAt") or ""):
        try:
            first_price = float(e.get("fieldOldValue"))
            break
        except (TypeError, ValueError):
            continue
    price = p.get("price")
    text = " ".join(str(x or "") for x in (p.get("title"), p.get("description")))
    energy = next(((a.get("energy") or {}).get("category") for a in live if (a.get("energy") or {}).get("category")), None)
    advert = max(live, key=lambda a: a.get("updatedAt") or "", default={}) if live else {}
    city = p.get("city") or {}
    return {
        "id": p.get("uuid"), "lat": lat, "lon": lon,
        "city": city.get("name"), "zipcode": city.get("zipcode"), "insee": city.get("insee"),
        "kind": KINDS.get(p.get("propertyType"), "Bien"), "title": p.get("title"),
        "price": price, "surface": p.get("surface"), "rooms": p.get("room"),
        "price_m2": round(p["pricePerMeter"]) if p.get("pricePerMeter") else None,
        "energy": energy if energy in list("ABCDEFG") else None,
        "first_seen": first_seen.isoformat() if first_seen else None,
        "days_online": (today - first_seen).days if first_seen else None,
        "drops": len(drops),
        "drop_pct": round(100 * (price - first_price) / first_price, 1) if price and first_price else None,
        "private": 0 in (p.get("publisherTypes") or []) and 1 not in (p.get("publisherTypes") or []),
        "portals": len({(a.get("publisher") or {}).get("name") for a in adverts if a.get("publisher")}),
        "no_agency": bool(NO_AGENCY.search(text)),
        "url": advert.get("url"), "picture": (p.get("pictures") or [None])[0],
    }


async def fetch(params: List[Tuple[str, str]], transport: Optional[httpx.AsyncBaseTransport] = None) -> List[Dict[str, Any]]:
    members: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20, transport=transport,
                                 headers={"X-API-KEY": api_key(), "Content-Type": "application/json"}) as client:
        for page in range(1, PAGES + 1):
            res = await client.get(API_URL, params=params + [("page", str(page))])
            if res.status_code in (401, 403):
                raise PermissionError("Clé Stream Estate refusée.")
            res.raise_for_status()
            data = res.json()
            batch = data.get("hydra:member") or []
            members += batch
            if len(batch) < 30 or not (data.get("hydra:view") or {}).get("hydra:next"):
                break
    return members


async def stale_listings(bbox: str, min_days: int, mode: str, private_only: bool, today: Optional[date] = None,
                         transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    today = today or date.today()
    box = prospection.parse_bbox(bbox)
    lat, lon, radius = area(bbox)
    key = (round(lat, 3), round(lon, 3), radius, min_days, mode, private_only, today.isoformat())
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    params = [("lat", f"{lat:.6f}"), ("lon", f"{lon:.6f}"), ("radius", str(radius)), ("transactionType", "0"),
              ("expired", "false"), ("withLocation", "true"), ("itemsPerPage", "30"),
              ("propertyTypes[]", "0"), ("propertyTypes[]", "1")]
    if mode == "baisse":
        # Price lowered in the last three months
        params += [("eventPriceVariationMax", "-1"), ("eventPriceVariationFromCreatedAt", (today - timedelta(days=90)).isoformat()),
                   ("order[updatedAt]", "desc")]
    else:
        # Online since at least min_days: the property was created before
        params += [("toDate", (today - timedelta(days=min_days)).isoformat()), ("order[createdAt]", "asc")]
    if private_only:
        params.append(("publisherTypes[]", "0"))
    members = await fetch(params, transport)
    items = [s for s in (summarize(p, today, box) for p in members) if s]
    kept = [s for s in items if not s["no_agency"]]
    kept.sort(key=lambda s: (-(s["days_online"] or 0)) if mode != "baisse" else (s["drop_pct"] or 0))
    out = {"items": kept, "hidden_no_agency": len(items) - len(kept), "truncated": len(members) >= PAGES * 30}
    _cache[key] = (time.time(), out)
    return out


@router.get("/listings", dependencies=[Depends(search_limiter.per_user)])
async def listings(bbox: str, min_days: int = Query(60, ge=30, le=365), mode: str = Query("anciennes", pattern="^(anciennes|baisse)$"),
                   private: bool = False, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    await require_pro(user, store)
    if not configured():
        raise HTTPException(status_code=503, detail="Le flux d'annonces n'est pas encore activé.")
    try:
        return await stale_listings(bbox, min_days, mode, private)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        logger.error(str(e))
        raise HTTPException(status_code=502, detail="Le flux d'annonces est indisponible.")
    except httpx.HTTPError as e:
        logger.error(f"Listings failed: {type(e).__name__}")
        raise HTTPException(status_code=502, detail="Le flux d'annonces ne répond pas pour le moment.")
