import math

import pytest

from api import green_value as gv

DATA = {
    "period": "2022T1-2025T4",
    "kinds": {
        "Appartement": {
            "national": {"n": 100000, "class": {"A": 0.08, "B": 0.06, "C": 0.03, "D": 0.0, "E": -0.04, "F": -0.08, "G": -0.14},
                         "class_se": {c: 0.005 for c in "ABCDEFG"}, "mix": {"A": 0, "B": 0.05, "C": 0.2, "D": 0.35, "E": 0.25, "F": 0.1, "G": 0.05},
                         "quarter": {"2025T4": 0.0, "2024T4": -0.02}},
            "departments": {"59": {"n": 8000, "class": {"A": 0.1, "B": 0.08, "C": 0.05, "D": 0.0, "E": -0.06, "F": -0.12, "G": -0.2},
                                   "class_se": {c: 0.02 for c in "ABCDEFG"}, "mix": {"A": 0, "B": 0, "C": 0.1, "D": 0.4, "E": 0.3, "F": 0.15, "G": 0.05}}},
        }
    },
}


def test_department_from_insee_or_postcode():
    assert gv.department("59350", None) == "59"
    assert gv.department(None, "97400") == "974"
    assert gv.department(None, "20090") == "2A" and gv.department(None, "20200") == "2B"
    assert gv.department(None, None) is None


def test_estimate_uses_department_effects_and_class_mix():
    res = gv.estimate("E", "C", 50, 3000, "Appartement", "59", DATA)
    mix_level = sum(DATA["kinds"]["Appartement"]["departments"]["59"]["mix"][c] * math.exp(DATA["kinds"]["Appartement"]["departments"]["59"]["class"][c]) for c in "ABCDEFG")
    value_now = 50 * 3000 * math.exp(-0.06) / mix_level
    assert res["method"] == "department"
    assert res["value"] == pytest.approx(value_now * (math.exp(0.11) - 1))
    assert res["low"] < res["value"] < res["high"]
    assert "8 000 ventes" in res["basis"]


def test_national_fallback_and_flat_rate_without_data():
    assert gv.estimate("G", "D", 50, 3000, "Appartement", "75", DATA)["method"] == "national"
    flat = gv.estimate("G", "D", 50, 3000, "Maison", "75", {"kinds": {}})
    assert flat["method"] == "flat" and flat["value"] == pytest.approx(3 * 50 * 3000 * 0.045)
    assert gv.estimate("D", "D", 50, 3000, "Appartement", "59", DATA)["value"] == 0
