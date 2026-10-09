"""Sale dossier of a whole building held by a company (monopropriété): what
the agent hands the owner to show why selling now makes sense.

Built from public data only:
- the building (BDNB, see api/monopro.py): dwellings, levels, year, last sale;
- the DPE of the building and of its dwellings (ADEME, around its position);
- local apartment prices (DVF, api/dvf.py) and the price gap between DPE
  classes measured on real sales (api/green_value.py);
- the law: rental ban of F and G dwellings, rent freeze, energy audit before
  selling a building held by a single owner, collective DPE.

Every figure is an order of magnitude, stated as such in the dossier.
"""
import re
import unicodedata
from datetime import date
from statistics import median
from typing import Any, Dict, List, Optional

try:
    from api.green_value import LABELS, department, kind_of, model
    from api.immeuble import (DPE_SINCE, collective_works, is_building_dpe, latest_per_apartment, since,
                              _float, _int)
    from api.valuation import class_factor, round_value
except ImportError:
    from green_value import LABELS, department, kind_of, model
    from immeuble import DPE_SINCE, collective_works, is_building_dpe, latest_per_apartment, since, _float, _int
    from valuation import class_factor, round_value

# Loi Climat et Résilience: dwellings of these classes can no longer be let (new
# lease or renewal) from these dates (mainland France)
RENTAL_BAN = {"G": date(2025, 1, 1), "F": date(2028, 1, 1), "E": date(2034, 1, 1)}
# Rents of F and G dwellings cannot be raised (no indexation) since 24 August 2022
RENT_FREEZE = date(2022, 8, 24)
# Energy audit required before selling a building held by a single owner
AUDIT_SALE = {"G": date(2023, 4, 1), "F": date(2023, 4, 1), "E": date(2025, 1, 1), "D": date(2034, 1, 1)}
# Average dwelling when no DPE gives the surfaces
DEFAULT_UNIT_M2 = 50
# Average dwelling surface beyond which the surface of a collective DPE is not believed
MIN_UNIT_M2, MAX_UNIT_M2 = 12, 200
# Whole-building energy renovation, € TTC per m² of living area, to reach C or D
# (order of magnitude from building audits), when the DPE does not detail the envelope
RENOVATION_M2 = {"G": (450, 750), "F": (350, 600), "E": (250, 450), "D": (120, 250)}
# Usual discount of a sale in one piece compared with selling flat by flat
BLOCK_DISCOUNT = (0.15, 0.25)
TARGET = "C"


def _date_fr(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def address_key(address: Optional[str]) -> str:
    """'121 Rue de Solférino 59800 Lille' -> '121 rue de solferino 59800 lille'."""
    plain = re.sub(r"[’‘`´]", "'", address or "")
    plain = unicodedata.normalize("NFKD", plain).encode("ascii", "ignore").decode().lower()
    # "(Saint-Pol-sur-Mer)": former commune, written by some sources only
    plain = re.sub(r"\([^)]*\)", " ", plain)
    plain = re.sub(r"[^a-z0-9]+", " ", plain).strip()
    # "18bis" and "18 bis"
    plain = re.sub(r"^(\d+) (bis|ter|quater|[a-h])\b", r"\1\2", plain)
    # Up to the postcode: the commune is written in full or not
    m = re.match(r"(.*?\b\d{5})\b", plain)
    return m.group(1) if m else plain


def rows_at_address(rows: List[Dict], address: Optional[str]) -> List[Dict]:
    """DPE published at the address of the building: the search around its
    position also returns the DPE of the neighbouring buildings."""
    key = address_key(address)
    return [r for r in rows if key and address_key(r.get("adresse_ban")) == key]


def scale_to(counts: Dict[str, int], total: int) -> Dict[str, int]:
    """Counts brought down to `total`, keeping their proportions (largest remainders)."""
    n = sum(counts.values())
    if n <= total:
        return dict(counts)
    exact = {l: c * total / n for l, c in counts.items()}
    out = {l: int(v) for l, v in exact.items()}
    for l in sorted(exact, key=lambda l: exact[l] - out[l], reverse=True)[:total - sum(out.values())]:
        out[l] += 1
    return out


def units_by_label(nb_log: int, apartments: List[Dict], building_label: Optional[str]) -> Dict[str, Any]:
    """Dwellings per DPE class: the published DPE of the dwellings, the others
    estimated at the class of the building. Never more than the dwellings of
    the building: more DPE than dwellings (old and new DPE of the same flat
    not told apart) only give the proportions."""
    known = {l: 0 for l in LABELS}
    for a in apartments:
        known[a["etiquette_dpe"]] += 1
    known = scale_to(known, nb_log)
    n_known = sum(known.values())
    estimated = {l: 0 for l in LABELS}
    rest = nb_log - n_known
    if rest > 0 and building_label in LABELS:
        estimated[building_label] = rest
        rest = 0
    total = {l: known[l] + estimated[l] for l in LABELS}
    return {"known": known, "estimated": estimated, "total": total, "unknown": rest, "n_known": n_known}


def arguments(units: Dict, works: Optional[Dict], value: Optional[Dict], holding: Optional[str],
              audit: Optional[Dict], today: date) -> List[str]:
    """Why selling now: the facts that weigh, strongest first."""
    out = []
    t = units["total"]
    for label in ("G", "F", "E"):
        n = t[label]
        if not n:
            continue
        ban = RENTAL_BAN[label]
        s = "s" if n > 1 else ""
        when = (f"ne peu{'vent' if n > 1 else 't'} plus être reloué{s} depuis le" if ban <= today else
                f"ne pourr{'ont' if n > 1 else 'a'} plus être reloué{s} à partir du")
        out.append(f"{n} logement{s} classé{s} {label} {when} {_date_fr(ban)}"
                   + (" : chaque départ de locataire laisse un logement vide." if ban <= today else "."))
    if t["F"] + t["G"]:
        out.append(f"Loyers gelés : depuis le {_date_fr(RENT_FREEZE)}, le loyer d'un logement F ou G ne peut plus être "
                   "révisé ni augmenté, même à la relocation.")
    if value and value.get("dpe_discount"):
        out.append(f"Décote liée au DPE : environ {fmt_eur(value['dpe_discount'])} de moins qu'un immeuble équivalent classé D, "
                   "d'après les ventes réelles du département.")
    if works:
        out.append(f"Travaux à prévoir pour sortir de ces classes : {fmt_range(works['low'], works['high'])}, "
                   "à financer par le propriétaire seul (pas de copropriété pour les partager).")
    if audit and audit["required"]:
        out.append(audit["text"])
    if holding:
        out.append(holding)
    return out


def fmt_range(low: float, high: float) -> str:
    """Same rounding as the figures of the dossier (to 100 €)."""
    r = lambda v: f"{int(round(v / 100) * 100):,}".replace(",", "\u202f") + "\u00a0€"
    return f"{r(low)} à {r(high)}"


def fmt_eur(v: float) -> str:
    return f"{round_value(v):,}".replace(",", " ") + " €"


def build_dossier(building: Dict, owner: Optional[Dict], company: Optional[Dict], portfolio_count: int,
                  rows: List[Dict], market: Optional[Dict], agency: Dict, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    nb_log = building["nb_log"]
    # Only the DPE published at the address of the building: the search around
    # its position also returns those of the neighbouring buildings
    rows = rows_at_address(rows, building.get("address"))
    buildings_dpe = sorted((r for r in rows if is_building_dpe(r) and r.get("etiquette_dpe") in set(LABELS)),
                           key=lambda r: r.get("date_etablissement_dpe") or "", reverse=True)
    building_dpe = buildings_dpe[0] if buildings_dpe else None
    apartments = latest_per_apartment(rows)
    label = (building_dpe or {}).get("etiquette_dpe") or building.get("dpe_label")
    units = units_by_label(nb_log, apartments, label)

    # Living area: collective DPE, else dwellings x median surface of their DPE
    surfaces = [s for s in (_float(a.get("surface_habitable_logement")) for a in apartments) if s]
    unit_m2 = median(surfaces) if surfaces else DEFAULT_UNIT_M2
    measured = _float((building_dpe or {}).get("surface_habitable_immeuble"))
    if measured and not MIN_UNIT_M2 <= measured / nb_log <= MAX_UNIT_M2:
        measured = None  # DPE of part of the building only, or a typing error
    shab = measured or nb_log * unit_m2
    shab_estimated = not measured
    levels = building.get("levels") or _int((building_dpe or {}).get("nombre_niveau_immeuble")) or 3

    # Works: detailed from the DPE when it describes the envelope, else per m² for the class
    source = building_dpe or (max(apartments, key=lambda a: LABELS.index(a["etiquette_dpe"])) if apartments else None)
    items = collective_works(source, shab, levels, nb_log, building.get("year_built")) if source else []
    worst = max((l for l in LABELS if units["total"][l]), key=LABELS.index, default=label)
    old_building = building.get("year_built") is not None and building["year_built"] < 1948
    if old_building:
        # Old façades (often protected): insulation from the inside, at about the same cost
        for it in items:
            if it.get("id") == "facade":
                it["name"] = "Isolation des murs (par l'intérieur ou l'extérieur)"
    works = None
    floor = RENOVATION_M2.get(worst)
    if items:
        works = {"items": items, "low": sum(w["low"] for w in items), "high": sum(w["high"] for w in items), "detailed": True}
    if floor:
        # Reaching class C from E, F or G takes more than the envelope works the
        # DPE points out (windows, heating, ventilation): the whole renovation
        # costs at least the usual amount per m² for the class
        low, high = round(shab * floor[0], -2), round(shab * floor[1], -2)
        if not works:
            works = {"items": [{"name": f"Rénovation énergétique globale (immeuble classé {worst})",
                                "reason": "ordre de grandeur par m² habitable", "low": low, "high": high}],
                     "low": low, "high": high, "detailed": False}
        elif works["low"] < low:
            rest_low, rest_high = low - works["low"], max(high - works["high"], low - works["low"])
            works["items"].append({"name": "Autres postes pour atteindre la classe C", "reason": "fenêtres, chauffage, ventilation, eau chaude",
                                   "low": round(rest_low, -2), "high": round(rest_high, -2)})
            works["low"], works["high"] = sum(w["low"] for w in works["items"]), sum(w["high"] for w in works["items"])

    # Value: local apartment prices, corrected for the DPE class of each dwelling
    value = None
    if market and market.get("price_per_m2"):
        dep = department(building.get("insee"), None)
        m = model(kind_of("Appartement"), dep)
        price = market["price_per_m2"]
        per_unit = shab / nb_log
        counted = {l: n for l, n in units["total"].items() if n}
        factor_now = (sum(n * class_factor(m, l) for l, n in counted.items()) + units["unknown"]) / nb_log
        factor_d = class_factor(m, "D")
        factor_target = class_factor(m, TARGET)
        lots_now = shab * price * factor_now
        value = {
            "price_m2": price, "source": market.get("source"), "per_unit_m2": round(per_unit),
            "lots_now": round_value(lots_now),
            "block_low": round_value(lots_now * (1 - BLOCK_DISCOUNT[1])),
            "block_high": round_value(lots_now * (1 - BLOCK_DISCOUNT[0])),
            "after_works": round_value(shab * price * max(factor_target, factor_now)),
            "dpe_discount": round_value(max(0.0, shab * price * (factor_d - factor_now))) or None,
            "measured": bool(m),
        }

    # Energy audit before the sale (building held by a single owner)
    audit = {"required": False, "text": None}
    if worst in AUDIT_SALE:
        start = AUDIT_SALE[worst]
        if start <= today:
            audit = {"required": True, "text": f"Audit énergétique obligatoire pour vendre l'immeuble (classe {worst}, depuis le "
                                               f"{_date_fr(start)}) : il chiffre les travaux et les rend visibles à tout acheteur."}
        else:
            audit = {"required": False, "text": f"Audit énergétique obligatoire à la vente à partir du {_date_fr(start)} (classe {worst})."}

    # Collective DPE of the building (permit before 2013)
    dpe_due = since(nb_log, DPE_SINCE)
    year = building.get("year_built")
    collective_dpe = None
    if (year is None or year < 2013) and dpe_due:
        collective_dpe = ({"done": True, "text": f"DPE collectif publié le {building_dpe['date_etablissement_dpe'][8:10]}/"
                                                 f"{building_dpe['date_etablissement_dpe'][5:7]}/{building_dpe['date_etablissement_dpe'][:4]} "
                                                 f"(classe {building_dpe['etiquette_dpe']})."}
                          if building_dpe else
                          {"done": False, "text": f"DPE collectif obligatoire depuis le {_date_fr(dpe_due)} pour un immeuble de "
                                                  f"{nb_log} logements ; aucun n'est publié à cette adresse."
                                                  if dpe_due <= today else
                                                  f"DPE collectif obligatoire à partir du {_date_fr(dpe_due)}."})

    holding = None
    if building.get("last_sale_date"):
        years = today.year - int(building["last_sale_date"][:4])
        if years >= 1:
            holding = f"Immeuble acquis en {building['last_sale_date'][:4]} (dernière vente connue) : détenu depuis environ {years} ans."
    else:
        holding = "Aucune vente de l'immeuble depuis 2014 (base DVF) : détenu depuis plus de dix ans."

    return {
        "building": building, "owner": owner, "company": company, "portfolio_count": portfolio_count,
        "agency": agency, "label": label, "worst": worst,
        "building_dpe": {"label": building_dpe["etiquette_dpe"], "date": building_dpe.get("date_etablissement_dpe")} if building_dpe else None,
        "units": units, "shab": round(shab), "shab_estimated": shab_estimated, "levels": levels,
        "works": works, "value": value, "audit": audit, "collective_dpe": collective_dpe, "holding": holding,
        "rental_ban": [{"label": l, "date": _date_fr(d), "passed": d <= today, "units": units["total"][l]} for l, d in RENTAL_BAN.items()],
        "arguments": arguments(units, works, value, holding, audit, today),
    }
