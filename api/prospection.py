"""Prospection map: dwellings with a poor DPE (E, F, G) in an area, from the
ADEME open data (DPE "logements existants", Licence Ouverte).

The DPE is published with the address of the dwelling, not the owner. Results
are grouped by address (several flats of a building); when a dwelling has
several poor DPE, only the latest is kept. A better DPE established since
(after works) is not checked: the date of each DPE is shown.
"""
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

ADEME_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
FIELDS = ["numero_dpe", "date_etablissement_dpe", "etiquette_dpe", "type_batiment", "surface_habitable_logement",
          "adresse_ban", "identifiant_ban", "code_insee_ban", "_geopoint", "periode_construction",
          "complement_adresse_logement", "numero_etage_appartement"]
LABELS = {"A", "B", "C", "D", "E", "F", "G"}
# Area limits: about 3 km x 3 km, and a cap on the number of DPE fetched
MAX_SPAN_DEG = 0.045
MAX_RESULTS = 4000
CACHE_TTL = 6 * 3600
_cache: Dict[Tuple, Tuple[float, Tuple[List[Dict], int]]] = {}


class AreaTooLarge(ValueError):
    pass


def parse_bbox(bbox: str) -> Tuple[float, float, float, float]:
    try:
        west, south, east, north = (float(x) for x in bbox.split(","))
    except ValueError:
        raise ValueError("bbox attendu : ouest,sud,est,nord")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox invalide")
    if east - west > MAX_SPAN_DEG or north - south > MAX_SPAN_DEG:
        raise AreaTooLarge("Zone trop grande : zoomez sur un quartier.")
    return west, south, east, north


def _point(value: Optional[str]) -> Optional[Tuple[float, float]]:
    try:
        lat, lon = (float(x) for x in (value or "").split(","))
        return lat, lon
    except ValueError:
        return None


def dwelling_detail(r: Dict) -> Optional[str]:
    """Address complement, else the floor of an apartment. ADEME returns the
    floor as a number and the complement as free text."""
    complement = str(r.get("complement_adresse_logement") or "").strip()
    if complement:
        return complement[:80]
    floor = r.get("numero_etage_appartement")
    if (r.get("type_batiment") or "").lower() != "appartement" or floor in (None, ""):
        return None
    try:
        n = int(float(floor))
    except (TypeError, ValueError):
        return str(floor)[:20]
    return "RDC" if n == 0 else f"{n}e étage"


def _surface(r: Dict) -> float:
    try:
        return float(r.get("surface_habitable_logement") or 0)
    except (TypeError, ValueError):
        return 0.0


def group_by_address(rows: List[Dict], labels: set) -> List[Dict]:
    """One entry per address; per dwelling (floor/complement + surface), the latest DPE only."""
    latest: Dict[Tuple, Dict] = {}
    for r in rows:
        point = _point(r.get("_geopoint"))
        if not point or r.get("etiquette_dpe") not in LABELS:
            continue
        address_key = r.get("identifiant_ban") or r.get("adresse_ban") or ""
        dwelling = (address_key, (r.get("type_batiment") or "").lower(),
                    (dwelling_detail(r) or "").lower(),
                    round(_surface(r)))
        current = latest.get(dwelling)
        if current is None or (r.get("date_etablissement_dpe") or "") > (current.get("date_etablissement_dpe") or ""):
            latest[dwelling] = {**r, "_point": point}

    addresses: Dict[str, Dict] = {}
    for (address_key, *_), r in latest.items():
        if r["etiquette_dpe"] not in labels:
            continue
        entry = addresses.setdefault(address_key, {
            "address": r.get("adresse_ban") or "Adresse non renseignée",
            "lat": round(r["_point"][0], 6),
            "lon": round(r["_point"][1], 6),
            "insee": r.get("code_insee_ban"),
            "dpe": [],
        })
        entry["dpe"].append({
            "number": r.get("numero_dpe"),
            "label": r["etiquette_dpe"],
            "kind": (r.get("type_batiment") or "").capitalize() or None,
            "surface": r.get("surface_habitable_logement"),
            "date": (r.get("date_etablissement_dpe") or "")[:10] or None,
            "period": r.get("periode_construction"),
            "detail": dwelling_detail(r),
        })
    out = []
    for entry in addresses.values():
        entry["dpe"].sort(key=lambda d: ("ABCDEFG".index(d["label"]) * -1, d["date"] or ""))
        entry["worst"] = max((d["label"] for d in entry["dpe"]), key="ABCDEFG".index)
        out.append(entry)
    out.sort(key=lambda e: (-"ABCDEFG".index(e["worst"]), -len(e["dpe"])))
    return out


async def search(bbox: str, labels: List[str], kind: Optional[str] = None, since: Optional[str] = None,
                 transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict:
    west, south, east, north = parse_bbox(bbox)
    wanted = {l for l in labels if l in LABELS} or {"F", "G"}
    key = (round(west, 4), round(south, 4), round(east, 4), round(north, 4), kind, since, tuple(sorted(wanted)))
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        rows, total = cached[1]
    else:
        query = [f"etiquette_dpe:({' OR '.join(sorted(wanted))})"]
        if kind in ("maison", "appartement", "immeuble"):
            query.append(f"type_batiment:{kind}")
        if since:
            # A year (from 1 January) or a date: recent DPE are the hottest prospects
            start = f"{since}-01-01" if len(str(since)) == 4 else str(since)
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
                raise ValueError("Date de DPE invalide.")
            query.append(f"date_etablissement_dpe:[{start} TO *]")
        params = {"bbox": f"{west},{south},{east},{north}", "size": str(MAX_RESULTS), "select": ",".join(FIELDS),
                  "qs": " AND ".join(query)}
        async with httpx.AsyncClient(timeout=20, transport=transport) as client:
            res = await client.get(ADEME_URL, params=params)
            res.raise_for_status()
            data = res.json()
        rows = data.get("results", [])
        total = data.get("total", len(rows))
        _cache[key] = (time.time(), (rows, total))
    addresses = group_by_address(rows, wanted)
    return {
        "addresses": addresses,
        "dwellings": sum(len(a["dpe"]) for a in addresses),
        "total": total,
        "truncated": total > len(rows),
    }
