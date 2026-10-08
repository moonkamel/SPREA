"""Local market price per m2, from the DVF open data (Demandes de valeurs
foncières, DGFiP), as published by Etalab ("geo-dvf": one CSV per commune and
per year, with the coordinates of each sale).

Comparable sales: same kind of dwelling (house or apartment), a similar
surface (price per m2 falls as surface grows), as close as possible to the
dwelling: within 500 m, then 1 km, 2 km, then the whole commune, until there
are enough sales. In small communes, the search widens to the neighbouring
communes (5 km, then 10 km). Older sales are brought to today's prices with the quarterly
index measured by scripts/green_value/build.py. The result is the median, with
the interquartile range.
"""
import asyncio
import csv
import io
import logging
import math
import statistics
import time
from datetime import date
from typing import Dict, List, Optional, Tuple

import httpx

try:
    from api.green_value import quarter_index
except ImportError:
    from green_value import quarter_index

logger = logging.getLogger(__name__)

DVF_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/communes/{dep}/{insee}.csv"
COMMUNES_URL = "https://geo.api.gouv.fr/departements/{dep}/communes?fields=code,nom,centre&format=json"

# (radius in metres, minimum number of comparable sales)
RINGS = [(500, 20), (1000, 15), (2000, 15)]
MIN_COMMUNE_SALES = 10
# Neighbouring communes, when the commune has too few sales
WIDE_RINGS = [(5000, 15), (10000, 15)]
MAX_NEIGHBOURS = 12
# Comparable surface: from 60 % to 160 % of the dwelling's surface
SURFACE_BAND = (0.6, 1.6)
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


def quarter(d: str) -> str:
    return f"{d[:4]}T{(int(d[5:7]) - 1) // 3 + 1}" if len(d) >= 7 else ""


def parse_sales(text: str, kind: str, year: int) -> List[Dict]:
    """Single-dwelling sales of the given kind, with their price per m2."""
    mutations: Dict[str, List[Dict]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("nature_mutation") != "Vente":
            continue
        mutations.setdefault(row.get("id_mutation") or "", []).append(row)
    sales = []
    for rows in mutations.values():
        if any((r.get("type_local") or "") in EXCLUDED_TYPES for r in rows):
            continue
        dwellings = [r for r in rows if r.get("type_local") in DWELLING_TYPES]
        # The same dwelling can appear on several parcels
        if len({(r["type_local"], r.get("surface_reelle_bati")) for r in dwellings}) != 1 or dwellings[0]["type_local"] != kind:
            continue
        d = dwellings[0]
        price = _float(d.get("valeur_fonciere"))
        surface = _float(d.get("surface_reelle_bati"))
        carrez = _float(d.get("lot1_surface_carrez")) if kind == "Appartement" else None
        if carrez and surface and abs(carrez - surface) / surface < 0.25:
            surface = carrez
        if not price or not surface or surface < MIN_SURFACE:
            continue
        price_m2 = price / surface
        if not MIN_PRICE_M2 <= price_m2 <= MAX_PRICE_M2:
            continue
        sales.append({"price_m2": price_m2, "surface": surface, "price": price, "lat": _float(d.get("latitude")),
                      "lon": _float(d.get("longitude")), "year": year, "quarter": quarter(d.get("date_mutation") or ""),
                      "date": (d.get("date_mutation") or "")[:10], "street": (d.get("adresse_nom_voie") or "").strip(),
                      "rooms": d.get("nombre_pieces_principales") or None, "commune": d.get("nom_commune")})
    return sales


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def adjust_to_today(sales: List[Dict], index: Dict[str, float]) -> None:
    """Brings each price to the latest quarter of the index (log change)."""
    for s in sales:
        s["adjusted_m2"] = s["price_m2"] * math.exp(-index.get(s["quarter"], 0.0))


def summarize(sales: List[Dict], kind: str, lat: Optional[float], lon: Optional[float],
              surface: Optional[float] = None, adjusted: bool = False, wide: bool = False) -> Optional[Dict]:
    pool = sales
    similar = "de surface comparable "
    if surface:
        low, high = surface * SURFACE_BAND[0], surface * SURFACE_BAND[1]
        banded = [s for s in sales if low <= s["surface"] <= high]
        # Not enough sales of a similar surface: all surfaces
        if len(banded) >= MIN_COMMUNE_SALES:
            pool = banded
        else:
            similar = ""
    else:
        similar = ""
    if lat is not None and lon is not None:
        located = [(distance_m(lat, lon, s["lat"], s["lon"]), s) for s in pool if s["lat"] is not None and s["lon"] is not None]
        for d, s in located:
            s["distance"] = d
        for radius, minimum in (WIDE_RINGS if wide else RINGS):
            near = [s for d, s in located if d <= radius]
            if len(near) >= minimum:
                scope = f"à moins de {radius} m" if radius < 1000 else f"à moins de {radius // 1000} km"
                if wide:
                    scope += ", communes voisines incluses"
                return {**_result(near, kind, scope, similar, adjusted), "wide": wide}
    if wide:
        return None
    if len(pool) >= MIN_COMMUNE_SALES:
        commune = next((s["commune"] for s in pool if s["commune"]), None)
        return _result(pool, kind, f"à {commune}" if commune else "dans la commune", similar, adjusted)
    return None


def _result(sales: List[Dict], kind: str, scope: str, similar: str, adjusted: bool) -> Dict:
    prices = sorted(s.get("adjusted_m2", s["price_m2"]) for s in sales)
    years = sorted({s["year"] for s in sales})
    period = str(years[0]) if len(years) == 1 else f"{years[0]}-{years[-1]}"
    n = len(sales)
    q = statistics.quantiles(prices, n=4) if n >= 4 else [prices[0], statistics.median(prices), prices[-1]]
    what = "de maisons" if kind == "Maison" else "d’appartements"
    return {
        "price_per_m2": round(statistics.median(prices)),
        "q25": round(q[0]),
        "q75": round(q[2]),
        "sales": n,
        "scope": scope,
        "period": period,
        "kind": "maisons" if kind == "Maison" else "appartements",
        "source": (f"prix médian DVF de {n} ventes {what} {similar}{scope} ({period}"
                   + (", actualisées au dernier trimestre)" if adjusted else ")")),
        "comparables": comparables(sales),
    }


def comparables(sales: List[Dict], limit: int = 8) -> List[Dict]:
    """Closest and most recent sales, for the valuation report. The street is
    shown without the house number."""
    ranked = sorted(sales, key=lambda s: (round(s.get("distance", 1e9) / 250), -int(s["date"].replace("-", "") or 0)))
    return [{
        "date": s["date"], "street": s["street"].title() if s["street"].isupper() else s["street"],
        "commune": s.get("commune"),
        "surface": round(s["surface"], 1), "rooms": s.get("rooms"), "price": round(s["price"]),
        "price_m2": round(s["price_m2"]), "adjusted_m2": round(s.get("adjusted_m2", s["price_m2"])),
        "distance": round(s["distance"]) if s.get("distance") is not None else None,
    } for s in ranked[:limit]]


async def commune_sales(client: httpx.AsyncClient, insee: str, kind: str, today: date) -> List[Dict]:
    """Sales of the commune, most recent years first; the current year is
    usually not published yet."""
    sales: List[Dict] = []
    years_found = 0
    for year in range(today.year, today.year - 7, -1):
        res = await client.get(DVF_URL.format(year=year, dep=department(insee), insee=insee))
        if res.status_code == 404:
            continue
        res.raise_for_status()
        sales += parse_sales(res.text, kind, year)
        years_found += 1
        if years_found >= MAX_YEARS or (years_found >= MIN_YEARS and len(sales) >= 200):
            break
    return sales


async def neighbours(client: httpx.AsyncClient, insee: str, lat: Optional[float],
                     lon: Optional[float]) -> Tuple[List[str], Optional[float], Optional[float]]:
    """Communes of the department whose centre is within the widest ring, the
    closest first, and the reference point (the commune's centre when the
    dwelling has no coordinates)."""
    res = await client.get(COMMUNES_URL.format(dep=department(insee)))
    res.raise_for_status()
    centres = {}
    for c in res.json():
        coords = (c.get("centre") or {}).get("coordinates")
        if c.get("code") and coords:
            centres[c["code"]] = (coords[1], coords[0])
    if lat is None or lon is None:
        if insee not in centres:
            return [], None, None
        lat, lon = centres[insee]
    # A commune's centre can be a few km from its edge
    reach = WIDE_RINGS[-1][0] + 3000
    near = sorted((distance_m(lat, lon, *c), code) for code, c in centres.items() if code != insee)
    return [code for d, code in near if d <= reach][:MAX_NEIGHBOURS], lat, lon


async def market_price(insee: str, building_type: Optional[str], lat: Optional[float] = None,
                       lon: Optional[float] = None, surface: Optional[float] = None,
                       transport: Optional[httpx.AsyncBaseTransport] = None,
                       today: Optional[date] = None) -> Optional[Dict]:
    """Median price per m2 of comparable sales around this dwelling, or None."""
    insee = (insee or "").strip().upper()
    if len(insee) != 5:
        return None
    kind = "Maison" if "maison" in (building_type or "").lower() else "Appartement"
    key = (insee, kind, round(lat or 0, 3), round(lon or 0, 3), round(surface or 0, -1))
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]

    today = today or date.today()
    index = quarter_index(kind, department(insee))
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            sales = await commune_sales(client, insee, kind, today)
            if index:
                adjust_to_today(sales, index)
            result = summarize(sales, kind, lat, lon, surface, adjusted=bool(index))
            if result is None:
                # Too few sales in the commune: the neighbouring communes too
                codes, ref_lat, ref_lon = await neighbours(client, insee, lat, lon)
                if codes:
                    more = await asyncio.gather(*(commune_sales(client, c, kind, today) for c in codes))
                    wider = [s for found in more for s in found]
                    if index:
                        adjust_to_today(wider, index)
                    result = summarize(sales + wider, kind, ref_lat, ref_lon, surface, adjusted=bool(index), wide=True)
    except httpx.HTTPError as e:
        logger.error(f"DVF fetch failed: {type(e).__name__}")
        return None

    _cache[key] = (time.time(), result)
    return result
