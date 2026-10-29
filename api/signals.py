"""Who is likely to sell, address by address, and the sales of the area.

GET /api/signals: every dwelling with a DPE in the visible map (last two
years), scored 0-100 on what announces a sale, each point explained:
- a recent DPE (compulsory before selling or letting, so often the first sign);
- several recent DPE in the same building (lots being sold one by one);
- a dwelling that can no longer, or soon will no longer, be let (G, F);
- a house with no sale recorded at its address since the start of the DVF
  window (owner for several years), or on the contrary bought recently;
- sales right next to it in the last eighteen months (the street moves);
- a company owning the whole building with a sale signal in the BODACC
  (dissolution, liquidation, death of a manager: api/sale_signals.py).
GET /api/sales: the recent single-dwelling sales of the visible map (DVF),
for the « votre voisin a vendu » letters.

Only public data: DPE (ADEME), DVF (DGFiP), BODACC (DILA). No owner's name.
"""
import logging
import re
import time
import unicodedata
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

try:
    from api import prospection
    from api.accounts import store_dep
    from api.auth import User, current_user
    from api.dvf import DVF_URL, department, distance_m, parse_sales
    from api.opportunities import require_pro
    from api.ratelimit import search_limiter
    from api.store import SupabaseStore
except ImportError:
    import prospection
    from accounts import store_dep
    from auth import User, current_user
    from dvf import DVF_URL, department, distance_m, parse_sales
    from opportunities import require_pro
    from ratelimit import search_limiter
    from store import SupabaseStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MAX_COMMUNES = 4
SHOWN = 400
NEAR_M = 150
STREET_TYPES = {
    "avenue": "av", "ave": "av", "av": "av", "boulevard": "bd", "bd": "bd", "bld": "bd", "chemin": "che", "che": "che",
    "route": "rte", "rte": "rte", "allee": "all", "all": "all", "place": "pl", "pl": "pl", "impasse": "imp", "imp": "imp",
    "square": "sq", "sq": "sq", "cours": "crs", "crs": "crs", "quai": "quai", "qu": "quai", "faubourg": "fg", "fg": "fg",
    "residence": "res", "res": "res", "lotissement": "lot", "lot": "lot", "rue": "rue", "r": "rue", "sentier": "sen",
    "sen": "sen", "passage": "pass", "pas": "pass", "pass": "pass", "hameau": "ham", "ham": "ham", "voie": "voie",
}
_sales: Dict[str, Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL = 24 * 3600


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def street_key(street: str) -> str:
    words = norm(street).split()
    if words:
        words[0] = STREET_TYPES.get(words[0], words[0])
    return " ".join(words)


def split_address(address: str) -> Tuple[str, str]:
    """« 12 bis Rue Nationale 59000 Lille » -> (« 12b », « rue nationale »)."""
    a = re.sub(r"\s+\d{5}\s.*$", "", address or "")
    m = re.match(r"^\s*(\d+)\s*(bis|ter|quater|b|t|q|[a-z])?\b[\s,]*(.*)$", norm(a))
    if not m:
        return "", street_key(a)
    suffix = {"bis": "b", "ter": "t", "quater": "q"}.get(m.group(2) or "", m.group(2) or "")
    return m.group(1) + suffix, street_key(m.group(3))


def sale_key(sale: Dict[str, Any]) -> Tuple[str, str]:
    """DVF number (« 12 », « 12B ») and street, in the form of split_address."""
    number = norm(sale.get("number") or "").replace(" ", "")
    if not number[:1].isdigit():
        number = ""
    number = re.sub(r"(bis|ter|quater)$", lambda m: m.group(0)[0], number)
    return number, street_key(sale.get("street") or "")


async def commune_sales(client: httpx.AsyncClient, insee: str, today: date) -> Dict[str, Any]:
    """Every single-dwelling sale of the commune over the DVF years
    published, and the first year covered."""
    key = f"{insee}:{today.isoformat()}"
    cached = _sales.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    sales: List[Dict[str, Any]] = []
    years: List[int] = []
    for year in range(today.year, today.year - 7, -1):
        res = await client.get(DVF_URL.format(year=year, dep=department(insee), insee=insee))
        if res.status_code in (403, 404, 410):
            continue
        res.raise_for_status()
        for kind in ("Maison", "Appartement"):
            sales += [{**x, "kind": kind} for x in parse_sales(res.text, kind, year)]
        years.append(year)
    out = {"sales": sales, "since": min(years) if years else None}
    _sales[key] = (time.time(), out)
    return out


def months_between(a: str, today: date) -> Optional[float]:
    try:
        return (today - date.fromisoformat(a[:10])).days / 30.44
    except (TypeError, ValueError):
        return None


def score_address(a: Dict[str, Any], sales: List[Dict[str, Any]], since: Optional[int],
                  buildings: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    reasons: List[Dict[str, Any]] = []

    def add(points: int, label: str, kind: str):
        reasons.append({"points": points, "label": label, "kind": kind})

    dpe = a["dpe"]
    newest = max((d["date"] for d in dpe if d.get("date")), default=None)
    age = months_between(newest, today) if newest else None
    if age is not None:
        if age <= 3:
            add(35, "DPE de moins de 3 mois : souvent le premier signe d'une vente ou d'une location", "dpe")
        elif age <= 6:
            add(28, "DPE de moins de 6 mois", "dpe")
        elif age <= 12:
            add(18, "DPE de moins d'un an", "dpe")
        elif age <= 24:
            add(8, "DPE de moins de deux ans", "dpe")
    recent = [d for d in dpe if d.get("date") and (months_between(d["date"], today) or 99) <= 6]
    if len(recent) >= 3:
        add(15, f"{len(recent)} DPE récents dans l'immeuble : des lots sont peut-être en vente", "building")
    worst = a.get("worst")
    if worst == "G":
        add(15, "Classé G : plus de nouveau bail possible depuis 2025", "rental")
    elif worst == "F":
        add(10, "Classé F : plus de nouveau bail possible à partir de 2028", "rental")
    elif worst == "E":
        add(4, "Classé E : location limitée à partir de 2034", "rental")

    house = all((d.get("kind") or "").lower().startswith("maison") for d in dpe)
    number, street = split_address(a.get("address") or "")
    here = [s for s in sales if number and sale_key(s) == (number, street)] if street else []
    last_sale = max(here, key=lambda s: s.get("date") or "", default=None)
    long_held = False
    if house and since:
        if last_sale and (months_between(last_sale["date"], today) or 0) <= 24:
            add(-20, f"Vendu en {last_sale['date'][:4]} : propriétaire récent", "held")
        elif not last_sale:
            years = today.year - since
            long_held = years >= 4
            if long_held:
                add(15, f"Aucune vente enregistrée depuis {since} : propriétaire depuis au moins {years} ans", "held")
    near = [s for s in sales if s.get("lat") and s.get("lon") and (months_between(s.get("date"), today) or 99) <= 18
            and distance_m(a["lat"], a["lon"], s["lat"], s["lon"]) <= NEAR_M and s not in here]
    if len(near) >= 3:
        add(10, f"{len(near)} ventes à moins de {NEAR_M} m en 18 mois : la rue bouge", "near")
    elif near:
        add(5, f"{len(near)} vente{'s' if len(near) > 1 else ''} à moins de {NEAR_M} m en 18 mois", "near")
    company = next((b for b in buildings if b.get("signal_level") in ("fort", "moyen")
                    and distance_m(a["lat"], a["lon"], b["lat"], b["lon"]) <= 25), None)
    if company:
        add(20 if company["signal_level"] == "fort" else 10,
            f"Immeuble d'une société avec un signal de vente {company['signal_level']} au BODACC", "company")

    value = max(0, min(100, sum(r["points"] for r in reasons)))
    latest_near = max(near, key=lambda s: s.get("date") or "", default=None)
    return {
        "address": a.get("address"), "lat": a["lat"], "lon": a["lon"], "insee": a.get("insee"),
        "score": value, "level": "fort" if value >= 60 else "moyen" if value >= 35 else "faible",
        "reasons": sorted(reasons, key=lambda r: -r["points"]),
        "label": worst, "dpe_date": newest, "dwellings": len(dpe), "kind": dpe[0].get("kind") if dpe else None,
        "surface": dpe[0].get("surface") if len(dpe) == 1 else None,
        "dpe_number": max(dpe, key=lambda d: d.get("date") or "")["number"] if dpe else None,
        "long_held": long_held, "last_sale": {"date": last_sale["date"], "price": last_sale["price"]} if last_sale else None,
        "near_sales": len(near),
        "near_sale": {"date": latest_near["date"], "price_m2": round(latest_near["price_m2"]), "street": latest_near.get("street")}
        if latest_near else None,
    }


async def area_signals(bbox: str, store: Optional[SupabaseStore], today: Optional[date] = None,
                       dpe_transport: Optional[httpx.AsyncBaseTransport] = None,
                       dvf_transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    today = today or date.today()
    found = await prospection.search(bbox, list(prospection.LABELS), since=(today - timedelta(days=730)).isoformat(),
                                     transport=dpe_transport)
    addresses = found["addresses"]
    communes = [c for c, _ in sorted(_count(a.get("insee") for a in addresses).items(), key=lambda kv: -kv[1]) if c][:MAX_COMMUNES]
    by_commune: Dict[str, Dict[str, Any]] = {}
    async with httpx.AsyncClient(timeout=30, transport=dvf_transport) as client:
        for c in communes:
            try:
                by_commune[c] = await commune_sales(client, c, today)
            except httpx.HTTPError as e:
                logger.warning(f"DVF of {c} unavailable: {type(e).__name__}")
    buildings: List[Dict[str, Any]] = []
    if store is not None:
        west, south, east, north = prospection.parse_bbox(bbox)
        try:
            buildings = await store.monopro_in_bbox(west, south, east, north, True, 3, 500, min_signal=25)
        except httpx.HTTPError:
            buildings = []
    items = []
    for a in addresses:
        data = by_commune.get(a.get("insee") or "", {"sales": [], "since": None})
        items.append(score_address(a, data["sales"], data["since"], buildings, today))
    items.sort(key=lambda x: x.get("dpe_date") or "", reverse=True)
    items.sort(key=lambda x: -x["score"])
    since = min((d["since"] for d in by_commune.values() if d.get("since")), default=None)
    return {"items": items[:SHOWN], "total": len(items), "truncated": found["truncated"] or len(items) > SHOWN,
            "dvf_since": since, "strong": sum(1 for x in items if x["level"] == "fort")}


def _count(values) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in values:
        if v:
            out[v] = out.get(v, 0) + 1
    return out


@router.get("/signals", dependencies=[Depends(search_limiter.per_user)])
async def signals(bbox: str, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    await require_pro(user, store)
    try:
        return await area_signals(bbox, store)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPError as e:
        logger.error(f"Signals failed: {type(e).__name__}")
        raise HTTPException(status_code=502, detail="La base DPE de l'ADEME ne répond pas pour le moment.")


async def area_sales(bbox: str, months: int, today: Optional[date] = None,
                     dvf_transport: Optional[httpx.AsyncBaseTransport] = None,
                     communes: Optional[List[str]] = None) -> Dict[str, Any]:
    today = today or date.today()
    west, south, east, north = prospection.parse_bbox(bbox)
    if communes is None:
        communes = await communes_in_bbox(west, south, east, north, dvf_transport)
    out: List[Dict[str, Any]] = []
    latest = None
    async with httpx.AsyncClient(timeout=30, transport=dvf_transport) as client:
        for c in communes[:MAX_COMMUNES]:
            try:
                data = await commune_sales(client, c, today)
            except httpx.HTTPError:
                continue
            for s in data["sales"]:
                if not s.get("lat") or not (south <= s["lat"] <= north and west <= s["lon"] <= east):
                    continue
                latest = max(latest or "", s.get("date") or "")
                out.append(s)
    # The DVF lag: count the months back from the latest sale published
    ref = date.fromisoformat(latest) if latest else today
    start = (ref - timedelta(days=int(months * 30.44))).isoformat()
    kept = sorted((s for s in out if (s.get("date") or "") >= start), key=lambda s: s.get("date") or "", reverse=True)
    return {"sales": [{"date": s["date"], "price": s["price"], "surface": s["surface"], "price_m2": round(s["price_m2"]),
                       "kind": s.get("kind"), "street": s.get("street"),
                       "number": s.get("number"), "commune": s.get("commune"), "lat": s["lat"], "lon": s["lon"],
                       "rooms": s.get("rooms")} for s in kept[:600]],
            "latest": latest, "truncated": len(kept) > 600}


async def communes_in_bbox(west: float, south: float, east: float, north: float,
                           transport: Optional[httpx.AsyncBaseTransport] = None) -> List[str]:
    """Communes under the corners and the centre of the map (geo.api.gouv.fr)."""
    points = [((south + north) / 2, (west + east) / 2), (south, west), (south, east), (north, west), (north, east)]
    found: List[str] = []
    async with httpx.AsyncClient(timeout=10, transport=transport) as client:
        for lat, lon in points:
            try:
                res = await client.get("https://geo.api.gouv.fr/communes", params={"lat": lat, "lon": lon, "fields": "code", "format": "json"})
                res.raise_for_status()
                for c in res.json():
                    if c.get("code") and c["code"] not in found:
                        found.append(c["code"])
            except httpx.HTTPError:
                continue
    return found


@router.get("/sales", dependencies=[Depends(search_limiter.per_user)])
async def sales(bbox: str, months: int = Query(12, ge=3, le=36), user: User = Depends(current_user),
                store: SupabaseStore = Depends(store_dep)):
    await require_pro(user, store)
    try:
        return await area_sales(bbox, months)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
