"""Content of the paid report: every figure and every factual sentence is
computed here from the simulation, so the report stays specific to the
dwelling whether or not the written analysis (api/ai_service.py) is available.
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional

try:
    from api.aids import AMPLEUR_LABELS
    from api.envelope import FLOOR_HEIGHT
    from api.simulation import (DEFAULT_PRICE_PER_M2, CURRENT_HEATING_EFFICIENCY, ampleur_variant, usage_split, wall_alternative, ENERGY_PRICES_EUR_KWH,
                                HEATING_SYSTEMS, HEAT_PUMP_WATER_HEATER_COP,
                                SimulationInput, WORKS_BY_ID, is_house, projected_performance,
                                simulate, single_work_effects)
except ImportError:
    from aids import AMPLEUR_LABELS
    from envelope import FLOOR_HEIGHT
    from simulation import (DEFAULT_PRICE_PER_M2, CURRENT_HEATING_EFFICIENCY, ampleur_variant, usage_split, wall_alternative, ENERGY_PRICES_EUR_KWH,
                            HEATING_SYSTEMS, HEAT_PUMP_WATER_HEATER_COP,
                            SimulationInput, WORKS_BY_ID, is_house, projected_performance,
                            simulate, single_work_effects)

ENERGY_NAMES = {
    "electricity": "électricité",
    "gas": "gaz",
    "oil": "fioul",
    "wood": "bois",
    "district_heating": "réseau de chaleur",
}

LOSS_NAMES = {
    "walls": "Murs",
    "roof": "Toiture ou plafond",
    "floor": "Plancher bas",
    "windows": "Fenêtres",
    "air": "Renouvellement d'air",
    "bridges": "Ponts thermiques et portes",
}

USAGE_NAMES = {"heating": "Chauffage", "hot_water": "Eau chaude", "other": "Autres usages (éclairage, auxiliaires)"}

QUALITY_ELEMENT = {"iti": "walls", "ite": "walls", "roof": "roof", "floor_ceiling": "floor", "windows": "windows"}

# Works order on site: envelope first, then ventilation, then systems
WORK_ORDER = ["roof", "iti", "ite", "floor_ceiling", "windows", "vmc", "pac_air_eau", "heating", "ecs"]

SMALL_WORDS = {"de", "du", "des", "la", "le", "les", "et", "à", "a", "au", "aux", "sur", "sous", "en", "d", "l"}


# --- Formatting helpers (plain text, the PDF escapes it) ---


def round500(value) -> int:
    return int(round((value or 0) / 500) * 500)

def fr_int(value: float) -> str:
    return f"{round(value):,}".replace(",", " ")


def fr_dec(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def r100(value: float) -> int:
    """Estimates are rounded to the hundred euros."""
    return int(round(value / 100) * 100)


def fr_eur(value: float) -> str:
    return f"{fr_int(value)} €"


def fr_pct(share: float) -> str:
    return f"{round(share * 100)} %"


def pretty_street(address: str) -> str:
    """'43 RUE BRULE MAISON' -> '43 Rue Brule Maison'; mixed-case input is kept."""
    if not address or address != address.upper():
        return address

    def word(w: str, first: bool) -> str:
        low = w.lower()
        if not first and low in SMALL_WORDS:
            return low
        # Elided article stays lowercase: de l'eglise -> de l'Eglise
        prefix = ""
        if not first and re.match(r"^[ld]['’]", low):
            prefix, low = low[:2], low[2:]
        return prefix + re.sub(r"(^|['’-])(\w)", lambda m: m.group(1) + m.group(2).upper(), low)

    return " ".join(word(w, i == 0) for i, w in enumerate(address.split()))


def display_address(address: str, postcode: Optional[str], city: Optional[str]) -> Dict[str, str]:
    street = pretty_street((address or "").strip()) or "Adresse non renseignée"
    locality = " ".join(x for x in [postcode or "", (city or "").strip()] if x)
    # The ADEME raw address sometimes already contains the postcode and city
    if postcode and postcode in street:
        locality = ""
    return {"street": street, "locality": locality, "full": f"{street}, {locality}" if locality else street}


def date_fr(d: Optional[date]) -> Optional[str]:
    return d.strftime("%d/%m/%Y") if d else None


def parse_date(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


# --- Sections ---

def usage_breakdown(sim_input: SimulationInput, works: List[str]) -> List[Dict[str, Any]]:
    """Final energy and bill per usage, before and after the works."""
    prop = sim_input.property
    balance = projected_performance(prop, works)["balance"]
    rows = []
    for usage in ("heating", "hot_water", "other"):
        kwh_before, energy_before = balance["before"][usage]
        kwh_after, energy_after = balance["after"][usage]
        rows.append({
            "usage": usage,
            "name": USAGE_NAMES[usage],
            "kwh_before": kwh_before * prop.surface,
            "kwh_after": kwh_after * prop.surface,
            "eur_before": kwh_before * prop.surface * ENERGY_PRICES_EUR_KWH[energy_before],
            "eur_after": kwh_after * prop.surface * ENERGY_PRICES_EUR_KWH[energy_after],
            "energy_before": ENERGY_NAMES[energy_before],
            "energy_after": ENERGY_NAMES[energy_after],
        })
    return rows


def hot_water_share(prop, env, energy: str) -> float:
    heating, hot_water, other = usage_split(prop, env, energy)
    total = heating + hot_water + other
    return hot_water / total if total else env.hot_water_share


def work_reason(work_id: str, ctx: Dict[str, Any]) -> str:
    """Why this work makes sense for this dwelling, from its own data."""
    shares = ctx["loss_shares"]
    qualities = ctx["qualities"]
    energy = ctx["energy"]
    element = QUALITY_ELEMENT.get(work_id)
    quality = (qualities.get(element) or "").lower() if element else ""
    quality_text = f" ; le DPE juge leur isolation « {quality} »" if quality else ""
    if work_id == "iti":
        return f"Les murs représentent {fr_pct(shares['walls'])} des pertes de chaleur{quality_text}."
    if work_id == "ite":
        return (f"Les murs représentent {fr_pct(shares['walls'])} des pertes de chaleur{quality_text}, et les ponts "
                f"thermiques {fr_pct(shares['bridges'])} : l'isolation par l'extérieur traite les deux.")
    if work_id == "roof":
        return f"La toiture représente {fr_pct(shares['roof'])} des pertes de chaleur{quality_text.replace('leur', 'son')}."
    if work_id == "floor_ceiling":
        return f"Le plancher bas représente {fr_pct(shares['floor'])} des pertes de chaleur{quality_text.replace('leur', 'son')}."
    if work_id == "windows":
        return (f"Les fenêtres représentent {fr_pct(shares['windows'])} des pertes de chaleur "
                f"(environ {ctx['window_count']} fenêtres){quality_text}.")
    if work_id == "vmc":
        return (f"Le renouvellement d'air pèse {fr_pct(shares['air'])} des pertes. Une ventilation contrôlée évite "
                "l'humidité et les moisissures une fois le logement isolé.")
    if work_id == "pac_air_eau":
        if energy in ("gas", "oil"):
            return (f"Remplace le chauffage au {ENERGY_NAMES[energy]} : pour la même chaleur, la pompe à chaleur "
                    f"consomme environ {fr_dec(HEATING_SYSTEMS['pac_air_eau']['efficiency'])} fois moins d'énergie.")
        return (f"Remplace la chaudière électrique : pour la même chaleur, la pompe à chaleur consomme environ "
                f"{fr_dec(HEATING_SYSTEMS['pac_air_eau']['efficiency'])} fois moins d'électricité.")
    if work_id == "heating":
        if energy in ("gas", "oil"):
            return (f"Le chauffage au {ENERGY_NAMES[energy]} fait l'essentiel des émissions de CO₂ du logement : des radiateurs "
                    "électriques à inertie améliorent son étiquette climat.")
        return ("Le logement est chauffé par des convecteurs électriques : des radiateurs à inertie bien régulés consomment "
                "environ 10 % de moins.")
    if work_id == "ecs":
        return (f"L'eau chaude représente {fr_pct(ctx['hot_water_share'])} de la consommation : un chauffe-eau "
                f"thermodynamique la divise par environ {fr_dec(HEAT_PUMP_WATER_HEATER_COP)}.")
    return ""


def tech_spec(work_id: str, ctx: Dict[str, Any]) -> Optional[str]:
    """How the work is to be done: materials, thicknesses and the performance
    the aids require (RGE, CEE fiches, MaPrimeRénov')."""
    if work_id == "iti":
        return ("Doublage isolant de 12 à 14 cm (laine minérale ou fibre de bois, λ ≤ 0,035) avec membrane pare-vapeur, "
                "résistance thermique R ≥ 3,7 m².K/W exigée pour les aides.")
    if work_id == "ite":
        return ("Isolant de 14 à 16 cm (polystyrène graphité ou fibre de bois) sous enduit ou bardage ventilé, "
                "R ≥ 3,7 m².K/W exigée pour les aides ; retours d'isolant en tableaux de fenêtres et en soubassement.")
    if work_id == "roof":
        return ("Combles perdus : 30 à 35 cm de laine soufflée, R ≥ 7 ; rampants ou toiture : 20 à 24 cm, R ≥ 6 "
                "(valeurs exigées pour les aides), avec pare-vapeur côté chauffé.")
    if work_id == "floor_ceiling":
        return "Panneaux isolants de 10 à 12 cm fixés en sous-face (polystyrène, polyuréthane ou laine minérale), R ≥ 3 m².K/W."
    if work_id == "windows":
        return ("Double vitrage à isolation renforcée avec gaz argon : Uw ≤ 1,3 W/m².K et Sw ≥ 0,3 (ou Uw ≤ 1,7 et Sw ≥ 0,36), "
                "menuiseries PVC, bois ou aluminium à rupture de pont thermique, pose en rénovation ou en dépose totale.")
    if work_id == "vmc":
        return "VMC simple flux hygroréglable type B ; double flux si le logement est rendu étanche à l'air."
    if work_id == "pac_air_eau":
        power = ctx.get("heat_pump_kw")
        sizing = (f"puissance indicative d'environ {power - 1} à {power + 1} kW après isolation, à confirmer par l'étude "
                  "de l'installateur" if power else "puissance à calculer après isolation par l'installateur")
        return ("Pompe à chaleur air/eau basse ou moyenne température, efficacité saisonnière ETAS ≥ 126 % (basse "
                f"température) ou ≥ 111 % (moyenne et haute) ; {sizing}.")
    if work_id == "ecs":
        return "Chauffe-eau thermodynamique de 200 à 270 L, COP ≥ 2,5 (norme EN 16147), sur air extérieur ou air d'un local non chauffé."
    if work_id == "heating":
        return ("Radiateurs à inertie (fonte, pierre ou fluide) avec programmation et détection d'ouverture de fenêtre, "
                "label NF Électricité Performance 3 étoiles.")
    return None


# Equivalent full-load hours of a heat pump in the north of France
FULL_LOAD_HOURS = 2000

QUALITY_NAMES = {"walls": "Isolation des murs", "roof": "Isolation de la toiture", "floor": "Isolation du plancher bas",
                 "windows": "Fenêtres"}


def insulation_state(prop) -> List[Dict[str, str]]:
    """Insulation of each wall as judged by the DPE."""
    q = prop.insulation_quality or {}
    return [{"label": QUALITY_NAMES[k], "value": f"{q[k][:1].upper()}{q[k][1:]} (selon le DPE)"}
            for k in ("walls", "roof", "floor", "windows") if q.get(k)]


def heat_pump_kw(prop, env, energy: str, works: List[str]) -> Optional[int]:
    """Rough heat pump power: the heat need after insulation spread over the
    equivalent full-load hours of a northern French winter."""
    if "pac_air_eau" not in works:
        return None
    heating, _, _ = usage_split(prop, env, energy)
    insulation = [w for w in works if w in ("iti", "ite", "roof", "floor_ceiling", "windows", "vmc")]
    need = heating * prop.surface * CURRENT_HEATING_EFFICIENCY.get(energy, 0.85) * (1 - env.heating_reduction(insulation))
    kw = round(need / FULL_LOAD_HOURS)
    return max(3, kw) if kw else None


def work_caution(work_id: str, ctx: Dict[str, Any]) -> Optional[str]:
    if work_id == "iti":
        return f"Surface habitable réduite d'environ {fr_dec(ctx['iti_surface_loss'])} m²."
    if work_id == "ite":
        return ("Déclaration préalable de travaux en mairie (aspect des façades, règles du PLU) ; prévoir les appuis de "
                "fenêtres, descentes d'eau et débords de toit.")
    if work_id == "pac_air_eau":
        return ("Vérifier que les radiateurs à eau supportent une eau moins chaude, et dimensionner la pompe à chaleur "
                "après l'isolation.")
    if work_id == "windows":
        return "Prévoir des entrées d'air : des fenêtres étanches sans ventilation favorisent la condensation."
    if work_id == "vmc":
        return "Le passage des gaines se prévoit avant les finitions de l'isolation."
    if work_id == "heating" and ctx["energy"] in ("gas", "oil"):
        return (f"La facture de chauffage augmente : le kWh d'électricité coûte plus cher que le {ENERGY_NAMES[ctx['energy']]}. "
                "À retenir surtout si l'étiquette compte (location, vente).")
    if work_id == "ecs":
        if ctx["house"]:
            return "Prévoir un emplacement de préférence non chauffé (garage, cellier) ou une gaine vers l'extérieur."
        return ("Il faut un local d'au moins 20 m³ ou une gaine vers l'extérieur ; une sortie en façade demande l'accord "
                "de la copropriété.")
    return None


def dpe_validity(dpe_date: Optional[date], today: Optional[date] = None) -> Optional[str]:
    """Validity of the DPE: 10 years since July 2021; the older ones have all expired."""
    if not dpe_date:
        return None
    today = today or date.today()
    if dpe_date < date(2021, 7, 1):
        return "Périmé : un nouveau DPE est nécessaire pour vendre ou louer"
    try:
        end = dpe_date.replace(year=dpe_date.year + 10)
    except ValueError:  # 29 February
        end = dpe_date.replace(year=dpe_date.year + 10, day=28)
    if end < today:
        return f"Expiré depuis le {date_fr(end)} : un nouveau DPE est nécessaire pour vendre ou louer"
    return f"Jusqu'au {date_fr(end)}"


def regulatory(sim: Dict[str, Any], house: bool, dpe_date: Optional[date], postcode: Optional[str],
               is_investor: bool = False, building_type: Optional[str] = None) -> Dict[str, Any]:
    current = sim["current_label"]
    # An owner-occupier is only concerned if they let the dwelling one day
    items = [
        {"label": "Location aujourd'hui" if is_investor else "Si vous mettez en location", "value": sim["rental_status"]},
        {"label": "Location après travaux", "value": sim["new_rental_status"]},
    ]
    if current in ("F", "G") and is_investor:
        items.append({"label": "Loyer", "value": "Gelé : aucune hausse possible (révision, relocation, renouvellement) tant que le logement reste classé F ou G"})
    # Sale audit: houses and buildings with a single owner, not flats in a copropriété
    if house or "immeuble" in (building_type or "").lower():
        if current in ("F", "G", "E"):
            items.append({"label": "Vente", "value": "Audit énergétique obligatoire, à remettre dès la première visite"})
        elif current == "D":
            items.append({"label": "Vente", "value": "Audit énergétique obligatoire à partir du 01/01/2034"})
    validity = dpe_validity(dpe_date)
    if validity:
        items.append({"label": "Validité du DPE", "value": validity})
    overseas = bool(postcode) and postcode.startswith("97")
    calendar = ([("G", "01/01/2028"), ("F", "01/01/2031")] if overseas else
                [("G", "01/01/2025"), ("F", "01/01/2028"), ("E", "01/01/2034")])
    return {"items": items, "calendar": calendar}


def next_steps(sim: Dict[str, Any], is_investor: bool) -> List[Dict[str, str]]:
    ampleur = sim["aid_pathway"] == "accompagne"
    steps = [{
        "title": "Rendez-vous France Rénov'",
        "when": "Semaines 1 à 2",
        "text": ("Gratuit, sur france-renov.gouv.fr ou au 0 808 800 700. "
                 + ("Obligatoire avant tout dépôt de rénovation d'ampleur." if ampleur
                    else "Il confirme les aides auxquelles vous avez droit." if sim["aid_pathway"] != "none"
                    else "Il vérifie aussi les aides locales (région, département, commune).")),
    }]
    if ampleur:
        steps.append({
            "title": "Accompagnateur Rénov' et audit",
            "when": "Semaines 2 à 6",
            "text": "L'Accompagnateur Rénov' est obligatoire : il réalise ou commande l'audit énergétique et construit le "
                    "programme de travaux définitif. Son coût est en partie pris en charge.",
        })
    steps.append({
        "title": "Devis d'artisans RGE",
        "when": "Semaines 3 à 8",
        "text": "Au moins deux devis par lot. "
                + ({"accompagne": "La certification RGE conditionne MaPrimeRénov'. ",
                    "geste": "La certification RGE conditionne " + ("MaPrimeRénov' et les primes CEE. " if sim["subsidies"] > 0 and sim["cee_est"] > 0
                                                                     else "MaPrimeRénov'. " if sim["subsidies"] > 0 else "les primes CEE. "),
                    "none": ""}[sim["aid_pathway"]])
                + "Comparez les fourchettes de ce rapport aux devis reçus.",
    })
    if sim["cee_est"] > 0:
        steps.append({
            "title": "Primes CEE",
            "when": "Avant de signer",
            "text": "Acceptez l'offre de prime d'un fournisseur d'énergie avant de signer les devis : une prime demandée après la signature est refusée.",
        })
    if sim["subsidies"] > 0:
        steps.append({
            "title": "Dépôt MaPrimeRénov'",
            "when": "Avant le début des travaux",
            "text": "Sur maprimerenov.gouv.fr, avec les devis. Ne commencez pas les travaux avant l'accusé de réception du dossier.",
        })
    if sim["eco_ptz_amount"] > 0:
        steps.append({
            "title": "Éco-prêt à taux zéro",
            "when": "En parallèle du dépôt" if sim["subsidies"] > 0 else "Avec les devis",
            "text": f"À demander à une banque partenaire avec les devis : environ {fr_eur(r100(sim['eco_ptz_amount']))} sans intérêts.",
        })
    steps.append({
        "title": "Travaux",
        "when": f"Environ {sim['duration_days']} jours ouvrés de chantier" if sim.get("duration_days") else "Selon le planning des artisans",
        "text": "Dans l'ordre conseillé ci-dessus. Gardez toutes les factures : elles déclenchent le versement des aides.",
    })
    if is_investor:
        steps.append({
            "title": "Nouveau DPE",
            "when": "Après les travaux",
            "text": "Faites réaliser un nouveau DPE : c'est lui qui fixe la nouvelle classe opposable à vos locataires et sur les annonces.",
        })
    return steps


def green_value_assumption(sim: Dict[str, Any], sim_input: SimulationInput, price_m2: float, price_is_default: bool) -> str:
    price = (f"{fr_int(price_m2)} €/m², valeur par défaut faute de ventes connues à proximité" if price_is_default
             else f"{fr_int(price_m2)} €/m², {sim_input.property.price_source}" if sim_input.property.price_source
             else f"{fr_int(price_m2)} €/m², prix saisi")
    if sim["green_value_method"] in ("department", "national"):
        return (f"Valeur verte : {sim['green_value_basis']} ; appliquée au prix local ({price}). "
                "Fourchette : de la moitié du bas de l'intervalle de confiance à 95 % de l'écart à la totalité de son haut.")
    if sim["green_value_method"] == "flat":
        return f"Valeur verte : {sim['green_value_basis']}, appliquée au prix local ({price})."
    return f"Prix local retenu : {price}."


def assumptions(sim: Dict[str, Any], sim_input: SimulationInput, price_per_m2_used: float, price_is_default: bool) -> List[str]:
    energy = sim["heating_energy"]
    prices = ", ".join(f"{ENERGY_NAMES[e]} {fr_dec(p, 2)} €" for e, p in ENERGY_PRICES_EUR_KWH.items()
                       if e in (energy, "electricity"))
    out = [
        "Point de départ : les consommations du DPE officiel (base ADEME), réparties entre chauffage, eau chaude et autres usages selon l'époque du logement.",
        "Effet de l'isolation calculé à partir des pertes de chaleur propres au logement (par paroi), et non d'un pourcentage forfaitaire.",
        f"Prix de l'énergie retenus (par kWh, hors abonnement) : {prices}.",
        "Coûts : prix moyens de marché actualisés (indice BT01), ajustés à la surface, à la région et à l'accès au chantier. "
        "Fourchette basse et haute selon la variabilité habituelle des devis.",
        f"Aides : {sim['aid_rules']}, catégorie de revenus « {sim['income_profile']} »."
        + (" Primes CEE : valeurs de marché indicatives." if sim["cee_est"] > 0 else ""),
        green_value_assumption(sim, sim_input, price_per_m2_used, price_is_default),
    ]
    if "pac_air_eau" in sim_input.works:
        out.insert(3, "Pompe à chaleur : rendement saisonnier prudent de 2,9 en logement existant.")
    if sim_input.is_investor:
        out.append("Rentabilité : loyer et prix d'achat saisis ; trésorerie hors charges, taxe foncière et impôt sur les loyers.")
    return out


def build_report(meta: Dict[str, Any], sim_input: SimulationInput) -> Dict[str, Any]:
    sim = simulate(sim_input)
    prop = sim_input.property
    house = is_house(prop.building_type)
    perf = projected_performance(prop, [])
    env = perf["envelope"]
    energy = sim["heating_energy"]
    works = [d for d in sim["detailed_costs"] if d["id"] in WORKS_BY_ID]
    work_ids = [d["id"] for d in works]
    effects = single_work_effects(sim_input)
    loss_shares = sim["loss_shares"]
    ctx = {
        "loss_shares": loss_shares,
        "qualities": {k: v for k, v in (prop.insulation_quality or {}).items()},
        "energy": energy,
        "window_count": env.window_count,
        "hot_water_share": hot_water_share(prop, env, energy),
        "house": house,
        # A 12-13 cm lining along the insulated walls
        "iti_surface_loss": env.wall_area / FLOOR_HEIGHT * 0.13,
        "heat_pump_kw": heat_pump_kw(prop, env, energy, list(sim_input.works)),
    }

    ordered = sorted(works, key=lambda d: WORK_ORDER.index(d["id"]) if d["id"] in WORK_ORDER else 99)
    per_work_aids = sim.get("aid_per_work") or {}
    work_rows = []
    for d in ordered:
        e = effects.get(d["id"], {})
        aid = per_work_aids.get(d["id"], {})
        work_rows.append({
            "id": d["id"],
            "name": d["name"],
            "suggested": d["suggested"],
            "cost": d["cost"],
            "cost_low": d["cost_low"],
            "cost_high": d["cost_high"],
            "days": d["days"],
            "reason": work_reason(d["id"], ctx),
            "caution": work_caution(d["id"], ctx),
            "spec": tech_spec(d["id"], ctx),
            "cep_saved": e.get("cep_saved", 0.0),
            "bill_saving": e.get("bill_saving", 0.0),
            "aid": (aid.get("mpr", 0.0) + aid.get("cee", 0.0)) if aid else None,
        })
    extra_costs = [d for d in sim["detailed_costs"] if d["id"] not in WORKS_BY_ID]

    details = meta.get("details") or {}
    postcode = meta.get("postcode") or prop.postcode
    address = display_address(meta.get("address") or "", postcode, meta.get("city"))
    dpe_date = parse_date(meta.get("dpe_date"))
    price_per_m2 = prop.price_per_m2 or DEFAULT_PRICE_PER_M2
    monthly_saving = sim["annual_savings"] / 12
    losses_sorted = sorted(((k, v) for k, v in loss_shares.items()), key=lambda kv: -kv[1])

    return {
        "address": address,
        "identity": {
            "building_type": (prop.building_type or "Logement").capitalize(),
            "surface": prop.surface,
            "period": meta.get("construction_period") or (str(meta.get("year")) if meta.get("year") else None),
            "dpe_number": meta.get("ademe_dpe_number"),
            "dpe_date": date_fr(dpe_date),
            # The DPE gives a floor for houses too (0): meaningless, and it
            # led the text to call any house "de plain-pied"
            "floor": None if house else details.get("floor"),
            "heating": " · ".join(x for x in [ENERGY_NAMES.get(energy, "").capitalize(), details.get("heating_system"),
                                                details.get("heating_installation")] if x) or None,
            "hot_water": details.get("hot_water_system"),
            "ventilation": details.get("ventilation"),
            "dpe_annual_cost": details.get("dpe_annual_cost"),
            "house": house,
        },
        "sim": sim,
        "is_investor": sim_input.is_investor,
        "purchase_price": sim_input.purchase_price,
        "monthly_rent": sim_input.monthly_rent,
        "losses": [{"key": k, "name": LOSS_NAMES[k], "share": v} for k, v in losses_sorted],
        "usages": usage_breakdown(sim_input, work_ids),
        "works": work_rows,
        "extra_costs": extra_costs,
        "regulatory": regulatory(sim, house, dpe_date, postcode, sim_input.is_investor, prop.building_type),
        "financing": {
            "monthly_saving": monthly_saving,
            "eco_ptz_monthly": sim["eco_ptz_monthly"],
            "eco_ptz_years": round(sim["eco_ptz_months"] / 12) if sim["eco_ptz_months"] else 0,
            "net_monthly_effort": sim["eco_ptz_monthly"] - monthly_saving if sim["eco_ptz_amount"] else None,
            "ampleur_possible_label": sim["current_label"] in AMPLEUR_LABELS,
        },
        "ampleur_variant": ampleur_variant(sim_input, sim),
        "wall_alternative": wall_alternative(sim_input, sim),
        "insulation_state": insulation_state(prop),
        "steps": next_steps(sim, sim_input.is_investor),
        "assumptions": assumptions(sim, sim_input, price_per_m2, not prop.price_per_m2),
        "price_per_m2": price_per_m2,
        "price_is_default": not prop.price_per_m2,
        "price_source": prop.price_source,
    }


def pathway_label(sim: Dict[str, Any]) -> str:
    """The aids actually counted, named as such."""
    if sim["aid_pathway"] == "accompagne":
        return "MaPrimeRénov' rénovation d'ampleur"
    mpr, cee = sim["subsidies"] > 0, sim["cee_est"] > 0
    if mpr and cee:
        return "MaPrimeRénov' par geste et primes CEE"
    if mpr:
        return "MaPrimeRénov' par geste"
    if cee:
        return "primes CEE"
    return "aucune aide"


def variant_facts(v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not v:
        return None
    return {
        "travail_ajoute": v["work_phrase"],
        "cout_du_travail_ajoute_fourchette_eur": [r100(v["work_cost_low"]), r100(v["work_cost_high"])],
        "parcours_aide": "MaPrimeRénov' rénovation d'ampleur",
        "maprimerenov_eur": r100(v["subsidies"]),
        "reste_a_charge_fourchette_eur": [r100(v["rest_to_pay_low"]), r100(v["rest_to_pay_high"])],
        "reste_a_charge_en_moins_eur": r100(v["saving_vs_programme"]),
        "classe_dpe_apres": v["new_label"],
        "economies_eur_an": int(round(v["annual_savings"], -1)),
        "a_verifier_sur_place": v.get("check"),
        "condition": "Accompagnement obligatoire par un Accompagnateur Rénov' et audit énergétique confirmant le gain de classes.",
    }


def facts_for_writer(report: Dict[str, Any]) -> Dict[str, Any]:
    """The data the writer is allowed to use (no email, no street address)."""
    sim = report["sim"]
    ident = report["identity"]
    fin = report["financing"]
    return {
        "logement": {
            "type": ident["building_type"],
            "surface_m2": round(ident["surface"], 1),
            "epoque_construction": ident["period"],
            "commune": report["address"]["locality"] or None,
            "etage": ident["floor"],
            "chauffage": ident["heating"],
            "eau_chaude": ident["hot_water"],
            "ventilation": ident["ventilation"],
            "date_dpe": ident["dpe_date"],
        },
        "etat_actuel": {
            "classe_dpe": sim["current_label"],
            "classe_energie": sim["current_cep_label"],
            "classe_climat": sim["current_ges_label"],
            "consommation_kwh_ep_m2_an": round(sim["initial_cep"]),
            "emissions_kg_co2_m2_an": round(sim["initial_ges"]),
            "facture_estimee_eur_an": int(round(sim["annual_bill_before"], -1)),
            "repartition_pertes_chaleur": {l["name"]: fr_pct(l["share"]) for l in report["losses"]},
            "factures_par_usage_eur_an": {u["name"]: int(round(u["eur_before"], -1)) for u in report["usages"]},
        },
        "travaux": [{
            "nom": w["name"],
            "recommande": w["suggested"],
            "fourchette_cout_eur": [r100(w["cost_low"]), r100(w["cost_high"])],
            "pourquoi": w["reason"],
            "point_de_vigilance": w["caution"],
            "preconisation_technique": w.get("spec"),
            "effet_seul_kwh_ep_m2_an": round(w["cep_saved"]),
            "economie_seule_eur_an": int(round(w["bill_saving"], -1)),
        } for w in report["works"]],
        "apres_travaux": {
            "classe_dpe": sim["new_label"],
            "consommation_kwh_ep_m2_an": round(sim["new_cep"]),
            "gain_classes": sim["gain_classes"],
            "facture_estimee_eur_an": int(round(sim["annual_bill_after"], -1)),
            "economies_eur_an": int(round(sim["annual_savings"], -1)),
            "duree_chantier_jours_ouvres": sim["duration_days"],
        },
        "financement": {
            "cout_total_fourchette_eur": [r100(sim["cost_low"]), r100(sim["cost_high"])],
            "parcours_aide": pathway_label(sim),
            "maprimerenov_eur": r100(sim["subsidies"]),
            "primes_cee_eur": r100(sim["cee_est"]),
            "reste_a_charge_fourchette_eur": [r100(sim["rest_to_pay_low"]), r100(sim["rest_to_pay_high"])],
            # Same condition as the PDF: only for dwellings rated E, F or G
            "pourquoi_pas_la_renovation_d_ampleur": (sim["aid_blockers"] or None) if sim["current_label"] in AMPLEUR_LABELS else None,
            "categorie_revenus": sim["income_profile"],
            "eco_ptz_eur": r100(sim["eco_ptz_amount"]) or None,
            "eco_ptz_mensualite_eur": round(fin["eco_ptz_monthly"]) or None,
            "eco_ptz_duree_ans": fin["eco_ptz_years"] or None,
            "economie_mensuelle_eur": round(fin["monthly_saving"]),
            "retour_sur_investissement_ans": round(sim["roi_years"]) if sim["roi_years"] is not None else None,
            "regles_aides": sim["aid_rules"],
        },
        "variante_renovation_d_ampleur": variant_facts(report.get("ampleur_variant")),
        "autre_solution_murs": {
            "travail": report["wall_alternative"]["work_name"],
            "reste_a_charge_fourchette_eur": [r100(report["wall_alternative"]["rest_to_pay_low"]), r100(report["wall_alternative"]["rest_to_pay_high"])],
            "ecart_reste_a_charge_eur": r100(report["wall_alternative"]["rest_difference"]),
            "classe_dpe_apres": report["wall_alternative"]["new_label"],
        } if report.get("wall_alternative") else None,
        "etat_isolation_selon_dpe": {i["label"]: i["value"] for i in report.get("insulation_state") or []} or None,
        "reglementation": {i["label"]: i["value"] for i in report["regulatory"]["items"]},
        # Rounded to 500 € like the PDF, so that the text quotes the same figures
        "valeur_verte_eur": round500(sim["latent_gain"]),
        "valeur_verte_fourchette_eur": [round500(sim["latent_gain_low"]), round500(sim["latent_gain_high"])],
        "valeur_verte_methode": sim["green_value_basis"],
        "ecart_de_prix_entre_classes_pct": sim["green_value_premium_pct"],
        "valeur_verte_calculee_sur_prix_m2_par_defaut": report["price_is_default"],
        "prix_m2_local": {"eur_m2": round(report["price_per_m2"]), "source": report["price_source"]} if not report["price_is_default"] else None,
        "profil": "bailleur investisseur" if report["is_investor"] else "propriétaire occupant",
        "investisseur": {
            "prix_achat_eur": round(report["purchase_price"]),
            "loyer_mensuel_eur": round(report["monthly_rent"]),
            "rendement_brut_pct": round(sim["yield_brut"], 1),
            "tresorerie_mensuelle_eur": round(sim["cashflow"]),
            "economie_impot_eur": round(sim["tax_benefit"]),
        } if report["is_investor"] else None,
    }
