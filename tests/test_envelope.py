import pytest

from api.envelope import Envelope, construction_year, period_index


def test_period_parsing():
    assert construction_year(None, "avant 1948") == 1947
    assert construction_year(None, "1948-1974") == 1948
    assert construction_year(1990, "1948-1974") == 1990
    assert period_index(None, "2013-2021") == 5
    assert period_index(None, None) == 1  # unknown: 1948-1974


def test_uninsulated_house_loss_breakdown_matches_ademe_orders_of_magnitude():
    shares = Envelope(90, "Maison", 1960).shares()
    assert shares["roof"] == max(shares.values())
    assert 0.20 <= shares["walls"] <= 0.35
    assert 0.05 <= shares["windows"] <= 0.15
    assert sum(shares.values()) == pytest.approx(1)


def test_apartment_has_little_roof_unless_on_top_floor():
    apt = Envelope(55, "Appartement", 1960)
    top = Envelope(55, "Appartement", 1960, exposed_elements={"roof"})
    assert apt.areas["roof"] == pytest.approx(55 * 0.25)
    assert top.areas["roof"] == pytest.approx(55)
    assert top.heating_reduction(["roof"]) > 2 * apt.heating_reduction(["roof"])


def test_quality_overrides_period():
    env = Envelope(90, "Maison", 1930, qualities={"walls": "très bonne", "windows": "insuffisante"})
    assert env.u["walls"] == 0.25
    assert env.u["windows"] == 4.5


def test_reductions_combine_without_exceeding_total():
    env = Envelope(90, "Maison", 1960)
    all_works = ["iti", "roof", "floor_ceiling", "windows", "vmc"]
    combined = env.heating_reduction(all_works)
    assert 0 < combined < 1
    assert combined == pytest.approx(sum(env.heating_reduction([w]) for w in all_works))


def test_incomplete_dpe_losses_are_ignored():
    env = Envelope(90, "Maison", 1960, dpe_losses={"walls": 100, "roof": None})
    assert env.dpe_losses is None
