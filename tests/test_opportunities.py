import asyncio
import json

import httpx

from api import dvf, opportunities, rents
from api.opportunities import analyse, investment, latest_per_dwelling, scan
from api.pdf_service import pdf_service
from api.rents import parse, pick
from tests.test_dvf import row, to_csv
from tests.test_pdf import pdf_text

# A G house of Lille heated with oil, whose walls and roof are poor
RAW = {
    "numero_dpe": "2659E0000001A", "adresse_ban": "10 Rue Nationale 59000 Lille", "identifiant_ban": "59350_x_00010",
    "code_insee_ban": "59350", "code_postal_ban": "59000", "nom_commune_ban": "Lille", "_geopoint": "50.6292,3.0573",
    "type_batiment": "maison", "surface_habitable_logement": 90, "periode_construction": "1948-1974",
    "etiquette_dpe": "G", "etiquette_ges": "G", "conso_5_usages_par_m2_ep": 480, "conso_5_usages_par_m2_ef": 450,
    "emission_ges_5_usages_par_m2": 120, "date_etablissement_dpe": "2026-09-01",
    "type_energie_principale_chauffage": "Fioul domestique", "type_generateur_n1_installation_n1": "Chaudière fioul classique",
    "qualite_isolation_murs": "insuffisante", "qualite_isolation_plancher_haut_comble_perdu": "insuffisante",
    "qualite_isolation_menuiseries": "insuffisante", "qualite_isolation_plancher_bas": "insuffisante",
}

RENT_CSV = "id_zone;INSEE_C;LIBGEO;loypredm2;lwr.IPm2;upr.IPm2\n1;59350;Lille;14,2;12,1;16,6\n2;75056;Paris;30,1;27;33\n"


def dvf_transport():
    sales = [row(str(i), 2600 * s, "Maison", s) for i, s in enumerate([80, 85, 90, 95, 100, 88, 92, 87, 91, 89, 93, 86] * 2)]
    text = to_csv(sales)

    def handler(request):
        if "/communes/59/59350.csv" in str(request.url):
            return httpx.Response(200, text=text)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def rent_transport():
    def handler(request):
        url = str(request.url)
        if "/api/1/datasets/" in url:
            return httpx.Response(200, json={"resources": [
                {"title": "pred-app12-mef-dhup.csv", "format": "csv", "url": "https://files/app12.csv"},
                {"title": "pred-mai-mef-dhup.csv", "format": "csv", "url": "https://files/mai.csv"},
                {"title": "pred-app-mef-dhup.csv", "format": "csv", "url": "https://files/app.csv"}]})
        if url.endswith("mai.csv") or url.endswith("app.csv"):
            return httpx.Response(200, text=RENT_CSV)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def ademe_transport(rows):
    return httpx.MockTransport(lambda request: httpx.Response(200, json={"results": rows, "total": len(rows)}))


def setup_function():
    dvf._cache.clear()
    dvf._sales_cache.clear()
    rents._tables.clear()
    rents._locks.clear()
    opportunities._cache.clear()


def test_rent_file_choice_and_parsing():
    resources = [{"title": "pred-app12-mef-dhup.csv", "format": "csv", "url": "a"},
                 {"title": "pred-app-mef-dhup.csv", "format": "csv", "url": "b"},
                 {"title": "pred-mai-mef-dhup.csv", "format": "csv", "url": "c"}]
    assert pick(resources, "appartement") == "b" and pick(resources, "maison") == "c"
    assert parse(RENT_CSV)["59350"] == (14.2, 12.1, 16.6)


def test_latest_dpe_per_dwelling():
    old = {**RAW, "numero_dpe": "OLD", "date_etablissement_dpe": "2021-01-01"}
    other = {**RAW, "numero_dpe": "OTHER", "surface_habitable_logement": 40}
    assert [r["numero_dpe"] for r in latest_per_dwelling([old, RAW, other])] == ["2659E0000001A", "OTHER"]


def test_investment_figures_by_profile():
    v = {"value_now": {"value": 200000}, "value_after": {"value": 260000, "low": 230000, "high": 290000}}
    sim = {"cost": 30000, "cost_low": 26000, "cost_high": 38000, "subsidies": 9000, "cee_est": 1000}
    dealer = investment(v, sim, "marchand", 90, None)
    assert dealer["notary"] == 6000 and dealer["aids"] == 0 and dealer["total"] == 236000 and dealer["margin"] == 24000
    landlord = investment(v, sim, "bailleur", 90, {"rent_m2": 14, "low": 12, "high": 16})
    assert landlord["aids"] == 10000 and landlord["total"] == 236000
    # Shown lines add up to the budget and the margin
    odd = investment({"value_now": {"value": 153049}, "value_after": {"value": 187020, "low": 1, "high": 2}},
                     {**sim, "cost": 26437, "subsidies": 10270, "cee_est": 1003}, "bailleur", 96, None)
    assert odd["total"] == odd["price"] + odd["notary"] + odd["works"] - odd["aids"] and odd["aids"] % 100 == 0
    assert odd["margin"] == odd["resale"] - odd["total"]
    assert landlord["rent_month"] == 1260 and landlord["gross_yield"] == round(100 * 1260 * 12 / 236000, 1)


def test_scan_ranks_and_dossier_pdf():
    rows = [RAW, {**RAW, "numero_dpe": "2659E0000002B", "identifiant_ban": "59350_x_00012", "surface_habitable_logement": 60}]
    res = asyncio.run(scan("3.05,50.62,3.07,50.64", ["G"], None, "bailleur", ademe_transport=ademe_transport(rows),
                           dvf_transport=dvf_transport(), rent_transport=rent_transport()))
    assert res["analysed"] == 2 and res["valued"] == 2
    item = res["items"][0]
    assert item["label"] == "G" and item["new_label"] < "G" and item["works_names"]
    assert item["rent_month"] and item["gross_yield"] and item["total"] > item["price"]
    assert not any(k.startswith("_") for k in item)

    o = asyncio.run(analyse(RAW, "marchand", dvf_transport=dvf_transport(), rent_transport=rent_transport()))
    thesis = opportunities.fallback_thesis(opportunities.public(o), "marchand")
    from api.report_content import display_address
    pdf = pdf_service.generate_investment({
        **opportunities.public(o), "profile": "marchand", "profile_name": "Marchand de biens", "notary_rate": 0.03,
        "thesis": {**thesis, "source": "rules"}, "agency": {"agency_name": "Agence Test", "phone": "03 20 00 00 00"},
        "address": display_address(o["address"], o["postcode"], o["city"]), "client_name": "M. Dupont",
        "valuation": o["_v"], "sim": o["_sim"], "market": o["_market"]})
    text = pdf_text(pdf)
    for part in ("Dossier d'investissement", "Marchand de biens", "Budget total", "Marge brute", "Le plan financier",
                 "Le scénario locatif", "Le programme de travaux", "Le marché local", "Agence Test", "Établi pour M. Dupont"):
        assert part in text, part
    assert "MaPrimeRénov'" in text  # said not counted for a company


def test_thesis_by_claude_and_its_facts(monkeypatch):
    o = asyncio.run(analyse(RAW, "bailleur", dvf_transport=dvf_transport(), rent_transport=rent_transport()))
    seen = {}

    async def fake_call(system, content, schema, **kw):
        seen["content"] = content
        return {"these": "Opération rentable.", "points_forts": ["a"], "risques": ["b"], "strategie": "c", "negociation": "d"}
    monkeypatch.setattr(opportunities.claude, "configured", lambda: True)
    monkeypatch.setattr(opportunities.claude, "json_call", fake_call)
    thesis = asyncio.run(opportunities.write_thesis(opportunities.public(o), "bailleur"))
    assert thesis["source"] == "claude" and thesis["these"] == "Opération rentable."
    facts = json.loads(seen["content"].split("\n", 1)[1])
    assert facts["acquisition"]["budget_total_eur"] == o["total"] and facts["sortie"]["rendement_brut_pct"] == o["gross_yield"]
