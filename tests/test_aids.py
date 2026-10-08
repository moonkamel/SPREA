import pytest

from api.aids import ResourceProfile, compute_aids, get_profile


def test_profile_depends_on_household_size_and_region():
    assert get_profile(20000, 1, "59000") == ResourceProfile.JAUNE
    assert get_profile(20000, 2, "59000") == ResourceProfile.BLEU
    assert get_profile(20000, 1, "75011") == ResourceProfile.BLEU
    assert get_profile(100000, 4, "59000") == ResourceProfile.ROSE
    # 2026 ceilings: 1 person outside Île-de-France
    assert get_profile(17363, 1, "59000") == ResourceProfile.BLEU
    assert get_profile(31186, 1, "59000") == ResourceProfile.ROSE
    # Beyond 5 people the per-person increment applies
    assert get_profile(45000, 6, "59000") == ResourceProfile.BLEU


def test_ampleur_is_capped_by_ht_ceiling():
    works = [
        {"id": "iti", "cost_ttc": 60000, "quantity": 80},
        {"id": "windows", "cost_ttc": 40000, "quantity": 10},
    ]
    res = compute_aids(works, ResourceProfile.BLEU, "E", "C")
    assert res["pathway"] == "accompagne"
    # 2 classes -> 30k HT ceiling * 80%
    assert res["mpr"] == pytest.approx(24000)
    assert res["cee"] == 0
    res3 = compute_aids(works, ResourceProfile.BLEU, "F", "C")
    assert res3["mpr"] == pytest.approx(32000)


def test_no_passoire_bonus_and_ecretement():
    works = [
        {"id": "iti", "cost_ttc": 10000, "quantity": 80},
        {"id": "roof", "cost_ttc": 5000, "quantity": 60},
    ]
    res = compute_aids(works, ResourceProfile.BLEU, "G", "D")
    assert res["mpr"] == pytest.approx(15000 / 1.055 * 0.8)
    res_rose = compute_aids(works, ResourceProfile.ROSE, "G", "D")
    assert res_rose["mpr"] == pytest.approx(15000 / 1.055 * 0.1)


def test_ampleur_reserved_to_e_f_g():
    works = [
        {"id": "iti", "cost_ttc": 10000, "quantity": 80},
        {"id": "roof", "cost_ttc": 5000, "quantity": 60},
    ]
    res = compute_aids(works, ResourceProfile.BLEU, "D", "B")
    assert res["pathway"] == "geste"
    assert res["mpr"] == 0
    assert any("E, F ou G" in b for b in res["blockers"])


def test_house_cannot_keep_gas_heating_in_ampleur():
    works = [
        {"id": "iti", "cost_ttc": 10000, "quantity": 80},
        {"id": "roof", "cost_ttc": 5000, "quantity": 60},
    ]
    res = compute_aids(works, ResourceProfile.JAUNE, "F", "D", house=True, energy="gas")
    assert res["pathway"] != "accompagne"
    with_pac = works + [{"id": "pac_air_eau", "cost_ttc": 14000, "quantity": 1}]
    assert compute_aids(with_pac, ResourceProfile.JAUNE, "F", "D", house=True, energy="gas")["pathway"] == "accompagne"
    # Apartments are not concerned
    assert compute_aids(works, ResourceProfile.JAUNE, "F", "D", house=False, energy="gas")["pathway"] == "accompagne"


def test_geste_only_funds_heat_pumps():
    works = [{"id": "pac_air_eau", "cost_ttc": 14000, "quantity": 1}]
    res = compute_aids(works, ResourceProfile.JAUNE, "F", "D", house=True, energy="gas")
    assert res["pathway"] == "geste"
    assert res["mpr"] == 4000
    # Coup de pouce CEE when it replaces a gas boiler
    assert res["cee"] == 4000
    assert res["per_work"]["pac_air_eau"]["mpr"] == 4000


def test_insulation_only_gets_cee_in_geste():
    works = [
        {"id": "iti", "cost_ttc": 8000, "quantity": 50},
        {"id": "heating", "cost_ttc": 3000, "quantity": 1},
    ]
    res = compute_aids(works, ResourceProfile.VIOLET, "E", "E")
    assert res["mpr"] == 0
    assert res["cee"] == 50 * 8
    assert res["notes"]
    res_rose = compute_aids(works, ResourceProfile.ROSE, "E", "E")
    assert res_rose["mpr"] == 0


def test_gesture_aids_never_exceed_cost_share():
    works = [{"id": "pac_air_eau", "cost_ttc": 9000, "quantity": 1}]
    res = compute_aids(works, ResourceProfile.BLEU, "E", "E", house=True, energy="oil")
    assert res["mpr"] + res["cee"] == pytest.approx(9000 * 0.9)
    assert sum(v["mpr"] + v["cee"] for v in res["per_work"].values()) == pytest.approx(9000 * 0.9)
