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
    async def in_bbox(w, s, e, n, company_only, min_log, limit):
        out = [b for b in BUILDINGS if s <= b["lat"] <= n and w <= b["lon"] <= e and b["nb_log"] >= min_log
               and (b["owner_siren"] or not company_only)]
        return sorted(out, key=lambda b: -b["nb_log"])[:limit]

    async def get(building_id):
        return next((b for b in BUILDINGS if b["id"] == building_id), None)

    async def by_owner(siren, limit):
        return [b for b in BUILDINGS if b["owner_siren"] == siren][:limit]

    async def owners(sirens):
        return [o for o in OWNERS if o["siren"] in sirens]

    store.monopro_in_bbox, store.get_monopro, store.monopro_by_owner, store.monopro_owners = in_bbox, get, by_owner, owners


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

OWNERS_BY_ID = {"P1": {"siren": "444315543"}, "P2": {"siren": "753808765"}, "PUB": {"siren": "225900018"}}


def test_owner_selection():
    assert bdnb.select_owner([], 5, OWNERS_BY_ID) == ("unknown", None, None)
    assert bdnb.select_owner([("P1", 5)], 5, OWNERS_BY_ID) == ("company", "444315543", 1.0)
    # Main owner with most units
    assert bdnb.select_owner([("P1", 1), ("P2", 9)], 10, OWNERS_BY_ID) == ("company", "753808765", 0.9)
    # Several owners sharing the building: most likely an unregistered copropriété
    assert bdnb.select_owner([("P1", 3), ("P2", 3)], 6, OWNERS_BY_ID)[0] == "skip"
    # Public body (SIREN starting with 1 or 2): not a prospect
    assert bdnb.select_owner([("PUB", 9)], 9, OWNERS_BY_ID)[0] == "skip"


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
    # C in the copropriété registry, D too small, E social housing, F public owner
    assert sorted(by_id) == ["A", "B"]
    a, b = by_id["A"], by_id["B"]
    assert a["owner_siren"] == "444315543" and a["owner_share"] == 1.0 and a["nb_log"] == 6
    assert a["dpe_label"] == "F" and a["dpe_fg"] == 3 and a["dpe_count"] == 4
    assert a["last_sale_date"] == "2023-10-16" and a["last_sale_price"] == 550000
    assert 50.5 < a["lat"] < 50.8 and 3.0 < a["lon"] < 3.2 and a["insee"] == "59350"
    # Owner not identified, no DPE label
    assert b["owner_siren"] is None and b["dpe_label"] is None
    assert list(owners) == ["444315543"] and owners["444315543"]["legal_form"] == "SCI"
    assert stats["in_copro_registry"] == 1 and stats["social_housing"] == 1 and stats["public_or_shared_owner"] == 1
