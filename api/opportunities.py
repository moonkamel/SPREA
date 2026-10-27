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
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

try:
    from api import claude
    from api.accounts import ReportMeta, is_pro, safe_filename, store_dep
    from api.ademe_client import AdemeConnector
    from api.auth import User, current_user
    from api.dvf import market_price
    from api.figures import cost_range
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
    from accounts import ReportMeta, is_pro, safe_filename, store_dep
    from ademe_client import AdemeConnector
    from auth import User, current_user
    from dvf import market_price
    from figures import cost_range
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
# Who reads the file: an investor client of the agency, the buyer of a
# dwelling the agency sells, or the owner the agency prospects
AUDIENCES = {"investisseur": "client investisseur de l'agence", "acheteur": "acquéreur du bien mis en vente par l'agence",
             "proprietaire": "propriétaire du bien, prospecté par l'agence"}
AUDIENCE_PATTERN = "^(investisseur|acheteur|proprietaire)$"


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


# Surfaces the "Carte des loyers" is calibrated on (typical dwellings of the
# model); a larger dwelling lets for less per m2, a smaller one for more
RENT_REF_SURFACE = {"maison": 92, "appartement": 52}


def rent_surface_factor(surface: float, kind: Optional[str]) -> float:
    """47 rue de Bourgogne, Lille: a 328 m2 house at the commune's 12,7 EUR/m2
    gave 4 180 EUR a month. Rent per m2 falls with the surface: elasticity
    -0.25, bounded to +/- 25 %."""
    ref = RENT_REF_SURFACE["maison" if "maison" in (kind or "").lower() else "appartement"]
    if not surface or surface <= 0:
        return 1.0
    return min(1.25, max(0.75, (ref / surface) ** 0.25))


def investment(v: Dict[str, Any], sim: Dict[str, Any], profile: str, surface: float,
               rent: Optional[Dict[str, Any]], kind: Optional[str] = None) -> Dict[str, Any]:
    """The investor's figures from the valuation and the simulation."""
    p = PROFILES[profile]
    # Each line rounded once, the totals from the rounded lines: the table adds up
    price = round(v["value_now"]["value"], -2)
    notary = round(price * p["notary"], -2)
    works = round(sim["cost"], -2)
    # Aids rounded as the report rounds them (api/figures.py display_figures)
    if not p["aids"]:
        aids = 0.0
    elif sim.get("aid_pathway") == "accompagne":
        aids = round(sim["subsidies"], -2)
    else:
        aids = round(sim["subsidies"], -1) + round(sim["cee_est"], -1)
    total = price + notary + works - aids
    resale = round(v["value_after"]["value"], -2)
    margin = resale - total
    out = {
        "price": price, "notary": notary, "works": works,
        "works_low": cost_range(sim)["low"], "works_high": cost_range(sim)["high"],
        "aids": aids, "total": total, "resale": resale,
        "resale_low": v["value_after"]["low"], "resale_high": v["value_after"]["high"],
        "margin": margin, "margin_pct": round(100 * margin / total, 1) if total > 0 else None,
        "value_created": resale - price - works + aids,
    }
    if rent:
        # The commune's rent, brought to this dwelling's surface (once)
        factor = 1.0 if rent.get("adjusted") else rent_surface_factor(surface, kind)
        monthly = rent["rent_m2"] * factor * surface
        out.update({
            "rent_m2": round(rent["rent_m2"] * factor, 1),
            "rent_m2_commune": round(rent.get("commune_m2") or rent["rent_m2"], 1),
            "rent_month": round(monthly, -1),
            "rent_month_low": round(rent["low"] * factor * surface, -1),
            "rent_month_high": round(rent["high"] * factor * surface, -1),
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
    rent = await rent_per_m2(prop.insee_code, prop.building_type, transport=rent_transport)
    return assemble(SimulationInput(property=sp, works=works), market, rent, profile, today, {
        "number": raw.get("numero_dpe"),
        # The BAN address carries its postcode and commune, shown on their own line
        "address": re.sub(r"\s+\d{5}\s.*$", "", raw.get("adresse_ban") or prop.address or ""),
        "lat": prop.latitude, "lon": prop.longitude,
        "insee": prop.insee_code, "postcode": prop.postcode, "city": prop.city,
        "building_type": prop.building_type, "surface": prop.shab, "period": prop.construction_period,
        "dpe_date": str(prop.date_etablissement)[:10] if prop.date_etablissement else None,
    })


def assemble(simulation: SimulationInput, market: Dict[str, Any], rent: Optional[Dict[str, float]], profile: str,
             today: date, info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The dwelling's file once its programme, market and rent are known:
    from a scanned DPE or from the simulator (the works the agent chose)."""
    sim = simulate(simulation)
    v = compute(sim, market, info["surface"], kind_of(info["building_type"]),
                department(info.get("insee"), info.get("postcode")), 0)
    if not v["works"] or not v["value_after"]:
        return None
    works = simulation.works
    facts = SimpleNamespace(date_etablissement=info.get("dpe_date"), construction_period=info.get("period"),
                            building_type=info.get("building_type"))
    return {
        **{k: info.get(k) for k in ("number", "address", "lat", "lon", "insee", "postcode", "city", "surface", "period", "dpe_date")},
        "kind": (info.get("building_type") or "").capitalize(),
        "label": sim["current_label"], "new_label": sim["new_label"],
        "works_ids": works,
        "works_names": [WORKS_BY_ID[w]["name"] for w in works if w in WORKS_BY_ID],
        "rental_now": sim["rental_status"], "rental_after": sim["new_rental_status"],
        **investment(v, sim, profile, info["surface"], rent, info.get("building_type")),
        "risks": risks(facts, sim, v, market, today),
        # Value after works bounded by twice the works (api/green_value.py)
        "gain_capped": bool(v.get("gain_capped")),
        "_v": v, "_sim": sim, "_market": market,
    }


def public(o: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in o.items() if not k.startswith("_")}


SORTS = ("potentiel", "recent", "valeur", "rendement")


def months_since(day: Optional[str], today: date) -> Optional[int]:
    try:
        d = date.fromisoformat(str(day)[:10])
    except (TypeError, ValueError):
        return None
    return (today.year - d.year) * 12 + today.month - d.month


async def scan(bbox: str, labels: List[str], kind: Optional[str], profile: str,
               max_budget: Optional[float] = None, sort: Optional[str] = None,
               max_value: Optional[float] = None, max_age_months: Optional[int] = None,
               today: Optional[date] = None, ademe_transport: Optional[httpx.AsyncBaseTransport] = None,
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
    today = today or date.today()
    items = [o for o in found["items"]
             if (not max_budget or o["total"] <= max_budget) and (not max_value or o["price"] <= max_value)
             and (not max_age_months or (months_since(o.get("dpe_date"), today) or 0) <= max_age_months)]
    # The agent ranks by potential (what the renovation adds, the owner's
    # argument), by freshness of the DPE or by value; an investor by yield
    sort = sort if sort in SORTS else ("rendement" if profile == "bailleur" else "potentiel")
    sort_key = {
        # For the agent: what the works add to the dwelling's value, aids
        # deducted, without a buyer's notary fees (those stay in the files)
        "potentiel": lambda o: (o.get("value_created") or 0, o["margin"]),
        "recent": lambda o: o.get("dpe_date") or "",
        "valeur": lambda o: o["price"],
        "rendement": lambda o: (o.get("gross_yield") or 0, o["margin"]),
    }[sort]
    items.sort(key=sort_key, reverse=True)
    positive = [o for o in items if (o.get("value_created") or 0) > 0]
    return {
        "profile": profile,
        "sort": sort,
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
                        sort: Optional[str] = Query(None, pattern="^(potentiel|recent|valeur|rendement)$"),
                        max_value: Optional[float] = Query(None, ge=0),
                        max_age_months: Optional[int] = Query(None, ge=1, le=120),
                        user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    await require_pro(user, store)
    try:
        return await scan(bbox, labels.split(","), kind, profile, max_budget, sort, max_value, max_age_months)
    except AreaTooLarge as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPError as e:
        logger.error(f"Opportunity scan failed: {type(e).__name__}")
        raise HTTPException(status_code=502, detail="La base DPE de l'ADEME ne répond pas pour le moment.")


# --- Investment file ---

THESIS_COMMON = """Quand "valeur_apres_travaux_plafonnee" est vrai, le gain de valeur attribué aux travaux a été limité à deux fois leur coût : ne présente pas la rénovation comme une source de forte plus-value. Tu disposes uniquement des chiffres fournis (estimations SPREA : valeur DVF corrigée de la classe DPE, programme de travaux simulé, aides, loyers de la commune). N'invente aucun chiffre, aucune caractéristique ni aucun élément de quartier absent des données. Écris en français, de façon factuelle et professionnelle, sans superlatifs ni promesse de rendement ou de plus-value. Les montants sont des estimations avant frais financiers et fiscalité : rappelle-le quand c'est utile."""

THESIS_SYSTEM = {
    "investisseur": "Tu es un analyste en investissement immobilier qui rédige, pour un agent immobilier, la note d'opportunité d'un logement à rénover destinée à un client investisseur (marchand de biens ou bailleur). " + THESIS_COMMON + " Signale clairement quand l'opération n'est pas rentable selon les chiffres.",
    "acheteur": "Tu rédiges, pour un agent immobilier qui a ce logement en vente, la note qui accompagne le dossier remis à un acquéreur (investisseur ou acheteur prêt à rénover). Le but : que l'acquéreur voie un projet chiffré plutôt qu'une passoire. " + THESIS_COMMON + " Ne critique jamais le prix demandé et ne donne aucun argument pour le faire baisser : l'agent représente le vendeur. Reste honnête sur les points à vérifier.",
    "proprietaire": "Tu rédiges, pour un agent immobilier, la note d'un dossier remis au propriétaire de ce logement lors d'un premier rendez-vous : ce que vaut son bien aujourd'hui, ce que les travaux changeraient, et comment le vendre malgré son DPE. " + THESIS_COMMON + " Ton respectueux, sans dramatiser la situation du propriétaire.",
}

THESIS_ARGUMENTS = {
    "investisseur": "Arguments de négociation du prix d'achat tirés du DPE et des travaux, en 2 à 4 phrases.",
    "acheteur": "Ce qui fait la valeur du projet pour l'acquéreur (classe atteinte, valeur après travaux, loyer, aides), en 2 à 4 phrases, sans critiquer le prix.",
    "proprietaire": "Comment présenter le bien aux acquéreurs pour le vendre au bon prix malgré son DPE (projet chiffré, aides, valeur après travaux), en 2 à 4 phrases.",
}


def thesis_schema(audience: str) -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "these": {"type": "string", "description": "2 à 3 phrases : le logement, le projet de rénovation, ce qu'il change et ce qu'il vaut."},
            "points_forts": {"type": "array", "items": {"type": "string"}, "description": "3 à 5 points forts chiffrés."},
            "risques": {"type": "array", "items": {"type": "string"}, "description": "3 à 5 points à vérifier (travaux, copropriété, diagnostics)."},
            "strategie": {"type": "string", "description": "Scénario conseillé (revente, location ou occupation), travaux, calendrier, en 3 à 5 phrases."},
            "arguments": {"type": "string", "description": THESIS_ARGUMENTS[audience]},
        },
        "required": ["these", "points_forts", "risques", "strategie", "arguments"],
    }


def thesis_facts(o: Dict[str, Any], profile: str, audience: str = "investisseur") -> Dict[str, Any]:
    return {
        "destinataire": AUDIENCES[audience],
        "profil_acquereur": PROFILES[profile]["name"],
        "logement": {"type": o["kind"], "surface_m2": o["surface"], "epoque": o["period"], "commune": o.get("city"),
                     "classe_dpe": o["label"], "date_dpe": o["dpe_date"]},
        "programme": {"travaux": o["works_names"], "classe_apres": o["new_label"],
                      "cout_eur": [o["works_low"], o["works_high"]], "aides_eur": o["aids"]},
        "acquisition": {("prix_demande_eur" if o.get("price_is_asked") else "prix_estime_eur"): o["price"], "frais_notaire_eur": o["notary"], "budget_total_eur": o["total"]},
        "sortie": {"valeur_apres_travaux_eur": o["resale"], "marge_brute_eur": o["margin"], "marge_pct": o["margin_pct"],
                   "loyer_mensuel_eur": o.get("rent_month"), "rendement_brut_pct": o.get("gross_yield")},
        "location": {"aujourd_hui": o["rental_now"], "apres_travaux": o["rental_after"]},
        "valeur_apres_travaux_plafonnee": bool(o.get("gain_capped")),
        "points_de_vigilance_calcules": o["risks"],
    }


def lower_first(name: str) -> str:
    return name[:1].lower() + name[1:]


def fallback_thesis(o: Dict[str, Any], profile: str, audience: str = "investisseur") -> Dict[str, Any]:
    def eur(v):
        return f"{round(v or 0):,}".replace(",", " ") + " €"

    def pct(v):
        return f"{v} %".replace(".", ",")
    gained = "ABCDEFG".index(o["label"]) - "ABCDEFG".index(o["new_label"])
    good = o["margin"] > 0
    surface = f"{o['surface']:g}".replace(".", ",")
    priced = f"proposé à {eur(o['price'])}" if o.get("price_is_asked") else f"estimé {eur(o['price'])}"
    these = (f"{o['kind']} de {surface} m² classé {o['label']}, {priced} : le programme de travaux "
             f"({', '.join(lower_first(n) for n in o['works_names'])}) le porte en classe {o['new_label']} pour une valeur estimée "
             f"de {eur(o['resale'])}. ")
    if audience == "investisseur":
        these += (f"La marge brute ressort à {eur(o['margin'])} ({pct(o['margin_pct'])} du budget), avant frais financiers et fiscalité."
                  if good else f"Aux prix estimés, l'opération ne dégage pas de marge (−{eur(abs(o['margin']))}) : le prix d'achat doit se négocier.")
    elif good:
        these += f"Achat, frais et travaux compris, le projet coûte {eur(o['total'])}, soit {eur(o['margin'])} de moins que la valeur estimée après rénovation."
    else:
        these += f"Achat, frais et travaux compris, le projet coûte {eur(o['total'])}, pour une valeur estimée après rénovation de {eur(o['resale'])}."
    strengths = [f"Gain de {gained} classe{'s' if gained > 1 else ''} DPE ({o['label']} → {o['new_label']}).",
                 f"Budget total estimé : {eur(o['total'])}, travaux compris."]
    if o.get("gross_yield"):
        strengths.append(f"Loyer de marché d'environ {eur(o['rent_month'])} par mois, soit {pct(o['gross_yield'])} brut sur le budget total.")
    if o["aids"]:
        strengths.append(f"Aides estimées : {eur(o['aids'])}.")
    return {
        "these": these,
        "points_forts": strengths,
        "risques": o["risks"] + ["Faire chiffrer les travaux par des artisans RGE" + (" avant toute offre." if audience != "proprietaire" else ".")],
        "strategie": ("Mettre en vente avec ce projet chiffré : l'acquéreur voit le coût des travaux, les aides et la valeur après "
                      "rénovation, et peut faire son offre en connaissance de cause." if audience == "proprietaire" else
                      "Acheter, réaliser le programme dans l'ordre conseillé (enveloppe puis équipements), puis "
                      + ("revendre une fois la nouvelle classe DPE établie." if profile == "marchand"
                         else "louer après le nouveau DPE, qui conditionne le droit de louer.")),
        "arguments": arguments(o, audience, eur) if audience != "investisseur" else (f"La classe {o['label']} et le coût des travaux ({eur(o['works_low'])} à {eur(o['works_high'])}) "
                        "justifient une décote : "
                        + ("le logement ne peut déjà plus être loué en l'état." if "interdite" in (o.get("rental_now") or "").lower()
                           else f"{(o.get('rental_now') or '').lower().replace('louable', 'il reste louable')}, puis le vendeur devra financer ces travaux pour louer."
                           if "jusqu" in (o.get("rental_now") or "").lower()
                           else "un acheteur occupant devra financer ces travaux.")),
    }


def arguments(o: Dict[str, Any], audience: str, eur) -> str:
    """What makes the project worth it, for the buyer or told to the owner."""
    parts = [f"Le programme fait passer le logement de la classe {o['label']} à la classe {o['new_label']}"
             + (f", pour {eur(o['works_low'])} à {eur(o['works_high'])} de travaux" if o.get('works_low') else "")
             + (f" dont environ {eur(o['aids'])} d'aides" if o.get("aids") else "") + "."]
    if o.get("rent_month"):
        parts.append(f"Une fois rénové, il se loue environ {eur(o['rent_month'])} par mois ({o['rental_after'].lower()}).")
    parts.append(f"Sa valeur estimée après travaux, {eur(o['resale'])}, repose sur les ventes comparables du secteur listées dans ce dossier.")
    if audience == "proprietaire":
        parts.append("Présenter ce projet chiffré aux acquéreurs évite qu'ils imaginent un coût de travaux plus élevé qu'il n'est.")
    return " ".join(parts)


async def write_thesis(o: Dict[str, Any], profile: str, audience: str = "investisseur") -> Dict[str, Any]:
    if claude.configured():
        try:
            import json as _json
            data = await claude.json_call(THESIS_SYSTEM[audience], "Données du dossier (JSON) :\n" + _json.dumps(
                thesis_facts(o, profile, audience), ensure_ascii=False, indent=1), thesis_schema(audience),
                model="claude-sonnet-5-5", effort="medium", max_tokens=4000, timeout=60)
            if data.get("these"):
                return {**data, "source": "claude"}
        except claude.ClaudeUnavailable as e:
            logger.warning(f"Thesis by rules: {e}")
    return {**fallback_thesis(o, profile, audience), "source": "rules"}


class DossierRequest(BaseModel):
    number: str = Field(..., pattern=r"^[0-9A-Za-z]{10,16}$")
    profile: str = Field("marchand", pattern="^(marchand|bailleur)$")
    audience: str = Field("investisseur", pattern=AUDIENCE_PATTERN)
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
        o = with_price(o, data.purchase_price, data.profile)
    return o


async def render_dossier(o: Dict[str, Any], profile: str, audience: str, client_name: Optional[str],
                         user: User, store: SupabaseStore) -> Response:
    thesis = await write_thesis(public(o), profile, audience)
    agency = await store.get_agent_page(user.id) or {}
    address = display_address(o["address"] or "", o.get("postcode"), o.get("city"))
    pdf = pdf_service.generate_investment({
        **public(o),
        "profile": profile, "profile_name": PROFILES[profile]["name"], "audience": audience,
        "notary_rate": PROFILES[profile]["notary"],
        "thesis": thesis, "agency": agency, "address": address, "client_name": client_name,
        "valuation": o["_v"], "sim": o["_sim"], "market": o["_market"],
    })
    name = {"investisseur": "Dossier_investissement", "acheteur": "Dossier_acheteur", "proprietaire": "Dossier_proprietaire"}[audience]
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename={name}_{safe_filename(o['address'] or o.get('number') or 'logement')}.pdf"})


@router.post("/opportunities/dossier", dependencies=[Depends(search_limiter.per_user)])
async def opportunity_dossier(data: DossierRequest, user: User = Depends(current_user),
                              store: SupabaseStore = Depends(store_dep)):
    await require_pro(user, store)
    o = await dossier_data(data)
    return await render_dossier(o, data.profile, data.audience, data.client_name, user, store)


class SimulationDossierRequest(BaseModel):
    """A dwelling opened in the simulator, with the works the agent chose:
    typically the buyer's file of a dwelling under mandate."""
    meta: ReportMeta
    simulation: SimulationInput
    profile: str = Field("bailleur", pattern="^(marchand|bailleur)$")
    audience: str = Field("acheteur", pattern=AUDIENCE_PATTERN)
    purchase_price: Optional[float] = Field(None, ge=1000, le=20_000_000)
    client_name: Optional[str] = Field(None, max_length=100)


async def simulation_dossier_data(data: SimulationDossierRequest,
                                  dvf_transport: Optional[httpx.AsyncBaseTransport] = None,
                                  rent_transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    meta, prop = data.meta, data.simulation.property
    insee = meta.insee_code or prop.insee_code
    if not insee or not prop.surface:
        raise HTTPException(status_code=400, detail="Commune ou surface inconnue : dossier impossible pour ce logement.")
    if not data.simulation.works:
        raise HTTPException(status_code=422, detail="Sélectionnez des travaux pour établir le dossier.")
    market = await market_price(insee, prop.building_type, meta.latitude, meta.longitude, prop.surface, transport=dvf_transport)
    if not market:
        raise HTTPException(status_code=422, detail="Pas assez de ventes comparables connues autour de ce logement.")
    prop.price_per_m2, prop.price_source, prop.insee_code = market["price_per_m2"], market["source"], insee
    rent = await rent_per_m2(insee, prop.building_type, transport=rent_transport)
    o = assemble(data.simulation, market, rent, data.profile, date.today(), {
        "number": meta.ademe_dpe_number, "address": meta.address, "lat": meta.latitude, "lon": meta.longitude,
        "insee": insee, "postcode": meta.postcode or prop.postcode, "city": meta.city,
        "building_type": prop.building_type or meta.building_type, "surface": prop.surface,
        "period": meta.construction_period or prop.construction_period, "dpe_date": meta.dpe_date,
    })
    if not o:
        raise HTTPException(status_code=422, detail="Ce logement ne peut pas être chiffré avec ces travaux.")
    if data.purchase_price:
        o = with_price(o, data.purchase_price, data.profile)
    return o


def with_price(o: Dict[str, Any], price: float, profile: str) -> Dict[str, Any]:
    """The price actually asked replaces the estimate."""
    o["_v"]["value_now"] = {**o["_v"]["value_now"], "value": price}
    rent = {"rent_m2": o["rent_m2"], "low": o["rent_month_low"] / o["surface"], "high": o["rent_month_high"] / o["surface"],
            "adjusted": True, "commune_m2": o.get("rent_m2_commune")} if o.get("rent_m2") else None
    o.update(investment(o["_v"], o["_sim"], profile, o["surface"], rent))
    o["price_is_asked"] = True
    return o


@router.post("/opportunities/dossier/simulation", dependencies=[Depends(search_limiter.per_user)])
async def simulation_dossier(data: SimulationDossierRequest, user: User = Depends(current_user),
                             store: SupabaseStore = Depends(store_dep)):
    await require_pro(user, store)
    o = await simulation_dossier_data(data)
    return await render_dossier(o, data.profile, data.audience, data.client_name, user, store)


# --- Follow-up of prospected addresses, shared by the agency ---

STATUSES = ("courrier", "relance", "rendez_vous", "mandat", "ecarte")
NUMBER_RE = re.compile(r"^[0-9A-Za-z]{10,16}$")


async def status_scope(user: User, store: SupabaseStore) -> str:
    """The agency when the user belongs to one: its agents see the same
    follow-up, so two of them do not write to the same owner."""
    profile = await store.ensure_profile(user.id, user.email)
    if not is_pro(profile):
        raise HTTPException(status_code=402, detail="Réservé aux abonnés Pro.")
    return (profile.get("org") or {}).get("id") or user.id


@router.get("/prospect-status")
async def get_statuses(numbers: str = Query(..., max_length=4000), user: User = Depends(current_user),
                       store: SupabaseStore = Depends(store_dep)):
    wanted = [n for n in dict.fromkeys(numbers.split(",")) if NUMBER_RE.match(n)][:200]
    scope = await status_scope(user, store)
    if not wanted:
        return {"statuses": {}}
    try:
        rows = await store.prospect_statuses(scope, wanted)
    except httpx.HTTPError as e:
        # Follow-up is a convenience: the list stays usable without it
        logger.warning(f"Prospect statuses unavailable: {type(e).__name__}")
        return {"statuses": {}, "unavailable": True}
    return {"statuses": {r["dpe_number"]: {"status": r["status"], "updated_at": r.get("updated_at"),
                                            "mine": r.get("user_id") == user.id} for r in rows}}


@router.get("/prospect-status/all")
async def pipeline(user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    """Every followed address of the agency, latest first: the follow-up board
    of SPREA Command, with what is due today."""
    scope = await status_scope(user, store)
    try:
        rows = await store.prospect_pipeline(scope)
    except httpx.HTTPError as e:
        logger.warning(f"Prospect pipeline unavailable: {type(e).__name__}")
        return {"items": [], "unavailable": True}
    return {"items": [{"number": r["dpe_number"], "status": r["status"], "address": r.get("address"),
                       "updated_at": r.get("updated_at"), "mine": r.get("user_id") == user.id} for r in rows]}


class StatusUpdate(BaseModel):
    number: str = Field(..., pattern=r"^[0-9A-Za-z]{10,16}$")
    status: Optional[str] = Field(None, pattern="^(courrier|relance|rendez_vous|mandat|ecarte)$")
    address: Optional[str] = Field(None, max_length=300)


@router.put("/prospect-status")
async def put_status(data: StatusUpdate, user: User = Depends(current_user), store: SupabaseStore = Depends(store_dep)):
    scope = await status_scope(user, store)
    try:
        if data.status:
            await store.set_prospect_status({"scope": scope, "dpe_number": data.number, "status": data.status,
                                             "address": data.address, "user_id": user.id,
                                             "updated_at": datetime.now(timezone.utc).isoformat()})
        else:
            await store.clear_prospect_status(scope, data.number)
    except httpx.HTTPError as e:
        logger.error(f"Prospect status not saved: {type(e).__name__}")
        raise HTTPException(status_code=503, detail="Le suivi n'a pas pu être enregistré, réessayez.")
    return {"number": data.number, "status": data.status}
