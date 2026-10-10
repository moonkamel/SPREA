"""Signs that a company owning a whole building may sell it, read in the
BODACC (Bulletin officiel des annonces civiles et commerciales, DILA, open
data): dissolution, liquidation, insolvency proceedings, removal from the
register, change of management, a death mentioned in the notices.

- classify() and score() turn the notices of a company into dated events and
  a 0-100 score; scripts/monopro/signals.py runs them on every owner of the
  monopro_buildings table (weekly) and stores the result (014_monopro_signals.sql);
- explain() asks Claude, when an agent opens the building sheet, what the
  events mean for this building and how to approach the owner. Stored, so
  it is asked once per set of events.

Only the kind and date of each event are kept, with the link to the notice:
not the names the notices may contain (managers, liquidators).
"""
import hashlib
import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

try:
    from api import claude
except ImportError:
    import claude

BODACC_URL = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
FIELDS = "id,dateparution,familleavis_lib,commercant,listepersonnes,jugement,modificationsgenerales,radiationaurcs,url_complete"

# Weight of each kind of event in the score
WEIGHTS = {
    "liquidation_judiciaire": 60,
    "plan_cession": 50,
    "dissolution": 55,
    "liquidation_amiable": 45,
    "redressement": 45,
    "deces": 40,
    "cloture": 35,
    "sauvegarde": 30,
    "cessation": 30,
    "radiation": 30,
    "dirigeant": 20,
}
LABELS = {
    "liquidation_judiciaire": "Liquidation judiciaire",
    "plan_cession": "Plan de cession",
    "dissolution": "Dissolution de la société",
    "liquidation_amiable": "Société en liquidation amiable",
    "redressement": "Redressement judiciaire",
    "deces": "Décès mentionné dans une annonce",
    "cloture": "Clôture de la procédure collective",
    "sauvegarde": "Procédure de sauvegarde",
    "cessation": "Cessation d'activité",
    "radiation": "Radiation du registre",
    "dirigeant": "Changement de dirigeant",
}
STRONG, MEDIUM = 50, 25
# Events that end the company
CLOSED = {"radiation", "cloture"}


def _json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        out = json.loads(value or "{}")
        return out if isinstance(out, dict) else {}
    except ValueError:
        return {}


def _lower(*values: Any) -> str:
    return " ".join(str(v) for v in values if v).lower()


def classify(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Events of one BODACC notice ([] for the ordinary ones)."""
    kinds: List[str] = []
    family = record.get("familleavis_lib") or ""
    judgment = _json(record.get("jugement"))
    changes = _json(record.get("modificationsgenerales"))
    person = _json(record.get("listepersonnes")).get("personne") or {}
    if isinstance(person, list):
        person = person[0] if person else {}
    administration = _lower(person.get("administration"))
    nature = _lower(judgment.get("nature"), judgment.get("famille"))
    described = _lower(changes.get("descriptif"))

    if family.startswith("Procédures collectives") or nature:
        if "clôture" in nature or "cloture" in nature:
            kinds.append("cloture")
        elif "plan de cession" in nature:
            kinds.append("plan_cession")
        elif "liquidation" in nature:
            kinds.append("liquidation_judiciaire")
        elif "redressement" in nature:
            kinds.append("redressement")
        elif "sauvegarde" in nature:
            kinds.append("sauvegarde")
    if "dissolution" in described:
        kinds.append("dissolution")
    elif "cessation" in described or "mise en sommeil" in described:
        kinds.append("cessation")
    if "(en liquidation)" in _lower(record.get("commercant")) and not kinds:
        kinds.append("liquidation_amiable")
    if family.startswith("Radiations") or record.get("radiationaurcs"):
        kinds.append("radiation")
    text = _lower(administration, described, judgment.get("complementJugement"))
    if re.search(r"d[ée]c[èe]s|d[ée]c[ée]d", text):
        kinds.append("deces")
    elif "partant" in administration or "démission" in administration or "nomination du gérant" in administration:
        kinds.append("dirigeant")
    return [{"date": record.get("dateparution"), "kind": k, "label": LABELS[k], "url": record.get("url_complete")}
            for k in dict.fromkeys(kinds)]


def recency(day: Optional[str], today: date) -> float:
    try:
        age = (today - date.fromisoformat(day[:10])).days if day else 99999
    except ValueError:
        return 0.0
    return 1.0 if age <= 365 else 0.6 if age <= 3 * 365 else 0.25 if age <= 6 * 365 else 0.0


def score(events: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    """The strongest recent event, plus a part of the others; events older
    than six years are left out."""
    kept = sorted((e for e in events if recency(e.get("date"), today) > 0), key=lambda e: e.get("date") or "", reverse=True)
    # The same kind of event counts once (its latest notice)
    latest = list({e["kind"]: e for e in reversed(kept)}.values())
    weights = sorted((WEIGHTS[e["kind"]] * recency(e.get("date"), today) for e in latest), reverse=True)
    value = round(min(100, (weights[0] + 0.3 * sum(weights[1:])) if weights else 0))
    if kept and kept[0]["kind"] in CLOSED and recency(kept[0].get("date"), today) < 1:
        # Company closed more than a year ago: the building has most likely
        # already been sold or handed to the partners
        value = min(value, MEDIUM + 10)
    level = "fort" if value >= STRONG else "moyen" if value >= MEDIUM else "faible" if value else None
    return {"score": value, "level": level, "events": kept[:15]}


# --- Claude: what it means for this building ---

EXPLAIN_SCHEMA = claude.strict_schema({
    "type": "object",
    "properties": {
        "titre": {"type": "string", "description": "Une phrase : la situation du propriétaire et ce qu'elle implique pour l'immeuble."},
        "lecture": {"type": "string", "description": "3 à 5 phrases : ce que signifient ces annonces pour une vente de l'immeuble, et à quel horizon."},
        "approche": {"type": "string", "description": "2 à 4 phrases : qui contacter (gérant, liquidateur, mandataire judiciaire, notaire chargé de la succession) et comment présenter la démarche, avec tact."},
        "probabilite": {"type": "string", "enum": ["faible", "moyenne", "forte"],
                        "description": "Probabilité que l'immeuble soit mis en vente dans les 12 mois."},
    },
})

EXPLAIN_SYSTEM = """Tu aides un agent immobilier à comprendre la situation d'une société propriétaire d'un immeuble entier, à partir des annonces légales publiées au BODACC, et à l'aborder avec tact.

Règles :
- Tu ne disposes que des événements fournis (nature et date) et des caractéristiques de l'immeuble. N'invente aucun fait, aucun montant, aucun nom.
- Explique en termes simples et justes : en liquidation judiciaire, les biens sont vendus par le liquidateur sous le contrôle du juge-commissaire ; après une dissolution amiable, le liquidateur amiable vend les actifs pour clôturer ; en redressement ou sauvegarde, une cession d'actifs est possible mais pas certaine ; une clôture ou une radiation peut signifier que l'immeuble a déjà changé de mains ; un décès ouvre souvent une succession.
- Ne nomme aucune personne. Parle « du gérant », « du liquidateur », « des associés ».
- Reste prudent : ce sont des indices, pas des certitudes. Recommande une démarche respectueuse, jamais insistante, et rappelle quand il le faut de vérifier l'annonce sur le BODACC.
- Français sobre, phrases courtes, pas de markdown."""


def explain_key(events: List[Dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps([[e.get("date"), e.get("kind")] for e in events]).encode()).hexdigest()[:16]


async def explain(signal: Dict[str, Any], building: Dict[str, Any], today: date) -> Dict[str, Any]:
    facts = {
        "date_du_jour": today.isoformat(),
        "evenements": [{"date": e.get("date"), "nature": e.get("label")} for e in signal.get("events") or []],
        "immeuble": {"logements": building.get("nb_log"), "construction": building.get("year_built"),
                     "classe_dpe": building.get("dpe_label"), "logements_f_ou_g": building.get("dpe_fg"),
                     "derniere_vente": building.get("last_sale_date"),
                     "autres_immeubles_du_proprietaire": building.get("portfolio_count")},
        "forme_juridique": building.get("legal_form"),
    }
    return await claude.json_call(EXPLAIN_SYSTEM, "Situation (JSON) :\n" + json.dumps(facts, ensure_ascii=False, indent=1),
                                  EXPLAIN_SCHEMA, effort="low", max_tokens=4000, timeout=50)
