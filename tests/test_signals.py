import asyncio
from datetime import date

import httpx

from api import prospection, signals
from tests.test_dvf import row, to_csv

TODAY = date(2026, 10, 29)


def dpe_row(number, address, ban, label, kind, when, lat=50.6300, lon=3.0600, floor=""):
    return {"numero_dpe": number, "date_etablissement_dpe": when, "etiquette_dpe": label, "type_batiment": kind,
            "surface_habitable_logement": 90, "adresse_ban": address, "identifiant_ban": ban, "code_insee_ban": "59350",
            "_geopoint": f"{lat},{lon}", "periode_construction": "1948-1974", "numero_etage_appartement": floor}


def sale(mid, when, number, street, lat=50.6300, lon=3.0600, kind="Maison"):
    r = row(mid, 250000, kind, 90, lat, lon)
    r.update(date_mutation=when, adresse_numero=number, adresse_nom_voie=street)
    return r


def setup_function():
    signals._sales.clear()
    prospection._cache.clear()


def transports(dpe_rows, sales_by_year):
    ademe = httpx.MockTransport(lambda r: httpx.Response(200, json={"results": dpe_rows, "total": len(dpe_rows)}))

    def dvf(request):
        for year, rows in sales_by_year.items():
            if f"/{year}/communes/59/59350.csv" in str(request.url):
                return httpx.Response(200, text=to_csv(rows))
        return httpx.Response(404)
    return ademe, httpx.MockTransport(dvf)


def test_address_matching():
    assert signals.split_address("12 bis Rue Nationale 59000 Lille") == ("12b", "rue nationale")
    assert signals.split_address("3 Avenue de la Paix 59000 Lille") == ("3", "av de la paix")
    assert signals.sale_key({"number": "12B", "street": "RUE NATIONALE"}) == ("12b", "rue nationale")
    assert signals.sale_key({"number": "3", "street": "AV DE LA PAIX"}) == ("3", "av de la paix")


def test_scores_explained_address_by_address():
    rows = [
        # Fresh DPE, G house never sold since the DVF window began: the best lead
        dpe_row("2659E0000001A", "10 Rue Nationale 59000 Lille", "a", "G", "maison", "2026-09-20"),
        # D house bought last year
        dpe_row("2659E0000002B", "4 Rue Colbert 59000 Lille", "b", "D", "maison", "2026-08-01", lat=50.6320),
        # Building where three flats were diagnosed this summer
        *[dpe_row(f"2659E000000{i}C", "7 Rue Solférino 59000 Lille", "c", "E", "appartement", "2026-07-1" + str(i),
                  lat=50.6340, floor=str(i)) for i in range(3)],
    ]
    sales_rows = {2026: [sale("9", "2026-03-02", "6", "RUE NATIONALE")],
                  2025: [sale("8", "2025-11-10", "4", "RUE COLBERT", lat=50.6320)],
                  2022: [sale("7", "2022-05-02", "20", "RUE DE PARIS", lat=50.7)]}
    ademe, dvf = transports(rows, sales_rows)
    res = asyncio.run(signals.area_signals("3.05,50.62,3.07,50.64", None, TODAY, dpe_transport=ademe, dvf_transport=dvf))
    by = {x["address"]: x for x in res["items"]}
    best = by["10 Rue Nationale 59000 Lille"]
    assert res["items"][0] is best and best["level"] == "fort" and best["long_held"]
    kinds = {r["kind"] for r in best["reasons"]}
    assert {"dpe", "rental", "held", "near"} <= kinds and best["score"] == 35 + 15 + 15 + 5
    assert res["dvf_since"] == 2022
    bought = by["4 Rue Colbert 59000 Lille"]
    assert bought["last_sale"]["date"] == "2025-11-10" and any(r["points"] == -20 for r in bought["reasons"])
    building = by["7 Rue Solférino 59000 Lille"]
    assert any(r["kind"] == "building" for r in building["reasons"]) and not building["long_held"]


def test_recent_sales_of_the_map():
    sales_rows = {2026: [sale("1", "2026-06-01", "6", "RUE NATIONALE"), sale("2", "2026-05-01", "8", "RUE NATIONALE", kind="Appartement")],
                  2024: [sale("3", "2024-01-15", "9", "RUE NATIONALE")],
                  2025: [sale("4", "2025-12-01", "2", "RUE LOIN", lat=51.5)]}
    _, dvf = transports([], sales_rows)
    res = asyncio.run(signals.area_sales("3.05,50.62,3.07,50.64", 12, TODAY, dvf_transport=dvf, communes=["59350"]))
    assert [s["date"] for s in res["sales"]] == ["2026-06-01", "2026-05-01"]
    assert res["sales"][0]["kind"] == "Maison" and res["sales"][1]["kind"] == "Appartement" and res["sales"][0]["number"] == "6"
