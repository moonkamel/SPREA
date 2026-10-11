"""Expert review of real reports: each report is generated exactly as the app
does it (DVF price, RGE companies, building sheet, analysis written by Claude,
PDF), then read by Claude as a seasoned renovation adviser would, against the
raw DPE data, with the checklist of every defect found on real reports so far.
The arithmetic audit (audit.py) checks figures; this one checks judgement:
a programme that costs too much for what it brings, a floor that contradicts
the address, an invented feature, advice that does not fit the dwelling.

  python scripts/audit/review_pdfs.py --count 40 --shard 0 --shards 5

Without --ai, nothing is sent to Claude: the analysis is the rule-based text
and the reports (PDF, text, DPE data) are written to reports/ to be read
outside, with the automatic checks of the audit.
"""
import argparse
import asyncio
import json
import os
import random
import sys
import traceback
from collections import Counter
from typing import Any, Dict, List

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api import claude  # noqa: E402
from api.ademe_client import AdemeConnector  # noqa: E402
from api.ai_service import ai_service, fallback_analysis  # noqa: E402
from api.dvf import market_price  # noqa: E402
from api.immeuble import sheet_or_none  # noqa: E402
from api.main import enrich_property, simulation_property  # noqa: E402
from api.pdf_service import pdf_service  # noqa: E402
from api.report_content import build_report, facts_for_writer  # noqa: E402
from api.rge import nearby_or_empty  # noqa: E402
from api.simulation import SimulationInput  # noqa: E402
from scripts.audit.audit import Case, sample_dpe  # noqa: E402
from scripts.audit.checks import pdf_text, report_checks, text_checks  # noqa: E402

REVIEWER_MODEL = os.getenv("REVIEW_MODEL", "claude-opus-5-5")
# Dollars per million tokens (input, output), to stop at the budget
PRICES = {"opus": (4.0, 20.0), "sonnet": (2.0, 10.0), "haiku": (0.10, 0.50)}
# A report costs about this much (analysis + review): no new report starts
# when the spend plus what the running ones may still cost passes the budget
REPORT_COST = 0.10
spent = [0.0]
USE_AI = [False]
OUT_DIR = "reports"


def count_usage(model: str, usage) -> None:
    price = next((p for k, p in PRICES.items() if k in model), PRICES["opus"])
    tokens_in = (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) \
        + (getattr(usage, "cache_read_input_tokens", 0) or 0)
    spent[0] += (tokens_in * price[0] + (usage.output_tokens or 0) * price[1]) / 1e6

RUBRIC = """Tu es un conseiller France Rénov' et un agent immobilier expérimentés. Tu relis un rapport de rénovation énergétique généré automatiquement, destiné à être remis par un agent immobilier à son client. Tu disposes du texte du PDF et des données brutes du DPE (base ADEME) dont il est tiré. Signale tout ce qu'un professionnel relèverait en le lisant et qui le ferait douter du rapport.

Cherche en particulier (défauts déjà trouvés sur de vrais rapports) :
1. Chiffres incohérents entre sections : coûts, totaux, aides (total ≠ somme du détail), reste à charge, économies, facture par usage, retour sur investissement, éco-PTZ et mensualité, valeur verte et sa fourchette, consommation et étiquette.
2. Programme mal choisi : travaux chers pour un gain faible ou nul sur la classe ; travaux qui ne changent pas la classe alors qu'un programme moins cher donne le même résultat ; équipement déjà présent reproposé ; travaux inadaptés au logement (isolation par l'extérieur d'un appartement, pompe à chaleur sans circuit d'eau, chauffe-eau sans eau chaude au DPE, toiture d'un appartement sans toit) ; isolation sans ventilation ; poste de pertes majeur ignoré sans explication.
3. Contradictions avec le DPE : étage, type de bien, surface, énergie, équipements de chauffage, d'eau chaude, de ventilation, qualité d'isolation, type de toiture, période de construction.
4. Le texte d'analyse invente une caractéristique absente des données (plain-pied, rez-de-chaussée, mitoyenneté, cave, combles aménagés, équipement « ancien »…) ou contredit les tableaux du rapport.
5. Règles fausses ou mal appliquées : calendrier d'interdiction de louer (G 2025, F 2028, E 2034 en métropole), audit énergétique obligatoire à la vente (maisons et immeubles en monopropriété classés E, F, G ; pas les appartements), rénovation d'ampleur (classes E, F, G, au moins 2 classes gagnées, au moins 2 gestes d'isolation, accompagnateur obligatoire, CEE non cumulables), MaPrimeRénov' par geste réservée depuis le 1er septembre 2026 aux pompes à chaleur, éco-PTZ (15 000 / 25 000 / 30 000 € selon 1 / 2 / 3 actions, 50 000 € en rénovation d'ampleur), seuils DPE adaptés aux logements de moins de 40 m², coefficient de l'électricité à 1,9 depuis le 1er janvier 2026.
6. Bâti ancien : sur un mur d'avant 1948, isolants perméables à la vapeur ; isolation par l'extérieur d'une façade ancienne soumise à l'accord de l'Architecte des Bâtiments de France.
7. Copropriété (appartements) : travaux collectifs, quote-part, obligations (plan pluriannuel, DPE collectif) cohérents avec la taille et l'époque de l'immeuble.
8. Rédaction : nombres sans espace des milliers, valeurs techniques visibles (None, nan, 0 € incongru), phrases creuses ou répétées, promesses ou certitudes (« garanti », « opposable »), jargon non expliqué, fautes.
9. Tout autre élément qui ferait perdre confiance à un client ou à un agent.

Ne signale pas : le fait que ce soient des estimations, l'absence d'informations que les données ne contiennent pas, des choix de méthode documentés dans le rapport (prix de l'énergie hors abonnement, coût annuel du DPE aux prix 2021, valeur verte à 70 % de l'écart mesuré), ni les préférences de style. Sois précis et vérifiable : cite le passage du rapport en cause. Un rapport sans défaut réel reçoit une liste vide."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "severity": {"type": "string", "enum": ["bloquant", "important", "mineur"]},
                    "category": {"type": "string", "enum": ["chiffres", "programme", "contradiction_dpe", "texte_invente",
                                                            "regles", "bati_ancien", "copropriete", "redaction", "autre"]},
                    "finding": {"type": "string", "description": "Le défaut, en une ou deux phrases."},
                    "excerpt": {"type": "string", "description": "Le passage du rapport en cause, cité."},
                },
                "required": ["severity", "category", "finding", "excerpt"],
            },
        },
        "verdict": {"type": "string", "description": "Une phrase : le rapport peut-il être remis tel quel à un client ?"},
    },
    "required": ["findings", "verdict"],
}

results: List[Dict[str, Any]] = []


def dpe_summary(prop) -> Dict[str, Any]:
    d = prop.model_dump(mode="json")
    keep = ("address", "ademe_dpe_number", "building_type", "shab", "construction_year", "construction_period",
            "dpe_class_current", "ges_class_current", "consumption_level", "final_consumption", "ges_value",
            "date_etablissement", "postcode", "city", "details", "insulation_quality", "dpe_losses", "usage_consumption")
    return {k: d.get(k) for k in keep}


async def review_one(number: str, store) -> None:
    out: Dict[str, Any] = {"number": number}
    before = spent[0]
    try:
        prop = await AdemeConnector().search_by_dpe_number(number)
        if not prop:
            out["error"] = "DPE introuvable"
            return
        enriched = enrich_property(prop)
        sp = simulation_property(prop)
        if prop.insee_code:
            market = await market_price(prop.insee_code, prop.building_type, prop.latitude, prop.longitude, prop.shab)
            if market:
                sp.price_per_m2, sp.price_source = market["price_per_m2"], market["source"]
            sp.insee_code = prop.insee_code
        works = enriched.get("preselected_works") or []
        sim_in = SimulationInput(property=sp, works=works, suggested_works=enriched.get("suggested_works") or [])
        meta = {"address": prop.address, "ademe_dpe_number": number, "building_type": prop.building_type,
                "construction_period": prop.construction_period,
                "dpe_date": str(prop.date_etablissement)[:10] if prop.date_etablissement else None,
                "postcode": prop.postcode, "city": prop.city, "insee_code": prop.insee_code,
                "latitude": prop.latitude, "longitude": prop.longitude, "details": prop.details}
        content = build_report(meta, sim_in)
        content["rge"] = await nearby_or_empty(prop.latitude, prop.longitude, works, prop.building_type)
        content["immeuble"] = await sheet_or_none(number, prop.building_type, store)
        if USE_AI[0]:
            analysis = await ai_service.write_analysis(facts_for_writer(content))
        else:
            analysis = {"source": "rules", "sections": fallback_analysis(facts_for_writer(content))}
        pdf = pdf_service.generate(content, analysis["sections"])
        text = pdf_text(pdf)
        out.update({"kind": prop.building_type, "surface": prop.shab, "label": content["sim"]["current_label"],
                    "new_label": content["sim"]["new_label"], "works": works, "analysis_source": analysis["source"],
                    "address": prop.address})
        if not USE_AI[0]:
            case = Case("logement", number)
            report_checks(case, sp, content, (sp.price_per_m2 * prop.shab) if sp.price_per_m2 and prop.shab else None)
            text_checks(case, text, sp)
            out["checks"] = case.failures
            out["dpe"] = dpe_summary(prop)
            os.makedirs(OUT_DIR, exist_ok=True)
            with open(os.path.join(OUT_DIR, f"{number}.pdf"), "wb") as f:
                f.write(pdf)
            with open(os.path.join(OUT_DIR, f"{number}.txt"), "w") as f:
                f.write(text)
            return
        review = await claude.json_call(
            RUBRIC,
            "Données brutes du DPE (ADEME) :\n" + json.dumps(dpe_summary(prop), ensure_ascii=False, default=str)
            + "\n\nTexte du rapport PDF :\n" + text,
            SCHEMA, model=REVIEWER_MODEL, effort=os.getenv("REVIEW_EFFORT", "medium"), max_tokens=8000, timeout=240)
        out["findings"] = review.get("findings") or []
        out["verdict"] = review.get("verdict")
        out["text"] = text
    except Exception as e:  # noqa: BLE001 - one report must not stop the review
        out["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        out["cost_usd"] = round(spent[0] - before, 4)
        results.append(out)
        f = out.get("findings") or []
        head = f"{out.get('kind', '?')} {out.get('surface', '?')} m² {out.get('label', '?')}→{out.get('new_label', '?')} {'+'.join(out.get('works') or [])}"
        bad = f or out.get("checks")
        print(f"{'ERR' if 'error' in out else ('OK ' if not bad else 'KO ')} {number} | {head} | {out.get('error') or out.get('verdict') or ''}", flush=True)
        for x in out.get("checks") or []:
            print(f"     ✗ {x}", flush=True)
        for x in f:
            print(f"     [{x['severity']}/{x['category']}] {x['finding']} « {x['excerpt'][:160]} »", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--numbers", default="")
    ap.add_argument("--ai", action="store_true", help="analysis written by Claude, then reviewed by Claude")
    ap.add_argument("--budget", type=float, default=0, help="dollars; stops starting reports past it (0 = none)")
    args = ap.parse_args()
    USE_AI[0] = args.ai
    if args.ai and not claude.configured():
        sys.exit("ANTHROPIC_API_KEY manquante")
    store = None
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        from api.store import SupabaseStore
        store = SupabaseStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"], timeout=30)
    if args.numbers:
        numbers = [n.strip() for n in args.numbers.split(",") if n.strip()]
    else:
        async with httpx.AsyncClient(timeout=20) as client:
            numbers = await sample_dpe(client, args.count, random.Random(args.seed), args.shard, args.shards)
    claude.USAGE_HOOK = count_usage
    gate = asyncio.Semaphore(max(1, args.concurrency))
    running = [0]

    async def one(n: str):
        async with gate:
            if args.budget and spent[0] + (running[0] + 1) * REPORT_COST > args.budget:
                return
            running[0] += 1
            try:
                await review_one(n, store)
            finally:
                running[0] -= 1
    await asyncio.gather(*(one(n) for n in numbers))
    with open("reviews.json", "w") as f:
        json.dump(results, f, ensure_ascii=False)
    done = [r for r in results if "error" not in r]
    cats = Counter(x["category"] for r in done for x in r.get("findings") or [])
    sev = Counter(x["severity"] for r in done for x in r.get("findings") or [])
    if not args.ai:
        print(f"\n{len(done)} rapports générés dans {OUT_DIR}/, {len(results) - len(done)} erreurs ; "
              f"{sum(1 for r in done if r.get('checks'))} avec un contrôle automatique en défaut")
        return
    print(f"\n{len(done)} rapports relus, {sum(1 for r in done if not r.get('findings'))} sans défaut ; "
          f"gravité {dict(sev)} ; catégories {dict(cats)} ; dépense ${spent[0]:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
