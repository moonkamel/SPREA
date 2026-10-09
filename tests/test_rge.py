import asyncio
from datetime import date

import httpx

from api import rge
from api.rge import closest_companies, nearby, query


def line(siret, name, dist, domaine, end="2027-01-01", **kw):
    return {"siret": siret, "nom_entreprise": name, "commune": "LILLE", "code_postal": "59000", "adresse": "1 RUE X",
            "domaine": domaine, "lien_date_fin": end, "_geo_distance": dist, "telephone": "03 20 00 00 00", **kw}


def test_query_quotes_exact_domains():
    q = query(["Pompe à chaleur : chauffage", 'Un "domaine"'])
    assert q == 'domaine:("Pompe à chaleur : chauffage" OR "Un \\"domaine\\"") AND particulier:true'


def test_closest_companies_dedup_and_expired():
    rows = [line("1", "A", 900, "x"), line("1", "A", 950, "y"), line("2", "B", 300, "x", end="2020-01-01"),
            line("3", "C", 1500, "x"), line("4", "D", 2500, "x"), line("5", "E", 4000, "x")]
    out = closest_companies(rows, date(2026, 10, 9))
    assert [c["name"] for c in out] == ["A", "C", "D"]
    assert out[0]["distance_km"] == 0.9 and out[0]["city"] == "Lille"


def test_nearby_widens_radius_and_adds_global_and_audit():
    rge._cache.clear()
    calls = []

    def handler(request):
        params = dict(request.url.params)
        calls.append(params)
        radius = int(params["geo_distance"].split(",")[2])
        qs = params["qs"]
        if "Pompe" in qs:
            results = [line("p1", "PAC Nord", 2000, "Pompe à chaleur : chauffage")] if radius < 25000 else \
                [line(f"p{i}", f"PAC {i}", 2000 * i, "Pompe à chaleur : chauffage") for i in range(1, 5)]
        elif "combles" in qs:
            results = [line(f"r{i}", f"Toit {i}", 1000 * i, "Isolation des combles perdus") for i in range(1, 4)]
        elif "Projet complet" in qs:
            results = [line("g1", "Renov Globale", 3000, "Projet complet de rénovation")] * 2
        else:
            results = [line("a1", "Audit Maison", 5000, "Audit énergétique Maison individuelle")]
        return httpx.Response(200, json={"total": len(results), "results": results})

    res = asyncio.run(nearby(50.63, 3.06, ["pac_air_eau", "roof", "inconnu"], "Maison",
                             transport=httpx.MockTransport(handler), today=date(2026, 10, 9)))
    assert [c["name"] for c in res["works"]["pac_air_eau"]] == ["PAC 1", "PAC 2", "PAC 3"]
    assert len(res["works"]["roof"]) == 3 and "inconnu" not in res["works"]
    assert [c["name"] for c in res["global"]] == ["Renov Globale"]
    assert res["audit"][0]["name"] == "Audit Maison"
    # PAC: 10 km first (1 company), then 25 km; lon,lat order
    pac = [c for c in calls if "Pompe" in c["qs"]]
    assert [c["geo_distance"] for c in pac] == ["3.06,50.63,10000", "3.06,50.63,25000"]
