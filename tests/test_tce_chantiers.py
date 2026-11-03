import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    "chantiers", os.path.join(os.path.dirname(__file__), "..", "scripts", "apify", "tce_chantiers.py"))
ch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ch)

ARRAS = (50.2925, 2.7810)


def building(i, label="G", shab=700, lat=ARRAS[0], lon=ARRAS[1]):
    return {"id": f"bdnb-{i}", "address": f"{i} rue X 62000 Arras", "lat": lat, "lon": lon, "nb_log": 10, "label": label,
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
    out = ch.match([firm("100000000", 15)], pos, [building(1, "F", 300), building(2, "G", 900)])
    assert out[0]["DPE"] == "G" and 9 <= out[0]["Score"] <= 10


def test_hook_states_only_facts():
    f = building(1, "F")
    text = ch.hook("Marie Durand", f, 12.4)
    assert text.startswith("Bonjour Marie Durand, un immeuble de 10 logements (environ 700 m², classé F) se trouve à 12 km")
    assert "à partir du 1er janvier 2028" in text and "315 000 € et 525 000 €" in text and text.endswith("L1")
    assert "depuis le 1er janvier 2025" in ch.hook("", building(2, "G"), 3)
