"""Content of the paid report: every figure and every factual sentence is
computed here from the simulation, so the report stays specific to the
dwelling whether or not the written analysis (api/ai_service.py) is available.
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional

try:
    from api.aids import AMPLEUR_LABELS
    from api.simulation import (DEFAULT_PRICE_PER_M2, ampleur_variant, ENERGY_PRICES_EUR_KWH,
                                HEATING_SYSTEMS, HEAT_PUMP_WATER_HEATER_COP,
                                SimulationInput, WORKS_BY_ID, is_house, projected_performance,
                                simulate, single_work_effects)
except ImportError:
    from aids import AMPLEUR_LABELS
    from simulation import (DEFAULT_PRICE_PER_M2, ampleur_variant, ENERGY_PRICES_EUR_KWH,
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

QUALITY_ELEMENT = {"iti": "walls", "roof": "roof", "floor_ceiling": "floor", "windows": "windows"}

# Works order on site: envelope first, then ventilation, then systems
WORK_ORDER = ["roof", "iti", "floor_ceiling", "windows", "vmc", "pac_air_eau", "heating", "ecs"]

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
        return "Remplace le système de chauffage actuel par une production de chaleur trois fois plus efficace."
    if work_id == "heating":
        return ("Le logement est chauffé à l'électricité : des radiateurs à inertie bien régulés consomment environ "
                "10 % de moins que d'anciens convecteurs.")
    if work_id == "ecs":
        return (f"L'eau chaude représente {fr_pct(ctx['hot_water_share'])} de la consommation : un chauffe-eau "
                f"thermodynamique la divise par environ {fr_dec(HEAT_PUMP_WATER_HEATER_COP)}.")
    return ""


def work_caution(work_id: str, ctx: Dict[str, Any]) -> Optional[str]:
    if work_id == "iti":
        return f"Surface habitable réduite d'environ {fr_dec(ctx['iti_surface_loss'])} m²."
    if work_id == "pac_air_eau":
        return ("Vérifier que les radiateurs à eau supportent une eau moins chaude, et dimensionner la pompe à chaleur "
                "après l'isolation.")
    if work_id == "windows":
        return "Prévoir des entrées d'air : des fenêtres étanches sans ventilation favorisent la condensation."
    if work_id == "vmc":
        return "Le passage des gaines se prévoit avant les finitions de l'isolation."
    return None


def regulatory(sim: Dict[str, Any], house: bool, dpe_date: Optional[date], postcode: Optional[str]) -> Dict[str, Any]:
    current = sim["current_label"]
    items = [
        {"label": "Location aujourd'hui", "value": sim["rental_status"]},
        {"label": "Location après travaux", "value": sim["new_rental_status"]},
    ]
    if current in ("F", "G"):
        items.append({"label": "Loyer", "value": "Gelé : aucune hausse possible (révision, relocation, renouvellement) tant que le logement reste classé F ou G"})
    if house:
        if current in ("F", "G", "E"):
            items.append({"label": "Vente", "value": "Audit énergétique obligatoire, à remettre dès la première visite"})
        elif current == "D":
            items.append({"label": "Vente", "value": "Audit énergétique obligatoire à partir du 01/01/2034"})
    if dpe_date and dpe_date >= date(2021, 7, 1):
        validity = date(dpe_date.year + 10, dpe_date.month, min(dpe_date.day, 28))
        items.append({"label": "Validité du DPE", "value": f"Jusqu'au {date_fr(validity)}"})
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
                 + ("Obligatoire avant tout dépôt de rénovation d'ampleur." if ampleur else "Il confirme les aides auxquelles vous avez droit.")),
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
        "text": "Au moins deux devis par lot. La certification RGE conditionne MaPrimeRénov' et les primes CEE. "
                "Comparez les fourchettes de ce rapport aux devis reçus.",
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
            "when": "En parallèle du dépôt",
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
        "Pompe à chaleur : rendement saisonnier prudent de 2,9 en logement existant.",
        "Coûts : prix moyens de marché actualisés (indice BT01), ajustés à la surface, à la région et à l'accès au chantier. "
        "Fourchette basse et haute selon la variabilité habituelle des devis.",
        f"Aides : {sim['aid_rules']}, catégorie de revenus « {sim['income_profile']} ». Primes CEE : valeurs de marché indicatives.",
        green_value_assumption(sim, sim_input, price_per_m2_used, price_is_default),
    ]
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
        "hot_water_share": env.hot_water_share,
        "iti_surface_loss": prop.surface * 0.015,
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
            "floor": details.get("floor"),
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
        "regulatory": regulatory(sim, house, dpe_date, postcode),
        "financing": {
            "monthly_saving": monthly_saving,
            "eco_ptz_monthly": sim["eco_ptz_monthly"],
            "eco_ptz_years": round(sim["eco_ptz_months"] / 12) if sim["eco_ptz_months"] else 0,
            "net_monthly_effort": sim["eco_ptz_monthly"] - monthly_saving if sim["eco_ptz_amount"] else None,
            "ampleur_possible_label": sim["current_label"] in AMPLEUR_LABELS,
        },
        "ampleur_variant": ampleur_variant(sim_input, sim),
        "steps": next_steps(sim, sim_input.is_investor),
        "assumptions": assumptions(sim, sim_input, price_per_m2, not prop.price_per_m2),
        "price_per_m2": price_per_m2,
        "price_is_default": not prop.price_per_m2,
        "price_source": prop.price_source,
    }


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
            "parcours_aide": {"accompagne": "MaPrimeRénov' rénovation d'ampleur", "geste": "MaPrimeRénov' par geste et primes CEE",
                              "none": "aucune aide"}[sim["aid_pathway"]],
            "maprimerenov_eur": r100(sim["subsidies"]),
            "primes_cee_eur": r100(sim["cee_est"]),
            "reste_a_charge_fourchette_eur": [r100(sim["rest_to_pay_low"]), r100(sim["rest_to_pay_high"])],
            "pourquoi_pas_la_renovation_d_ampleur": sim["aid_blockers"] or None,
            "categorie_revenus": sim["income_profile"],
            "eco_ptz_eur": r100(sim["eco_ptz_amount"]),
            "eco_ptz_mensualite_eur": round(fin["eco_ptz_monthly"]),
            "eco_ptz_duree_ans": fin["eco_ptz_years"],
            "economie_mensuelle_eur": round(fin["monthly_saving"]),
            "retour_sur_investissement_ans": round(sim["roi_years"]) if sim["roi_years"] is not None else None,
            "regles_aides": sim["aid_rules"],
        },
        "variante_renovation_d_ampleur": variant_facts(report.get("ampleur_variant")),
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
