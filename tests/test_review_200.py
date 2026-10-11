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


def test_analysis_and_tables_show_the_same_figures():
    """192 rue de la Chasse: the written analysis and the avis de valeur gave
    17 600 - 26 100 € and an aid of 8 900 € where the tables gave 17 700 -
    26 000 € and an aid of 7 500 - 11 100 €."""
    from api.figures import display_figures
    from api.report_content import build_report, facts_for_writer
    from tests.test_pdf import META, PROP
    p = {**PROP, "initial_cep": 410, "ges_value": 117, "heating_energy": "Fioul domestique",
         "construction_period": "avant 1948"}
    content = build_report(META, SimulationInput(property=p, works=["roof", "iti", "vmc", "pac_air_eau"]))
    fig = display_figures(content["sim"], content["works"], content["extra_costs"])
    fin = facts_for_writer(content)["financement"]
    assert fin["cout_total_fourchette_eur"] == [fig["cost_low"], fig["cost_high"]]
    assert fin["reste_a_charge_fourchette_eur"] == [fig["rest_low"], fig["rest_high"]]
    assert fig["cost_low"] - fig["aids_low"] == fig["rest_low"]


def test_studio_rue_de_dinan():
    """Live case (49 rue de Dinan, Rennes, 26.2 m² G, electric panels, old
    VMC): the walls alone give E; no other work gains a class, so the report
    does not tell to aim higher; DPE floor 0 with no floor loss is not shown
    as a ground floor; the loan does not exceed the rest to pay; a sale at a
    third of the median is not shown as comparable; the analysis gets no
    green value range when the PDF calls it too wide."""
    from api.dvf import comparables
    from api.figures import display_figures
    from api.report_content import build_report, facts_for_writer
    p = {"surface": 26.2, "initial_cep": 494, "ges_value": 19, "official_label": "G", "building_type": "appartement",
         "postcode": "35000", "construction_period": "avant 1948", "heating_energy": "Électricité",
         "heating_generator": "Panneau rayonnant électrique NFC, NF** et NF***",
         "hot_water_system": "Ballon électrique à accumulation horizontal", "hot_water_energy": "Électricité",
         "ventilation": "VMC SF Auto réglable avant 1982",
         "insulation_quality": {"walls": "insuffisante", "roof": "très bonne", "floor": "très bonne", "windows": "moyenne"},
         "dpe_losses": {"walls": 53, "air": 31, "windows": 9, "bridges": 7, "roof": 0, "floor": 0},
         "price_per_m2": 4299, "price_source": "DVF"}
    from api.simulation import SimulationProperty
    sp = SimulationProperty(**p)
    works = suggest_works(sp, "G")["preselected"]
    meta = {"address": "49 rue de Dinan", "postcode": "35000", "city": "Rennes", "dpe_date": "2026-10-05",
            "details": {"floor": "0"}}
    content = build_report(meta, SimulationInput(property=sp, works=works))
    assert content["identity"]["floor"] is None
    fig = display_figures(content["sim"], content["works"], content["extra_costs"])
    assert fig["eco_ptz"] <= fig["rest"]
    if content["sim"].get("new_ban_date") and not content["better_label_reachable"]:
        from api.pdf_service import pdf_service
        from api.ai_service import fallback_analysis
        from tests.test_pdf import pdf_text
        text = pdf_text(pdf_service.generate(content, fallback_analysis(facts_for_writer(content))))
        assert "viser une classe de plus" not in text
    sales = [{"date": "2025-12-01", "street": "Rue X", "surface": 28, "price": 37345, "price_m2": 1334},
             {"date": "2025-12-01", "street": "Rue Y", "surface": 30, "price": 120000, "price_m2": 4000}]
    assert [c["street"] for c in comparables(sales, median=4299)] == ["Rue Y"]
    content["sim"].update(latent_gain=6500, latent_gain_low=1500, latent_gain_high=15500)
    facts = facts_for_writer(content)
    found = [facts] + [v for v in facts.values() if isinstance(v, dict)]
    found = [v for v in found if "valeur_verte_fourchette_eur" in v]
    assert found and found[0]["valeur_verte_fourchette_eur"] is None
