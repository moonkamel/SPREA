"""Consistency audit on real public data, run by .github/workflows/audit.yml.

Runs the same code as the app on real cases and checks that every figure
holds together:
- dwellings: real DPE of several regions, kinds and classes -> search,
  suggested works, simulation, valuation, PDF report, building sheet of
  apartments;
- whole buildings (monopropriétés): buildings of the Supabase table ->
  sale dossier and its PDF;
- prospection map: real areas -> addresses inside the area, classes and
  dates as asked.

Read-only: nothing is written anywhere. Prints one line per case and the
failed checks, and a summary (also in the GitHub job summary).

  python scripts/audit/audit.py --dwellings 60 --buildings 40
"""
import argparse
import asyncio
import io
import itertools
import json
import os
import random
import sys
import traceback
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api import immeuble, monopro_pdf, prospection  # noqa: E402
from api.ademe_client import AdemeConnector  # noqa: E402
from api.ai_service import fallback_analysis  # noqa: E402
from api.dvf import market_price  # noqa: E402
from api.green_value import department, kind_of  # noqa: E402
from api.main import enrich_property, simulation_property  # noqa: E402
from api.address import parts, same_address, same_street  # noqa: E402
from api.monopro_report import RENOVATION_M2, build_dossier  # noqa: E402
from api.pdf_service import pdf_service  # noqa: E402
from api.report_content import build_report, facts_for_writer  # noqa: E402
from api.simulation import SimulationInput, available_works, simulate  # noqa: E402
from api.valuation import compute  # noqa: E402

ADEME = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
LABELS = "ABCDEFG"
# Communes of several regions, to vary climates, markets and housing stock
PLACES = ["59350", "62041", "75111", "75117", "69383", "13208", "33063", "35238", "67482", "31555", "44109", "06088",
          "34172", "38185", "76540", "21231", "63113", "29019", "80021", "02691", "57463", "87085", "14118", "25056"]

results: List[Dict[str, Any]] = []


class Case:
    def __init__(self, kind: str, name: str):
        self.kind, self.name = kind, name
        self.failures: List[str] = []
        self.notes: List[str] = []
        self.data: Dict[str, Any] = {}

    def check(self, ok: bool, message: str):
        if not ok:
            self.failures.append(message)

    def note(self, message: str):
        self.notes.append(message)

    def done(self):
        status = "OK " if not self.failures else "KO "
        print(f"{status} [{self.kind}] {self.name}" + (f" | {' ; '.join(self.notes)}" if self.notes else ""), flush=True)
        for f in self.failures:
            print(f"     ✗ {f}", flush=True)
        if self.failures and self.data:
            # What it takes to reproduce the case without the network
            print("     DATA " + json.dumps(self.data, ensure_ascii=False, default=str), flush=True)
        results.append({"kind": self.kind, "name": self.name, "failures": self.failures, "notes": self.notes})


def pdf_pages(data: bytes) -> int:
    return data.count(b"/Type /Page") - data.count(b"/Type /Pages")


def idx(label: Optional[str]) -> int:
    return LABELS.index(label) if label in LABELS else -1


# --- Dwellings ---

async def sample_dpe(client: httpx.AsyncClient, n: int, rng: random.Random) -> List[str]:
    """Recent DPE of apartments and houses, every class, several regions."""
    numbers: List[str] = []
    combos = [(kind, label, insee) for kind in ("appartement", "maison") for label in LABELS for insee in PLACES]
    rng.shuffle(combos)
    for kind, label, insee in combos:
        if len(numbers) >= n:
            break
        res = await client.get(ADEME, params={
            "qs": f"type_batiment:{kind} AND etiquette_dpe:{label} AND code_insee_ban:{insee} AND date_etablissement_dpe:[2024-01-01 TO *]",
            "size": 2, "select": "numero_dpe", "sort": "-date_etablissement_dpe"})
        if res.status_code == 200:
            numbers += [r["numero_dpe"] for r in res.json().get("results", [])[:1]]
    return numbers


async def audit_dwelling(number: str, store) -> None:
    case = Case("logement", number)
    try:
        prop = await AdemeConnector().search_by_dpe_number(number)
        if not prop:
            case.check(False, "DPE introuvable par son numéro")
            return case.done()
        case.data["property"] = prop.model_dump(mode="json")
        enriched = enrich_property(prop)
        sp = simulation_property(prop)
        label = prop.dpe_class_current.value if prop.dpe_class_current else None
        case.note(f"{prop.building_type} {prop.shab:g} m² {label} {prop.postcode}")
        case.check(prop.shab and 5 <= prop.shab <= 2000, f"surface improbable : {prop.shab}")
        works = enriched.get("preselected_works") or []
        sim_in = SimulationInput(property=sp, works=works, suggested_works=enriched.get("suggested_works") or [])
        sim = simulate(sim_in)
        case.check(sim["current_label"] == label, f"classe recalculée {sim['current_label']} ≠ classe officielle {label}")
        case.check(idx(sim["new_label"]) <= idx(sim["current_label"]), f"classe après travaux {sim['new_label']} pire que {sim['current_label']}")
        if label in ("E", "F", "G"):
            case.check(bool(works), "aucun travaux proposé pour une passoire")
            # Best reachable: every work that applies to this kind of dwelling
            every = sorted(available_works(sp)["works"])
            # Some works can raise the label (electric heating replacing gas): every combination
            best = min((simulate(SimulationInput(property=sp, works=list(c)))["new_label"]
                        for n in range(1, len(every) + 1) for c in itertools.combinations(every, n)), key=idx)
            if works:
                case.check(idx(sim["new_label"]) < idx(label) or idx(best) >= idx(label),
                           f"travaux proposés sans gain de classe ({label} → {sim['new_label']}, possible : {best})")
                case.check(idx(sim["new_label"]) <= idx("D") or idx(best) > idx("D"),
                           f"scénario recommandé n'atteint pas D ({label} → {sim['new_label']}) alors que {best} est atteignable")
            if idx(best) > idx("D"):
                case.note(f"D inatteignable (au mieux {best})")
        if works:
            case.check(0 < sim["cost_low"] <= sim["cost"] <= sim["cost_high"], f"coûts incohérents {sim['cost_low']}/{sim['cost']}/{sim['cost_high']}")
            per_m2 = sim["cost"] / prop.shab
            case.check(per_m2 < 1500, f"coût {per_m2:.0f} €/m² trop élevé")
            case.check(0 <= sim["subsidies"] <= sim["cost"], f"aides {sim['subsidies']} hors [0, coût {sim['cost']}]")
            case.check(sim["rest_to_pay"] >= 0, f"reste à charge négatif {sim['rest_to_pay']}")
            case.check(sim["new_cep"] <= sim["initial_cep"] + 1, f"consommation après travaux {sim['new_cep']} > avant {sim['initial_cep']}")
            case.check(sim["annual_savings"] >= 0, f"économies négatives {sim['annual_savings']}")
            case.check(sim["annual_bill_after"] <= sim["annual_bill_before"] + 1, "facture après travaux plus élevée")
        # Valuation
        market = None
        if prop.insee_code:
            market = await market_price(prop.insee_code, prop.building_type, prop.latitude, prop.longitude, prop.shab)
        if market:
            price = market["price_per_m2"]
            case.check(300 <= price <= 25000, f"prix DVF improbable {price} €/m²")
            sp.price_per_m2, sp.price_source, sp.insee_code = price, market["source"], prop.insee_code
            sim2 = simulate(SimulationInput(property=sp, works=works))
            v = compute(sim2, market, prop.shab, kind_of(prop.building_type), department(prop.insee_code, prop.postcode), 0)
            now = v["value_now"]["value"]
            case.check(0.4 * price * prop.shab <= now <= 1.6 * price * prop.shab, f"valeur actuelle {now:.0f} incohérente avec {price} €/m² × {prop.shab} m²")
            if v.get("value_after"):
                case.check(v["value_after"]["value"] >= now, "valeur après travaux inférieure à la valeur actuelle")
            case.note(f"DVF {price} €/m²")
        else:
            case.note("pas de prix DVF")
        # PDF report
        meta = {"address": prop.address, "ademe_dpe_number": number, "building_type": prop.building_type,
                "construction_period": prop.construction_period, "dpe_date": str(prop.date_etablissement)[:10] if prop.date_etablissement else None,
                "postcode": prop.postcode, "city": prop.city, "insee_code": prop.insee_code,
                "latitude": prop.latitude, "longitude": prop.longitude, "details": prop.details}
        content = build_report(meta, SimulationInput(property=sp, works=works))
        pdf = pdf_service.generate(content, fallback_analysis(facts_for_writer(content)))
        case.check(pdf[:4] == b"%PDF" and 3 <= pdf_pages(pdf) <= 9, f"rapport PDF : {pdf_pages(pdf)} pages")
        # Building sheet of an apartment
        if (prop.building_type or "").lower().startswith("appartement"):
            sheet = await immeuble.sheet(number, store)
            if sheet:
                case.data["sheet"] = {k: sheet.get(k) for k in ("address", "copro", "building_dpe", "apartments", "dimensions")}
                dims, est = sheet["dimensions"], sheet.get("estimate")
                case.check(sheet["apartments"]["count"] >= 1, "fiche immeuble sans l'appartement lui-même")
                if est:
                    case.check(0 < est["share"] <= 1, f"quote-part {est['share']} hors (0, 1]")
                    case.check(est["share_low"] <= est["share_high"], "quote-part basse > haute")
                    case.check(est["net_low"] <= est["share_low"], "quote-part après aides > avant aides")
                copro = sheet.get("copro")
                # Copropriété set aside because registered on another street: shown, to check
                if store is not None and not copro:
                    async with httpx.AsyncClient(timeout=15) as client:
                        found = await immeuble.ademe_rows(client, {"qs": f'numero_dpe:"{number}"', "size": "1"})
                    point = immeuble._point((found[0] if found else {}).get("_geopoint"))
                    near = immeuble.nearest_copro(await store.copros_near(*point), point) if point else None
                    if near:
                        case.note(f"copro écartée : {near.get('address')} ({near.get('lots_housing')} log.) pour {sheet.get('address')}")
                if copro and copro.get("match") == "position" and copro.get("address"):
                    case.check(same_street(copro["address"], sheet.get("address")),
                               f"copropriété d'une autre rue : {copro['address']} pour {sheet.get('address')}")
                if copro and copro.get("lots_housing") and sheet["apartments"]["count"] > copro["lots_housing"] * 1.5 + 2:
                    case.note(f"{sheet['apartments']['count']} DPE pour {copro['lots_housing']} logements (expliqué sur la fiche)")
                case.note(f"immeuble : {dims.get('dwellings')} log., copro {'oui' if sheet.get('copro') else 'non'}")
    except Exception as e:
        case.check(False, f"erreur : {type(e).__name__}: {e}")
        traceback.print_exc()
    case.done()


# --- Whole buildings ---

async def sample_buildings(store, n: int, rng: random.Random) -> List[Dict]:
    """Buildings of every size, with and without DPE."""
    out: List[Dict] = []
    filters = [{"nb_log": "lte.4"}, {"nb_log": "gte.5", "and": "(nb_log.lte.9)"}, {"nb_log": "gte.10"},
               {"dpe_label": "in.(F,G)"}, {"dpe_label": "is.null"}, {"dpe_label": "in.(A,B,C,D)"}]
    per = max(1, n // len(filters))
    for f in filters:
        offset = rng.randint(0, 2000)
        rows = await store._request("GET", "monopro_buildings", params={**f, "select": "*", "offset": str(offset), "limit": str(per)})
        if not rows:
            rows = await store._request("GET", "monopro_buildings", params={**f, "select": "*", "limit": str(per)})
        out += rows
    return out[:n]


async def audit_building(b: Dict, store) -> None:
    case = Case("immeuble", f"{b.get('address')} ({b['nb_log']} log.)")
    try:
        owners = await store.monopro_owners([b["owner_siren"]]) if b.get("owner_siren") else []
        async with httpx.AsyncClient(timeout=15) as client:
            rows = await immeuble.ademe_rows(client, {"geo_distance": f"{b['lon']},{b['lat']},30", "size": "300"})
        market = await market_price(b.get("insee") or "", "Appartement", b["lat"], b["lon"], 50)
        case.data = {"building": b, "rows": [{k: r.get(k) for k in ("numero_dpe", "type_batiment", "methode_application_dpe", "adresse_ban",
                                                                  "etiquette_dpe", "date_etablissement_dpe", "surface_habitable_logement",
                                                                  "surface_habitable_immeuble")} for r in rows]}
        d = build_dossier(b, owners[0] if owners else None, None, 0, rows, market, {"agency_name": "Audit"})
        u, nb = d["units"], b["nb_log"]
        counted = sum(u["total"].values()) + u["unknown"]
        case.check(counted == nb, f"{counted} logements comptés pour {nb}")
        case.check(u["n_known"] <= nb, f"{u['n_known']} DPE retenus pour {nb} logements")
        per_unit = d["shab"] / nb
        case.check(12 <= per_unit <= 200, f"surface moyenne {per_unit:.0f} m² par logement")
        w = d["works"]
        if w:
            case.check(0 < w["low"] <= w["high"], f"travaux {w['low']} > {w['high']}")
            case.check(w["high"] / d["shab"] <= 1100, f"travaux {w['high'] / d['shab']:.0f} €/m²")
            floor = RENOVATION_M2.get(d["worst"])
            if floor and d["worst"] in ("E", "F", "G"):
                case.check(w["low"] >= floor[0] * d["shab"] - 200, f"travaux {w['low']} sous le minimum pour un immeuble {d['worst']}")
        v = d["value"]
        if v:
            price = v["price_m2"]
            case.check(300 <= price <= 25000, f"prix DVF improbable {price}")
            case.check(v["block_low"] < v["block_high"] < v["lots_now"] <= v["after_works"],
                       f"valeurs incohérentes bloc {v['block_low']}-{v['block_high']} / lots {v['lots_now']} / après {v['after_works']}")
            ratio = v["lots_now"] / (price * d["shab"])
            case.check(0.6 <= ratio <= 1.3, f"valeur lot par lot = {ratio:.2f} × prix × surface")
            case.note(f"{d['shab']} m², {price} €/m², valeur {v['lots_now']}")
        text = " ".join(d["arguments"])
        for label in ("G", "F", "E"):
            n_label = u["total"][label]
            if n_label:
                case.check(f"{n_label} logement" in text, f"argument sans les {n_label} logements {label}")
        case.check(len([r for r in rows if not immeuble.is_building_dpe(r)]) >= u["n_known"] or u["n_known"] == 0, "DPE retenus inexistants")
        # Same number and street written differently: DPE of the building left out
        # Same number, a street word in common, yet not retained: to review
        number, postcode, street = parts(b.get("address"))
        near_miss = set()
        for r in rows:
            n2, p2, s2 = parts(r.get("adresse_ban"))
            if (n2 and number and n2.rstrip("abcdefghiqurtes") == number.rstrip("abcdefghiqurtes") and p2 == postcode
                    and street & s2 and not same_address(r.get("adresse_ban"), b.get("address"))):
                near_miss.add(r.get("adresse_ban"))
        if near_miss:
            case.note(f"adresses voisines écartées : {sorted(near_miss)[:3]}")
        case.note(f"DPE autour : {len(rows)}, retenus : {u['n_known']}, classe {d['worst']}")
        pdf = monopro_pdf.generate(d)
        case.check(pdf[:4] == b"%PDF" and pdf_pages(pdf) <= 2, f"dossier PDF sur {pdf_pages(pdf)} pages")
    except Exception as e:
        case.check(False, f"erreur : {type(e).__name__}: {e}")
        traceback.print_exc()
    case.done()


# --- Prospection map ---

async def audit_area(name: str, lat: float, lon: float) -> None:
    case = Case("carte", name)
    try:
        d = 0.012
        bbox = f"{lon - d * 1.5},{lat - d},{lon + d * 1.5},{lat + d}"
        since = (date.today() - timedelta(days=183)).isoformat()
        res = await prospection.search(bbox, ["F", "G"], None, since)
        w, s, e, n = (float(x) for x in bbox.split(","))
        for a in res["addresses"]:
            case.check(s <= a["lat"] <= n and w <= a["lon"] <= e, f"adresse hors zone : {a['address']}")
            for x in a["dpe"]:
                case.check(x["label"] in ("F", "G"), f"classe {x['label']} non demandée ({a['address']})")
                case.check((x["date"] or "") >= since, f"DPE trop ancien {x['date']} ({a['address']})")
        case.check(res["dwellings"] == sum(len(a["dpe"]) for a in res["addresses"]), "nombre de logements incohérent")
        case.note(f"{res['dwellings']} logements, {len(res['addresses'])} adresses")
    except Exception as e:
        case.check(False, f"erreur : {type(e).__name__}: {e}")
    case.done()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dwellings", type=int, default=60)
    ap.add_argument("--buildings", type=int, default=40)
    ap.add_argument("--seed", type=int, default=int(date.today().strftime("%Y%m%d")))
    args = ap.parse_args()
    rng = random.Random(args.seed)

    store = None
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        from api.store import SupabaseStore
        store = SupabaseStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"], timeout=30)

    for name, lat, lon in [("Lille centre", 50.6365, 3.0635), ("Roubaix", 50.6900, 3.1817), ("Paris 11e", 48.8590, 2.3790),
                           ("Marseille 1er", 43.2980, 5.3810), ("Lyon 3e", 45.7600, 4.8500)]:
        await audit_area(name, lat, lon)

    async with httpx.AsyncClient(timeout=20) as client:
        numbers = await sample_dpe(client, args.dwellings, rng)
    print(f"--- {len(numbers)} logements", flush=True)
    for number in numbers:
        await audit_dwelling(number, store)

    if store:
        buildings = await sample_buildings(store, args.buildings, rng)
        print(f"--- {len(buildings)} immeubles", flush=True)
        for b in buildings:
            await audit_building(b, store)

    failed = [r for r in results if r["failures"]]
    lines = [f"## Audit de cohérence : {len(results) - len(failed)} / {len(results)} cas sans anomalie", ""]
    by_kind: Dict[str, List[int]] = {}
    for r in results:
        by_kind.setdefault(r["kind"], [0, 0])[0 if not r["failures"] else 1] += 1
    lines += [f"- {k} : {ok} OK, {ko} KO" for k, (ok, ko) in by_kind.items()]
    if failed:
        lines += ["", "### Anomalies", ""] + [f"- [{r['kind']}] {r['name']} : " + " ; ".join(r["failures"]) for r in failed]
    summary = "\n".join(lines)
    print("\n" + summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary + "\n")
    with open("audit.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
