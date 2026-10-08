from fastapi.testclient import TestClient

from api import main
from api.observatoire import build


def test_observatoire_from_real_data_file():
    res = TestClient(main.app).get("/api/observatoire")
    assert res.status_code == 200 and "s-maxage" in res.headers["cache-control"]
    data = res.json()
    assert data["total_sales"] > 1_000_000
    houses = data["national"]["maisons"]["premium"]
    assert houses["D"] == 0 and houses["G"] < houses["F"] < houses["E"] < 0 < houses["C"]
    nord = next(d for d in data["departments"] if d["code"] == "59")
    assert nord["name"] == "Nord" and nord["maisons"]["premium"]["G"] < 0
    codes = [d["code"] for d in data["departments"]]
    mainland = [c for c in codes if not c.startswith("97")]
    assert mainland == sorted(mainland, key=lambda c: c.replace("2A", "20A").replace("2B", "20B"))
    assert all(c.startswith("97") for c in codes[len(mainland):])


def test_small_departments_are_not_shown():
    data = {"period": "2022T1-2025T4", "kinds": {"Maison": {
        "national": {"n": 1000, "class": {c: 0.0 for c in "ABCDEFG"}, "mix": {c: 1 / 7 for c in "ABCDEFG"}},
        "departments": {"48": {"n": 120, "class": {c: 0.0 for c in "ABCDEFG"}, "mix": {}}}}}}
    assert build(data)["departments"] == []
