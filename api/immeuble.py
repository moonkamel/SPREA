"""Building sheet for an apartment in a copropriété.

Crosses three public sources:
- the national registry of copropriétés (RNIC, Anah, Licence Ouverte), loaded
  monthly into the coproprietes table: lots, construction period, syndic;
- the ADEME DPE open data: the collective DPE of the building when there is
  one, and the DPE of the other apartments at the same address;
- the copropriété law: projet de plan pluriannuel de travaux (PPT) and
  collective DPE, mandatory by size of the copropriété.

From there, an order of magnitude of the collective works to come (façades,
roof, floor, heating plant, ventilation) and the share of an apartment, pro
rata of its surface (the real share follows the tantièmes of the règlement).
"""
import logging
import math
import re
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

try:
    from api.accounts import store_dep, subscriber_access
    from api.address import same_address, same_street
    from api.prospection import ADEME_URL, dwelling_detail
    from api.ratelimit import search_limiter
except ImportError:
    from accounts import store_dep, subscriber_access
    from address import same_address, same_street
    from prospection import ADEME_URL, dwelling_detail
    from ratelimit import search_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

LABELS = "ABCDEFG"
FIELDS = ["numero_dpe", "date_etablissement_dpe", "etiquette_dpe", "etiquette_ges", "type_batiment",
          "methode_application_dpe", "numero_immatriculation_copropriete", "numero_dpe_immeuble_associe",
          "surface_habitable_logement", "surface_habitable_immeuble", "nombre_appartement", "nombre_niveau_immeuble",
          "adresse_ban", "identifiant_ban", "_geopoint", "periode_construction", "complement_adresse_logement",
          "numero_etage_appartement", "type_installation_chauffage", "type_energie_principale_chauffage",
          "type_ventilation", "qualite_isolation_murs", "qualite_isolation_menuiseries",
          "qualite_isolation_plancher_bas", "qualite_isolation_plancher_haut_comble_perdu",
          "qualite_isolation_plancher_haut_comble_amenage", "qualite_isolation_plancher_haut_toit_terrase"]
CACHE_TTL = 6 * 3600
_cache: Dict[str, Tuple[float, Dict]] = {}

PERIODS = {
    "AVANT_1949": "Avant 1949", "DE_1949_A_1960": "1949 – 1960", "DE_1961_A_1974": "1961 – 1974",
    "DE_1975_A_1993": "1975 – 1993", "DE_1994_A_2000": "1994 – 2000", "DE_2001_A_2010": "2001 – 2010",
    "A_COMPTER_DE_2011": "Depuis 2011", "APRES_2011": "Depuis 2011",
}

# Projet de plan pluriannuel de travaux (copropriétés of more than 15 years,
# art. 14-2 loi du 10 juillet 1965) and collective DPE (buildings whose permit
# predates 2013, art. L. 126-31 CCH): dates by number of main lots.
PPT_SINCE = ((200, date(2023, 1, 1)), (50, date(2024, 1, 1)), (0, date(2025, 1, 1)))
DPE_SINCE = ((200, date(2024, 1, 1)), (50, date(2025, 1, 1)), (0, date(2026, 1, 1)))

# Collective works, € TTC (5.5 % VAT), order of magnitude from copropriété
# audits. Envelope works are per m² of the element, systems per dwelling.
FACADE_PER_SHAB = 0.6       # Opaque façade area per m² of living area
COSTS = {
    "facade": (150, 250),        # Isolation thermique par l'extérieur, € / m² of façade
    "roof_terrace": (150, 250),  # Toiture-terrasse, € / m² of roof
    "roof_attic": (30, 60),      # Combles perdus, € / m² of roof
    "roof": (60, 180),           # Unknown roof type
    "floor": (30, 60),           # Plancher bas (cave, parking), € / m²
    "heating": (3000, 7000),     # Chaufferie collective, € / dwelling
    "vmc": (1500, 3000),         # VMC collective hygroréglable, € / dwelling
}
WORK_NAMES = {
    "facade": "Isolation des façades par l'extérieur",
    "roof": "Isolation de la toiture",
    "floor": "Isolation du plancher bas (caves, parking)",
    "heating": "Remplacement de la chaufferie collective",
    "vmc": "Ventilation mécanique collective",
}
POOR = ("insuffisante", "moyenne")
# MaPrimeRénov' Copropriété: 30 % (gain of 35 %) or 45 % (gain of 50 %) of the
# works HT, within 25 000 € HT per dwelling
MPR_COPRO_RATES = (0.30, 0.45)
MPR_COPRO_CAP = 25000
TVA = 0.055


def _float(value: Any) -> Optional[float]:
    try:
        f = float(value)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    f = _float(value)
    return int(f) if f is not None else None


def _point(value: Optional[str]) -> Optional[Tuple[float, float]]:
    try:
        lat, lon = (float(x) for x in (value or "").split(","))
        return lat, lon
    except ValueError:
        return None


def metres(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def is_building_dpe(r: Dict) -> bool:
    """DPE of the whole building. "dpe appartement généré à partir des données
    DPE immeuble" is the DPE of one apartment, drawn from the building's."""
    method = (r.get("methode_application_dpe") or "").lower()
    return (r.get("type_batiment") or "").lower() == "immeuble" or ("immeuble" in method and "appartement" not in method)


def last_year(period: Optional[str]) -> Optional[int]:
    """Last construction year of a period ("DE_1961_A_1974" -> 1974,
    "AVANT_1949" -> 1948, "1948-1974" -> 1974); None when open-ended or unknown."""
    p = (period or "").upper()
    if not p or "COMPTER" in p or "APRES" in p or "APRÈS" in p or "NON" in p:
        return None
    years = [int(y) for y in re.findall(r"\d{4}", p)]
    if not years:
        return None
    return years[-1] - 1 if "AVANT" in p else years[-1]


def period_label(period: Optional[str]) -> Optional[str]:
    """None when unknown ("NON_CONNUE", "non renseigné"): the DPE period is used instead."""
    if not period or "NON" in period.upper():
        return None
    return PERIODS.get(period.upper(), period.replace("_", " ").capitalize())


def since(lots: Optional[int], table) -> Optional[date]:
    if lots is None:
        return None
    for above, start in table:
        if lots > above:
            return start
    return table[-1][1]


def obligations(lots: Optional[int], built_until: Optional[int], building_dpe: Optional[Dict], today: date) -> List[Dict]:
    """PPT and collective DPE: due date, and whether the collective DPE is published."""
    out = []
    old = built_until is not None and built_until <= today.year - 15
    ppt = since(lots, PPT_SINCE)
    if old:
        out.append({
            "id": "ppt", "title": "Projet de plan pluriannuel de travaux (PPT)",
            "since": ppt.isoformat() if ppt else None,
            "status": "due" if ppt and ppt <= today else ("upcoming" if ppt else "check"),
            "detail": "Obligatoire pour les copropriétés de plus de 15 ans : il liste les travaux des 10 prochaines "
                      "années et le syndic doit le présenter en assemblée générale. Il alimente le fonds travaux.",
        })
    dpe = since(lots, DPE_SINCE)
    if built_until is not None and built_until < 2013:
        if building_dpe:
            status, detail = "done", f"DPE de l'immeuble publié le {building_dpe['date_fr']} (classe {building_dpe['label']})."
        else:
            status = "due" if dpe and dpe <= today else ("upcoming" if dpe else "check")
            detail = "Aucun DPE de l'immeuble n'est publié à cette adresse dans la base de l'ADEME : demandez au syndic s'il est réalisé."
        out.append({"id": "dpe", "title": "DPE collectif de l'immeuble", "since": dpe.isoformat() if dpe else None,
                    "status": status, "detail": detail})
    return out


def latest_per_apartment(rows: List[Dict]) -> List[Dict]:
    """Apartment DPE at the address, the latest per dwelling (floor/complement + surface)."""
    latest: Dict[Tuple, Dict] = {}
    for r in rows:
        if is_building_dpe(r) or r.get("etiquette_dpe") not in set(LABELS):
            continue
        key = ((dwelling_detail(r) or "").lower(), round(_float(r.get("surface_habitable_logement")) or 0))
        current = latest.get(key)
        if current is None or (r.get("date_etablissement_dpe") or "") > (current.get("date_etablissement_dpe") or ""):
            latest[key] = r
    return list(latest.values())


def _date_fr(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def building_summary(r: Dict) -> Dict:
    return {
        "number": r.get("numero_dpe"), "label": r.get("etiquette_dpe"), "ges": r.get("etiquette_ges"),
        "date": (r.get("date_etablissement_dpe") or "")[:10] or None,
        "date_fr": _date_fr(r.get("date_etablissement_dpe")),
        "surface": _float(r.get("surface_habitable_immeuble")), "apartments": _int(r.get("nombre_appartement")),
        "levels": _int(r.get("nombre_niveau_immeuble")),
    }


def poor_levels(label: Optional[str]) -> Tuple[str, ...]:
    """Insulation qualities worth collective works, by energy class: none for
    A to C (the building already performs), "insuffisante" only for D."""
    if label in ("A", "B", "C"):
        return ()
    if label in ("E", "F", "G"):
        return POOR
    return ("insuffisante",)


def collective_works(source: Dict, shab: float, levels: int, dwellings: int,
                     built_until: Optional[int] = None) -> List[Dict]:
    """Collective works suggested by the insulation and systems of the DPE
    (the building's when published, else the apartment's)."""
    works = []
    roof_area = shab / max(levels, 1)
    label = source.get("etiquette_dpe")
    poor = poor_levels(label)
    # Since the RT 2000, walls are insulated: a façade is only redone for a poor class
    recent = built_until is not None and built_until > 2000

    def add(work_id: str, reason: str, low: float, high: float):
        works.append({"id": work_id, "name": WORK_NAMES[work_id], "reason": reason,
                      "low": round(low, -2), "high": round(high, -2)})

    walls = (source.get("qualite_isolation_murs") or "").lower()
    if walls in poor and not (recent and label not in ("E", "F", "G")):
        area = shab * FACADE_PER_SHAB
        add("facade", f"Isolation des murs {walls}", area * COSTS["facade"][0], area * COSTS["facade"][1])
    terrace = (source.get("qualite_isolation_plancher_haut_toit_terrase") or "").lower()
    attic = (source.get("qualite_isolation_plancher_haut_comble_perdu") or "").lower()
    other_roof = (source.get("qualite_isolation_plancher_haut_comble_amenage") or "").lower()
    if terrace in poor:
        add("roof", f"Toiture-terrasse : isolation {terrace}", roof_area * COSTS["roof_terrace"][0], roof_area * COSTS["roof_terrace"][1])
    elif attic in poor:
        add("roof", f"Combles : isolation {attic}", roof_area * COSTS["roof_attic"][0], roof_area * COSTS["roof_attic"][1])
    elif other_roof in poor:
        add("roof", f"Toiture : isolation {other_roof}", roof_area * COSTS["roof"][0], roof_area * COSTS["roof"][1])
    floor = (source.get("qualite_isolation_plancher_bas") or "").lower()
    if floor in poor:
        add("floor", f"Plancher bas : isolation {floor}", roof_area * COSTS["floor"][0], roof_area * COSTS["floor"][1])
    collective = "collectif" in (source.get("type_installation_chauffage") or "").lower()
    if collective and source.get("etiquette_dpe") in ("E", "F", "G"):
        energy = (source.get("type_energie_principale_chauffage") or "").lower()
        add("heating", f"Chauffage collectif{(' ' + energy) if energy else ''}, classe {source['etiquette_dpe']}",
            dwellings * COSTS["heating"][0], dwellings * COSTS["heating"][1])
    ventilation = (source.get("type_ventilation") or "").lower()
    if poor and ventilation and ("naturelle" in ventilation or "ouverture" in ventilation or "sans" in ventilation):
        add("vmc", f"Ventilation actuelle : {source['type_ventilation']}", dwellings * COSTS["vmc"][0], dwellings * COSTS["vmc"][1])
    return works


def copro_summary(c: Dict, match: str) -> Dict:
    professional = "pro" in (c.get("syndic_type") or "").lower()
    return {
        "immat": c.get("immat"), "name": c.get("name") or None, "address": c.get("address"),
        "lots_total": c.get("lots_total"), "lots_main": c.get("lots_main"), "lots_housing": c.get("lots_housing"),
        "lots_parking": c.get("lots_parking"), "period": period_label(c.get("period")),
        "syndic_type": (c.get("syndic_type") or "").replace("_", " ").lower() or None,
        # Volunteer syndics are private persons: only professional syndics are named
        "syndic_name": c.get("syndic_name") if professional else None,
        "mandate_end": c.get("mandate_end"), "aided": bool(c.get("aided")), "in_pdp": bool(c.get("in_pdp")),
        "qpv": c.get("qpv") or None, "registry_updated": c.get("registry_updated"), "match": match,
    }


def build_sheet(apartment: Dict, rows: List[Dict], copro: Optional[Dict], match: Optional[str],
                today: Optional[date] = None) -> Dict:
    today = today or date.today()
    buildings = sorted((r for r in rows if is_building_dpe(r) and r.get("etiquette_dpe") in set(LABELS)),
                       key=lambda r: r.get("date_etablissement_dpe") or "", reverse=True)
    associated = apartment.get("numero_dpe_immeuble_associe")
    building_row = next((r for r in buildings if associated and r.get("numero_dpe") == associated), None) or \
        (buildings[0] if buildings else None)
    building = building_summary(building_row) if building_row else None
    apartments = latest_per_apartment(rows + [apartment])
    distribution = {l: 0 for l in LABELS}
    for r in apartments:
        distribution[r["etiquette_dpe"]] += 1

    surface = _float(apartment.get("surface_habitable_logement"))
    dwellings = (copro or {}).get("lots_housing") or (building or {}).get("apartments") or \
        _int(apartment.get("nombre_appartement")) or len(apartments)
    shab = (building or {}).get("surface") or _float(apartment.get("surface_habitable_immeuble")) or \
        (surface * dwellings if surface and dwellings else None)
    floors = [_int(r.get("numero_etage_appartement")) for r in apartments]
    levels = (building or {}).get("levels") or _int(apartment.get("nombre_niveau_immeuble")) or \
        max([f + 1 for f in floors if f is not None] or [0]) or 4

    built_until = last_year((copro or {}).get("period")) or last_year(apartment.get("periode_construction"))
    lots = (copro or {}).get("lots_main") or dwellings
    source = building_row or apartment
    works = collective_works(source, shab, levels, dwellings, built_until) if shab and dwellings else []
    works_note = None
    if not works and source.get("etiquette_dpe") in ("A", "B", "C"):
        works_note = (f"{'Immeuble' if building_row else 'Appartement'} classé {source['etiquette_dpe']} : "
                      "pas de gros travaux énergétiques collectifs à prévoir d'après le DPE.")
    elif not works:
        works_note = "Le DPE ne fait pas ressortir de travaux énergétiques collectifs importants."
    total = [sum(w["low"] for w in works), sum(w["high"] for w in works)]
    share = min(surface / shab, 1.0) if surface and shab else None
    estimate = None
    if works and share:
        # MaPrimeRénov' Copropriété on the works HT, within the ceiling per dwelling
        def aid(cost_ttc: float, rate: float) -> float:
            return rate * min(cost_ttc / (1 + TVA), MPR_COPRO_CAP * dwellings)
        estimate = {
            "share": round(share, 4),
            "share_low": round(total[0] * share, -2), "share_high": round(total[1] * share, -2),
            "aid_rates": list(MPR_COPRO_RATES),
            # Net share: lowest cost with the best aid, highest cost with the lowest aid
            "net_low": round((total[0] - aid(total[0], MPR_COPRO_RATES[1])) * share, -2),
            "net_high": round((total[1] - aid(total[1], MPR_COPRO_RATES[0])) * share, -2),
        }
    return {
        "address": apartment.get("adresse_ban"),
        "copro": copro_summary(copro, match) if copro else None,
        "building_dpe": building,
        "apartments": {"count": len(apartments), "distribution": distribution},
        "dimensions": {"surface": round(shab) if shab else None, "levels": levels, "dwellings": dwellings,
                       "apartment_surface": surface},
        "period": period_label((copro or {}).get("period")) or apartment.get("periode_construction"),
        "obligations": obligations(lots, built_until, building, today),
        "works": works, "total": total if works else None, "estimate": estimate, "works_note": works_note,
        "works_source": "immeuble" if building_row else "appartement",
    }


# A copropriété registered on another street is taken only this close (the
# same corner building, entered under its other address)
CORNER_M = 15


def nearest_copro(candidates: List[Dict], point: Tuple[float, float], max_m: float = 40,
                  address: Optional[str] = None) -> Optional[Dict]:
    """The registered copropriété at this position: at the same address when
    one is, never one registered on another street (the next building)."""
    if address:
        here = [c for c in candidates if same_address(c.get("address"), address)]
        candidates = here or [c for c in candidates if not c.get("address") or same_street(c.get("address"), address)]
    best, best_d = None, max_m
    for c in candidates:
        if c.get("lat") is None or c.get("lon") is None:
            continue
        d = metres(point, (c["lat"], c["lon"]))
        if d <= best_d:
            best, best_d = c, d
    return best


def match_copro(candidates: List[Dict], point: Tuple[float, float], address: Optional[str]) -> Tuple[Optional[Dict], Optional[str]]:
    """Copropriété of the building and how it was found: "position" (same
    address or street), "corner" (another street, a few metres away: a corner
    building registered under its other address, to check)."""
    found = nearest_copro(candidates, point, address=address)
    if found:
        return found, "position"
    if address:
        corner = nearest_copro(candidates, point, max_m=CORNER_M)
        if corner:
            return corner, "corner"
    return None, None


async def ademe_rows(client: httpx.AsyncClient, params: Dict[str, str]) -> List[Dict]:
    res = await client.get(ADEME_URL, params={"select": ",".join(FIELDS), **params})
    if res.status_code == 400:
        # A field renamed by the ADEME: whole lines rather than no sheet
        logger.warning("ADEME rejected the field selection")
        res = await client.get(ADEME_URL, params=params)
    res.raise_for_status()
    return res.json().get("results") or []


async def sheet(dpe_number: str, store, transport: Optional[httpx.AsyncBaseTransport] = None,
                today: Optional[date] = None) -> Optional[Dict]:
    """None when the DPE is unknown or not an apartment's."""
    cached = _cache.get(dpe_number)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    async with httpx.AsyncClient(timeout=12, transport=transport) as client:
        found = await ademe_rows(client, {"qs": f'numero_dpe:"{dpe_number}"', "size": "1"})
        if not found or (found[0].get("type_batiment") or "").lower() != "appartement":
            return None
        apartment = found[0]
        point = _point(apartment.get("_geopoint"))
        if apartment.get("identifiant_ban"):
            rows = await ademe_rows(client, {"qs": f'identifiant_ban:"{apartment["identifiant_ban"]}"', "size": "300"})
        elif point:
            rows = await ademe_rows(client, {"geo_distance": f"{point[1]},{point[0]},25", "size": "300"})
        else:
            rows = []
        associated = apartment.get("numero_dpe_immeuble_associe")
        if associated and not any(r.get("numero_dpe") == associated for r in rows):
            rows += await ademe_rows(client, {"qs": f'numero_dpe:"{associated}"', "size": "1"})
    rows = [r for r in rows if r.get("numero_dpe") != apartment.get("numero_dpe")]

    copro, match = None, None
    if store is not None:
        try:
            immat = apartment.get("numero_immatriculation_copropriete") or \
                next((r["numero_immatriculation_copropriete"] for r in rows if r.get("numero_immatriculation_copropriete")), None)
            if immat:
                copro, match = await store.get_copro(str(immat).strip().upper()), "immat"
            if not copro and point:
                copro, match = match_copro(await store.copros_near(*point), point, apartment.get("adresse_ban"))
        except httpx.HTTPError as e:
            logger.warning(f"Copro registry lookup failed: {type(e).__name__}")
            copro = None
    result = build_sheet(apartment, rows, copro, match if copro else None, today)
    _cache[dpe_number] = (time.time(), result)
    return result


async def sheet_or_none(dpe_number: Optional[str], building_type: Optional[str], store) -> Optional[Dict]:
    """Same, for the report: None outside apartments or when ADEME does not answer."""
    if not dpe_number or not (building_type or "").lower().startswith("appartement"):
        return None
    try:
        return await sheet(dpe_number, store)
    except httpx.HTTPError as e:
        logger.warning(f"Building sheet failed: {type(e).__name__}")
        return None


def optional_store(request: Request):
    override = request.app.dependency_overrides.get(store_dep, store_dep)
    try:
        return override()
    except HTTPException:
        return None  # Registry not configured: the sheet works with the DPE alone


@router.get("/immeuble", dependencies=[Depends(search_limiter), Depends(subscriber_access)])
async def building_sheet(dpe: str = Query(..., pattern=r"^[0-9A-Za-z]{10,16}$"), store=Depends(optional_store)):
    try:
        result = await sheet(dpe.upper(), store)
    except httpx.HTTPError as e:
        logger.error(f"Building sheet failed: {type(e).__name__}")
        raise HTTPException(status_code=502, detail="La base DPE de l'ADEME ne répond pas pour le moment.")
    if result is None:
        raise HTTPException(status_code=404, detail="Fiche immeuble disponible uniquement pour un DPE d'appartement.")
    return result
