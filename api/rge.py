"""RGE companies near a dwelling, for each planned work.

Source: ADEME open data "Liste des entreprises RGE" (data-fair, updated daily),
one line per company and qualification, with its work domain and location.
Public professional data (Licence Ouverte 2.0): shown as found, closest first,
without any ranking or recommendation.
"""
import asyncio
import logging
import math
import time
import unicodedata
from datetime import date
from typing import Dict, List, Optional, Tuple

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

RGE_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/liste-des-entreprises-rge-2/lines"
FIELDS = "siret,nom_entreprise,adresse,code_postal,commune,latitude,longitude,telephone,email,site_internet,domaine,lien_date_fin,particulier"

# Work of the simulation -> RGE work domains (values of the "domaine" field)
DOMAINS: Dict[str, List[str]] = {
    "iti": ["Isolation par l'intérieur des murs ou rampants de toitures  ou plafonds"],
    "ite": ["Isolation des murs par l'extérieur"],
    "roof": ["Isolation des combles perdus", "Isolation des toitures terrasses ou des toitures par l'extérieur",
             "Isolation par l'intérieur des murs ou rampants de toitures  ou plafonds"],
    "floor_ceiling": ["Isolation des planchers bas"],
    "windows": ["Fenêtres, volets, portes donnant sur l'extérieur"],
    "vmc": ["Ventilation mécanique"],
    "pac_air_eau": ["Pompe à chaleur : chauffage"],
    "heating": ["Radiateurs électriques, dont régulation."],
    "ecs": ["Chauffe-Eau Thermodynamique"],
}
# A renovation of several works: global renovation companies and energy audits
GLOBAL_DOMAINS = ["Projet complet de rénovation"]
AUDIT_DOMAINS = {"maison": ["Audit énergétique Maison individuelle"], "appartement": ["Audit énergétique Logement collectif"]}

GEO_URL = "https://geo.api.gouv.fr/communes"

RADII_KM = (10, 25, 50)
# A company whose town lies further than this from the dwelling, although
# ADEME puts it close by, has wrong coordinates in the directory
MAX_TOWN_KM = 15
PER_WORK = 3
CACHE_TTL = 24 * 3600
_cache: Dict[Tuple, Tuple[float, Dict]] = {}
_towns: Dict[str, Optional[List[Tuple[str, float, float]]]] = {}  # postcode -> (name, lat, lon) of its towns


def _norm(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return "".join(c for c in text if c.isalnum())


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


async def _postcode_towns(client: httpx.AsyncClient, postcode: str) -> Optional[List[Tuple[str, float, float]]]:
    """Towns of a postcode with their centre (geo.api.gouv.fr); None when unknown."""
    if postcode in _towns:
        return _towns[postcode]
    towns = None
    try:
        res = await client.get(GEO_URL, params={"codePostal": postcode, "fields": "nom,centre", "format": "json"}, timeout=4)
        if res.status_code == 200:
            towns = [(_norm(t["nom"]), t["centre"]["coordinates"][1], t["centre"]["coordinates"][0])
                     for t in res.json() if isinstance(t, dict) and t.get("centre")]
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
        towns = None
    _towns[postcode] = towns or None
    return _towns[postcode]


def town_distance(row: Dict, towns: Optional[List[Tuple[str, float, float]]], lat: float, lon: float) -> Optional[float]:
    """Distance from the dwelling to the centre of the company's town, when known."""
    if not towns:
        return None
    name = _norm(row.get("commune") or "")
    match = [t for t in towns if t[0] == name] or [t for t in towns if name and (name in t[0] or t[0] in name)]
    if not match and len(towns) > 1:
        return None
    t = (match or towns)[0]
    return km(lat, lon, t[1], t[2])


async def plausible(client: httpx.AsyncClient, rows: List[Dict], lat: float, lon: float) -> List[Dict]:
    """Drops the companies whose town is far from the dwelling while ADEME
    places them nearby (wrong coordinates in the directory)."""
    postcodes = sorted({r.get("code_postal") for r in rows if r.get("code_postal")})
    towns = dict(zip(postcodes, await asyncio.gather(*(_postcode_towns(client, p) for p in postcodes))))
    out = []
    for r in rows:
        d = town_distance(r, towns.get(r.get("code_postal")), lat, lon)
        if d is not None and d > MAX_TOWN_KM:
            continue
        out.append(r)
    return out


def query(domains: List[str]) -> str:
    """Lucene query on the exact domain values, for companies working for private clients."""
    values = " OR ".join('"' + d.replace('"', '\\"') + '"' for d in domains)
    return f"domaine:({values}) AND particulier:true"


def company(row: Dict) -> Dict:
    return {
        "siret": row.get("siret"),
        "name": (row.get("nom_entreprise") or "").strip(),
        "address": " ".join(x for x in (row.get("adresse"), row.get("code_postal"), row.get("commune")) if x),
        "city": (row.get("commune") or "").title(),
        "phone": row.get("telephone") or None,
        "email": row.get("email") or None,
        "website": row.get("site_internet") or None,
        "domain": row.get("domaine"),
        "distance_km": round((row.get("_geo_distance") or 0) / 1000, 1),
    }


def closest_companies(rows: List[Dict], today: date, limit: int = PER_WORK) -> List[Dict]:
    """One entry per company (a company holds several qualifications), still
    qualified today, closest first."""
    seen, out = set(), []
    for row in sorted(rows, key=lambda r: r.get("_geo_distance") or 0):
        end = row.get("lien_date_fin") or ""
        if end and end < today.isoformat():
            continue
        key = row.get("siret") or row.get("nom_entreprise")
        if key in seen:
            continue
        seen.add(key)
        out.append(company(row))
        if len(out) >= limit:
            break
    return out


async def search(client: httpx.AsyncClient, lat: float, lon: float, domains: List[str], today: date,
                 limit: int = PER_WORK) -> List[Dict]:
    """Closest companies for these domains, widening the radius when needed."""
    found: List[Dict] = []
    for radius in RADII_KM:
        res = await client.get(RGE_URL, params={
            "qs": query(domains), "geo_distance": f"{lon},{lat},{radius * 1000}",
            "size": 40, "select": FIELDS})
        res.raise_for_status()
        rows = await plausible(client, res.json().get("results") or [], lat, lon)
        found = closest_companies(rows, today, limit)
        if len(found) >= limit:
            break
    return found


async def nearby(lat: float, lon: float, works: List[str], kind: Optional[str] = None,
                 transport: Optional[httpx.AsyncBaseTransport] = None, today: Optional[date] = None) -> Dict:
    """For each work: the closest qualified companies. Plus, for a renovation of
    several works, global renovation companies and energy auditors."""
    today = today or date.today()
    works = [w for w in dict.fromkeys(works) if w in DOMAINS]
    key = (round(lat, 3), round(lon, 3), tuple(sorted(works)), kind)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    result: Dict = {"works": {}, "global": [], "audit": []}
    async with httpx.AsyncClient(timeout=10, transport=transport) as client:
        for w in works:
            result["works"][w] = await search(client, lat, lon, DOMAINS[w], today)
        if len(works) >= 2:
            result["global"] = await search(client, lat, lon, GLOBAL_DOMAINS, today, limit=2)
            audit = AUDIT_DOMAINS["maison" if (kind or "").lower().startswith("maison") else "appartement"]
            result["audit"] = await search(client, lat, lon, audit, today, limit=2)
    _cache[key] = (time.time(), result)
    return result


async def nearby_or_empty(lat: Optional[float], lon: Optional[float], works: List[str], kind: Optional[str] = None,
                          transport: Optional[httpx.AsyncBaseTransport] = None) -> Optional[Dict]:
    """Same, for the report: None when the location is unknown or ADEME does not answer."""
    if lat is None or lon is None or not works:
        return None
    try:
        return await nearby(lat, lon, works, kind, transport)
    except httpx.HTTPError as e:
        logger.warning(f"RGE lookup failed: {type(e).__name__}")
        return None


@router.get("/rge", dependencies=[Depends(search_limiter), Depends(subscriber_access)])
async def rge_companies(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
                        works: str = "", kind: Optional[str] = None):
    work_list = [w for w in works.split(",") if w in DOMAINS]
    if not work_list:
        return {"works": {}, "global": [], "audit": []}
    try:
        return await nearby(lat, lon, work_list, kind)
    except httpx.HTTPError as e:
        logger.error(f"RGE lookup failed: {type(e).__name__}")
        raise HTTPException(status_code=502, detail="L'annuaire RGE de l'ADEME ne répond pas pour le moment.")
