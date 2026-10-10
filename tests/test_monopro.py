import asyncio
import importlib.util
from pathlib import Path

import httpx

from api import main, monopro
from tests.test_accounts import ALICE, env, make_pro  # noqa: F401 (fixture)

BUILDINGS = [
    {"id": "bdnb-bg-AAAA", "dep": "59", "address": "38 Rue de Bourgogne 59800 Lille", "lat": 50.6301, "lon": 3.0702,
     "nb_log": 5, "owner_siren": "444315543", "owner_share": 1.0, "dpe_label": "F", "dpe_fg": 3, "dpe_count": 4},
    {"id": "bdnb-bg-BBBB", "dep": "59", "address": "12 Rue Patou 59800 Lille", "lat": 50.6305, "lon": 3.0710,
     "nb_log": 8, "owner_siren": None, "owner_share": None, "dpe_label": "G"},
    {"id": "bdnb-bg-CCCC", "dep": "59", "address": "2 Rue Basse 59800 Lille", "lat": 50.6402, "lon": 3.0601,
     "nb_log": 3, "owner_siren": "444315543", "owner_share": 1.0},
]
OWNERS = [{"siren": "444315543", "name": "DU BRUNIOL", "legal_form": "SCI", "postcode": "59000", "city": "LILLE"}]


def add_monopro(store):
    async def in_bbox(w, s, e, n, company_only, min_log, limit, poor_dpe=False, min_signal=None):
        out = [b for b in BUILDINGS if s <= b["lat"] <= n and w <= b["lon"] <= e and b["nb_log"] >= min_log
               and (b["owner_siren"] or not company_only)
               and (min_signal is None or (b.get("signal_score") or 0) >= min_signal)
               and (not poor_dpe or b.get("dpe_label") in ("F", "G") or (b.get("dpe_fg") or 0) > 0)]
        return sorted(out, key=lambda b: -b["nb_log"])[:limit]

    async def get(building_id):
        return next((b for b in BUILDINGS if b["id"] == building_id), None)

    async def by_owner(siren, limit):
        return [b for b in BUILDINGS if b["owner_siren"] == siren][:limit]

    async def owners(sirens):
        return [o for o in OWNERS if o["siren"] in sirens]

    store.signals, store.summaries = {}, []

    async def signal(siren):
        return store.signals.get(siren)

    async def save_summary(siren, summary, key):
        store.signals[siren].update(summary=summary, summary_key=key)
        store.summaries.append(siren)

    store.monopro_in_bbox, store.get_monopro, store.monopro_by_owner, store.monopro_owners = in_bbox, get, by_owner, owners
    store.monopro_signal, store.save_signal_summary = signal, save_summary


def test_map_is_pro_only_and_lists_buildings(env):
    client, store, _, _ = env
    add_monopro(store)
    url = "/api/monopro?bbox=3.06,50.62,3.08,50.64"
    assert client.get(url).status_code == 402
    make_pro(store)
    res = client.get(url).json()
    assert [b["id"] for b in res["buildings"]] == ["bdnb-bg-BBBB", "bdnb-bg-AAAA"]
    assert res["buildings"][1]["owner"] == {"siren": "444315543", "name": "DU BRUNIOL", "legal_form": "SCI", "city": "59000 LILLE"}
    assert res["buildings"][0]["owner"] is None
    company = client.get(url + "&owner=company").json()["buildings"]
    assert [b["id"] for b in company] == ["bdnb-bg-AAAA"]
    # Poor DPE only (F or G)
    assert [b["id"] for b in client.get(url + "&dpe=fg").json()["buildings"]] == ["bdnb-bg-BBBB", "bdnb-bg-AAAA"]
    assert client.get("/api/monopro?bbox=1,2,3,4").status_code == 400
    main.search_limiter.calls.clear()


def test_sheet_with_company_officers_and_portfolio(env, monkeypatch):
    client, store, _, _ = env
    add_monopro(store)
    make_pro(store)
    monopro._company_cache.clear()

    def handler(request):
        assert request.url.params["q"] == "444315543"
        return httpx.Response(200, json={"results": [{
            "siren": "444315543", "nom_raison_sociale": "SCI DU BRUNIOL", "etat_administratif": "A", "date_creation": "2002-11-05",
            "siege": {"adresse": "10 RUE NATIONALE 59000 LILLE"},
            "dirigeants": [{"type_dirigeant": "personne physique", "nom": "MARTIN", "prenoms": "JEAN PIERRE", "qualite": "Gérant",
                            "date_de_naissance": "1960-01"},
                           {"type_dirigeant": "personne morale", "denomination": "HOLDING NORD", "qualite": "Associé"}]}]})

    real = monopro.fetch_company
    monkeypatch.setattr(monopro, "fetch_company", lambda siren: real(siren, transport=httpx.MockTransport(handler)))
    res = client.get("/api/monopro/bdnb-bg-AAAA").json()
    assert res["owner"]["name"] == "DU BRUNIOL"
    assert res["company"]["address"] == "10 RUE NATIONALE 59000 LILLE" and res["company"]["active"] is True
    # First name and name only: no date of birth
    assert res["company"]["officers"] == [{"name": "Jean MARTIN", "role": "Gérant", "company": False},
                                          {"name": "HOLDING NORD", "role": "Associé", "company": True}]
    assert [b["id"] for b in res["portfolio"]] == ["bdnb-bg-CCCC"]
    # Owner not identified: no company lookup
    res = client.get("/api/monopro/bdnb-bg-BBBB").json()
    assert res["owner"] is None and res["company"] is None and res["portfolio"] == []
    assert client.get("/api/monopro/bdnb-bg-ZZZZ").status_code == 404
    assert client.get("/api/monopro/autre").status_code == 404
    main.search_limiter.calls.clear()


def test_company_lookup_failure_is_not_cached():
    monopro._company_cache.clear()
    down = httpx.MockTransport(lambda r: httpx.Response(503))
    assert asyncio.run(monopro.fetch_company("444315543", transport=down)) is None
    assert "444315543" not in monopro._company_cache


# --- Import of the BDNB ---

spec = importlib.util.spec_from_file_location("import_bdnb", Path(__file__).parent.parent / "scripts/monopro/import_bdnb.py")
bdnb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bdnb)

OWNERS_BY_ID = {"P1": {"siren": "444315543", "legal_form": "SCI", "name": "DU BRUNIOL"},
                "P2": {"siren": "753808765", "legal_form": "SARL", "name": "HISI"},
                "PUB": {"siren": "225900018", "legal_form": "", "name": "DEPARTEMENT DU NORD"},
                "HLM": {"siren": "413782509", "legal_form": "SA", "name": "VILOGIA SOCIETE ANONYME D'HLM"},
                "OPH": {"siren": "783713498", "legal_form": "EPIC", "name": "LILLE METROPOLE HABITAT OPH"}}


def test_owner_selection():
    assert bdnb.select_owner([], 5, OWNERS_BY_ID) == ("unknown", None, None)
    assert bdnb.select_owner([("P1", 5)], 5, OWNERS_BY_ID) == ("company", "444315543", 1.0)
    # Main owner with most units
    assert bdnb.select_owner([("P1", 1), ("P2", 9)], 10, OWNERS_BY_ID) == ("company", "753808765", 0.9)
    # Several owners sharing the building: most likely an unregistered copropriété
    assert bdnb.select_owner([("P1", 3), ("P2", 3)], 6, OWNERS_BY_ID)[0] == "skip"
    # Public body (SIREN starting with 1 or 2), social landlords: not prospects
    assert bdnb.select_owner([("PUB", 9)], 9, OWNERS_BY_ID)[0] == "skip"
    assert bdnb.select_owner([("HLM", 9)], 9, OWNERS_BY_ID)[0] == "skip"
    assert bdnb.select_owner([("OPH", 9)], 9, OWNERS_BY_ID)[0] == "skip"


def test_private_companies_only():
    private = lambda form, name: bdnb.is_private_company({"siren": "444315543", "legal_form": form, "name": name})
    assert private("SCI", "DU BRUNIOL") and private("SAS", "FONCIERE LILLOISE FAMILIALE") and private("SC", "CDEF")
    for form, name in [("SA", "NOREVIE"), ("SA", "CPH ARCADE-VYV"), ("SA", "SIA HABITAT"), ("EPIC", "OFFICE PUBLIC DE L'HABITAT DU NORD"),
                       ("ASS", "ASSOCIATION DIOCESAINE LILLE"), ("SEM", "ADOMA"), ("SCPI", "KYANEOS PIERRE"),
                       ("SA", "LA FABRIQUE DES QUARTIERS SPLA"), ("SA", "SOCIETE NATIONALE SNCF"),
                       ("SA", "SA D ECONOMIE MIXTE URBAVILEO"), ("SA", "SOCIETE PUBLIQUE LOCALE EURALILLE")]:
        assert not private(form, name), name


def test_centroid_and_dates():
    assert bdnb.centroid("MULTIPOLYGON (((0 0,4 0,4 2,0 2)))") == (2.0, 1.0)
    assert bdnb.centroid("") is None
    assert bdnb._date("2023/10/16") == "2023-10-16" and bdnb._date("") is None



L93 = ('PROJCS["RGF93 v1 / Lambert-93",GEOGCS["RGF93 v1",DATUM["Reseau_Geodesique_Francais_1993_v1",'
       'SPHEROID["GRS 1980",6378137,298.257222101]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
       'PROJECTION["Lambert_Conformal_Conic_2SP"],PARAMETER["latitude_of_origin",46.5],PARAMETER["central_meridian",3],'
       'PARAMETER["standard_parallel_1",49],PARAMETER["standard_parallel_2",44],PARAMETER["false_easting",700000],'
       'PARAMETER["false_northing",6600000],UNIT["metre",1]]')


def test_build_from_bdnb_tables(tmp_path):
    import zipfile
    import pytest
    pytest.importorskip("pyproj")
    tables = {
        "batiment_groupe_ffo_bat": "batiment_groupe_id;nb_niveau;annee_construction;nb_log\nA;4;1900;6\nB;3;1930;5\nC;2;1950;4\nD;1;1960;1\nE;3;1970;8\nF;3;1890;4\n",
        "batiment_groupe_rnc": "batiment_groupe_id;numero_immat_principal\nC;AB123\n",
        "batiment_groupe_rpls": "batiment_groupe_id\nE\n",
        "proprietaire": 'personne_id;siren;forme_juridique;denomination;code_postal;libelle_commune\nP1;"444315543";SCI;DU BRUNIOL;"59000";LILLE\nP9;"225900018";;DEPARTEMENT DU NORD;"59000";LILLE\n',
        "rel_batiment_groupe_proprietaire": "batiment_groupe_id;personne_id;nb_locaux_open\nA;P1;6\nF;P9;4\n",
        "batiment_groupe_adresse": "batiment_groupe_id;libelle_adr_principale_ban\nA;38 Rue de Bourgogne 59800 Lille\nB;12 Rue Patou 59800 Lille\n",
        "batiment_groupe_dpe_representatif_logement": "batiment_groupe_id;classe_bilan_dpe;date_etablissement_dpe\nA;F;2024-05-02\nB;;\n",
        "batiment_groupe_dpe_statistique_logement": "batiment_groupe_id;nb_classe_bilan_dpe_e;nb_classe_bilan_dpe_f;nb_classe_bilan_dpe_g\nA;1;2;1\n",
        "batiment_groupe_dvf_open_representatif": "batiment_groupe_id;valeur_fonciere;date_mutation;nb_locaux_mutee_mutation\nA;550000;2023/10/16;7\n",
        "batiment_groupe": 'geom_groupe;batiment_groupe_id;code_commune_insee\n"MULTIPOLYGON (((704000 7059000,704010 7059000,704010 7059010,704000 7059010)))";A;"59350"\n'
                           '"MULTIPOLYGON (((704100 7059100,704110 7059100,704110 7059110,704100 7059110)))";B;"59350"\n',
    }
    path = tmp_path / "bdnb.zip"
    with zipfile.ZipFile(path, "w") as z:
        for name, content in tables.items():
            z.writestr(f"csv/{name}.csv", content)
        z.writestr("csv/batiment_groupe.prj", L93)
    with zipfile.ZipFile(path) as z:
        buildings, owners, stats = bdnb.build(z, "59", "2026-10-09")
    by_id = {b["id"]: b for b in buildings}
    # B no company owner, C in the copropriété registry, D too small, E social housing, F public owner
    assert sorted(by_id) == ["A"]
    a = by_id["A"]
    assert a["owner_siren"] == "444315543" and a["owner_share"] == 1.0 and a["nb_log"] == 6
    assert a["dpe_label"] == "F" and a["dpe_fg"] == 3 and a["dpe_count"] == 4
    assert a["last_sale_date"] == "2023-10-16" and a["last_sale_price"] == 550000
    assert 50.5 < a["lat"] < 50.8 and 3.0 < a["lon"] < 3.2 and a["insee"] == "59350"
    assert list(owners) == ["444315543"] and owners["444315543"]["legal_form"] == "SCI"
    assert stats["in_copro_registry"] == 1 and stats["social_housing"] == 1 and stats["public_or_shared_owner"] == 1
    assert stats["owner_unknown"] == 1


def test_building_found_from_a_dpe_position(env):
    client, store, _, _ = env
    add_monopro(store)
    assert client.get("/api/monopro/near?lat=50.6301&lon=3.0702").status_code == 402
    make_pro(store)
    # 10 m away from 38 Rue de Bourgogne
    assert client.get("/api/monopro/near?lat=50.63019&lon=3.07025").json() == {"id": "bdnb-bg-AAAA"}
    # Nothing within 40 m: copropriété or several owners
    assert client.get("/api/monopro/near?lat=50.6500&lon=3.0900").status_code == 404
    main.search_limiter.calls.clear()


# --- Sale dossier ---

from datetime import date as _date  # noqa: E402

from api import monopro_report  # noqa: E402

TODAY = _date(2026, 10, 9)
DOSSIER_BUILDING = {"id": "bdnb-bg-AAAA", "address": "38 Rue de Bourgogne 59800 Lille", "lat": 50.6301, "lon": 3.0702, "insee": "59350",
                    "nb_log": 6, "levels": 4, "year_built": 1900, "owner_siren": "444315543", "dpe_label": "F",
                    "last_sale_date": "2016-03-02", "last_sale_price": 410000}


def flat(n, label, surface=40, date_="2025-01-01", address="38 Rue de Bourgogne 59800 Lille"):
    return {"numero_dpe": f"N{n}", "type_batiment": "appartement", "etiquette_dpe": label, "surface_habitable_logement": surface,
            "numero_etage_appartement": n, "date_etablissement_dpe": date_, "adresse_ban": address}


def test_dossier_units_bans_and_arguments():
    rows = [flat(1, "G"), flat(2, "G"), flat(3, "F", 45), {**flat(4, "F"), "qualite_isolation_murs": "insuffisante"}]
    market = {"price_per_m2": 3000, "source": "prix médian DVF"}
    d = monopro_report.build_dossier(DOSSIER_BUILDING, OWNERS[0], None, 2, rows, market, {"agency_name": "Agence du Beffroi"}, TODAY)
    # 4 dwellings with a DPE, the 2 others estimated at the class of the building (F)
    assert d["units"]["known"]["G"] == 2 and d["units"]["known"]["F"] == 2 and d["units"]["estimated"]["F"] == 2
    assert d["worst"] == "G" and d["shab"] == 6 * 40 and d["shab_estimated"]
    bans = {r["label"]: r for r in d["rental_ban"]}
    assert bans["G"]["passed"] and bans["G"]["units"] == 2 and not bans["F"]["passed"] and bans["F"]["units"] == 4
    text = " ".join(d["arguments"])
    assert "2 logements classés G ne peuvent plus être reloués depuis le 01/01/2025" in text
    assert "Loyers gelés" in text and "Audit énergétique obligatoire" in text and "détenu depuis environ 10 ans" in text
    # No envelope detail: works per m² for a G building
    assert not d["works"]["detailed"] and d["works"]["low"] == 240 * 450
    v = d["value"]
    assert v["block_low"] < v["block_high"] < v["lots_now"] < v["after_works"] and v["dpe_discount"] > 0
    assert d["collective_dpe"] == {"done": False, "text": "DPE collectif obligatoire depuis le 01/01/2026 pour un immeuble de 6 logements ; "
                                                          "aucun n'est publié à cette adresse."}


def test_dossier_without_dpe_nor_prices():
    d = monopro_report.build_dossier({**DOSSIER_BUILDING, "dpe_label": None, "last_sale_date": None}, None, None, 0, [], None, {}, TODAY)
    assert d["works"] is None and d["value"] is None and d["units"]["unknown"] == 6
    assert d["arguments"] == ["Aucune vente de l'immeuble depuis 2014 (base DVF) : détenu depuis plus de dix ans."]


def test_dossier_pdf_route(env, monkeypatch):
    client, store, _, _ = env
    add_monopro(store)
    make_pro(store)

    async def no_company(siren):
        return None

    async def rows(client_, params):
        return [flat(1, "G"), flat(2, "F")]

    async def market(*a, **k):
        return {"price_per_m2": 3000, "source": "prix médian DVF"}
    monkeypatch.setattr(monopro, "fetch_company", no_company)
    monkeypatch.setattr(monopro, "ademe_rows", rows)
    monkeypatch.setattr(monopro, "market_price", market)
    # The dossier is in the agency's name
    assert client.get("/api/monopro/bdnb-bg-AAAA/dossier").status_code == 409
    asyncio.run(store.upsert_agent_page(ALICE.id, {"agency_name": "Agence du Beffroi", "phone": "03 20 00 00 00"}))
    res = client.get("/api/monopro/bdnb-bg-AAAA/dossier")
    assert res.status_code == 200 and res.content[:4] == b"%PDF"
    assert "Dossier_immeuble_38_Rue_de_Bourgogne" in res.headers["content-disposition"]
    assert client.get("/api/monopro/bdnb-bg-ZZZZ/dossier").status_code == 404
    main.ai_limiter.calls.clear()


def test_dossier_counts_only_the_dwellings_of_the_building():
    """121 rue de Solférino: 3 dwellings, but the search around the building
    also returned the DPE of the neighbours (12 DPE): value 15 times too high."""
    building = {**DOSSIER_BUILDING, "address": "121 Rue de Solférino 59800 Lille", "nb_log": 3}
    here = "121 Rue de Solferino 59800 LILLE"  # Same address, written differently
    rows = ([flat(i, "E", address="119 Rue de Solférino 59800 Lille") for i in range(6)]
            + [flat(10 + i, "F", address="123 Rue de Solférino 59800 Lille") for i in range(3)]
            + [flat(20, "G", address=here), flat(21, "G", address=here)])
    market = {"price_per_m2": 3000, "source": "DVF"}
    d = monopro_report.build_dossier(building, None, None, 0, rows, market, {}, TODAY)
    assert d["units"]["known"]["G"] == 2 and sum(d["units"]["total"].values()) == 3
    assert d["value"]["lots_now"] < 3 * 40 * 3000 * 1.2
    # More DPE than dwellings at the address: proportions only
    d = monopro_report.build_dossier(building, None, None, 0, [flat(i, "G" if i < 4 else "F", address=here) for i in range(6)],
                                     market, {}, TODAY)
    assert d["units"]["total"]["G"] == 2 and d["units"]["total"]["F"] == 1


def test_scale_to_keeps_proportions():
    assert monopro_report.scale_to({"E": 6, "F": 3, "G": 3}, 3) == {"E": 1, "F": 1, "G": 1}
    assert monopro_report.scale_to({"F": 1, "G": 1}, 5) == {"F": 1, "G": 1}


def test_dossier_works_reach_class_c():
    """39 rue du Sec Arembault: G building of 1840, 279 m²: the envelope works
    of the DPE alone (29 000 € to 50 000 €) understated the renovation."""
    building = {**DOSSIER_BUILDING, "address": "39 Rue du Sec Arembault 59800 Lille", "nb_log": 5, "year_built": 1840}
    collective = {"numero_dpe": "IMM", "type_batiment": "immeuble", "methode_application_dpe": "dpe immeuble collectif",
                  "etiquette_dpe": "G", "date_etablissement_dpe": "2026-03-10", "surface_habitable_immeuble": 279,
                  "qualite_isolation_murs": "insuffisante", "qualite_isolation_plancher_haut_comble_perdu": "insuffisante",
                  "qualite_isolation_plancher_bas": "insuffisante", "adresse_ban": building["address"]}
    rows = [collective] + [flat(i, "G" if i < 3 else "F", 55, address=building["address"]) for i in range(4)]
    d = monopro_report.build_dossier(building, None, None, 0, rows, {"price_per_m2": 4216, "source": "DVF"}, {}, TODAY)
    w = d["works"]
    # At least the usual cost per m² of a G building (amounts rounded to 100 €)
    assert w["low"] >= 279 * 450 - 100 and w["high"] >= 279 * 750 - 100
    names = [i["name"] for i in w["items"]]
    assert names[0] == "Isolation des murs (par l'intérieur ou l'extérieur)" and names[-1] == "Autres postes pour atteindre la classe C"
    # Same rounding in the reasons as in the figures
    assert monopro_report.fmt_range(w["low"], w["high"]) in " ".join(d["arguments"])


def test_address_key_variants():
    k = monopro_report.address_key
    assert k("18bis Rue Edmond Bricout 59540 Caudry") == k("18 Bis Rue Edmond Bricout 59540 CAUDRY")
    assert k("193 Rue de la République (Saint-Pol-sur-Mer) 59430 Dunkerque") == k("193 Rue de la République 59430 Dunkerque")
    assert k("13 Rue Vincent d’Indy 59650 Villeneuve-d'Ascq") == k("13 Rue Vincent d'Indy 59650 Villeneuve-d'Ascq")
    assert k("18 Rue Edmond Bricout 59540 Caudry") != k("18bis Rue Edmond Bricout 59540 Caudry")


def test_dossier_ignores_the_collective_dpe_of_a_neighbour():
    """69 rue Boucher de Perthes (20 dwellings) took the 137 m² of the
    collective DPE of number 75: 7 m² per dwelling."""
    building = {**DOSSIER_BUILDING, "address": "69 Rue Boucher de Perthes 59800 Lille", "nb_log": 20}
    neighbour = {"numero_dpe": "IMM75", "type_batiment": "immeuble", "etiquette_dpe": "F", "date_etablissement_dpe": "2025-05-01",
                 "surface_habitable_immeuble": 137, "adresse_ban": "75 Rue Boucher de Perthes 59800 Lille"}
    rows = [neighbour] + [flat(i, "E", 45, address=building["address"]) for i in range(2)]
    d = monopro_report.build_dossier(building, None, None, 0, rows, None, {}, TODAY)
    assert d["building_dpe"] is None and d["shab"] == 20 * 45 and d["shab_estimated"]
    # A collective DPE at the address but of part of the building only
    part = {**neighbour, "adresse_ban": building["address"]}
    d = monopro_report.build_dossier(building, None, None, 0, [part, *rows[1:]], None, {}, TODAY)
    assert d["shab"] == 20 * 45


def test_dossier_singular_wording():
    rows = [flat(1, "F"), flat(2, "E"), flat(3, "G")]
    d = monopro_report.build_dossier({**DOSSIER_BUILDING, "nb_log": 3}, None, None, 0, rows, None, {}, TODAY)
    text = " ".join(d["arguments"])
    assert "1 logement classé G ne peut plus être reloué depuis" in text
    assert "1 logement classé F ne pourra plus être reloué à partir du" in text


def test_dossier_pdf_fits_two_pages_with_every_section():
    from api import monopro_pdf
    collective = {"numero_dpe": "IMM", "type_batiment": "immeuble", "date_etablissement_dpe": "2026-03-10",
                  "surface_habitable_immeuble": 300, "etiquette_dpe": "G", "qualite_isolation_murs": "insuffisante",
                  "qualite_isolation_plancher_haut_comble_perdu": "insuffisante", "qualite_isolation_plancher_bas": "insuffisante",
                  "type_installation_chauffage": "installation collective", "type_energie_principale_chauffage": "Gaz naturel",
                  "type_ventilation": "Ventilation par ouverture des fenêtres", "adresse_ban": DOSSIER_BUILDING["address"]}
    rows = [collective] + [flat(i, "GFE"[i % 3]) for i in range(4)]
    company = {"name": "SCI LES GRANDS TERRAINS DU NORD ET DE L'ARTOIS", "address": "123 BOULEVARD DE LA LIBERTE BATIMENT B 59800 LILLE"}
    agency = {"agency_name": "Agence immobilière du Vieux-Lille", "agent_name": "Jean Dupont", "phone": "03 20 00 00 00", "email": "j@agence.fr"}
    d = monopro_report.build_dossier({**DOSSIER_BUILDING, "nb_log": 12}, OWNERS[0], company, 7, rows,
                                     {"price_per_m2": 4100, "source": "prix médian des ventes DVF voisines"}, agency, TODAY)
    assert len(d["works"]["items"]) >= 5 and len(d["arguments"]) == 8
    assert monopro_pdf.pages(monopro_pdf.generate(d)) == 2


# --- Sale signals (BODACC) ---

from datetime import date as _d  # noqa: E402

from api import sale_signals  # noqa: E402

LIQUIDATION = {"id": "A1", "dateparution": "2026-09-01", "familleavis_lib": "Procédures collectives", "commercant": "DU BRUNIOL",
               "jugement": '{"famille": "Jugement d\'ouverture", "nature": "Jugement d\'ouverture de liquidation judiciaire", '
                           '"complementJugement": "désignant liquidateur Selarl X (maître Pierre Dupont)"}',
               "url_complete": "https://www.bodacc.fr/a1"}
DISSOLUTION = {"id": "B1", "dateparution": "2025-03-01", "familleavis_lib": "Modifications diverses",
               "commercant": "DU BRUNIOL (en liquidation)",
               "listepersonnes": '{"personne": {"administration": "nomination du Liquidateur : Dupont, Jean ; Gérant partant : Dupont, Jean"}}',
               "modificationsgenerales": '{"descriptif": "Cessation d\'activité et dissolution de la société"}'}
DEATH = {"id": "C1", "dateparution": "2026-01-15", "familleavis_lib": "Modifications diverses",
         "listepersonnes": '{"personne": {"administration": "Gérant partant : Martin, Paul (décédé)"}}'}
ORDINARY = {"id": "D1", "dateparution": "2026-01-01", "familleavis_lib": "Modifications diverses",
            "modificationsgenerales": '{"descriptif": "modification survenue sur l\'adresse du siège"}'}


def test_bodacc_events_and_score():
    assert [e["kind"] for e in sale_signals.classify(LIQUIDATION)] == ["liquidation_judiciaire"]
    assert [e["kind"] for e in sale_signals.classify(DISSOLUTION)] == ["dissolution", "dirigeant"]
    assert [e["kind"] for e in sale_signals.classify(DEATH)] == ["deces"]
    assert sale_signals.classify(ORDINARY) == []
    # No names kept: kind, label, date, link only
    for e in sale_signals.classify(LIQUIDATION) + sale_signals.classify(DISSOLUTION):
        assert set(e) == {"date", "kind", "label", "url"} and "Dupont" not in str(e)
    today = _d(2026, 10, 10)
    events = [e for r in (LIQUIDATION, DISSOLUTION, ORDINARY) for e in sale_signals.classify(r)]
    s = sale_signals.score(events, today)
    assert s["level"] == "fort" and s["score"] >= 60 and s["events"][0]["kind"] == "liquidation_judiciaire"
    # Old events weigh less, very old ones not at all
    assert sale_signals.score(sale_signals.classify(DEATH), today)["level"] == "moyen"
    assert sale_signals.score(sale_signals.classify({**DEATH, "dateparution": "2015-01-01"}), today) == {"score": 0, "level": None, "events": []}


def test_signal_on_the_sheet_and_explained_once(env, monkeypatch):
    from tests import claude_mock
    client, store, _, _ = env
    add_monopro(store)
    make_pro(store)

    async def no_company(siren):
        return None
    monkeypatch.setattr(monopro, "fetch_company", no_company)
    today = _d.today()
    events = [{"date": today.isoformat(), "kind": "liquidation_judiciaire", "label": "Liquidation judiciaire", "url": "https://www.bodacc.fr/a1"}]
    store.signals["444315543"] = {"siren": "444315543", "score": 60, "level": "fort", "events": events, "checked_on": today.isoformat()}
    answer = {"titre": "Société en liquidation judiciaire : l'immeuble sera vendu par le liquidateur.",
              "lecture": "La vente des actifs est conduite par le liquidateur.", "approche": "Contactez le liquidateur.",
              "probabilite": "forte"}
    mock = claude_mock.install(monkeypatch, lambda body: answer)
    sheet = client.get("/api/monopro/bdnb-bg-AAAA").json()
    assert sheet["signal"]["level"] == "fort" and sheet["signal"]["summary"] is None and sheet["signal"]["can_explain"]
    assert client.post("/api/monopro/bdnb-bg-AAAA/signal/explain").json()["probabilite"] == "forte"
    assert client.post("/api/monopro/bdnb-bg-AAAA/signal/explain").json()["titre"].startswith("Société en liquidation")
    assert len(mock.requests) == 1 and store.summaries == ["444315543"]
    sent = mock.requests[0]["body"]["messages"][0]["content"]
    assert "Liquidation judiciaire" in sent and "bodacc.fr" not in sent
    assert client.get("/api/monopro/bdnb-bg-AAAA").json()["signal"]["summary"]["probabilite"] == "forte"
    # New events: the explanation is written again
    store.signals["444315543"]["events"] = events + [{"date": today.isoformat(), "kind": "deces", "label": "Décès", "url": None}]
    assert client.get("/api/monopro/bdnb-bg-AAAA").json()["signal"]["summary"] is None
    # Building without an identified owner
    assert client.post("/api/monopro/bdnb-bg-BBBB/signal/explain").status_code == 404
    BUILDINGS[0]["signal_score"] = 60
    res = client.get("/api/monopro", params={"bbox": "3.06,50.62,3.08,50.64", "signal": "strong"}).json()
    assert [b["id"] for b in res["buildings"]] == ["bdnb-bg-AAAA"] and res["buildings"][0]["signal_level"] is None
    BUILDINGS[0].pop("signal_score")


def test_closed_company_signal_is_capped():
    today = _d(2026, 10, 10)
    events = [{"date": "2024-05-01", "kind": "radiation", "label": "Radiation du registre", "url": None},
              {"date": "2024-05-01", "kind": "radiation", "label": "Radiation du registre", "url": None},
              {"date": "2024-01-01", "kind": "dissolution", "label": "Dissolution de la société", "url": None}]
    assert sale_signals.score(events, today)["level"] == "moyen"
    # Dissolution under way, not closed yet: strong
    assert sale_signals.score(events[2:3] + [{**events[2], "date": "2026-06-01"}], today)["level"] == "fort"
