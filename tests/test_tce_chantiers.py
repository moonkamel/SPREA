import importlib.util
import os
from datetime import date

spec = importlib.util.spec_from_file_location(
    "chantiers", os.path.join(os.path.dirname(__file__), "..", "scripts", "apify", "tce_chantiers.py"))
ch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ch)

ARRAS = (50.2925, 2.7810)


TODAY = date(2026, 11, 3)


def building(i, label="G", shab=700, lat=ARRAS[0], lon=ARRAS[1], dpe="2026-03-10"):
    return {"id": f"bdnb-{i}", "address": f"{i} rue X 62000 Arras", "lat": lat, "lon": lon, "nb_log": 10, "label": label,
            "dpe_date": dpe,
            "worst": label, "shab": shab, "works_low": 315000, "works_high": 525000, "sci_name": f"SCI {i}",
            "sci_siren": "829226372", "sci_officer": "Jean DUPONT (Gérant)", "sci_office": "Arras", "link": f"L{i}"}


def firm(siren, score):
    return {"SIRET": siren + "00011", "Score_Final": str(score), "Entreprise_Nom": f"TCE {siren}",
            "Dirigeant_Nom": "Marie Durand", "Email": "m@x.fr", "Téléphone": "03"}


def test_each_building_goes_to_two_firms_at_most_and_stays_within_reach():
    firms = [firm(str(100000000 + i), 15 - i) for i in range(4)]
    pos = {f["SIRET"][:9]: ARRAS for f in firms}
    far = building(9, lat=49.0, lon=2.0)  # about 150 km away
    out = ch.match(firms, pos, [building(1), far])
    assert [r["Entreprise"] for r in out] == ["TCE 100000000", "TCE 100000001"]
    assert all(r["Immeuble_Adresse"].startswith("1 ") for r in out)


def test_g_and_large_first_then_score_on_ten():
    pos = {"100000000": ARRAS}
    out = ch.match([firm("100000000", 15)], pos, [building(1, "F", 300), building(2, "G", 900)], TODAY)
    assert out[0]["DPE"] == "G" and 9 <= out[0]["Score"] <= 10
    assert out[0]["Date_DPE"] == "2026-03-10"


def test_recent_dpe_first_old_ones_kept_at_the_end():
    assert ch.freshness({"dpe_date": "2026-01-01"}, TODAY) == 1.0
    assert 0 < ch.freshness({"dpe_date": "2024-06-01"}, TODAY) < 1
    assert ch.freshness({"dpe_date": "2022-09-01"}, TODAY) == 0.0
    assert ch.is_old({"dpe_date": "2022-09-01"}, TODAY) and ch.is_old({"dpe_date": None}, TODAY)
    pos = {"100000000": ARRAS, "100000001": ARRAS}
    # a bigger G building with a 2022 DPE loses to a recent F one
    out = ch.match([firm("100000000", 15)], pos, [building(1, "G", 900, dpe="2022-09-01"),
                                                  building(2, "F", 300, dpe="2025-12-01")], TODAY)
    assert out[0]["Immeuble_Adresse"].startswith("2 ")
    # a firm with only an old DPE nearby keeps it, after the recent ones, whatever its score
    lille = (50.6292, 3.0573)  # about 45 km from Arras
    pos = {"100000000": lille, "100000001": ARRAS}
    out = ch.match([firm("100000000", 15), firm("100000001", 3)], pos,
                   [building(3, "G", 900, *lille, dpe="2022-09-01"), building(4, "F", 100, dpe="2026-06-01")], TODAY)
    assert [r["Date_DPE"] for r in out] == ["2026-06-01", "2022-09-01"]
    assert out[0]["Score"] < out[1]["Score"]


def test_building_whose_collective_dpe_is_better_than_f_is_left_out():
    d_building = dict(building(1, "D"), worst="F")
    assert ch.match([firm("100000000", 15)], {"100000000": ARRAS}, [d_building], TODAY) == []


def test_hook_states_only_facts():
    f = building(1, "F")
    text = ch.hook("Marie Durand", f, 12.4)
    assert text.startswith("Bonjour Marie Durand, un immeuble de 10 logements (environ 700 m², classé F au DPE de mars 2026) "
                           "se trouve à 12 km")
    assert "à partir du 1er janvier 2028" in text and "315 000 € et 525 000 €" in text and text.endswith("L1")
    assert "depuis le 1er janvier 2025" in ch.hook("", building(2, "G"), 3)
