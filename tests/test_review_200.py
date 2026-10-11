"""Defects found by reading 200 real reports generated as the app does (review
of 11/10/2026): LPG priced as mains gas, a heat pump on room heaters, the
hot water of a replaced boiler forgotten, rénovation d'ampleur aids shown as
one amount above a rest to pay that does not follow from it, empty reports
for efficient dwellings, a national default price inventing a green value,
copropriété sheets of the next building."""
from api.immeuble import build_sheet, periods_agree
from api.simulation import (SimulationInput, ampleur_variant, available_works, build_envelope, energy_balance,
                            normalize_energy, prop_energy, simulate, suggest_works)
from tests.test_consistency import HOUSE, prop
from tests.test_immeuble import APT, COPRO, TODAY, flat
from tests.test_pdf import render


def test_lpg_is_its_own_energy():
    assert normalize_energy("Propane", None) == "lpg"
    assert normalize_energy(None, "Chaudière gpl/propane/butane basse température 2001-2015") == "lpg"
    assert normalize_energy("Gaz naturel", None) == "gas"
    gas = simulate(SimulationInput(property=prop(HOUSE)))
    lpg = simulate(SimulationInput(property=prop(HOUSE, heating_energy="GPL")))
    assert lpg["annual_bill_before"] > gas["annual_bill_before"] * 1.3


def test_no_heat_pump_on_room_heaters():
    heaters = prop(HOUSE, heating_generator="radiateur à gaz indépendant ou autonome avant 2006")
    assert "pac_air_eau" not in available_works(heaters)["works"]
    assert "pac_air_eau" in available_works(prop(HOUSE, heating_generator="Chaudière gaz standard 1991-2000"))["works"]


def test_heat_pump_takes_over_the_hot_water_of_the_boiler():
    p = prop(HOUSE, heating_energy="Fioul domestique", heating_generator="Chaudière fioul basse température",
             hot_water_system="Chaudière fioul basse température", hot_water_energy="Fioul domestique")
    balance = energy_balance(p, build_envelope(p, ["pac_air_eau"]), prop_energy(p), ["pac_air_eau"])
    assert balance["after"]["hot_water"][1] == "electricity"
    # An electric tank stays as it is
    tank = p.model_copy(update={"hot_water_system": "Ballon électrique à accumulation", "hot_water_energy": "Électricité"})
    balance = energy_balance(tank, build_envelope(tank, ["pac_air_eau"]), prop_energy(tank), ["pac_air_eau"])
    assert balance["after"]["hot_water"] == balance["before"]["hot_water"]


def test_ampleur_aid_range_gives_the_rest_to_pay():
    sim = simulate(SimulationInput(property=prop(HOUSE, official_label="G", initial_cep=480, ges_value=100),
                                   works=["iti", "roof", "pac_air_eau", "vmc"]))
    if sim["aid_pathway"] == "accompagne":
        assert abs(sim["cost_low"] - sim["aids_low"] - sim["rest_to_pay_low"]) < 1
        assert abs(sim["cost_high"] - sim["aids_high"] - sim["rest_to_pay_high"]) < 1


def test_report_without_works_has_no_empty_figures():
    text = render(works=[])
    assert "entre 0 € et 0 €" not in text and "jours ouvrés" not in text and "Devis d'artisans RGE" not in text
    assert "Le plan de financement" not in text


def test_no_green_value_on_a_default_price():
    text = render(works=["roof", "iti"])
    assert "Valeur verte estimée" in text and "pas de ventes connues" in text
    assert "+ " not in text.split("Valeur verte estimée")[1][:30]


def test_cheaper_ampleur_variant_is_adopted():
    p = prop(HOUSE, official_label="F", initial_cep=380)
    works = suggest_works(p, "F")["preselected"]
    sim = simulate(SimulationInput(property=p, works=works))
    variant = ampleur_variant(SimulationInput(property=p, works=works), sim)
    assert variant is None or variant["new_label"] > sim["new_label"]


def test_copro_of_another_number_or_era_is_left_out():
    other_number = {**COPRO, "address": "15 Rue Meurein 59000 Lille"}
    assert build_sheet(APT, [], other_number, "position", TODAY)["copro"] is None
    same = {**COPRO, "address": "54 Rue Meurein 59000 Lille"}
    assert build_sheet(APT, [], same, "position", TODAY)["copro"] is not None
    other_era = {**same, "period": "A_COMPTER_DE_2011"}
    assert build_sheet(APT, [], other_era, "position", TODAY)["copro"] is None
    assert periods_agree("DE_1961_A_1974", "1948-1974") and not periods_agree("AVANT_1949", "1965")


def test_one_dwelling_or_absurd_surface_gives_no_quote_part():
    one = {**COPRO, "lots_housing": 1, "address": "54 Rue Meurein 59000 Lille"}
    s = build_sheet({**APT, "surface_habitable_immeuble": 13219}, [], one, "position", TODAY)
    assert s["estimate"] is None
    many = build_sheet(APT, [flat(1, "E", 1), flat(2, "E", 2)], {**one, "lots_housing": 63}, "position", TODAY)
    dims = many["dimensions"]
    assert dims["surface"] is None or dims["surface"] / dims["dwellings"] >= 12


def test_heat_pump_priced_on_its_power():
    def pac_cost(**kw):
        sim = simulate(SimulationInput(property=prop(HOUSE, heating_generator="Chaudière gaz standard 1991-2000", **kw),
                                       works=["pac_air_eau"]))
        return next(d["cost"] for d in sim["detailed_costs"] if d["id"] == "pac_air_eau")
    small, large = pac_cost(surface=50), pac_cost(surface=200)
    assert large > small * 1.3
    # Still within the usual market range
    assert 8000 < small and large < 32000


def test_second_review_round():
    """Second batch of 200 reports: good walls not redone, no label change
    without works, sums that hold once rounded, green range said when too wide."""
    good_windows = prop(HOUSE, insulation_quality={"windows": "très bonne", "walls": "insuffisante"})
    assert "windows" not in available_works(good_windows)["works"]
    official_b = prop(HOUSE, official_label="B", initial_cep=70, ges_value=2, heating_energy="Électricité")
    sim = simulate(SimulationInput(property=official_b, works=[]))
    assert sim["new_label"] == sim["current_label"]
    from api.pdf_service import figures, green_range
    from api.report_content import build_report
    from tests.test_pdf import META, PROP
    content = build_report(META, SimulationInput(property=PROP, works=["roof", "iti", "pac_air_eau"]))
    f = figures(content)
    assert f["rest"] == f["cost"] - f["aids"] and f["rest_low"] == f["cost_low"] - f["aids_low"]
    assert f["cost_low"] == sum(round(w["cost_low"] / 100) * 100 for w in content["works"]) + \
        sum(round(x["cost"] / 10) * 10 for x in content["extra_costs"])
    assert "fourchette large" in green_range({"latent_gain": 20000, "latent_gain_low": 0, "latent_gain_high": 134000})
