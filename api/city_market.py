"""The commune's market for the owner's file: median price per m2 of the
three last years, number of sales, typical sale and nearby communes, for one
kind of dwelling. Read from the site's public price files (/prix/<dep>.json,
built monthly from DVF by scripts/seo/city_prices.py), kept in memory."""
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_files: Dict[str, Dict[str, Any]] = {}


def department_code(insee: str) -> str:
    return insee[:3] if insee.startswith("97") else insee[:2]


def base_url() -> str:
    return os.getenv("PUBLIC_APP_URL", "https://sprea.app").rstrip("/")


async def department_file(dep: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> Optional[Dict[str, Any]]:
    if dep in _files:
        return _files[dep]
    try:
        async with httpx.AsyncClient(timeout=8, transport=transport) as client:
            res = await client.get(f"{base_url()}/prix/{dep}.json")
            res.raise_for_status()
            _files[dep] = res.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"City prices of {dep} unavailable: {type(e).__name__}")
        return None
    return _files[dep]


def extract(data: Dict[str, Any], insee: str, kind: str) -> Optional[Dict[str, Any]]:
    communes = data.get("communes") or {}
    c = communes.get(insee)
    if not c or kind not in (c.get("kinds") or {}):
        return None
    k = c["kinds"][kind]
    years = sorted(((int(y), v) for y, v in (k.get("years") or {}).items() if v.get("m2")), key=lambda x: x[0])
    near = []
    for code in c.get("near") or []:
        other = communes.get(code)
        ok = other and (other.get("kinds") or {}).get(kind)
        if ok and ok.get("m2"):
            near.append({"name": other["name"], "m2": ok["m2"], "n": ok.get("n")})
    return {
        "name": c["name"], "kind": kind, "m2": k.get("m2"), "q25": k.get("q25"), "q75": k.get("q75"), "n": k.get("n"),
        "surface": k.get("surface"), "price": k.get("price"),
        "years": [{"year": y, "m2": v["m2"], "n": v.get("n")} for y, v in years],
        "near": near[:5], "updated": data.get("updated"),
    }


async def city_market(insee: Optional[str], building_type: Optional[str],
                      transport: Optional[httpx.AsyncBaseTransport] = None) -> Optional[Dict[str, Any]]:
    if not insee:
        return None
    kind = "maison" if (building_type or "").lower().startswith("maison") else "appartement"
    data = await department_file(department_code(insee), transport)
    return extract(data, insee, kind) if data else None
