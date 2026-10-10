"""Green value on real dwellings of a few towns: real DPE (ADEME), local DVF
price, recommended works, then the green value of the report and the
valuation, with consistency checks. Read-only.

  python scripts/audit/green_check.py --insee 62041 62263 --per-town 4
"""
import argparse
import asyncio
import os
import sys
from typing import Dict, List

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api.ademe_client import AdemeConnector  # noqa: E402
from api.dvf import market_price  # noqa: E402
from api.green_value import department, kind_of  # noqa: E402
from api.main import enrich_property, simulation_property  # noqa: E402
from api.simulation import SimulationInput, ampleur_variant, simulate  # noqa: E402
from api.valuation import compute  # noqa: E402

ADEME = "https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/lines"
# Arras and around, then a few towns of the Pas-de-Calais and the Nord outside Lille
TOWNS = {"62041": "Arras", "62263": "Dainville", "62004": "Achicourt", "62753": "Saint-Laurent-Blangy",
         "62099": "Beaurains", "62764": "Saint-Nicolas", "62037": "Anzin-Saint-Aubin", "62080": "Bapaume",
         "62767": "Saint-Pol-sur-Ternoise", "62498": "Lens", "62119": "Béthune", "59178": "Douai"}


async def sample(client: httpx.AsyncClient, insee: str, per_town: int) -> List[str]:
    out: List[str] = []
    for kind in ("maison", "appartement"):
        res = await client.get(ADEME, params={
            "qs": f"type_batiment:{kind} AND etiquette_dpe:(E OR F OR G) AND code_insee_ban:{insee} "
                  "AND date_etablissement_dpe:[2024-01-01 TO *]",
            "size": per_town, "select": "numero_dpe", "sort": "-date_etablissement_dpe"})
        if res.status_code == 200:
            out += [r["numero_dpe"] for r in res.json().get("results", [])][: per_town // 2 or 1]
    return out


def eur(v: float) -> str:
    return f"{v:,.0f} €".replace(",", " ")


async def check(number: str, town: str) -> Dict:
    prop = await AdemeConnector().search_by_dpe_number(number)
    if not prop or not prop.insee_code:
        return {"number": number, "error": "DPE introuvable"}
    enriched = enrich_property(prop)
    sp = simulation_property(prop)
    market = await market_price(prop.insee_code, prop.building_type, prop.latitude, prop.longitude, prop.shab)
    if not market:
        return {"number": number, "error": "pas de prix DVF"}
    sp.price_per_m2, sp.price_source, sp.insee_code = market["price_per_m2"], market["source"], prop.insee_code
    works = enriched.get("preselected_works") or []
    data = SimulationInput(property=sp, works=works, suggested_works=enriched.get("suggested_works") or [])
    sim = simulate(data)
    kind, dep = kind_of(prop.building_type), department(prop.insee_code, prop.postcode)
    val = compute(sim, market, prop.shab, kind, dep, 0)
    base = sp.price_per_m2 * prop.shab
    green = sim["latent_gain"]
    problems = []
    if works and sim["new_label"] != sim["current_label"]:
        if not (0 < green <= 0.35 * base):
            problems.append(f"valeur verte {eur(green)} hors de 0 à 35 % de {eur(base)}")
        if not (sim["latent_gain_low"] <= green <= sim["latent_gain_high"]):
            problems.append("valeur verte hors de sa fourchette")
        if val["value_after"]:
            gap = val["value_after"]["value"] - val["value_now"]["value"]
            # Report and valuation use the same class effects and works share (rounding apart)
            if abs(gap - green) > max(2000, 0.1 * green):
                problems.append(f"écart avis de valeur {eur(gap)} ≠ valeur verte du rapport {eur(green)}")
    now = val["value_now"]["value"]
    if not (0.5 * base <= now <= 1.3 * base):
        problems.append(f"valeur actuelle {eur(now)} loin de {eur(base)}")
    variant = ampleur_variant(data, sim)
    return {
        "number": number, "town": town, "kind": kind, "surface": prop.shab, "label": sim["current_label"],
        "target": sim["new_label"], "works": works, "price": market["price_per_m2"], "sales": market.get("sales"),
        "source": market["source"], "value_now": now, "green": green, "low": sim["latent_gain_low"],
        "high": sim["latent_gain_high"], "pct": 100 * green / now if now else 0, "premium": sim["green_value_premium_pct"],
        "rest": sim["rest_to_pay"], "aid": sim["subsidies"] + sim["cee_est"], "pathway": sim["aid_pathway"],
        "variant": variant, "problems": problems,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insee", nargs="*", default=list(TOWNS))
    ap.add_argument("--per-town", type=int, default=4)
    args = ap.parse_args()
    async with httpx.AsyncClient(timeout=30) as client:
        numbers = [(n, TOWNS.get(i, i)) for i in args.insee for n in await sample(client, i, args.per_town)]
    rows = []
    for number, town in numbers:
        try:
            rows.append(await check(number, town))
        except Exception as e:  # noqa: BLE001 - one bad DPE must not stop the run
            rows.append({"number": number, "error": f"{type(e).__name__}: {e}"})
    ok = [r for r in rows if "error" not in r]
    print("| Commune | Bien | Classe | Prix DVF | Valeur actuelle | Valeur verte (fourchette) | % | Écart mesuré | Aides / parcours | Variante | Problèmes |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in ok:
        v = r["variant"]
        variant = (f"+ {v['work_name'].lower()} : {eur(v['subsidies'])} d'aide, reste {eur(v['rest_to_pay'])}" if v else "–")
        print(f"| {r['town']} | {r['kind']} {r['surface']:g} m² | {r['label']} → {r['target']} | {r['price']:.0f} €/m² ({r['sales']} ventes) "
              f"| {eur(r['value_now'])} | {eur(r['green'])} ({eur(r['low'])} – {eur(r['high'])}) | {r['pct']:.1f} % | {r['premium']} % "
              f"| {eur(r['aid'])} {r['pathway']} | {variant} | {'; '.join(r['problems']) or 'OK'} |")
    for r in rows:
        if "error" in r:
            print(f"ERREUR {r['number']} : {r['error']}")
    pcts = sorted(r["pct"] for r in ok if r["green"])
    if pcts:
        print(f"\n{len(ok)} biens ; valeur verte de {pcts[0]:.1f} % à {pcts[-1]:.1f} % de la valeur actuelle, "
              f"médiane {pcts[len(pcts) // 2]:.1f} % ; {sum(1 for r in ok if r['problems'])} avec un problème ; "
              f"{sum(1 for r in ok if r['variant'])} avec une variante rénovation d'ampleur.")


if __name__ == "__main__":
    asyncio.run(main())
