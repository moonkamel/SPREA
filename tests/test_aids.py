import pytest

from api.aids import ResourceProfile, compute_aids, get_profile


def test_profile_depends_on_household_size_and_region():
    assert get_profile(20000, 1, "59000") == ResourceProfile.JAUNE
    assert get_profile(20000, 2, "59000") == ResourceProfile.BLEU
    assert get_profile(20000, 1, "75011") == ResourceProfile.BLEU
    assert get_profile(100000, 4, "59000") == ResourceProfile.ROSE
    # Beyond 5 people the per-person increment applies
    assert get_profile(45000, 6, "59000") == ResourceProfile.BLEU


def test_accompagne_is_capped_by_ht_ceiling():
    works = [
        {"id": "iti", "cost_ttc": 60000, "quantity": 80},
        {"id": "windows", "cost_ttc": 40000, "quantity": 10},
    ]
    res = compute_aids(works, ResourceProfile.BLEU, "E", "C")
    assert res["pathway"] == "accompagne"
    # 2 classes -> 40k HT ceiling * 80%
    assert res["mpr"] == pytest.approx(32000)
    assert res["cee"] == 0


def test_passoire_bonus_and_ecretement():
    works = [
        {"id": "iti", "cost_ttc": 10000, "quantity": 80},
        {"id": "roof", "cost_ttc": 5000, "quantity": 60},
    ]
    res = compute_aids(works, ResourceProfile.BLEU, "G", "D")
    # 80% + 10% bonus on HT amount, but never more than 100% of TTC
    assert res["mpr"] == pytest.approx(15000 / 1.055 * 0.9)
    res_rose = compute_aids(works, ResourceProfile.ROSE, "G", "D")
    assert res_rose["mpr"] == pytest.approx(15000 / 1.055 * 0.2)


def test_accompagne_requires_two_insulation_works():
    works = [{"id": "pac_air_eau", "cost_ttc": 14000, "quantity": 1}]
    res = compute_aids(works, ResourceProfile.JAUNE, "F", "D")
    assert res["pathway"] == "geste"
    assert res["mpr"] == 4000
    assert res["notes"]


def test_gesture_forfaits_and_superieur_not_eligible():
    works = [
        {"id": "iti", "cost_ttc": 8000, "quantity": 150},
        {"id": "heating", "cost_ttc": 3000, "quantity": 1},
    ]
    res = compute_aids(works, ResourceProfile.VIOLET, "E", "E")
    # ITI capped at 100 m2, electric radiators not funded
    assert res["mpr"] == 1500
    assert res["cee"] == 800
    res_rose = compute_aids(works, ResourceProfile.ROSE, "E", "E")
    assert res_rose["mpr"] == 0


def test_gesture_aids_never_exceed_cost_share():
    works = [{"id": "ecs", "cost_ttc": 1000, "quantity": 1}]
    res = compute_aids(works, ResourceProfile.BLEU, "E", "E")
    assert res["mpr"] + res["cee"] <= 1000 * 0.9 + 1e-6
