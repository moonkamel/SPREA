import asyncio
import csv
import io
from datetime import date

import httpx

from api import dvf
from api.dvf import market_price, parse_sales

HEADER = ("id_mutation,date_mutation,numero_disposition,nature_mutation,valeur_fonciere,adresse_numero,adresse_suffixe,"
          "adresse_nom_voie,adresse_code_voie,code_postal,code_commune,nom_commune,code_departement,ancien_code_commune,"
          "ancien_nom_commune,id_parcelle,ancien_id_parcelle,numero_volume,lot1_numero,lot1_surface_carrez,lot2_numero,"
          "lot2_surface_carrez,lot3_numero,lot3_surface_carrez,lot4_numero,lot4_surface_carrez,lot5_numero,"
          "lot5_surface_carrez,nombre_lots,code_type_local,type_local,surface_reelle_bati,nombre_pieces_principales,"
          "code_nature_culture,nature_culture,code_nature_culture_speciale,nature_culture_speciale,surface_terrain,"
          "longitude,latitude").split(",")

LILLE = (50.6292, 3.0573)


def row(mid, price, kind, surface, lat=LILLE[0], lon=LILLE[1], nature="Vente"):
    r = {k: "" for k in HEADER}
    r.update(id_mutation=mid, nature_mutation=nature, valeur_fonciere=str(price), type_local=kind,
             surface_reelle_bati=str(surface), nom_commune="Lille", code_commune="59350", latitude=str(lat), longitude=str(lon))
    return r


def to_csv(rows):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=HEADER)
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def test_parse_keeps_single_dwelling_sales_only():
    text = to_csv([
        row("1", 150000, "Appartement", 50),
        row("2", 300000, "Appartement", 60), row("2", 300000, "Appartement", 40),   # 2 flats in one sale
        row("3", 200000, "Appartement", 40), row("3", 200000, "Dépendance", 0),     # flat + cellar: kept
        row("4", 90000, "Appartement", 5),                                          # too small
        row("5", 120000, "Maison", 80),                                             # other kind
        row("6", 100000, "Appartement", 40, nature="Echange"),
        row("7", 500000, "Appartement", 50), row("7", 500000, "Local industriel. commercial ou assimilé", 100),
    ])
    sales = parse_sales(text, "Appartement", 2025)
    assert sorted(round(s["price_m2"]) for s in sales) == [3000, 5000]


def transport_for(files):
    def handler(request):
        for year, text in files.items():
            if f"/{year}/communes/59/59350.csv" in str(request.url):
                return httpx.Response(200, text=text)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_median_near_the_dwelling_first():
    dvf._cache.clear()
    near = [row(f"n{i}", 3000 * 50 + i * 500, "Appartement", 50) for i in range(20)]
    far = [row(f"f{i}", 9000 * 50, "Appartement", 50, lat=50.70, lon=3.20) for i in range(40)]
    files = {2025: to_csv(near[:10] + far[:20]), 2024: to_csv(near[10:] + far[20:])}
    res = asyncio.run(market_price("59350", "Appartement", *LILLE, transport=transport_for(files), today=date(2026, 10, 8)))
    assert res["sales"] == 20 and res["scope"] == "à moins de 500 m"
    assert 3000 <= res["price_per_m2"] <= 3200
    assert res["q25"] <= res["price_per_m2"] <= res["q75"]
    assert res["period"] == "2024-2025"
    assert res["source"].startswith("prix médian DVF de 20 ventes d’appartements à moins de 500 m (2024-2025")


def test_commune_median_without_coordinates_and_none_when_too_few():
    dvf._cache.clear()
    files = {2025: to_csv([row(f"m{i}", 2500 * 100, "Maison", 100) for i in range(12)])}
    res = asyncio.run(market_price("59350", "Maison", transport=transport_for(files), today=date(2026, 10, 8)))
    assert res["price_per_m2"] == 2500 and res["scope"] == "à Lille"
    dvf._cache.clear()
    few = {2025: to_csv([row("x", 250000, "Maison", 100)])}
    assert asyncio.run(market_price("59350", "Maison", transport=transport_for(few), today=date(2026, 10, 8))) is None
    assert asyncio.run(market_price("bad", "Maison")) is None


def test_surface_band_and_time_adjustment(monkeypatch):
    dvf._cache.clear()
    small = [row(f"s{i}", 5000 * 20, "Appartement", 20) for i in range(25)]   # studios: 5 000 €/m²
    large = [row(f"l{i}", 3000 * 80, "Appartement", 80) for i in range(25)]   # large flats: 3 000 €/m²
    files = {2025: to_csv(small + large)}
    res = asyncio.run(market_price("59350", "Appartement", *LILLE, surface=75, transport=transport_for(files), today=date(2026, 10, 8)))
    assert res["price_per_m2"] == 3000 and res["surface_matched"]
    # No surface given: the report must not claim comparable surfaces
    dvf._cache.clear()
    res = asyncio.run(market_price("59350", "Appartement", *LILLE, transport=transport_for(files), today=date(2026, 10, 8)))
    assert not res["surface_matched"] and "surface comparable" not in res["source"]
    # Sales of the first quarter 2025 were 10 % cheaper than the latest quarter
    dvf._cache.clear()
    monkeypatch.setattr(dvf, "quarter_index", lambda kind, dep: {"2025T1": -0.0953})
    dated = [{**r, "date_mutation": "2025-02-01"} for r in large]
    res = asyncio.run(market_price("59350", "Appartement", *LILLE, surface=75, transport=transport_for({2025: to_csv(dated)}), today=date(2026, 10, 8)))
    assert res["price_per_m2"] == 3300 and res["adjusted"]
    assert "actualisées" in res["source"] and res["comparables"][0]["adjusted_m2"] == 3300


def test_widens_to_neighbouring_communes():
    dvf._cache.clear()
    village = (50.60, 3.10)
    # 3 sales in the village, 20 in a commune 4 km away, 20 in one 30 km away
    own = [{**row(f"v{i}", 2000 * 60, "Appartement", 60, *village), "nom_commune": "Village"} for i in range(3)]
    near = [{**row(f"n{i}", 2500 * 60, "Appartement", 60, 50.636, 3.10), "nom_commune": "Voisine"} for i in range(20)]
    far = [row(f"f{i}", 6000 * 60, "Appartement", 60, 50.87, 3.10) for i in range(20)]
    files = {"59001": to_csv(own), "59002": to_csv(near), "59003": to_csv(far)}
    communes = [{"code": "59001", "nom": "Village", "centre": {"coordinates": [3.10, 50.60]}},
                {"code": "59002", "nom": "Voisine", "centre": {"coordinates": [3.10, 50.636]}},
                {"code": "59003", "nom": "Loin", "centre": {"coordinates": [3.10, 50.87]}}]

    def handler(request):
        url = str(request.url)
        if "geo.api.gouv.fr/departements/59/communes" in url:
            return httpx.Response(200, json=communes)
        for code, text in files.items():
            if f"/2025/communes/59/{code}.csv" in url:
                return httpx.Response(200, text=text)
        return httpx.Response(404)

    t = httpx.MockTransport(handler)
    res = asyncio.run(market_price("59001", "Appartement", *village, transport=t, today=date(2026, 10, 8)))
    assert res["wide"] and res["scope"] == "à moins de 5 km, communes voisines incluses"
    assert res["sales"] == 23 and res["price_per_m2"] == 2500
    assert {c["commune"] for c in res["comparables"]} == {"Village", "Voisine"}
    # Without coordinates: around the commune's centre
    dvf._cache.clear()
    res = asyncio.run(market_price("59001", "Appartement", transport=t, today=date(2026, 10, 8)))
    assert res["sales"] == 23


def test_follows_redirects_and_skips_forbidden_years():
    dvf._cache.clear()
    sales = to_csv([row(f"r{i}", 2500 * 100, "Maison", 100) for i in range(12)])

    def handler(request):
        url = str(request.url)
        if "/2026/" in url:
            return httpx.Response(403)
        if url.startswith("https://files.data.gouv.fr/") and "/2025/" in url:
            return httpx.Response(302, headers={"location": url.replace("files.data.gouv.fr", "object.files.data.gouv.fr")})
        if url.startswith("https://object.files.data.gouv.fr/") and "/2025/" in url:
            return httpx.Response(200, text=sales)
        return httpx.Response(404)

    res = asyncio.run(market_price("59350", "Maison", transport=httpx.MockTransport(handler), today=date(2026, 10, 8)))
    assert res["price_per_m2"] == 2500
