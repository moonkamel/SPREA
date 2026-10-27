import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "seo"))
import city_prices  # noqa: E402

HEADER = ("id_mutation,date_mutation,nature_mutation,valeur_fonciere,code_commune,nom_commune,type_local,"
          "surface_reelle_bati,nombre_pieces_principales,lot1_surface_carrez,adresse_nom_voie,latitude,longitude")


def csv_for(year, rows):
    lines = [HEADER] + [f"{year}-{i},{year}-06-01,Vente,{price},{code},X,{kind},{surface},{rooms},,RUE A,50.6,3.0"
                        for i, (code, kind, price, surface, rooms) in enumerate(rows)]
    return gzip.compress("\n".join(lines).encode())


def test_extract_per_commune_with_city_totals(tmp_path, monkeypatch):
    def rows(year, base):
        out = []
        for i in range(20):
            out.append(("59350", "Appartement", base * 50 + i * 1000, 50, 2 + i % 2))
            out.append(("75115", "Appartement", int(2.5 * base) * 40, 40, 2))
            out.append(("75111", "Appartement", int(2.7 * base) * 40, 40, 2))
        out.append(("59999", "Maison", 200000, 100, 4))  # too few sales: no page
        return out
    files = {2025: csv_for(2025, rows(2025, 4000)), 2024: csv_for(2024, rows(2024, 3800)), 2023: csv_for(2023, rows(2023, 3600))}
    monkeypatch.setattr(city_prices, "fetch", lambda url: next((v for y, v in files.items() if f"/{y}/" in url), None))
    out = tmp_path / "p.json"
    city_prices.extract("59", str(out))
    data = json.loads(out.read_text())
    assert data["years"] == [2025, 2024, 2023]
    c = data["communes"]
    assert "59999" not in c and {"59350", "75115", "75111", "75056"} <= set(c)
    lille = c["59350"]["kinds"]["appartement"]
    assert lille["n"] == 40 and set(lille["years"]) == {"2023", "2024", "2025"}
    assert lille["years"]["2025"]["m2"] > lille["years"]["2023"]["m2"]
    assert set(lille["rooms"]) == {"2", "3"}
    # Paris gathers its arrondissements
    assert c["75056"]["kinds"]["appartement"]["n"] == 80


def test_slugify():
    assert city_prices.slugify("Villeneuve-d'Ascq") == "villeneuve-d-ascq"
    assert city_prices.slugify("Saint-Étienne") == "saint-etienne"
