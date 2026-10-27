"""Cadastral reference of the parcel at a point, for the « Connaître le
propriétaire » request: anyone can ask the land registry service or the town
hall for the owner of a given property (article L107 A of the Livre des
procédures fiscales, a few requests a week). SPREA only prefills that request
with the parcel reference; it never fetches nor stores owners' names.

Source: API Carto cadastre of the IGN (parcels of the cadastral map, open data).
"""
import json
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

try:
    from api.accounts import subscriber_access
    from api.ratelimit import search_limiter
except ImportError:
    from accounts import subscriber_access
    from ratelimit import search_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

PARCEL_URL = "https://apicarto.ign.fr/api/cadastre/parcelle"
# An address point often lies on the street: then the parcels within this distance
AROUND_M = 25
CACHE_TTL = 7 * 24 * 3600
_cache: Dict[Tuple[float, float], Tuple[float, Optional[Dict]]] = {}

# Tests only: an httpx transport answering in place of the API
TRANSPORT: Optional[httpx.AsyncBaseTransport] = None


def _centroid(geometry: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Mean of the outer ring's points (lon, lat): enough to rank close parcels."""
    coords = geometry.get("coordinates") or []
    if geometry.get("type") == "MultiPolygon":
        coords = coords[0] if coords else []
    ring = coords[0] if coords else []
    if not ring:
        return None
    return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)


def parcel(props: Dict[str, Any]) -> Dict[str, Any]:
    dep = props.get("code_dep") or ""
    com = props.get("code_com") or ""
    insee = props.get("code_insee") or (dep + com if dep and com else None)
    return {"insee": insee, "commune": props.get("nom_com"), "section": props.get("section"),
            "numero": props.get("numero"), "prefixe": props.get("com_abs") if props.get("com_abs") not in (None, "000") else None,
            "idu": props.get("idu"), "contenance": props.get("contenance")}


async def _query(client: httpx.AsyncClient, geom: Dict[str, Any]) -> List[Dict[str, Any]]:
    res = await client.get(PARCEL_URL, params={"geom": json.dumps(geom)})
    res.raise_for_status()
    return res.json().get("features") or []


async def find_parcel(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    key = (round(lat, 6), round(lon, 6))
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    async with httpx.AsyncClient(timeout=15, transport=TRANSPORT) as client:
        features = await _query(client, {"type": "Point", "coordinates": [lon, lat]})
        if not features:
            dlat = AROUND_M / 111320
            dlon = AROUND_M / (111320 * math.cos(math.radians(lat)))
            square = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat],
                      [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]
            near = await _query(client, {"type": "Polygon", "coordinates": [square]})

            def dist(f):
                c = _centroid(f.get("geometry") or {})
                return math.hypot(c[0] - lon, c[1] - lat) if c else 1e9
            features = sorted(near, key=dist)
    found = parcel(features[0]["properties"]) if features else None
    _cache[key] = (time.time(), found)
    return found


@router.get("/parcel", dependencies=[Depends(search_limiter), Depends(subscriber_access)])
async def get_parcel(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    try:
        found = await find_parcel(lat, lon)
    except httpx.HTTPError as e:
        logger.error(f"Cadastre lookup failed: {type(e).__name__}")
        raise HTTPException(status_code=502, detail="Le cadastre ne répond pas, réessayez dans un instant.")
    if not found:
        raise HTTPException(status_code=404, detail="Aucune parcelle cadastrale trouvée à cette adresse.")
    return found
