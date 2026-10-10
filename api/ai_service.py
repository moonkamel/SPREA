"""Written analysis of the report, by Claude (Anthropic API).

The writer only receives the facts computed by api/report_content.py (no
email, no street address) and must not introduce any other figure. Without
ANTHROPIC_API_KEY, or if the call fails, a rule-based text built from the
same facts is used, so the report is never left without an analysis.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

try:
    from api import claude
except ImportError:
    import claude

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5-5"
NARRATIVE_VERSION = 2
TIMEOUT_SECONDS = 50

SECTIONS = ("verdict", "diagnostic", "strategie", "financement", "profil")

SCHEMA = claude.strict_schema({
    "type": "object",
        "properties": {
            "verdict": {"type": "string", "description": "2 phrases maximum : ce qu'il faut retenir pour ce logement, avec les 2 chiffres décisifs."},
            "diagnostic": {"type": "string", "description": "Un paragraphe de 70 à 110 mots : pourquoi ce logement est classé ainsi, en s'appuyant sur ses pertes de chaleur, son chauffage et son époque."},
            "strategie": {"type": "string", "description": "Un paragraphe de 80 à 130 mots : l'ordre des travaux et ce que chacun apporte ici, chiffres à l'appui."},
            "financement": {"type": "string", "description": "Un paragraphe de 60 à 100 mots : aides, reste à charge, éco-PTZ et effort mensuel, avec les conditions qui comptent."},
            "profil": {"type": "string", "description": "Un paragraphe de 50 à 90 mots propre au profil (occupant ou bailleur) : confort et facture, ou location, loyer et rentabilité."},
            "vigilance": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5,
                          "description": "3 à 5 points de vigilance concrets pour ce projet, une phrase chacun."},
        },
        "required": ["verdict", "diagnostic", "strategie", "financement", "profil", "vigilance"],
})

SYSTEM_PROMPT = """Tu rédiges la partie « analyse » d'un rapport de rénovation énergétique payant, destiné à un client qui va s'engager financièrement. Le rapport contient déjà tous les tableaux chiffrés ; ton texte les relie et les interprète pour ce logement précis.

Règles de fond :
- N'utilise que les faits fournis. N'invente aucun chiffre, aucune aide, aucune date, aucune caractéristique du logement. Si une information manque, n'en parle pas.
- Ne déduis pas de caractéristique physique absente des données : nombre de niveaux, plain-pied, cave, vide sanitaire, combles aménagés, mitoyenneté, état des menuiseries.
- Chaque paragraphe cite au moins un chiffre des données, arrondi comme dans les données, en euros ou en kWh.
- Parle de CE logement : son type, sa surface, son époque, son chauffage, ses pertes de chaleur dominantes. Une phrase qui pourrait figurer dans le rapport d'un autre logement est à supprimer.
- Présente les montants comme des estimations (« environ », « entre … et … »), jamais comme des certitudes. Les aides restent à confirmer par France Rénov'.
- Si les données expliquent pourquoi la rénovation d'ampleur n'est pas accessible, explique-le simplement.
- Dans la stratégie, donne pour les travaux d'isolation la préconisation technique fournie (épaisseur, résistance thermique R exigée pour les aides) et, pour la pompe à chaleur, la puissance indicative si elle est fournie.
- Si « autre_solution_murs » est fournie, compare en une ou deux phrases l'isolation des murs par l'intérieur et par l'extérieur (surface habitable, ponts thermiques, coût, déclaration en mairie), avec l'écart de reste à charge.
- Si « variante_renovation_d_ampleur » est fournie, termine le paragraphe financement par cette variante : ajouter ce travail d'isolation ouvre la rénovation d'ampleur ; cite l'aide et le reste à charge de la variante, son accompagnement obligatoire et, s'il est fourni, ce qui est à vérifier sur place.
- Si « valeur_verte_calculee_sur_prix_m2_par_defaut » vaut true, ne cite pas le montant de la valeur verte : il repose sur un prix au m² par défaut.
- Les montants sont déjà arrondis : garde-les tels quels, sans recalculer de total.
- « facture_estimee_eur_an » est la facture totale (chauffage, eau chaude, éclairage) : ne l'appelle pas « facture de chauffage ».
- Si « eco_ptz_eur » est absent ou nul, ne parle pas d'éco-prêt. Si « parcours_aide » vaut « primes CEE », ne parle pas de MaPrimeRénov' pour ce programme.
- Si le profil est « propriétaire occupant », ne parle de location qu'au conditionnel (« si vous mettez en location »).
- Pas de conseil juridique ou fiscal personnalisé au-delà des faits fournis.

Règles de style (le texte ne doit pas sonner comme généré automatiquement) :
- Français sobre de conseiller : vouvoiement, phrases courtes, verbes concrets.
- Interdits : formules creuses et superlatifs (« véritable », « idéal », « optimal », « crucial », « essentiel de », « il est important de noter », « n'hésitez pas », « en somme », « en conclusion », « en définitive », « levier », « booster », « clé en main », « un investissement judicieux »), points d'exclamation, questions rhétoriques, émojis, listes à puces dans les paragraphes, titres, markdown, guillemets décoratifs.
- Ne commence pas deux phrases de suite par le même mot. Ne répète pas le même chiffre dans deux sections, sauf le reste à charge.
- Écris les nombres comme dans les données, avec une espace pour les milliers (12 400 €).

Réponds avec le texte final, dans le format demandé."""

BANNED = re.compile(r"\*\*|__|^#+\s|[\U0001F300-\U0001FAFF☀-➿]", re.M)


# An amount or a consumption written without the thousands space ("3680 €",
# "7400 à 10 900 €"): the tables show "3 680 €"
AMOUNT = re.compile(r"(?<![\d.,])(\d{1,3})(\d{3})(?=(?:\s?(?:€|kWh|euros))|(?:\s(?:et|à)\s\d[\d ]*\s?(?:€|kWh)))")


def thousands(text: str) -> str:
    return AMOUNT.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)


def _clean(value: Any, limit: int) -> str:
    text = BANNED.sub("", str(value or "")).replace("!", ".").strip()
    text = re.sub(r"\s+", " ", text)
    return thousands(text)[:limit]


def validate(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Keeps a well-formed analysis only."""
    out: Dict[str, Any] = {}
    for key in SECTIONS:
        value = _clean(raw.get(key), 1400)
        if len(value) < 20:
            return None
        out[key] = value
    points = [_clean(p, 300) for p in (raw.get("vigilance") or []) if isinstance(p, str)]
    points = [p for p in points if len(p) >= 15][:5]
    if len(points) < 2:
        return None
    out["vigilance"] = points
    return out


# --- Rule-based analysis (no API key, or API failure) ---

def _join(items: List[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " et " + items[-1]


def fallback_analysis(facts: Dict[str, Any]) -> Dict[str, Any]:
    log = facts["logement"]
    now = facts["etat_actuel"]
    after = facts["apres_travaux"]
    fin = facts["financement"]
    works = facts["travaux"]

    def eur(v: float) -> str:
        return f"{round(v):,}".replace(",", " ") + " €"

    losses = list(now["repartition_pertes_chaleur"].items())[:2]
    kind = (log["type"] or "logement").lower()
    feminine = kind == "maison"
    article = "Cette" if feminine else ("Cet" if kind[:1] in "aeéèiouyh" else "Ce")
    e = "e" if feminine else ""
    epoch = str(log.get("epoque_construction") or "")
    m = re.fullmatch(r"(\d{4})\s*-\s*(\d{4})", epoch)
    if m:
        period = f", construit{e} entre {m.group(1)} et {m.group(2)},"
    elif epoch.isdigit():
        period = f", construit{e} en {epoch},"
    elif epoch:
        period = f", construit{e} {epoch.lower()},"
    else:
        period = ""
    surface = f"{float(log['surface_m2']):g}".replace(".", ",")
    diag = (f"{article} {kind} de {surface} m²{period} est classé{e} {now['classe_dpe']}, "
            f"avec {now['consommation_kwh_ep_m2_an']} kWh/m²/an. "
            f"Ses pertes de chaleur passent d'abord par : {losses[0][0].lower()} ({losses[0][1]})"
            + (f", puis {losses[1][0].lower()} ({losses[1][1]})" if len(losses) > 1 else "") + ". "
            f"La facture d'énergie est estimée à {eur(now['facture_estimee_eur_an'])} par an, hors abonnement.")

    best = max(works, key=lambda w: w["economie_seule_eur_an"]) if works else None
    names = [w["nom"][:1].lower() + w["nom"][1:] for w in works]
    strat = (f"Le programme retenu enchaîne {_join(names)}, dans l'ordre du tableau des travaux : l'enveloppe d'abord, "
             f"les équipements ensuite, pour dimensionner ces derniers sur des besoins réduits. ") if works else ""
    if best:
        strat += (f"Pris isolément, le geste le plus efficace est : {best['nom'][:1].lower() + best['nom'][1:]}, "
                  f"avec environ {eur(best['economie_seule_eur_an'])} d'économie par an. ")
    specs = [w["preconisation_technique"] for w in works if w.get("preconisation_technique")][:2]
    if specs:
        strat += "Préconisations : " + " ".join(specs) + " "
    alt = facts.get("autre_solution_murs")
    if alt:
        gap = alt["ecart_reste_a_charge_eur"]
        strat += (f"Autre solution pour les murs : {alt['travail'][:1].lower() + alt['travail'][1:]}, pour un reste à charge "
                  f"{'supérieur' if gap > 0 else 'inférieur'} d'environ {eur(abs(gap))}. ")
    if not works:
        strat = "Aucun travaux n'est retenu dans ce scénario : choisissez des travaux pour obtenir une estimation."
    elif after["gain_classes"]:
        strat += (f"Ensemble, ces travaux amènent le logement en classe {after['classe_dpe']} "
                  f"({after['consommation_kwh_ep_m2_an']} kWh/m²/an) et la facture à environ {eur(after['facture_estimee_eur_an'])} par an.")
    else:
        strat += (f"Ces travaux ne changent pas la classe ({after['classe_dpe']}) mais ramènent la consommation à "
                  f"{after['consommation_kwh_ep_m2_an']} kWh/m²/an et la facture à environ {eur(after['facture_estimee_eur_an'])} par an.")

    rest_low, rest_high = fin["reste_a_charge_fourchette_eur"]
    finance = (f"Le coût des travaux se situe entre {eur(fin['cout_total_fourchette_eur'][0])} et {eur(fin['cout_total_fourchette_eur'][1])}. "
               f"Avec {fin['parcours_aide']}, le reste à charge est estimé entre {eur(rest_low)} et {eur(rest_high)}. ")
    if fin.get("pourquoi_pas_la_renovation_d_ampleur") and fin["parcours_aide"] != "MaPrimeRénov' rénovation d'ampleur":
        finance += fin["pourquoi_pas_la_renovation_d_ampleur"][0] + " "
    variant = facts.get("variante_renovation_d_ampleur")
    if variant:
        low, high = variant["reste_a_charge_fourchette_eur"]
        finance += (f"Ajouter {variant['travail_ajoute']} ouvrirait la rénovation d'ampleur : "
                    f"environ {eur(variant['maprimerenov_eur'])} d'aide, pour un reste à charge entre {eur(low)} et {eur(high)}, "
                    "avec un Accompagnateur Rénov' obligatoire. ")
    if fin["eco_ptz_eur"]:
        finance += (f"Un éco-prêt à taux zéro de {eur(fin['eco_ptz_eur'])} sur {fin['eco_ptz_duree_ans']} ans représente "
                    f"environ {eur(fin['eco_ptz_mensualite_eur'])} par mois, à comparer à {eur(fin['economie_mensuelle_eur'])} "
                    "d'économie mensuelle sur la facture.")

    if facts["profil"] == "bailleur investisseur":
        reg = facts["reglementation"]
        today = reg.get("Location aujourd'hui", "")
        later = reg.get("Location après travaux", "")
        profile = f"Situation locative actuelle : {today.lower()} ; après travaux : {later.lower()}. "
        inv = facts.get("investisseur") or {}
        if inv.get("loyer_mensuel_eur"):
            profile += (f"Avec un loyer de {eur(inv['loyer_mensuel_eur'])} par mois, le rendement brut ressort à "
                        f"{str(inv['rendement_brut_pct']).replace('.', ',')} % travaux compris.")
    else:
        insulated = any(w["nom"].lower().startswith(("isolation", "fenêtres")) for w in works)
        profile = (f"Pour un occupant, l'enjeu est la facture et le confort : environ {eur(after['economies_eur_an'])} "
                   "d'économie par an" + (", des parois moins froides et moins de courants d'air." if insulated else "."))
        if fin.get("retour_sur_investissement_ans"):
            profile += f" Le reste à charge est remboursé par les économies en {fin['retour_sur_investissement_ans']} ans environ."

    vigilance = [w["point_de_vigilance"] for w in works if w.get("point_de_vigilance")][:3]
    vigilance.append("Faites confirmer le montant des aides par un conseiller France Rénov' avant de signer un devis.")
    vigilance.append("Comparez au moins deux devis d'artisans RGE par lot avec les fourchettes de ce rapport.")

    if not works:
        verdict = f"Logement classé {now['classe_dpe']}, facture estimée à {eur(now['facture_estimee_eur_an'])} par an. Aucun travaux retenu."
    elif after["gain_classes"]:
        verdict = (f"Passer de {now['classe_dpe']} à {after['classe_dpe']} coûte entre {eur(rest_low)} et {eur(rest_high)} "
                   f"après aides, pour environ {eur(after['economies_eur_an'])} d'économie par an.")
    else:
        verdict = (f"Ces travaux coûtent entre {eur(rest_low)} et {eur(rest_high)} après aides, sans changer la classe "
                   f"{now['classe_dpe']}, pour environ {eur(after['economies_eur_an'])} d'économie par an.")
    return {"verdict": verdict, "diagnostic": diag, "strategie": strat, "financement": finance,
            "profil": profile, "vigilance": vigilance[:5]}


# --- Claude ---

class AIService:
    @property
    def model(self) -> str:
        return os.getenv("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL

    async def write_analysis(self, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Returns {"source": "claude" | "rules", "sections": {...}}."""
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if key:
            sections = await self._claude(facts)
            if sections:
                return {"v": NARRATIVE_VERSION, "source": "claude", "model": self.model, "sections": sections}
        else:
            logger.warning("ANTHROPIC_API_KEY not set: rule-based analysis")
        return {"v": NARRATIVE_VERSION, "source": "rules", "sections": fallback_analysis(facts)}

    async def _claude(self, facts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        content = "Données du logement et du projet (JSON) :\n" + json.dumps(facts, ensure_ascii=False, indent=1)
        try:
            raw = await claude.json_call(SYSTEM_PROMPT, content, SCHEMA, model=self.model, effort="medium",
                                         max_tokens=8000, timeout=TIMEOUT_SECONDS)
        except claude.ClaudeUnavailable:
            return None
        sections = validate(raw)
        if not sections:
            logger.error("Anthropic analysis rejected by validation")
        return sections


def parse_stored(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Stored analysis, if it is a current-format analysis written by Claude."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None  # Old plain-text narrative
    if isinstance(data, dict) and data.get("v") == NARRATIVE_VERSION and data.get("source") == "claude":
        # Texts stored before the thousands fix
        sections = data.get("sections") or {}
        for key, value in sections.items():
            if isinstance(value, str):
                sections[key] = thousands(value)
            elif isinstance(value, list):
                sections[key] = [thousands(v) if isinstance(v, str) else v for v in value]
        return data
    return None


ai_service = AIService()
