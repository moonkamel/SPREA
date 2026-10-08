import csv
import gzip
import json
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "green_value"))
import build  # noqa: E402


def dvf_row(mid, price, kind, surface, numero="2", voie="0092", insee="59648", street="RUE FLEMING", date="2024-03-01", carrez=""):
    return {"id_mutation": mid, "nature_mutation": "Vente", "valeur_fonciere": str(price), "type_local": kind,
            "surface_reelle_bati": str(surface), "lot1_surface_carrez": carrez, "date_mutation": date,
            "code_commune": insee, "ancien_code_commune": "", "adresse_code_voie": voie, "adresse_numero": numero,
            "adresse_nom_voie": street, "latitude": "50.58", "longitude": "3.04"}


def dpe(label, surface, kind="Appartement", ban="59648_0092_00002", date="2023-12-01", street="Rue Fleming", numero=2):
    return {"kind": kind, "date": date, "label": label, "surface": surface, "ban": ban, "insee": "59648",
            "numero": numero, "street": build.norm_street(street), "period": "1948-1974"}


def test_single_dwelling_sales_and_carrez():
    rows = [
        dvf_row("1", 100000, "Appartement", 52, carrez="50"),
        dvf_row("1", 100000, "Dépendance", 0),
        dvf_row("2", 300000, "Appartement", 60), dvf_row("2", 300000, "Appartement", 40, numero="4"),
    ]
    sales = build.dvf_sales(rows)
    assert len(sales) == 1 and sales[0]["surface"] == 50 and sales[0]["price_m2"] == 2000


def test_match_on_ban_identifier_surface_and_date():
    sales = build.dvf_sales([dvf_row("1", 100000, "Appartement", 50)])
    dpes = [dpe("E", 51), dpe("C", 80), dpe("B", 50, date="2024-06-01")]  # B is after the sale
    m = build.match(sales, dpes)
    assert len(m) == 1 and m[0]["label"] == "E" and m[0]["how"] == "ban"


def test_match_falls_back_to_street_name_and_skips_ambiguous():
    sales = build.dvf_sales([dvf_row("1", 100000, "Appartement", 50, voie="B123", street="RUE DU GÉNÉRAL DE GAULLE")])
    m = build.match(sales, [dpe("F", 49, ban="59648_x9z_00002", street="Rue du Général-de-Gaulle")])
    assert len(m) == 1 and m[0]["how"] == "street"
    ambiguous = build.match(sales, [dpe("F", 50, ban="59648_x9z_00002", street="Rue du Général de Gaulle"),
                                    dpe("C", 50.2, ban="59648_x9z_00002", street="Rue du Général de Gaulle")])
    assert ambiguous == []


def test_hedonic_recovers_class_effects(tmp_path):
    pytest.importorskip("numpy")
    rng = random.Random(1)
    truth = {"A": 0.10, "B": 0.07, "C": 0.03, "D": 0.0, "E": -0.04, "F": -0.09, "G": -0.15}
    rows = []
    for dep in ("59", "62"):
        for i in range(4000):
            label = rng.choice("ABCDEFG")
            cell = rng.randrange(40)
            loc = math.log(2000 + 100 * cell)
            surface = rng.uniform(25, 120)
            date = f"{rng.choice([2023, 2024, 2025])}-0{rng.randint(1, 9)}-15"
            y = loc + truth[label] - 0.1 * math.log(surface) + rng.gauss(0, 0.12)
            rows.append({"dep": dep, "insee": f"{dep}{cell:03d}", "kind": "Appartement", "date": date,
                         "price_m2": round(math.exp(y), 1), "surface": round(surface, 1), "label": label,
                         "period": "1948-1974", "lat": "", "lon": "", "how": "ban"})
    with gzip.open(tmp_path / "matched_59.csv.gz", "wt", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=build.OUT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    out = tmp_path / "green_value.json"
    build.fit(str(tmp_path), str(out))
    data = json.loads(out.read_text())
    nat = data["kinds"]["Appartement"]["national"]
    for c, v in truth.items():
        assert abs(nat["class"][c] - v) < 0.02, (c, nat["class"][c])
    dep = data["kinds"]["Appartement"]["departments"]["59"]
    assert abs(dep["class"]["G"] - truth["G"]) < 0.03
    assert abs(sum(dep["mix"].values()) - 1) < 0.01


def test_summary_compares_with_previous_file():
    new = {"period": "2022T1-2026T2", "kinds": {"Maison": {"national": {"n": 1200, "class": {c: v for c, v in zip(build.LABELS, [0.07, 0.07, 0.05, 0, -0.1, -0.2, -0.3])}}, "departments": {"59": {}}}}}
    old = {"kinds": {"Maison": {"national": {"n": 1000, "class": {c: 0.0 for c in build.LABELS}}}}}
    md = build.summary_markdown(new, old)
    assert "Maisons : 1 200 ventes" in md
    assert "| G | -25.9 % | +0.0 % |" in md


def test_monotone_pools_violations_weighted_by_sales():
    effects = {"A": 0.10, "B": 0.12, "C": 0.05, "D": 0.0, "E": -0.02, "F": -0.01, "G": 0.04}
    weights = {"A": 10, "B": 30, "C": 100, "D": 500, "E": 300, "F": 100, "G": 20}
    out = build.monotone(effects, weights)
    values = [out[c] for c in build.LABELS]
    assert all(a >= b - 1e-12 for a, b in zip(values, values[1:]))
    assert out["D"] == 0
    assert out["A"] == out["B"]  # pooled
    assert out["G"] <= out["F"] <= out["E"]
