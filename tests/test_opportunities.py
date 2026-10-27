import asyncio
import json
from datetime import date

import httpx

from api import dvf, opportunities, rents
from api.opportunities import analyse, investment, latest_per_dwelling, scan
from api.pdf_service import pdf_service
from api.rents import parse, pick
from tests.test_dvf import row, to_csv
from tests.test_pdf import pdf_text
from tests.test_accounts import env  # noqa: F401 (fixture)

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
    landlord = investment(v, sim, "bailleur", 92, {"rent_m2": 14, "low": 12, "high": 16}, "maison")
    assert landlord["aids"] == 10000 and landlord["total"] == 236000
    # Shown lines add up to the budget and the margin
    odd = investment({"value_now": {"value": 153049}, "value_after": {"value": 187020, "low": 1, "high": 2}},
                     {**sim, "cost": 26437, "subsidies": 10270, "cee_est": 1003}, "bailleur", 96, None)
    assert odd["total"] == odd["price"] + odd["notary"] + odd["works"] - odd["aids"] and odd["aids"] % 10 == 0
    assert odd["margin"] == odd["resale"] - odd["total"]
    assert landlord["rent_month"] == 1290 and landlord["gross_yield"] == round(100 * 14 * 92 * 12 / 236000, 1)
    # 47 rue de Bourgogne, Lille: a 328 m2 house does not let at the commune's rent per m2
    big = investment(v, sim, "bailleur", 328.1, {"rent_m2": 12.7, "low": 8.9, "high": 18.1}, "maison")
    assert big["rent_m2"] == 9.5 and big["rent_m2_commune"] == 12.7 and big["rent_month"] == 3130
    studio = investment(v, sim, "bailleur", 20, {"rent_m2": 14, "low": 12, "high": 16}, "appartement")
    assert studio["rent_m2"] == 17.5


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
        return {"these": "Opération rentable.", "points_forts": ["a"], "risques": ["b"], "strategie": "c", "arguments": "d"}
    monkeypatch.setattr(opportunities.claude, "configured", lambda: True)
    monkeypatch.setattr(opportunities.claude, "json_call", fake_call)
    thesis = asyncio.run(opportunities.write_thesis(opportunities.public(o), "bailleur"))
    assert thesis["source"] == "claude" and thesis["these"] == "Opération rentable."
    facts = json.loads(seen["content"].split("\n", 1)[1])
    assert facts["acquisition"]["budget_total_eur"] == o["total"] and facts["sortie"]["rendement_brut_pct"] == o["gross_yield"]


def dossier_pdf(o, audience, profile="bailleur"):
    from api.report_content import display_address
    pub = opportunities.public(o)
    return pdf_text(pdf_service.generate_investment({
        **pub, "profile": profile, "profile_name": opportunities.PROFILES[profile]["name"], "audience": audience,
        "notary_rate": opportunities.PROFILES[profile]["notary"],
        "thesis": {**opportunities.fallback_thesis(pub, profile, audience), "source": "rules"},
        "agency": {"agency_name": "Agence Test"}, "address": display_address(o["address"], o["postcode"], o["city"]),
        "client_name": None, "valuation": o["_v"], "sim": o["_sim"], "market": o["_market"]}))


def test_files_for_the_buyer_and_the_owner():
    """Same figures told to the buyer of a dwelling under mandate (no argument
    against the price, the agent represents the seller) and to its owner;
    the comparable sales and a fixed notice on every page."""
    o = asyncio.run(analyse(RAW, "bailleur", dvf_transport=dvf_transport(), rent_transport=rent_transport()))
    buyer = dossier_pdf(o, "acheteur")
    for part in ("Dossier acheteur", "Le projet en bref", "Ce qui fait la valeur du projet", "Ventes comparables les plus proches",
                 "Estimations indicatives, à confirmer par devis"):
        assert part in buyer, part
    assert "négociation" not in buyer.lower() and "décote" not in buyer and "Marge brute" not in buyer
    assert buyer.count("Estimations indicatives") >= 2  # every page
    owner = dossier_pdf(o, "proprietaire")
    assert "Dossier propriétaire" in owner and "Valeur estimée aujourd'hui" in owner and "Comment le présenter aux acquéreurs" in owner
    assert "Arguments de négociation" in dossier_pdf(o, "investisseur")


def test_buyer_file_from_the_simulator_with_the_mandate_price():
    from api.accounts import ReportMeta
    from api.simulation import SimulationInput, SimulationProperty
    prop = SimulationProperty(surface=90, initial_cep=480, ges_value=120, official_label="G", building_type="maison",
                              postcode="59000", construction_period="1948-1974", heating_energy="Fioul domestique",
                              insulation_quality={"walls": "insuffisante", "roof": "insuffisante"})
    req = opportunities.SimulationDossierRequest(
        meta=ReportMeta(address="10 Rue Nationale", postcode="59000", city="Lille", insee_code="59350",
                        latitude=50.6292, longitude=3.0573, dpe_date="2026-09-01"),
        simulation=SimulationInput(property=prop, works=["roof", "iti"]), purchase_price=210000)
    o = asyncio.run(opportunities.simulation_dossier_data(req, dvf_transport=dvf_transport(), rent_transport=rent_transport()))
    assert o["price"] == 210000 and o["price_is_asked"] and o["works_ids"] == ["roof", "iti"]
    assert o["total"] == o["price"] + o["notary"] + o["works"] - o["aids"]
    assert "Prix d'acquisition demandé" in dossier_pdf(o, "acheteur")


def test_scan_sorts_and_filters_for_the_agent():
    recent = {**RAW, "numero_dpe": "2659E0000002B", "identifiant_ban": "59350_x_00012", "surface_habitable_logement": 60,
              "date_etablissement_dpe": "2026-10-01"}
    old = {**RAW, "numero_dpe": "2659E0000003C", "identifiant_ban": "59350_x_00014", "surface_habitable_logement": 120,
           "date_etablissement_dpe": "2025-01-10"}
    run = lambda **kw: asyncio.run(scan("3.05,50.62,3.07,50.64", ["G"], None, "bailleur", ademe_transport=ademe_transport([RAW, recent, old]),
                                        dvf_transport=dvf_transport(), rent_transport=rent_transport(), today=date(2026, 10, 11), **kw))
    assert [o["number"] for o in run(sort="recent")["items"]] == ["2659E0000002B", "2659E0000001A", "2659E0000003C"]
    by_value = run(sort="valeur")
    assert by_value["sort"] == "valeur" and by_value["items"][0]["number"] == "2659E0000003C"
    assert "2659E0000003C" not in [o["number"] for o in run(max_age_months=6)["items"]]
    assert all(o["price"] <= 200000 for o in run(max_value=200000)["items"])
    # The count and the ranking are the agent's potential: value added by the works, aids deducted
    res = run(sort="potentiel")
    assert res["positive"] == sum(1 for o in res["items"] if o["value_created"] > 0)
    assert [o["value_created"] for o in res["items"]] == sorted((o["value_created"] for o in res["items"]), reverse=True)


def test_follow_up_shared_by_the_agency(env):
    from tests.test_accounts import ALICE, BOB, make_pro
    client, store, _, state = env
    rows = {}

    async def statuses(scope, numbers):
        return [r for (s, n), r in rows.items() if s == scope and n in numbers]

    async def set_status(row):
        rows[(row["scope"], row["dpe_number"])] = row

    async def clear(scope, number):
        rows.pop((scope, number), None)
    async def pipeline(scope, limit=500):
        return sorted((r for (s, _), r in rows.items() if s == scope), key=lambda r: r["updated_at"], reverse=True)
    store.prospect_statuses, store.set_prospect_status, store.clear_prospect_status = statuses, set_status, clear
    store.prospect_pipeline = pipeline
    assert client.get("/api/prospect-status?numbers=2659E0000001A").status_code == 402
    make_pro(store)
    make_pro(store, BOB)
    store.orgs["org1"] = {"id": "org1", "name": "Agence"}
    store.memberships[ALICE.id] = {"org_id": "org1", "role": "owner"}
    store.memberships[BOB.id] = {"org_id": "org1", "role": "member"}
    assert client.put("/api/prospect-status", json={"number": "2659E0000001A", "status": "courrier"}).status_code == 200
    assert client.put("/api/prospect-status", json={"number": "2659E0000001A", "status": "envoye"}).status_code == 422
    state["user"] = BOB
    got = client.get("/api/prospect-status?numbers=2659E0000001A,bad,2659E0000002B").json()["statuses"]
    assert got == {"2659E0000001A": {"status": "courrier", "updated_at": got["2659E0000001A"]["updated_at"], "mine": False}}
    client.put("/api/prospect-status", json={"number": "2659E0000002B", "status": "rendez_vous", "address": "3 place de la Victoire"})
    board = client.get("/api/prospect-status/all").json()["items"]
    assert [(i["number"], i["status"], i["mine"]) for i in board] == [("2659E0000002B", "rendez_vous", True), ("2659E0000001A", "courrier", False)]
    assert board[0]["address"] == "3 place de la Victoire"
    client.put("/api/prospect-status", json={"number": "2659E0000001A", "status": None})
    assert client.get("/api/prospect-status?numbers=2659E0000001A").json()["statuses"] == {}


def test_files_show_the_report_cost_range():
    """2659E0132455X: the report and the avis said 25 800 - 38 200 EUR, the
    screen and the files 25 700 - 38 200 EUR."""
    from api.figures import display_figures
    o = asyncio.run(analyse(RAW, "bailleur", dvf_transport=dvf_transport(), rent_transport=rent_transport()))
    sim = o["_sim"]
    works = [d for d in sim["detailed_costs"] if d["id"] != "parking"]
    extras = [d for d in sim["detailed_costs"] if d["id"] == "parking"]
    fig = display_figures(sim, works, extras)
    assert (o["works_low"], o["works_high"]) == (fig["cost_low"], fig["cost_high"])
