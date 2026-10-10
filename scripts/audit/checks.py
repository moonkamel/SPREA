"""Deep checks of one dwelling's report, from the defects found on real reports
(Dainville, Lille rue Sainte-Catherine, Façade de l'Esplanade...): every
figure of the report against the others, works against the dwelling's own
equipment, regulatory dates, and the PDF text itself.

The checks read the DPE fields directly rather than through the app's helpers,
so that a helper's bug is not checked against itself.
"""
import io
import re
from datetime import date
from typing import Any, Dict, List, Optional

from api.report_content import AMPLEUR_LABELS
from api.simulation import SimulationInput, simulate

LABELS = "ABCDEFG"
ENVELOPE_SHARE = {"iti": "walls", "ite": "walls", "roof": "roof", "floor_ceiling": "floor", "windows": "windows"}
QUALITY_KEY = {"iti": "walls", "ite": "walls", "roof": "roof", "floor_ceiling": "floor", "windows": "windows"}
HEATING_WORKS = {"pac_air_eau", "heating"}


def idx(label: Optional[str]) -> int:
    return LABELS.index(label) if label in LABELS else -1


def close(a: float, b: float, rel: float = 0.02, absolute: float = 20) -> bool:
    return abs(a - b) <= max(absolute, rel * max(abs(a), abs(b)))


def pdf_text(pdf: bytes) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def equipment_checks(case, sp, works: List[str], suggested: List[str]) -> None:
    gen = (sp.heating_generator or "").lower()
    hw = (sp.hot_water_system or "").lower()
    vent = (sp.ventilation or "").lower()
    proposed = set(works) | set(suggested)
    if "pac " in gen + " " or "pompe à chaleur" in gen:
        case.check(not HEATING_WORKS & proposed, f"chauffage proposé alors qu'une PAC existe ({sp.heating_generator})")
    if "thermodynamique" in hw:
        case.check("ecs" not in proposed, f"chauffe-eau thermodynamique proposé alors qu'il existe ({sp.hot_water_system})")
    if ("hygro" in vent and "vmc" in vent) or "double flux" in vent:
        case.check("vmc" not in proposed, f"VMC proposée alors qu'elle existe ({sp.ventilation})")
    if any(k in gen for k in ("convecteur", "rayonnant", "radiateur électrique", "radiateur electrique")):
        case.check("pac_air_eau" not in proposed, f"PAC air/eau proposée sans circuit d'eau ({sp.heating_generator})")
    if "collecti" in (sp.heating_installation or "").lower():
        case.check(not HEATING_WORKS & proposed, "système de chauffage individuel proposé sur un chauffage collectif")
    if "collecti" in (sp.hot_water_installation or "").lower():
        case.check("ecs" not in proposed, "chauffe-eau individuel proposé sur une eau chaude collective")
    house = (sp.building_type or "").lower().startswith("maison")
    if not house:
        case.check("ite" not in works, "isolation par l'extérieur cochée pour un appartement")
    # Insulating a dwelling aired through its windows: ventilation comes with it
    if ("fenêtre" in vent or "fenetre" in vent) and {"iti", "ite", "roof", "floor_ceiling", "windows"} & set(works) \
            and "vmc" in suggested + works:
        case.check("vmc" in works, "isolation sans ventilation mécanique : VMC non cochée")
    u = sp.usage_consumption or {}
    if (u.get("heating") or 0) > 0 and not u.get("hot_water"):
        case.check("ecs" not in proposed, "chauffe-eau proposé alors que le DPE ne donne aucune consommation d'eau chaude")


def marginal_checks(case, sp, works: List[str], sim: Dict[str, Any]) -> None:
    """A default envelope work must matter: a real share of the losses, or
    pointed out by the DPE, or needed for the label."""
    shares = sim.get("loss_shares") or {}
    qualities = {k: (v or "").lower() for k, v in (sp.insulation_quality or {}).items()}
    for w in works:
        if w not in ENVELOPE_SHARE:
            continue
        share = shares.get(ENVELOPE_SHARE[w], 0)
        poor = qualities.get(QUALITY_KEY[w], "") in ("insuffisante", "très insuffisante")
        if share >= 0.06 or poor:
            continue
        without = simulate(SimulationInput(property=sp, works=[x for x in works if x != w]))
        case.check(idx(without["new_label"]) > idx(sim["new_label"]),
                   f"travail marginal coché par défaut : {w} ({share:.0%} des pertes, isolation non jugée insuffisante, sans effet sur la classe)")


def report_checks(case, sp, content: Dict[str, Any], market_value: Optional[float]) -> None:
    sim = content["sim"]
    works = content["works"]
    if works:
        all_costs = works + content.get("extra_costs", [])
        case.check(close(sum(w["cost"] for w in all_costs), sim["cost"], 0.01, 50),
                   f"somme des travaux {sum(w['cost'] for w in all_costs):.0f} ≠ coût {sim['cost']:.0f}")
        case.check(sim["cost_low"] <= sim["cost"] <= sim["cost_high"], "coût hors de sa fourchette")
        for w in works:
            case.check(w["cost_low"] <= w["cost"] <= w["cost_high"], f"{w['id']} : coût hors fourchette")
            case.check(w["bill_saving"] >= -1 and w["cep_saved"] >= -1, f"{w['id']} : effet seul négatif")
            case.check(bool(w.get("spec")), f"{w['id']} : pas de préconisation technique")
            case.check(bool(w.get("reason")), f"{w['id']} : pas de motif")
        aids = sim["subsidies"] + sim["cee_est"]
        case.check(close(sim["rest_to_pay"], max(0, sim["cost"] - aids), 0.01, 60),
                   f"reste à charge {sim['rest_to_pay']:.0f} ≠ coût {sim['cost']:.0f} − aides {aids:.0f}")
        case.check(sim["rest_to_pay_low"] <= sim["rest_to_pay"] <= sim["rest_to_pay_high"], "reste à charge hors fourchette")
        case.check(close(sim["annual_savings"], sim["annual_bill_before"] - sim["annual_bill_after"], 0.02, 15),
                   "économies ≠ facture avant − facture après")
        if sim["annual_savings"] > 50 and sim.get("roi_years"):
            case.check(close(sim["roi_years"], sim["rest_to_pay"] / sim["annual_savings"], 0.1, 0.6),
                       f"retour sur investissement {sim['roi_years']} ≠ reste {sim['rest_to_pay']:.0f} / économies {sim['annual_savings']:.0f}")
    # Bill per usage = total bill
    usages = content["usages"]
    case.check(close(sum(u["eur_before"] for u in usages), sim["annual_bill_before"], 0.02, 15), "facture par usage ≠ facture totale (avant)")
    case.check(close(sum(u["eur_after"] for u in usages), sim["annual_bill_after"], 0.02, 15), "facture par usage ≠ facture totale (après)")
    for u in usages:
        case.check(u["eur_after"] <= u["eur_before"] + 15 or u["energy_after"] != u["energy_before"],
                   f"{u['name']} : facture en hausse après travaux sans changement d'énergie")
    # Eco-PTZ
    if sim["eco_ptz_amount"]:
        case.check(sim["eco_ptz_amount"] <= sim["eco_ptz_limit"] + 1, f"éco-PTZ {sim['eco_ptz_amount']} > plafond {sim['eco_ptz_limit']}")
        case.check(sim["eco_ptz_amount"] <= sim["rest_to_pay"] + 100, "éco-PTZ supérieur au reste à charge")
        case.check(close(sim["eco_ptz_monthly"], sim["eco_ptz_amount"] / sim["eco_ptz_months"], 0.02, 1.5), "mensualité éco-PTZ incohérente")
    # Aid pathway
    if sim["aid_pathway"] == "accompagne":
        case.check(sim["gain_classes"] >= 2, f"rénovation d'ampleur avec un gain de {sim['gain_classes']} classe(s)")
        case.check(sim["current_label"] in AMPLEUR_LABELS, f"rénovation d'ampleur pour une classe {sim['current_label']}")
        case.check(sim["cee_est"] == 0, "CEE cumulés avec la rénovation d'ampleur")
    case.check(sim["subsidies"] + sim["cee_est"] <= sim["cost"] + 1, "aides supérieures au coût")
    # Green value
    if sim["new_label"] != sim["current_label"] and works:
        case.check(sim["latent_gain_low"] <= sim["latent_gain"] <= sim["latent_gain_high"], "valeur verte hors de sa fourchette")
        if market_value:
            case.check(0 <= sim["latent_gain"] <= 0.35 * market_value,
                       f"valeur verte {sim['latent_gain']:.0f} hors de 0 à 35 % de {market_value:.0f}")
    # Regulatory
    if not (sp.postcode or "").startswith("97"):
        expected = {"G": "interdite", "F": "2028", "E": "2034"}.get(sim["current_label"], "sans limite")
        case.check(expected in (sim["rental_status"] or ""), f"statut locatif « {sim['rental_status']} » pour une classe {sim['current_label']}")
        expected_after = {"G": "interdite", "F": "2028", "E": "2034"}.get(sim["new_label"], "sans limite")
        case.check(expected_after in (sim["new_rental_status"] or ""), f"statut après travaux « {sim['new_rental_status']} » pour {sim['new_label']}")
    house = content["identity"]["house"]
    labels = {i["label"]: i["value"] for i in content["regulatory"]["items"]}
    if not house and "immeuble" not in (sp.building_type or "").lower():
        case.check("Vente" not in labels, "audit de vente annoncé pour un appartement")
    elif sim["current_label"] in "EFG":
        case.check("Vente" in labels, "audit de vente manquant pour une maison E/F/G")
    if content["identity"].get("dpe_date") and "Validité du DPE" in labels:
        d = content["identity"]["dpe_date"]
        try:
            day, month, year = (int(x) for x in d.split("/"))
            dpe_day = date(year, month, day)
            if dpe_day >= date(2021, 7, 1):
                case.check(str(year + 10) in labels["Validité du DPE"], f"validité {labels['Validité du DPE']} pour un DPE du {d}")
        except ValueError:
            pass
    # Wall alternative: houses only; old facades warned
    alt = content.get("wall_alternative")
    if alt:
        case.check(house, "autre solution pour les murs sur un appartement")
        if alt["work"] == "ite" and "avant 1948" in (sp.construction_period or ""):
            case.check(bool(alt.get("caution")), "isolation par l'extérieur d'une façade d'avant 1948 sans rappel ABF")
    # Bill against the DPE's own annual cost (2021 prices, with subscription)
    dpe_cost = content["identity"].get("dpe_annual_cost")
    if dpe_cost:
        ratio = sim["annual_bill_before"] / float(dpe_cost) if float(dpe_cost) else 1
        case.check(0.33 <= ratio <= 3, f"facture estimée {sim['annual_bill_before']:.0f} € pour {dpe_cost} € au DPE")
        if not 0.5 <= ratio <= 1.8:
            case.note(f"facture {ratio:.1f} × coût DPE")


AMOUNT_NO_SPACE = re.compile(r"(?<![\d,.])\d{4,}\s?(?:€|kWh)")
LEFTOVERS = re.compile(r"\b(None|nan|NaN|undefined|null)\b|\{|\}")


def text_checks(case, text: str, sp) -> None:
    if not text:
        return
    for m in set(AMOUNT_NO_SPACE.findall(text)):
        case.check(False, f"nombre sans espace des milliers dans le PDF : « {m} »")
    for m in set(x.group(0) for x in LEFTOVERS.finditer(text)):
        case.check(False, f"valeur technique dans le PDF : « {m} »")
    case.check(not re.search(r"Eau chaude\s+0\s?€", text), "eau chaude à 0 € dans le PDF")
    case.check("NF, NF" not in text, "étoiles NF effacées dans le PDF")
    case.check("plain-pied" not in text.lower(), "« plain-pied » dans le PDF (jamais fourni par le DPE)")
