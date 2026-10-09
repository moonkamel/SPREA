import asyncio
import importlib.util
import io
from datetime import date
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from api import immeuble, main
from api.immeuble import build_sheet, last_year, nearest_copro, obligations, sheet

TODAY = date(2026, 10, 9)
APT = {"numero_dpe": "2659E0000001A", "type_batiment": "appartement", "etiquette_dpe": "F", "etiquette_ges": "E",
       "date_etablissement_dpe": "2025-03-01", "surface_habitable_logement": 50, "adresse_ban": "54 Rue Meurein 59000 Lille",
       "identifiant_ban": "59350_5789_00054", "_geopoint": "50.6300,3.0600", "periode_construction": "1948-1974",
       "numero_etage_appartement": 2, "qualite_isolation_murs": "insuffisante",
       "qualite_isolation_plancher_haut_toit_terrase": "moyenne", "type_installation_chauffage": "collectif",
       "type_energie_principale_chauffage": "Gaz naturel", "type_ventilation": "Ventilation par ouverture des fenêtres"}
BUILDING = {"numero_dpe": "2659E0000099Z", "type_batiment": "immeuble", "etiquette_dpe": "E", "etiquette_ges": "E",
            "date_etablissement_dpe": "2025-11-20", "surface_habitable_immeuble": 1000, "nombre_appartement": 18,
            "nombre_niveau_immeuble": 5, "qualite_isolation_murs": "insuffisante", "type_installation_chauffage": "collectif"}
COPRO = {"immat": "AB1234567", "name": "Résidence Meurein", "lat": 50.63005, "lon": 3.06003, "lots_main": 20,
         "lots_housing": 18, "lots_total": 30, "period": "DE_1961_A_1974", "syndic_type": "PROFESSIONNEL",
         "syndic_name": "Syndic du Nord", "aided": False, "in_pdp": False}


def flat(n, label, floor, date_="2024-01-01", surface=40):
    return {"numero_dpe": f"N{n}", "type_batiment": "appartement", "etiquette_dpe": label,
            "numero_etage_appartement": floor, "surface_habitable_logement": surface, "date_etablissement_dpe": date_}


def test_last_year_periods():
    assert last_year("DE_1961_A_1974") == 1974
    assert last_year("AVANT_1949") == 1948
    assert last_year("1948-1974") == 1974
    assert last_year("A_COMPTER_DE_2011") is None and last_year(None) is None


def test_obligations_by_size():
    small = obligations(20, 1974, None, TODAY)
    assert [o["id"] for o in small] == ["ppt", "dpe"]
    assert small[0]["since"] == "2025-01-01" and small[0]["status"] == "due"
    assert small[1]["since"] == "2026-01-01" and small[1]["status"] == "due"
    big = obligations(250, 1974, None, TODAY)
    assert big[0]["since"] == "2023-01-01" and big[1]["since"] == "2024-01-01"
    done = obligations(20, 1974, {"label": "E", "date_fr": "20/11/2025"}, TODAY)
    assert done[1]["status"] == "done"
    # Recent building: neither
    assert obligations(20, None, None, TODAY) == []


def test_build_sheet_with_building_dpe_and_registry():
    rows = [BUILDING, flat(1, "E", 1), flat(2, "G", 3), flat(2, "D", 3, "2025-06-01"), flat(3, "F", 4, surface=60)]
    s = build_sheet(APT, rows, COPRO, "immat", TODAY)
    assert s["building_dpe"]["label"] == "E" and s["building_dpe"]["date_fr"] == "20/11/2025"
    # Latest per apartment: flat 2 is D now; plus the apartment itself
    assert s["apartments"]["count"] == 4
    assert s["apartments"]["distribution"]["D"] == 1 and s["apartments"]["distribution"]["G"] == 0
    assert s["copro"]["syndic_name"] == "Syndic du Nord" and s["copro"]["period"] == "1961 – 1974"
    assert s["dimensions"] == {"surface": 1000, "levels": 5, "dwellings": 18, "apartment_surface": 50}
    ids = [w["id"] for w in s["works"]]
    # Works from the building DPE: façades, heating plant (class E, collective)
    assert ids == ["facade", "heating"]
    assert s["works"][0]["low"] == 1000 * 0.6 * 150 and s["works"][1]["high"] == 18 * 7000
    est = s["estimate"]
    assert est["share"] == 0.05
    assert est["share_low"] == round(s["total"][0] * 0.05, -2)
    assert 0 < est["net_low"] < est["share_low"] and est["net_low"] < est["net_high"] < est["share_high"]
    assert [o["status"] for o in s["obligations"]] == ["due", "done"]


def test_build_sheet_without_building_dpe_uses_apartment():
    s = build_sheet(APT, [flat(1, "E", 1), flat(3, "G", 5)], None, None, TODAY)
    assert s["copro"] is None and s["building_dpe"] is None
    assert s["works_source"] == "appartement"
    assert [w["id"] for w in s["works"]] == ["facade", "roof", "heating", "vmc"]
    # 3 dwellings seen, 6 levels from the highest floor
    assert s["dimensions"]["levels"] == 6 and s["dimensions"]["dwellings"] == 3


def test_volunteer_syndic_not_named():
    s = build_sheet(APT, [], {**COPRO, "syndic_type": "BENEVOLE", "syndic_name": "Jean Dupont"}, "position", TODAY)
    assert s["copro"]["syndic_name"] is None


def test_nearest_copro_within_40m():
    far = {**COPRO, "immat": "FAR", "lat": 50.6310, "lon": 3.0600}
    assert nearest_copro([far, COPRO], (50.63, 3.06))["immat"] == "AB1234567"
    assert nearest_copro([far], (50.63, 3.06)) is None


class FakeStore:
    def __init__(self, copros):
        self.copros = copros
        self.calls = []

    async def get_copro(self, immat):
        self.calls.append(("immat", immat))
        return next((c for c in self.copros if c["immat"] == immat), None)

    async def copros_near(self, lat, lon, delta=0.0006):
        self.calls.append(("near", lat, lon))
        return self.copros


def ademe_handler(rows_at_address):
    def handler(request):
        params = dict(request.url.params)
        qs = params.get("qs", "")
        if qs.startswith("numero_dpe"):
            number = qs.split('"')[1]
            found = [r for r in [APT, *rows_at_address] if r["numero_dpe"] == number]
            return httpx.Response(200, json={"results": found})
        return httpx.Response(200, json={"results": [APT, *rows_at_address]})
    return handler


def test_sheet_matches_registry_by_position():
    immeuble._cache.clear()
    store = FakeStore([COPRO])
    s = asyncio.run(sheet("2659E0000001A", store, transport=httpx.MockTransport(ademe_handler([BUILDING])), today=TODAY))
    assert s["copro"]["match"] == "position" and s["copro"]["immat"] == "AB1234567"
    assert s["apartments"]["count"] == 1
    assert store.calls[0][0] == "near"


def test_sheet_matches_by_registration_number():
    immeuble._cache.clear()
    store = FakeStore([COPRO])
    apt = {**APT, "numero_immatriculation_copropriete": "ab1234567 "}

    def handler(request):
        return httpx.Response(200, json={"results": [apt]})
    s = asyncio.run(sheet("2659E0000001A", store, transport=httpx.MockTransport(handler), today=TODAY))
    assert s["copro"]["match"] == "immat" and store.calls == [("immat", "AB1234567")]


def test_sheet_not_for_houses():
    immeuble._cache.clear()

    def handler(request):
        return httpx.Response(200, json={"results": [{**APT, "type_batiment": "maison"}]})
    assert asyncio.run(sheet("2659E0000001A", None, transport=httpx.MockTransport(handler))) is None


def test_endpoint_requires_subscription():
    client = TestClient(main.app)
    assert client.get("/api/immeuble?dpe=2659E0000001A").status_code in (401, 403)


# --- Import of the registry ---

spec = importlib.util.spec_from_file_location("import_rnic", Path(__file__).parent.parent / "scripts/copro/import_rnic.py")
rnic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rnic)

CSV = (
    "numero_d_immatriculation,nom_d_usage_de_la_copropriete,adresse_de_reference,code_postal_adresse_de_reference,commune,"
    "long,lat,nombre_total_de_lots,nombre_total_de_lots_a_usage_d_habitation_de_bureaux_ou_de_comm,"
    "nombre_de_lots_a_usage_d_habitation,nombre_de_lots_de_stationnement,periode_de_construction,"
    "date_du_reglement_de_copropriete,type_de_syndic_benevole_professionnel_non_connu,raison_sociale_du_representant_legal,"
    "siret_du_representant_legal,date_de_fin_du_dernier_mandat,copro_aidee,copro_dans_pdp,nom_qp_2024,date_de_la_derniere_maj\n"
    "ab1234567,Résidence Meurein,54 rue Meurein 59000 Lille,59000,59350,3.06,50.63,30,20,18,8,DE_1961_A_1974,"
    "1965-04-02,PROFESSIONNEL,Syndic du Nord,12345678900011,31/12/2027,non,non,,2025-09-30\n"
    "CD7654321,,1 rue X,59000,59350,,,4,4,4,0,AVANT_1949,,BENEVOLE,Jean Dupont,,,oui,non,Moulins,\n"
    ",,,,,,,,,,,,,,,,,,,,\n"
)


def test_import_maps_rows():
    rows = list(rnic.read_rows(io.StringIO(CSV), "2026-10-09"))
    assert len(rows) == 2
    a, b = rows
    assert a["immat"] == "AB1234567" and a["lat"] == 50.63 and a["lon"] == 3.06
    assert a["lots_main"] == 20 and a["mandate_end"] == "2027-12-31" and a["rules_date"] == "1965-04-02"
    assert a["syndic_name"] == "Syndic du Nord" and a["aided"] is False and a["imported_on"] == "2026-10-09"
    assert b["syndic_name"] is None and b["syndic_siret"] is None and b["lat"] is None
    assert b["aided"] is True and b["qpv"] == "Moulins" and b["name"] is None


def test_import_semicolon_and_batches():
    rows = list(rnic.read_rows(io.StringIO(CSV.replace(",", ";")), "2026-10-09"))
    assert len(rows) == 2
    assert [len(b) for b in rnic.batches(rows * 3, size=5)] == [2]  # Same keys deduplicated


def test_latest_csv_skips_dictionary():
    api = {"resources": [
        {"format": "csv", "title": "Fichier T2 2025", "created_at": "2025-10-01", "url": "t2"},
        {"format": "csv", "title": "Fichier T3 2025", "created_at": "2026-01-05", "url": "t3"},
        {"format": "pdf", "title": "Notice", "created_at": "2026-02-01", "url": "pdf"},
        {"format": "csv", "title": "Dictionnaire des données", "created_at": "2026-03-01", "url": "dict"}]}
    assert rnic.latest_csv(api) == "t3"


def test_sheet_retries_without_field_selection():
    immeuble._cache.clear()

    def handler(request):
        if "select" in request.url.params:
            return httpx.Response(400, json={"error": "unknown field"})
        return httpx.Response(200, json={"results": [APT]})
    s = asyncio.run(sheet("2659E0000001A", None, transport=httpx.MockTransport(handler), today=TODAY))
    assert s["apartments"]["count"] == 1


def test_no_collective_works_for_a_performing_building():
    # The case seen in production: building rated C, built 2006-2012, walls "insuffisante"
    recent = {**BUILDING, "etiquette_dpe": "C"}
    apt = {**APT, "periode_construction": "2006-2012", "etiquette_dpe": "C"}
    s = build_sheet(apt, [recent], None, None, TODAY)
    assert s["works"] == [] and s["estimate"] is None
    assert s["works_note"].startswith("Immeuble classé C")


def test_class_d_only_insufficient_and_recent_walls_kept():
    d = {**APT, "etiquette_dpe": "D", "qualite_isolation_murs": "insuffisante",
         "qualite_isolation_plancher_haut_toit_terrase": "moyenne"}
    assert [w["id"] for w in immeuble.collective_works(d, 1000, 5, 18, 1974)] == ["facade", "vmc"]
    # Built after 2000 and rated D: walls are not redone
    assert [w["id"] for w in immeuble.collective_works(d, 1000, 5, 18, 2010)] == ["vmc"]
    # Rated F: walls redone whatever the period
    f = {**d, "etiquette_dpe": "F"}
    assert "facade" in [w["id"] for w in immeuble.collective_works(f, 1000, 5, 18, 2010)]


def test_unknown_registry_period_falls_back_to_dpe():
    for unknown in ("NON_CONNUE", "non renseigné"):
        s = build_sheet(APT, [], {**COPRO, "period": unknown}, "immat", TODAY)
        assert s["period"] == "1948-1974" and s["copro"]["period"] is None


def test_apartment_dpe_drawn_from_the_building_dpe_is_an_apartment():
    """Audit: the sheet of such an apartment did not count the apartment itself."""
    from api.immeuble import is_building_dpe
    assert not is_building_dpe({"type_batiment": "appartement",
                                "methode_application_dpe": "dpe appartement généré à partir des données DPE immeuble"})
    assert is_building_dpe({"type_batiment": "immeuble", "methode_application_dpe": "dpe immeuble collectif"})
    assert is_building_dpe({"type_batiment": "", "methode_application_dpe": "dpe immeuble collectif"})
