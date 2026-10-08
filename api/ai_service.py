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

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5-5"
NARRATIVE_VERSION = 2
TIMEOUT_SECONDS = 50

SECTIONS = ("verdict", "diagnostic", "strategie", "financement", "profil")

TOOL = {
    "name": "rediger_analyse",
    "description": "Enregistre l'analyse rédigée du rapport de rénovation.",
    "input_schema": {
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
    },
}

SYSTEM_PROMPT = """Tu rédiges la partie « analyse » d'un rapport de rénovation énergétique payant, destiné à un client qui va s'engager financièrement. Le rapport contient déjà tous les tableaux chiffrés ; ton texte les relie et les interprète pour ce logement précis.

Règles de fond :
- N'utilise que les faits fournis. N'invente aucun chiffre, aucune aide, aucune date, aucune caractéristique du logement. Si une information manque, n'en parle pas.
- Chaque paragraphe cite au moins un chiffre des données, arrondi comme dans les données, en euros ou en kWh.
- Parle de CE logement : son type, sa surface, son époque, son chauffage, ses pertes de chaleur dominantes. Une phrase qui pourrait figurer dans le rapport d'un autre logement est à supprimer.
- Présente les montants comme des estimations (« environ », « entre … et … »), jamais comme des certitudes. Les aides restent à confirmer par France Rénov'.
- Si les données expliquent pourquoi la rénovation d'ampleur n'est pas accessible, explique-le simplement.
- Si « valeur_verte_calculee_sur_prix_m2_par_defaut » vaut true, ne cite pas le montant de la valeur verte : il repose sur un prix au m² par défaut.
- Les montants sont déjà arrondis : garde-les tels quels, sans recalculer de total.
- Pas de conseil juridique ou fiscal personnalisé au-delà des faits fournis.

Règles de style (le texte ne doit pas sonner comme généré automatiquement) :
- Français sobre de conseiller : vouvoiement, phrases courtes, verbes concrets.
- Interdits : formules creuses et superlatifs (« véritable », « idéal », « optimal », « crucial », « essentiel de », « il est important de noter », « n'hésitez pas », « en somme », « en conclusion », « en définitive », « levier », « booster », « clé en main », « un investissement judicieux »), points d'exclamation, questions rhétoriques, émojis, listes à puces dans les paragraphes, titres, markdown, guillemets décoratifs.
- Ne commence pas deux phrases de suite par le même mot. Ne répète pas le même chiffre dans deux sections, sauf le reste à charge.
- Écris les nombres comme dans les données, avec une espace pour les milliers (12 400 €).

Appelle l'outil rediger_analyse avec le texte final."""

BANNED = re.compile(r"\*\*|__|^#+\s|[\U0001F300-\U0001FAFF☀-➿]", re.M)


def _clean(value: Any, limit: int) -> str:
    text = BANNED.sub("", str(value or "")).replace("!", ".").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


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
    article = "Cet" if kind[:1] in "aeéèiouyh" else "Ce"
    period = f" construit {log['epoque_construction'].lower()}" if log.get("epoque_construction") and not str(log["epoque_construction"]).isdigit() else (
        f" construit en {log['epoque_construction']}" if log.get("epoque_construction") else "")
    diag = (f"{article} {kind} de {str(log['surface_m2']).replace('.', ',')} m²{period} est classé {now['classe_dpe']}, "
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
    strat += (f"Ensemble, ces travaux amènent le logement en classe {after['classe_dpe']} "
              f"({after['consommation_kwh_ep_m2_an']} kWh/m²/an) et la facture à environ {eur(after['facture_estimee_eur_an'])} par an.")

    rest_low, rest_high = fin["reste_a_charge_fourchette_eur"]
    finance = (f"Le coût des travaux se situe entre {eur(fin['cout_total_fourchette_eur'][0])} et {eur(fin['cout_total_fourchette_eur'][1])}. "
               f"Avec {fin['parcours_aide']}, le reste à charge est estimé entre {eur(rest_low)} et {eur(rest_high)}. ")
    if fin.get("pourquoi_pas_la_renovation_d_ampleur") and fin["parcours_aide"] != "MaPrimeRénov' rénovation d'ampleur":
        finance += fin["pourquoi_pas_la_renovation_d_ampleur"][0] + " "
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
        profile = (f"Pour un occupant, l'enjeu est la facture et le confort : environ {eur(after['economies_eur_an'])} "
                   "d'économie par an, des parois moins froides et moins de courants d'air.")
        if fin.get("retour_sur_investissement_ans"):
            profile += f" Le reste à charge est remboursé par les économies en {fin['retour_sur_investissement_ans']} ans environ."

    vigilance = [w["point_de_vigilance"] for w in works if w.get("point_de_vigilance")][:3]
    vigilance.append("Faites confirmer le montant des aides par un conseiller France Rénov' avant de signer un devis.")
    vigilance.append("Comparez au moins deux devis d'artisans RGE par lot avec les fourchettes de ce rapport.")

    verdict = (f"Passer de {now['classe_dpe']} à {after['classe_dpe']} coûte entre {eur(rest_low)} et {eur(rest_high)} "
               f"après aides, pour environ {eur(after['economies_eur_an'])} d'économie par an.")
    return {"verdict": verdict, "diagnostic": diag, "strategie": strat, "financement": finance,
            "profil": profile, "vigilance": vigilance[:5]}


# --- Claude ---

class AIService:
    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.transport = transport  # Tests only

    @property
    def model(self) -> str:
        return os.getenv("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL

    async def write_analysis(self, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Returns {"source": "claude" | "rules", "sections": {...}}."""
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if key:
            sections = await self._claude(key, facts)
            if sections:
                return {"v": NARRATIVE_VERSION, "source": "claude", "model": self.model, "sections": sections}
        else:
            logger.warning("ANTHROPIC_API_KEY not set: rule-based analysis")
        return {"v": NARRATIVE_VERSION, "source": "rules", "sections": fallback_analysis(facts)}

    async def _claude(self, key: str, facts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = {
            "model": self.model,
            "max_tokens": 3000,
            "system": SYSTEM_PROMPT,
            "tools": [TOOL],
            "tool_choice": {"type": "tool", "name": TOOL["name"]},
            "messages": [{
                "role": "user",
                "content": "Données du logement et du projet (JSON) :\n" + json.dumps(facts, ensure_ascii=False, indent=1),
            }],
        }
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self.transport) as client:
                res = await client.post(ANTHROPIC_URL, json=payload, headers=headers)
            if res.status_code != 200:
                # Never log the body of the request (facts) nor the key
                logger.error(f"Anthropic API error {res.status_code}: {res.text[:300]}")
                return None
            for block in res.json().get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == TOOL["name"]:
                    sections = validate(block.get("input") or {})
                    if not sections:
                        logger.error("Anthropic analysis rejected by validation")
                    return sections
            logger.error("Anthropic response without analysis")
        except Exception as e:
            logger.error(f"Anthropic call failed: {type(e).__name__}")
        return None


def parse_stored(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Stored analysis, if it is a current-format analysis written by Claude."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None  # Old plain-text narrative
    if isinstance(data, dict) and data.get("v") == NARRATIVE_VERSION and data.get("source") == "claude":
        return data
    return None


ai_service = AIService()
