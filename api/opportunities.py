"""Opportunities for investors and property dealers (Pro): the poorly rated
dwellings of an area ranked by what the renovation leaves once everything
is paid, and an investment file for each.

For each E, F or G dwelling of the area (latest DPE per dwelling, ADEME):
the default renovation programme of the simulator, its cost and aids, the
value today and after works (comparable DVF sales brought to the DPE class
with the class effects measured in the department, as in the avis de
valeur), the acquisition costs, and the rent of the commune ("Carte des
loyers"). Two profiles:
- "marchand": a property dealer buys, renovates and resells: reduced notary
  fees (commitment to resell within five years), no MaPrimeRénov' (a company
  is not eligible), margin = resale value - all costs;
- "bailleur": a private landlord buys, renovates and lets: usual notary
  fees, aids counted, gross yield after works, value created.
All figures are estimates before financing costs, taxes and resale fees.
"""
import asyncio
import logging
import math
import re
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

try:
    from api import claude
    from api.accounts import is_pro, safe_filename, store_dep
    from api.ademe_client import AdemeConnector
    from api.auth import User, current_user
    from api.dvf import market_price
    from api.green_value import department, kind_of
    from api.pdf_service import pdf_service
    from api.prospection import ADEME_URL, AreaTooLarge, parse_bbox
    from api.ratelimit import search_limiter
    from api.rents import rent_per_m2
    from api.report_content import display_address
    from api.simulation import WORKS_BY_ID, SimulationInput, simulate, suggest_works
    from api.store import SupabaseStore
    from api.valuation import compute
except ImportError:
    import claude
    from accounts import is_pro, safe_filename, store_dep
    from ademe_client import AdemeConnector
    from auth import User, current_user
    from dvf import market_price
    from green_value import department, kind_of
    from pdf_service import pdf_service
    from prospection import ADEME_URL, AreaTooLarge, parse_bbox
    from ratelimit import search_limiter
    from rents import rent_per_m2
    from report_content import display_address
    from simulation import WORKS_BY_ID, SimulationInput, simulate, suggest_works
    from store import SupabaseStore
    from valuation import compute

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Dwellings analysed per scan: the most recent DPE of the area first
SCAN_LIMIT = 150
SHOWN = 40
CACHE_TTL = 6 * 3600
_cache: Dict[Tuple, Tuple[float, Dict]] = {}

PROFILES = {
    # Notary fees on an old dwelling: about 7.5 to 8 %; a property dealer
    # committing to resell within five years pays about 3 %
    "marchand": {"notary": 0.03, "aids": False, "name": "Marchand de biens"},
    "bailleur": {"notary": 0.08, "aids": True, "name": "Investisseur bailleur"},
}
MIN_SURFACE = 9


def latest_per_dwelling(rows: List[Dict]) -> List[Dict]:
    """One DPE per dwelling (address, kind, floor, surface): the latest."""
    latest: Dict[Tuple, Dict] = {}
    for r in rows:
        key = (r.get("identifiant_ban") or r.get("adresse_ban") or "", (r.get("type_batiment") or "").lower(),
               str(r.get("numero_etage_appartement") or ""), round(float(r.get("surface_habitable_logement") or 0)))
        if key not in latest or (r.get("date_etablissement_dpe") or "") > (latest[key].get("date_etablissement_dpe") or ""):
            latest[key] = r
    return sorted(latest.values(), key=lambda r: r.get("date_etablissement_dpe") or "", reverse=True)


async def area_rows(bbox: str, labels: List[str], kind: Optional[str],
                    transport: Optional[httpx.AsyncBaseTransport] = None) -> Tuple[List[Dict], int]:
    """Full DPE lines (every field the simulation reads) of the poorly rated
    dwellings of the area, most recent first."""
    west, south, east, north = parse_bbox(bbox)
    query = [f"etiquette_dpe:({' OR '.join(labels)})"]
    if kind in ("maison", "appartement"):
        query.append(f"type_batiment:{kind}")
    else:
        query.append("type_batiment:(maison OR appartement)")
    params = {"bbox": f"{west},{south},{east},{north}", "size": str(SCAN_LIMIT * 2), "qs": " AND ".join(query),
              "sort": "-date_etablissement_dpe"}
    async with httpx.AsyncClient(timeout=25, transport=transport) as client:
        res = await client.get(ADEME_URL, params=params)
        res.raise_for_status()
        data = res.json()
    rows = latest_per_dwelling(data.get("results") or [])
    return rows[:SCAN_LIMIT], data.get("total", len(rows))


def investment(v: Dict[str, Any], sim: Dict[str, Any], profile: str, surface: float,
               rent: Optional[Dict[str, float]]) -> Dict[str, Any]:
    """The investor's figures from the valuation and the simulation."""
    p = PROFILES[profile]
    price = v["value_now"]["value"]
    notary = price * p["notary"]
    works = sim["cost"]
    aids = (sim["subsidies"] + sim["cee_est"]) if p["aids"] else 0.0
    total = price + notary + works - aids
    resale = v["value_after"]["value"]
    margin = resale - total
    out = {
        "price": round(price, -2), "notary": round(notary, -2), "works": round(works, -2),
        "works_low": round(sim["cost_low"], -2), "works_high": round(sim["cost_high"], -2),
        "aids": round(aids, -1), "total": round(total, -2), "resale": round(resale, -2),
        "resale_low": v["value_after"]["low"], "resale_high": v["value_after"]["high"],
        "margin": round(margin, -2), "margin_pct": round(100 * margin / total, 1) if total > 0 else None,
        "value_created": round(resale - price - works + aids, -2),
    }
    if rent:
        monthly = rent["rent_m2"] * surface
        out.update({
            "rent_m2": round(rent["rent_m2"], 1),
            "rent_month": round(monthly, -1),
            "rent_month_low": round(rent["low"] * surface, -1),
            "rent_month_high": round(rent["high"] * surface, -1),
            "gross_yield": round(100 * monthly * 12 / total, 1) if total > 0 else None,
        })
    return out


def risks(prop, sim: Dict[str, Any], v: Dict[str, Any], market: Dict[str, Any], today: date) -> List[str]:
    """What an investor must check before an offer."""
    out = []
    try:
        dpe_date = datetime.fromisoformat(str(prop.date_etablissement)[:10]).date() if prop.date_etablissement else None
    except ValueError:
        dpe_date = None
    if dpe_date and (today - dpe_date).days > 2 * 365:
        out.append(f"DPE de {dpe_date.year} : des travaux ont pu être faits depuis.")
    if "avant 1948" in (prop.construction_period or "").lower():
        out.append("Bâti d'avant 1948 : isolants perméables à la vapeur, façade souvent protégée.")
    if (prop.building_type or "").lower().startswith("appartement"):
        out.append("Copropriété : travaux collectifs et charges à vérifier (plan pluriannuel, PV d'AG).")
    if market.get("wide"):
        out.append("Peu de ventes dans la commune : prix tiré des communes voisines.")
    if sim["current_label"] != sim.get("current_cep_label") and sim.get("current_ges_label") == sim["current_label"]:
        out.append("Classe fixée par les émissions de CO₂ : le changement d'énergie compte autant que l'isolation.")
    if sim["new_label"] in ("E", "F", "G"):
        out.append(f"Classe {sim['new_label']} après travaux : location encore limitée dans le temps.")
    return out


async def analyse(raw: Dict[str, Any], profile: str, today: Optional[date] = None,
                  dvf_transport: Optional[httpx.AsyncBaseTransport] = None,
                  rent_transport: Optional[httpx.AsyncBaseTransport] = None) -> Optional[Dict[str, Any]]:
    """One dwelling: programme, valuation and the investor's figures; None
    when it cannot be valued (no works, no comparable sales)."""
    today = today or date.today()
    prop = AdemeConnector()._map_to_internal(raw)
    if not prop.shab or prop.shab < MIN_SURFACE or not prop.dpe_class_current or not prop.insee_code:
        return None
    label = prop.dpe_class_current.value
    try:
        from api.main import simulation_property  # main imports this module's router
    except ImportError:
        from main import simulation_property
    sp = simulation_property(prop)
    works = suggest_works(sp, label)["preselected"]
    if not works:
        return None
    market = await market_price(prop.insee_code, prop.building_type, prop.latitude, prop.longitude, prop.shab,
                                transport=dvf_transport)
    if not market:
        return None
    sp.price_per_m2, sp.price_source, sp.insee_code = market["price_per_m2"], market["source"], prop.insee_code
    sim = simulate(SimulationInput(property=sp, works=works))
    kind = kind_of(prop.building_type)
    v = compute(sim, market, prop.shab, kind, department(prop.insee_code, prop.postcode), 0)
    if not v["works"] or not v["value_after"]:
        return None
    rent = await rent_per_m2(prop.insee_code, prop.building_type, transport=rent_transport)
    figures = investment(v, sim, profile, prop.shab, rent)
    return {
        "number": raw.get("numero_dpe"),
        # The BAN address carries its postcode and commune, shown on their own line
        "address": re.sub(r"\s+\d{5}\s.*$", "", raw.get("adresse_ban") or prop.address or ""),
        "lat": prop.latitude, "lon": prop.longitude,
        "insee": prop.insee_code, "postcode": prop.postcode, "city": prop.city,
        "kind": (prop.building_type or "").capitalize(),
        "surface": prop.shab,
        "period": prop.construction_period,
        "dpe_date": str(prop.date_etablissement)[:10] if prop.date_etablissement else None,
        "label": sim["current_label"], "new_label": sim["new_label"],
        "works_ids": works,
        "works_names": [WORKS_BY_ID[w]["name"] for w in works if w in WORKS_BY_ID],
        "rental_now": sim["rental_status"], "rental_after": sim["new_rental_status"],
        **figures,
        "risks": risks(prop, sim, v, market, today),
        "_v": v, "_sim": sim, "_market": market, "_prop": prop,
    }


def public(o: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in o.items() if not k.startswith("_")}


async def scan(bbox: str, labels: List[str], kind: Optional[str], profile: str,
               max_budget: Optional[float] = None, ademe_transport: Optional[httpx.AsyncBaseTransport] = None,
               dvf_transport: Optional[httpx.AsyncBaseTransport] = None,
               rent_transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    wanted = sorted({l for l in labels if l in ("E", "F", "G")}) or ["F", "G"]
    key = (bbox, tuple(wanted), kind, profile)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        found = cached[1]
    else:
        rows, total = await area_rows(bbox, wanted, kind, ademe_transport)
        gate = asyncio.Semaphore(8)

        async def one(raw):
            async with gate:
                try:
                    return await analyse(raw, profile, dvf_transport=dvf_transport, rent_transport=rent_transport)
                except Exception as e:  # noqa: BLE001 - one dwelling must not stop the scan
                    logger.warning(f"Opportunity {raw.get('numero_dpe')} skipped: {type(e).__name__}: {e}")
                    return None

        results = [o for o in await asyncio.gather(*(one(r) for r in rows)) if o]
        found = {"items": [public(o) for o in results], "analysed": len(rows), "total": total}
        _cache[key] = (time.time(), found)
    items = [o for o in found["items"] if not max_budget or o["total"] <= max_budget]
    sort_key = (lambda o: (o.get("gross_yield") or 0, o["margin"])) if profile == "bailleur" else (lambda o: o["margin"])
    items.sort(key=sort_key, reverse=True)
    positive = [o for o in items if o["margin"] > 0]
    return {
        "profile": profile,
        "items": items[:SHOWN],
        "analysed": found["analysed"],
        "valued": len(found["items"]),
        "positive": len(positive),
        "total": found["total"],
        "best_margin": items[0]["margin"] if items else None,
    }


async def require_pro(user: User, store: SupabaseStore) -> None:
    profile = await store.ensure_profile(user.id, user.email)
    if not is_pro(profile):
        raise HTTPException(status_code=402, detail="Réservé aux abonnés Pro.")


@router.get("/opportunities", dependencies=[Depends(search_limiter.per_user)])
async def opportunities(bbox: str, labels: str = "F,G", kind: Optional[str] = None,
                        profile: str = Query("marchand", pattern="^(marchand|bailleur)$"),
                        max_budget: Optional[float] = Query(None, ge=0),
                        user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    await require_pro(user, store)
    try:
        return await scan(bbox, labels.split(","), kind, profile, max_budget)
    except AreaTooLarge as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPError as e:
        logger.error(f"Opportunity scan failed: {type(e).__name__}")
        raise HTTPException(status_code=502, detail="La base DPE de l'ADEME ne répond pas pour le moment.")


# --- Investment file ---

THESIS_SYSTEM = """Tu es un analyste en investissement immobilier qui rédige, pour un agent immobilier, la note d'opportunité d'un logement à rénover destinée à un client investisseur (marchand de biens ou bailleur). Tu disposes uniquement des chiffres fournis (estimations SPREA : valeur DVF corrigée de la classe DPE, programme de travaux simulé, aides, loyers de la commune). N'invente aucun chiffre, aucune caractéristique ni aucun élément de quartier absent des données. Écris en français, de façon factuelle et professionnelle, sans superlatifs ni promesse de rendement. Les montants sont des estimations avant frais financiers, fiscalité et frais de revente : rappelle-le quand c'est utile. Signale clairement quand l'opération n'est pas rentable selon les chiffres."""

THESIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "these": {"type": "string", "description": "2 à 3 phrases : l'opération, ce qu'elle rapporte et pourquoi."},
        "points_forts": {"type": "array", "items": {"type": "string"}, "description": "3 à 5 points forts chiffrés."},
        "risques": {"type": "array", "items": {"type": "string"}, "description": "3 à 5 risques et vérifications avant offre."},
        "strategie": {"type": "string", "description": "Scénario conseillé (revente ou location), travaux, calendrier, en 3 à 5 phrases."},
        "negociation": {"type": "string", "description": "Arguments de négociation du prix d'achat tirés du DPE et des travaux, en 2 à 4 phrases."},
    },
    "required": ["these", "points_forts", "risques", "strategie", "negociation"],
}


def thesis_facts(o: Dict[str, Any], profile: str) -> Dict[str, Any]:
    return {
        "profil_investisseur": PROFILES[profile]["name"],
        "logement": {"type": o["kind"], "surface_m2": o["surface"], "epoque": o["period"], "commune": o.get("city"),
                     "classe_dpe": o["label"], "date_dpe": o["dpe_date"]},
        "programme": {"travaux": o["works_names"], "classe_apres": o["new_label"],
                      "cout_eur": [o["works_low"], o["works_high"]], "aides_eur": o["aids"]},
        "acquisition": {"prix_estime_eur": o["price"], "frais_notaire_eur": o["notary"], "budget_total_eur": o["total"]},
        "sortie": {"valeur_apres_travaux_eur": o["resale"], "marge_brute_eur": o["margin"], "marge_pct": o["margin_pct"],
                   "loyer_mensuel_eur": o.get("rent_month"), "rendement_brut_pct": o.get("gross_yield")},
        "location": {"aujourd_hui": o["rental_now"], "apres_travaux": o["rental_after"]},
        "points_de_vigilance_calcules": o["risks"],
    }


def lower_first(name: str) -> str:
    return name[:1].lower() + name[1:]


def fallback_thesis(o: Dict[str, Any], profile: str) -> Dict[str, Any]:
    def eur(v):
        return f"{round(v or 0):,}".replace(",", " ") + " €"

    def pct(v):
        return f"{v} %".replace(".", ",")
    gained = "ABCDEFG".index(o["label"]) - "ABCDEFG".index(o["new_label"])
    good = o["margin"] > 0
    surface = f"{o['surface']:g}".replace(".", ",")
    these = (f"{o['kind']} de {surface} m² classé {o['label']}, estimé {eur(o['price'])} : le programme proposé "
             f"({', '.join(lower_first(n) for n in o['works_names'])}) le porte en classe {o['new_label']} pour une valeur estimée "
             f"de {eur(o['resale'])}. ")
    these += (f"La marge brute ressort à {eur(o['margin'])} ({pct(o['margin_pct'])} du budget), avant frais financiers et fiscalité."
              if good else f"Aux prix estimés, l'opération ne dégage pas de marge (−{eur(abs(o['margin']))}) : le prix d'achat doit se négocier.")
    strengths = [f"Gain de {gained} classe{'s' if gained > 1 else ''} DPE ({o['label']} → {o['new_label']}).",
                 f"Budget total estimé : {eur(o['total'])}, travaux compris."]
    if o.get("gross_yield"):
        strengths.append(f"Loyer de marché d'environ {eur(o['rent_month'])} par mois, soit {pct(o['gross_yield'])} brut sur le budget total.")
    if o["aids"]:
        strengths.append(f"Aides estimées : {eur(o['aids'])}.")
    return {
        "these": these,
        "points_forts": strengths,
        "risques": o["risks"] + ["Faire chiffrer les travaux par des artisans RGE avant toute offre."],
        "strategie": ("Acheter, réaliser le programme dans l'ordre conseillé (enveloppe puis équipements), puis "
                      + ("revendre une fois la nouvelle classe DPE établie." if profile == "marchand"
                         else "louer après le nouveau DPE, qui conditionne le droit de louer.")),
        "negociation": (f"La classe {o['label']} et le coût des travaux ({eur(o['works_low'])} à {eur(o['works_high'])}) "
                        "justifient une décote : "
                        + ("le logement ne peut déjà plus être loué en l'état." if "interdite" in (o.get("rental_now") or "").lower()
                           else f"{(o.get('rental_now') or '').lower().replace('louable', 'il reste louable')}, puis le vendeur devra financer ces travaux pour louer."
                           if "jusqu" in (o.get("rental_now") or "").lower()
                           else "un acheteur occupant devra financer ces travaux.")),
    }


async def write_thesis(o: Dict[str, Any], profile: str) -> Dict[str, Any]:
    if claude.configured():
        try:
            import json as _json
            data = await claude.json_call(THESIS_SYSTEM, "Données de l'opportunité (JSON) :\n" + _json.dumps(
                thesis_facts(o, profile), ensure_ascii=False, indent=1), THESIS_SCHEMA,
                model="claude-sonnet-5-5", effort="medium", max_tokens=4000, timeout=60)
            if data.get("these"):
                return {**data, "source": "claude"}
        except claude.ClaudeUnavailable as e:
            logger.warning(f"Thesis by rules: {e}")
    return {**fallback_thesis(o, profile), "source": "rules"}


class DossierRequest(BaseModel):
    number: str = Field(..., pattern=r"^[0-9A-Za-z]{10,16}$")
    profile: str = Field("marchand", pattern="^(marchand|bailleur)$")
    purchase_price: Optional[float] = Field(None, ge=1000, le=20_000_000)
    client_name: Optional[str] = Field(None, max_length=100)


async def dossier_data(data: DossierRequest) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(ADEME_URL, params={"qs": f'numero_dpe:"{data.number}"', "size": "1"})
        res.raise_for_status()
        rows = res.json().get("results") or []
    if not rows:
        raise HTTPException(status_code=404, detail="DPE introuvable.")
    o = await analyse(rows[0], data.profile)
    if not o:
        raise HTTPException(status_code=422, detail="Ce logement ne peut pas être chiffré (pas de travaux ou pas de ventes comparables).")
    if data.purchase_price:
        # The price actually asked replaces the estimate
        o["_v"]["value_now"] = {**o["_v"]["value_now"], "value": data.purchase_price}
        rent = {"rent_m2": o["rent_m2"], "low": o["rent_month_low"] / o["surface"], "high": o["rent_month_high"] / o["surface"]} \
            if o.get("rent_m2") else None
        o.update(investment(o["_v"], o["_sim"], data.profile, o["surface"], rent))
        o["price_is_asked"] = True
    return o


@router.post("/opportunities/dossier", dependencies=[Depends(search_limiter.per_user)])
async def opportunity_dossier(data: DossierRequest, user: User = Depends(current_user),
                              store: SupabaseStore = Depends(store_dep)):
    await require_pro(user, store)
    o = await dossier_data(data)
    thesis = await write_thesis(public(o), data.profile)
    agency = await store.get_agent_page(user.id) or {}
    address = display_address(o["address"] or "", o.get("postcode"), o.get("city"))
    pdf = pdf_service.generate_investment({
        **public(o),
        "profile": data.profile, "profile_name": PROFILES[data.profile]["name"],
        "notary_rate": PROFILES[data.profile]["notary"],
        "thesis": thesis, "agency": agency, "address": address, "client_name": data.client_name,
        "valuation": o["_v"], "sim": o["_sim"], "market": o["_market"],
    })
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=Dossier_investissement_{safe_filename(o['address'] or data.number)}.pdf"})
