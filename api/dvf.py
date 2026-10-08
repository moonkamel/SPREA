"""Local market price per m2, from the DVF open data (Demandes de valeurs
foncières, DGFiP), as published by Etalab ("geo-dvf": one CSV per commune and
per year, with the coordinates of each sale).

Median price per m2 of the sales of the same kind of dwelling (house or
apartment): within 1 km of the dwelling when there are enough of them, else
in the whole commune. Used for the "valeur verte" (green value).
"""
import csv
import io
import logging
import math
import statistics
import time
from datetime import date
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

DVF_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/communes/{dep}/{insee}.csv"

NEAR_RADIUS_M = 1000
MIN_NEAR_SALES = 15
MIN_COMMUNE_SALES = 10
# The two most recent years with data, up to 4 years when sales are scarce
MIN_YEARS, MAX_YEARS = 2, 4
# Excludes outliers (garages sold as dwellings, data errors)
MIN_SURFACE, MIN_PRICE_M2, MAX_PRICE_M2 = 9, 300, 30000

DWELLING_TYPES = {"Maison", "Appartement"}
# Mutations mixing dwellings with these are not representative
EXCLUDED_TYPES = {"Local industriel. commercial ou assimilé"}

CACHE_TTL = 24 * 3600
_cache: Dict[Tuple, Tuple[float, Optional[Dict]]] = {}


def department(insee: str) -> str:
    return insee[:3] if insee.startswith("97") else insee[:2]


def _float(value: Optional[str]) -> Optional[float]:
    try:
        return float((value or "").replace(",", ".")) if value not in (None, "") else None
    except ValueError:
        return None


def parse_sales(text: str, kind: str, year: int) -> List[Dict]:
    """Single-dwelling sales of the given kind, with their price per m2."""
    mutations: Dict[str, List[Dict]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("nature_mutation") != "Vente":
            continue
        mutations.setdefault(row.get("id_mutation") or "", []).append(row)
    sales = []
    for rows in mutations.values():
        types = [r.get("type_local") or "" for r in rows]
        if any(t in EXCLUDED_TYPES for t in types):
            continue
        dwellings = [r for r in rows if r.get("type_local") in DWELLING_TYPES]
        if len(dwellings) != 1 or dwellings[0]["type_local"] != kind:
            continue
        d = dwellings[0]
        price = _float(d.get("valeur_fonciere"))
        surface = _float(d.get("surface_reelle_bati"))
        if not price or not surface or surface < MIN_SURFACE:
            continue
        price_m2 = price / surface
        if not MIN_PRICE_M2 <= price_m2 <= MAX_PRICE_M2:
            continue
        sales.append({"price_m2": price_m2, "lat": _float(d.get("latitude")), "lon": _float(d.get("longitude")),
                      "year": year, "commune": d.get("nom_commune")})
    return sales


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def summarize(sales: List[Dict], kind: str, lat: Optional[float], lon: Optional[float]) -> Optional[Dict]:
    if lat is not None and lon is not None:
        near = [s for s in sales if s["lat"] is not None and s["lon"] is not None
                and distance_m(lat, lon, s["lat"], s["lon"]) <= NEAR_RADIUS_M]
        if len(near) >= MIN_NEAR_SALES:
            return _result(near, kind, f"à moins de {NEAR_RADIUS_M // 1000} km")
    if len(sales) >= MIN_COMMUNE_SALES:
        commune = next((s["commune"] for s in sales if s["commune"]), None)
        return _result(sales, kind, f"à {commune}" if commune else "dans la commune")
    return None


def _result(sales: List[Dict], kind: str, scope: str) -> Dict:
    years = sorted({s["year"] for s in sales})
    period = str(years[0]) if len(years) == 1 else f"{years[0]}-{years[-1]}"
    label = "maisons" if kind == "Maison" else "appartements"
    n = len(sales)
    return {
        "price_per_m2": round(statistics.median(s["price_m2"] for s in sales)),
        "sales": n,
        "scope": scope,
        "period": period,
        "kind": label,
        "source": f"prix médian DVF de {n} ventes {'de maisons' if kind == 'Maison' else 'd’appartements'} {scope} ({period})",
    }


async def market_price(insee: str, building_type: Optional[str], lat: Optional[float] = None,
                       lon: Optional[float] = None, transport: Optional[httpx.AsyncBaseTransport] = None,
                       today: Optional[date] = None) -> Optional[Dict]:
    """Median price per m2 for this kind of dwelling around this place, or None."""
    insee = (insee or "").strip().upper()
    if len(insee) != 5:
        return None
    kind = "Maison" if "maison" in (building_type or "").lower() else "Appartement"
    key = (insee, kind, round(lat or 0, 3), round(lon or 0, 3))
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]

    today = today or date.today()
    sales: List[Dict] = []
    years_found = 0
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            # Recent years first; the current year is usually not published yet
            for year in range(today.year, today.year - 7, -1):
                res = await client.get(DVF_URL.format(year=year, dep=department(insee), insee=insee))
                if res.status_code == 404:
                    continue
                res.raise_for_status()
                sales += parse_sales(res.text, kind, year)
                years_found += 1
                if years_found >= MAX_YEARS or (years_found >= MIN_YEARS and len(sales) >= 4 * MIN_NEAR_SALES):
                    break
    except httpx.HTTPError as e:
        logger.error(f"DVF fetch failed: {type(e).__name__}")
        return None

    result = summarize(sales, kind, lat, lon)
    _cache[key] = (time.time(), result)
    return result
